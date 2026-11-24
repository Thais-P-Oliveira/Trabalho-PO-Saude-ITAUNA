# Copia de model.py para integrar a APS completa sem alterar o arquivo original.
# Ajustes locais: status do solver, exportacao precisa dos fluxos e retorno ao integrador.
import argparse
import math
import os
import sys
import builtins
from functools import partial
print = partial(builtins.print, flush=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
import pandas as pd
import pulp as pl

# ----------------------------------------------------------------------------
# Parametros de custo (R$/mes)
# ----------------------------------------------------------------------------
# Salarios-base mensais. ACS = piso nacional de 2 salarios minimos (EC 120/2022);
# salario minimo 2026 = R$ 1.621 (Decreto 12.797/2025) -> R$ 3.242.
SALARIO = dict(medico=14000.0, enfermeiro=5000.0, tecnico=3000.0, acs=2.0 * 1621.0)
# Encargos e provisoes (hipotese CLT/RGPS): 13o salario e 1/3 de ferias
# (13 + 1/3 salarios por ano / 12) sobre os quais incidem INSS patronal 20%,
# RAT 2% e FGTS 8%. Fator = (13 + 1/3) / 12 * 1,30 = 1,4444.
ENCARGOS = (13 + 1 / 3) / 12 * (1 + 0.20 + 0.02 + 0.08)
CUSTO = dict(ubs_existente=12000.0, ubs_nova=15000.0,
             **{k: v * ENCARGOS for k, v in SALARIO.items()})
CUSTO_ESF = CUSTO["medico"] + CUSTO["enfermeiro"] + CUSTO["tecnico"]
HAB_POR_ACS = 750.0


# ----------------------------------------------------------------------------
# Utilitarios
# ----------------------------------------------------------------------------
def br(x, dec=0):
    """Formato brasileiro: 1.234,56"""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def haversine_matrix(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1 = np.radians(np.asarray(lat1))[:, None]
    p2 = np.radians(np.asarray(lat2))[None, :]
    dphi = p2 - p1
    dl = np.radians(np.asarray(lon2))[None, :] - np.radians(np.asarray(lon1))[:, None]
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def nome_curto(s, n=30):
    s = str(s).replace("UBS ", "").title()
    return s if len(s) <= n else s[: n - 1] + "…"


def porte_por_esf(n):
    return {0: "-", 1: "Porte I (1 eSF)", 2: "Porte II (2 eSF)",
            3: "Porte III (3 eSF)"}.get(int(n), "Porte IV (4 eSF)")


# ----------------------------------------------------------------------------
# Dados
# ----------------------------------------------------------------------------
def carregar_dados(args):
    dem = pd.read_csv(args.demanda)
    ubs = pd.read_csv(args.ubs)
    for c in ("lat", "lon", "pessoas"):
        dem[c] = pd.to_numeric(dem[c], errors="coerce")
    dem = dem.dropna(subset=["lat", "lon", "pessoas"]).reset_index(drop=True)
    dem["pessoas_base"] = dem["pessoas"].astype(float)

    # crescimento populacional por ponto (id 'i')
    pct = pd.Series(0.0, index=dem["i"])
    if args.growth_file:
        g = pd.read_csv(args.growth_file)
        g.columns = [c.strip().lower() for c in g.columns]
        g["pct"] = pd.to_numeric(g["pct"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
        desconhecidos = set(g["i"]) - set(dem["i"])
        if desconhecidos:
            sys.exit(f"Ids do CSV de crescimento ausentes na demanda: {sorted(desconhecidos)[:10]}")
        pct.loc[g["i"].values] = g["pct"].values
    elif args.growth:
        pct[:] = args.growth
    dem["crescimento_pct"] = pct.loc[dem["i"]].values
    dem["pessoas"] = dem["pessoas_base"] * (1.0 + dem["crescimento_pct"] / 100.0)

    ex = ubs[ubs["nivel_sugerido"] == "PHC"].copy().reset_index(drop=True)
    for c in ("lat", "lon"):
        ex[c] = pd.to_numeric(ex[c], errors="coerce")
    ex = ex.dropna(subset=["lat", "lon"]).reset_index(drop=True)

    d_ex = haversine_matrix(dem["lat"], dem["lon"], ex["lat"], ex["lon"]) * args.fator_rota
    dem["dist_ubs_existente_km"] = d_ex.min(axis=1)

    # sitios: existentes + pool de candidatas
    sites = [dict(id=f"UBS{int(r.j)}", nome=r.nome_fantasia, lat=r.lat, lon=r.lon,
                  existente=True, fixo=CUSTO["ubs_existente"], ponto=None)
             for r in ex.itertuples()]
    pool = dem[dem["dist_ubs_existente_km"] > args.dist_min_cand]
    for r in pool.itertuples():
        sites.append(dict(id=f"NOVA_{int(r.i)}", nome=f"NOVA UBS ({r.NM_BAIRRO})", lat=r.lat,
                          lon=r.lon, existente=False, fixo=CUSTO["ubs_nova"], ponto=int(r.i)))
    sites = pd.DataFrame(sites)
    D = haversine_matrix(dem["lat"], dem["lon"], sites["lat"], sites["lon"]) * args.fator_rota
    return dem, ex, sites, D


# ----------------------------------------------------------------------------
# Solver
# ----------------------------------------------------------------------------
def minimo_nova(site, dem, args):
    """Zona do ponto candidato: rural sem minimo por padrao; urbano mantem 2000."""
    if site.get('ponto') is None:
        return args.hab_min_nova
    ponto = dem.loc[dem['i'] == int(site['ponto'])].iloc[0]
    rural = '(rural)' in str(ponto.get('NM_BAIRRO', '')).casefold()
    return getattr(args, 'hab_min_nova_rural', 0) if rural else args.hab_min_nova


def limites_equipes(sites, args):
    """Preserva eSF atuais; salas limitam apenas a expansao e as novas UBS."""
    arquivo = getattr(args, 'limites_equipes', None)
    if not arquivo:
        return {j: (1 if s['existente'] else 0, args.esf_max)
                for j, s in sites.iterrows()}
    tabela = pd.read_csv(arquivo, sep=';', dtype={'cnes': str})
    if tabela['cnes'].duplicated().any():
        raise ValueError('CNES repetido na tabela de limites de equipes')
    regras = tabela.set_index('cnes').to_dict('index')
    cadastro = pd.read_csv(args.ubs, dtype={'cnes': str})
    cnes_por_id = {f'UBS{int(r.j)}': str(r.cnes) for r in cadastro.itertuples()}
    limites = {}
    for j, s in sites.iterrows():
        codigo = cnes_por_id.get(s['id']) if s['existente'] else 'NOVA'
        if codigo not in regras:
            raise ValueError(f'Unidade sem limite de equipes documentado: {s["id"]} / {codigo}')
        regra = regras[codigo]
        atual, maximo = float(regra['esf_atuais']), float(regra['esf_max'])
        if not atual.is_integer() or not maximo.is_integer() or atual < 0 or maximo < max(1, atual):
            raise ValueError(f'Limites de equipes invalidos: {codigo}')
        if s['existente'] and atual < 1:
            raise ValueError(f'UBS existente sem equipe atual: {codigo}')
        limites[j] = (int(atual) if s['existente'] else 0, int(maximo))
    return limites


def escolher_solver(nome, time_limit, gap, msg):
    nome = (nome or "auto").upper()
    ordem = ["GUROBI", "HIGHS", "PULP_CBC_CMD"] if nome == "AUTO" else [nome]
    for c in ordem:
        try:
            s = pl.getSolver("HiGHS" if c == "HIGHS" else c, msg=msg,
                             timeLimit=time_limit, gapRel=gap)
            if s.available():
                return s, ("HiGHS" if c == "HIGHS" else c)
        except Exception:
            continue
    sys.exit(f"Nenhum solver disponivel entre {ordem}. Instale highspy (pip install highspy).")


# ----------------------------------------------------------------------------
# Modelo MILP
# ----------------------------------------------------------------------------
def otimizar(dem, sites, D, args, solver, cob_min=None, log=print):
    m_, n_ = D.shape
    pop = dem["pessoas"].values
    total = pop.sum()
    cov = D <= args.raio + 1e-9
    existentes = [j for j in range(n_) if sites.at[j, "existente"]]
    cands = [j for j in range(n_) if not sites.at[j, "existente"]]
    limites = limites_equipes(sites, args)

    certificados = []
    prob = pl.LpProblem("Itauna_APS", pl.LpMinimize)
    x = {(i, j): pl.LpVariable(f"x_{i}_{j}", lowBound=0) for i in range(m_) for j in range(n_)}
    y = {j: pl.LpVariable(f"y_{j}", cat="Binary") for j in cands}
    ne = {j: pl.LpVariable(f"esf_{j}", lowBound=limites[j][0],
                           upBound=limites[j][1], cat="Integer") for j in range(n_)}
    ac = {j: pl.LpVariable(f"acs_{j}", lowBound=0, cat="Integer") for j in range(n_)}

    carga = {j: pl.lpSum(x[i, j] for i in range(m_)) for j in range(n_)}
    coberta = {j: pl.lpSum(x[i, j] for i in range(m_) if cov[i, j]) for j in range(n_)}
    cov_expr = pl.lpSum(x[i, j] for i in range(m_) for j in range(n_) if cov[i, j])

    for i in range(m_):
        prob += pl.lpSum(x[i, j] for j in range(n_)) == float(pop[i]), f"dem_{i}"
    for j in range(n_):
        prob += carga[j] <= args.hab_esf * ne[j], f"cap_{j}"
        prob += carga[j] <= HAB_POR_ACS * ac[j], f"acs_{j}"
    for j in cands:
        prob += ne[j] <= limites[j][1] * y[j], f"abre_max_{j}"
        prob += ne[j] >= y[j], f"abre_min_{j}"
        prob += coberta[j] >= minimo_nova(sites.iloc[j], dem, args) * y[j], f"viab_{j}"
    # Sem teto por padrao; o limite so vale quando informado explicitamente.
    if args.max_novas is not None:
        prob += pl.lpSum(y.values()) <= args.max_novas, "max_novas"

    custo_fixo = (sum(sites.at[j, "fixo"] for j in existentes)
                  + pl.lpSum(sites.at[j, "fixo"] * y[j] for j in cands))
    custo_eq = pl.lpSum(CUSTO_ESF * ne[j] + CUSTO["acs"] * ac[j] for j in range(n_))
    custo_desl = args.custo_km * pl.lpSum(D[i, j] * x[i, j] for i in range(m_) for j in range(n_))
    custo_total = custo_fixo + custo_eq + custo_desl

    if cob_min is None:
        log("  etapa 1/2: maximizando a populacao coberta ...")
        prob.setObjective(cov_expr)
        prob.sense = pl.LpMaximize
        prob.solve(solver)
        certificados.append(dict(status=pl.LpStatus[prob.status], sol_status=pl.LpSolution.get(prob.sol_status, str(prob.sol_status))))
        if pl.LpStatus[prob.status] != "Optimal":
            raise RuntimeError(f"Etapa 1 sem solucao otima: {pl.LpStatus[prob.status]}")
        c_star = pl.value(cov_expr)
        log(f"    cobertura maxima: {br(c_star)} hab ({c_star / total:.2%})")
        alvo = c_star - max(0.5, 1e-6 * total)
    else:
        alvo = cob_min * total
    prob += cov_expr >= alvo, "cobertura"
    prob.setObjective(custo_total)
    prob.sense = pl.LpMinimize
    log("  etapa 2/2: minimizando o custo ..." if cob_min is None else f"  minimizando o custo (cobertura >= {cob_min:.1%}) ...")
    prob.solve(solver)
    certificados.append(dict(status=pl.LpStatus[prob.status], sol_status=pl.LpSolution.get(prob.sol_status, str(prob.sol_status))))
    status = pl.LpStatus[prob.status]
    if status != "Optimal":
        return dict(status=status)
    if args.folga_custo is not None:
        print("  etapa 3: minimizando a distancia mantendo cobertura e custo ...")
        c2 = pl.value(custo_total)
        prob += custo_total <= c2 * (1 + args.folga_custo), "teto_custo"
        prob.setObjective(custo_desl)
        prob.sense = pl.LpMinimize
        prob.solve(solver)
        certificados.append(dict(status=pl.LpStatus[prob.status], sol_status=pl.LpSolution.get(prob.sol_status, str(prob.sol_status))))
        status = pl.LpStatus[prob.status]
    if status != "Optimal":
        return dict(status=status)

    certificado = dict(status=pl.LpStatus[prob.status], sol_status=pl.LpSolution.get(prob.sol_status, str(prob.sol_status)))
    val = lambda v: (v.varValue or 0.0)
    abertas = [j for j in cands if val(y[j]) > 0.5]
    ativos = existentes + abertas
    linhas = []
    for j in ativos:
        L = sum(val(x[i, j]) for i in range(m_))
        linhas.append(dict(
            id_ubs=sites.at[j, "id"], nome=sites.at[j, "nome"], lat=sites.at[j, "lat"],
            lon=sites.at[j, "lon"], status="EXISTENTE" if sites.at[j, "existente"] else "NOVA",
            pop_atendida=L,
            pop_coberta_raio=sum(val(x[i, j]) for i in range(m_) if cov[i, j]),
            n_esf=int(round(val(ne[j]))), acs=int(round(val(ac[j]))), idx=j,
            esf_atuais=limites[j][0] if sites.at[j, 'existente'] else 0,
            esf_max=limites[j][1],
            minimo_pop_abertura=0 if sites.at[j, "existente"] else minimo_nova(sites.iloc[j], dem, args)))
    ubs = pd.DataFrame(linhas)
    arcos = []
    for j in ativos:
        for i in range(m_):
            v = val(x[i, j])
            if v > 1e-8:
                arcos.append(dict(i=int(dem.at[i, "i"]), j_idx=j, id_ubs=sites.at[j, "id"],
                                  nome_ubs=sites.at[j, "nome"], pessoas=v, dist_km=D[i, j],
                                  coberto=bool(cov[i, j]), idx_dem=i))
    arcos = pd.DataFrame(arcos)
    custos = dict(
        fixo_existentes=float(sum(sites.at[j, "fixo"] for j in existentes)),
        fixo_novas=float(sum(sites.at[j, "fixo"] for j in abertas)),
        esf=float(CUSTO_ESF * ubs["n_esf"].sum()),
        acs=float(CUSTO["acs"] * ubs["acs"].sum()),
        deslocamento_proxy=float(pl.value(custo_desl)),
        objetivo=float(pl.value(custo_total)))
    custos["operacional"] = custos["fixo_existentes"] + custos["fixo_novas"] + custos["esf"] + custos["acs"]
    return dict(status=status, certificados=certificados, certificado=certificado, ubs=ubs, arcos=arcos, custos=custos,
                cobertura=float(pl.value(cov_expr)), total=float(total))


# ----------------------------------------------------------------------------
# Metricas e tabelas
# ----------------------------------------------------------------------------
def dist_quantil(d, w, q):
    o = np.argsort(d)
    d, w = np.asarray(d)[o], np.asarray(w)[o]
    c = np.cumsum(w) / w.sum()
    return float(d[np.searchsorted(c, q)])


def metricas_acesso(d, w, raio):
    d, w = np.asarray(d, float), np.asarray(w, float)
    return dict(
        pop=w.sum(),
        dist_media=float((d * w).sum() / w.sum()),
        dist_p90=dist_quantil(d, w, 0.90),
        dist_max=float(d.max()),
        pct_1km=float(w[d <= 1].sum() / w.sum()),
        pct_2km=float(w[d <= 2].sum() / w.sum()),
        pct_raio=float(w[d <= raio + 1e-9].sum() / w.sum()))


def montar_tabelas(res, dem, D, sites, args):
    ubs = res["ubs"].copy()
    ubs["ocupacao"] = ubs["pop_atendida"] / (args.hab_esf * ubs["n_esf"])
    ubs["hab_por_esf"] = ubs["pop_atendida"] / ubs["n_esf"]
    ubs["porte"] = ubs["n_esf"].apply(porte_por_esf)

    def situacao(r):
        if r["hab_por_esf"] < args.hab_min_esf:
            return "Subutilizada"
        if r["ocupacao"] >= 0.95:
            return "Lotada (>=95%)"
        return "Adequada"
    ubs["situacao"] = ubs.apply(situacao, axis=1)
    ubs["medicos"] = ubs["enfermeiros"] = ubs["tecnicos"] = ubs["n_esf"]
    ubs["custo_equipes"] = ubs["n_esf"] * CUSTO_ESF + ubs["acs"] * CUSTO["acs"]
    ubs["custo_fixo"] = np.where(ubs["status"] == "NOVA", CUSTO["ubs_nova"], CUSTO["ubs_existente"])
    ubs["custo_mensal"] = ubs["custo_equipes"] + ubs["custo_fixo"]
    ubs = ubs.sort_values(["status", "pop_atendida"], ascending=[False, False]).reset_index(drop=True)

    arcos = res["arcos"].merge(dem[["i", "NM_BAIRRO", "tipo_ponto"]], on="i", how="left")
    # ponto -> UBS mais proxima (qualquer) p/ territorios descobertos
    desc = arcos[~arcos["coberto"]].copy()
    ativos = ubs["idx"].values          # só as UBS que realmente existem no plano
    Dativ = D[:, ativos]
    near_all = Dativ.min(axis=1)
    near_idx = ativos[Dativ.argmin(axis=1)]
    mp = {int(dem.at[k, "i"]): k for k in range(len(dem))}
    desc["ubs_mais_proxima"] = [sites.at[near_idx[mp[i]], "nome"] for i in desc["i"]]
    desc["dist_mais_proxima_km"] = [near_all[mp[i]] for i in desc["i"]]
    desc = desc.sort_values("pessoas", ascending=False)

    # base: cada ponto na UBS existente mais proxima
    ex_idx = [j for j in range(len(sites)) if sites.at[j, "existente"]]
    d_base = D[:, ex_idx].min(axis=1)
    w = dem["pessoas"].values
    m_base = metricas_acesso(d_base, w, args.raio)
    m_plano = metricas_acesso(arcos["dist_km"].values, arcos["pessoas"].values, args.raio)
    return ubs, arcos, desc, m_base, m_plano, d_base


# ----------------------------------------------------------------------------
# Relatorio
# ----------------------------------------------------------------------------
def montar_relatorio(res, ubs, arcos, desc, m_base, m_plano, dem, args, solver_nome, pareto_df=None):
    c = res["custos"]
    total_pop = res["total"]
    novas = ubs[ubs["status"] == "NOVA"]
    ex = ubs[ubs["status"] == "EXISTENTE"]
    n_esf = int(ubs["n_esf"].sum())
    n_acs = int(ubs["acs"].sum())
    L = []
    add = L.append
    bar = "=" * 98
    add(bar)
    add("PLANO MUNICIPAL DE SAUDE DE ITAUNA - MG: LOCALIZACAO-ALOCACAO DA ATENCAO PRIMARIA")
    add(bar)
    cres = (dem["pessoas"].sum() / dem["pessoas_base"].sum() - 1) * 100
    regra_equipes = ('limites por unidade; equipes atuais preservadas' if getattr(args, 'limites_equipes', None)
                     else f'max. {args.esf_max} eSF/UBS')
    add(f"Solver: {solver_nome} | raio de cobertura: {args.raio:g} km | {br(args.hab_esf)} hab/eSF | "
        f"{regra_equipes} | limite de novas UBS: {args.max_novas if args.max_novas is not None else 'sem teto adicional'}")
    add(f"Populacao base: {br(dem['pessoas_base'].sum())} hab | cenario: {br(total_pop)} hab "
        f"({cres:+.1f}% de crescimento)")
    for fase, certificado in enumerate(res.get('certificados', []), 1):
        situacao = ('otimo confirmado' if certificado.get('sol_status') == 'Optimal Solution Found'
                    else 'solucao viavel; otimo nao comprovado no tempo de execucao')
        add(f"Fase {fase}: {situacao}.")
    if any(c.get('sol_status') != 'Optimal Solution Found' for c in res.get('certificados', [])):
        add('A quantidade de UBS deste plano nao foi comprovada como minima. A folga de custo usa a solucao encontrada na fase 2.')

    add("\n1. RESUMO EXECUTIVO")
    add("-" * 98)
    add(f" - UBS existentes mantidas: {len(ex)} | novas UBS recomendadas: {len(novas)}")
    add(f" - Populacao coberta a ate {args.raio:g} km: {br(res['cobertura'])} hab "
        f"({res['cobertura'] / total_pop:.1%})  [base, so UBS existentes: {m_base['pct_raio']:.1%}]")
    add(f" - Equipes de Saude da Familia (eSF): {n_esf} | ACS: {n_acs}")
    add(f" - Custo operacional mensal estimado: R$ {br(c['operacional'])}  "
        f"(R$ {br(c['operacional'] / total_pop, 2)} por habitante/mes)")
    if len(novas):
        add(f"   Das novas UBS, o impacto: +{(m_plano['pct_raio'] - m_base['pct_raio']) * 100:.1f} p.p. de cobertura")

    add("\n2. ACESSO GEOGRAFICO (distancia em linha reta ponderada pela populacao)")
    add("-" * 98)
    add(f"{'Indicador':<34}{'Base (so existentes)':>22}{'Plano proposto':>22}")
    rows = [("Distancia media (km)", m_base["dist_media"], m_plano["dist_media"], 2),
            ("Distancia p90 (km)", m_base["dist_p90"], m_plano["dist_p90"], 2),
            ("Distancia maxima (km)", m_base["dist_max"], m_plano["dist_max"], 2)]
    for nome, a, b, dd in rows:
        add(f"{nome:<34}{br(a, dd):>22}{br(b, dd):>22}")
    for nome, k in (("% pop. a ate 1 km", "pct_1km"), ("% pop. a ate 2 km", "pct_2km"),
                    (f"% pop. a ate {args.raio:g} km", "pct_raio")):
        add(f"{nome:<34}{m_base[k]:>21.1%} {m_plano[k]:>21.1%}")

    add("\n3. CUSTOS MENSAIS ESTIMADOS (R$)")
    add("-" * 98)
    add(f" - Custo fixo UBS existentes:       {br(c['fixo_existentes']):>14}")
    add(f" - Custo fixo UBS novas:            {br(c['fixo_novas']):>14}")
    add(f" - Equipes eSF ({n_esf}):                {br(c['esf']):>14}   (medico + enfermeiro + tecnico = R$ {br(CUSTO_ESF)}/eSF)")
    add(f" - Agentes comunitarios ({n_acs}):      {br(c['acs']):>14}")
    add(f" - TOTAL OPERACIONAL:               {br(c['operacional']):>14}")
    add(f" (o termo de deslocamento R$ {args.custo_km:g}/hab.km e um proxy usado so na otimizacao: "
        f"R$ {br(c['deslocamento_proxy'])})")

    add("\n4. NOVAS UBS RECOMENDADAS")
    add("-" * 98)
    if len(novas):
        add(f"{'Local':<44}{'Pop.':>8}{'Pop.<=R':>9}{'eSF':>5}{'ACS':>5}  {'Coordenadas'}")
        for r in novas.itertuples():
            add(f"{r.nome[:43]:<44}{br(r.pop_atendida):>8}{br(r.pop_coberta_raio):>9}{r.n_esf:>5}{r.acs:>5}  "
                f"({r.lat:.4f}, {r.lon:.4f})")
    else:
        add(" Nenhuma nova UBS se justifica sob as restricoes atuais (viabilidade/raio/limite).")

    add("\n5. REDE DE UBS (carga e dimensionamento)")
    add("-" * 98)
    add(f"{'ID':<9}{'UBS':<32}{'Status':<11}{'Pop.':>7}{'eSF':>4}{'Ocup.':>7}{'hab/eSF':>9}  {'Situacao'}")
    for r in ubs.sort_values("pop_atendida", ascending=False).itertuples():
        add(f"{r.id_ubs:<9}{nome_curto(r.nome, 31):<32}{r.status:<11}{br(r.pop_atendida):>7}{r.n_esf:>4}"
            f"{r.ocupacao:>7.0%}{br(r.hab_por_esf):>9}  {r.situacao}")
    sub = ubs[ubs["situacao"] == "Subutilizada"]
    lot = ubs[ubs["situacao"] == "Lotada (>=95%)"]
    add(f" Alertas: {len(sub)} UBS subutilizadas (< {br(args.hab_min_esf)} hab/eSF) e {len(lot)} lotadas (>= 95% da capacidade).")

    add("\n6. TERRITORIOS FORA DO RAIO DE COBERTURA")
    add("-" * 98)
    if len(desc):
        add(f" {br(desc['pessoas'].sum())} hab em {len(desc)} alocacoes acima de {args.raio:g} km "
            f"({desc['pessoas'].sum() / total_pop:.1%} da populacao). Maiores casos:")
        add(f"{'Ponto':<36}{'Tipo':<8}{'Pop.':>7}{'Dist. (km)':>11}  {'UBS mais proxima'}")
        for r in desc.head(12).itertuples():
            add(f"{nome_curto(r.NM_BAIRRO, 35):<36}{r.tipo_ponto:<8}{br(r.pessoas):>7}{r.dist_km:>11.1f}  "
                f"{nome_curto(r.ubs_mais_proxima, 30)}")
        add(" Sugestao: avaliar equipe itinerante/unidade movel, ou pontos de apoio com ACS, para esses territorios")
        add(" (uma UBS fixa nao atinge a viabilidade minima de populacao nessas areas).")
    else:
        add(f" Toda a populacao esta a ate {args.raio:g} km de uma UBS.")

    if pareto_df is not None and len(pareto_df):
        add("\n7. TROCA ENTRE COBERTURA E CUSTO (meta de cobertura -> plano)")
        add("-" * 98)
        add(f"{'Meta':>8}{'Cobertura':>11}{'Novas UBS':>11}{'eSF':>5}{'Custo (R$/mes)':>17}")
        for r in pareto_df.itertuples():
            add(f"{r.meta:>8}{r.cobertura:>11.1%}{r.novas:>11}{r.esf:>5}{br(r.custo):>17}")

    add("\nNOTAS METODOLOGICAS")
    add("-" * 98)
    add(f" * Distancias: Haversine x fator de rota {args.fator_rota:g}. Cobertura = alocada a UBS a ate {args.raio:g} km.")
    add(f" * Capacidade: {br(args.hab_esf)} hab por eSF; ACS: 1 por {br(HAB_POR_ACS)} hab, sem teto fixo por UBS.")
    if getattr(args, 'limites_equipes', None):
        add(" * Equipes atuais preservadas. Expansao limitada pelas salas de cada UBS; Central e Zona Rural mantem uma equipe. Novas UBS: estrutura planejada conforme tabela de limites.")
    else:
        add(f" * Limite uniforme de {args.esf_max} eSF por UBS (cenario sem tabela de limites fisicos).")
    add(f" * Minimo por nova UBS: urbana {br(args.hab_min_nova)} hab; rural {br(args.hab_min_nova_rural)} hab dentro do raio. Rural identificado por (rural) no nome do ponto. Existentes permanecem abertas (>= 1 eSF).")
    add(" * Otimizacao lexicografica: (1) max. cobertura; (2) min. custo; (3) min. distancia (custo limitado pela solucao da fase 2 e pela folga).")
    add(" * Alocacao fracionada permitida (um bairro pode dividir populacao entre UBS vizinhas).")
    add(bar)
    return "\n".join(L)


# ----------------------------------------------------------------------------
# Graficos
# ----------------------------------------------------------------------------
COR = dict(ex="#1e8449", nova="#c0392b", bairro="#2e86c1", setor="#e67e22", desc="#c0392b")


def _ellipse(ax, lat, lon, r_km, **kw):
    w = 2 * r_km / (111.32 * math.cos(math.radians(lat)))
    h = 2 * r_km / 110.57
    ax.add_patch(Ellipse((lon, lat), w, h, **kw))


def mapa(dem, ubs, arcos, args, caminho, zoom=False, titulo=""):
    fig, ax = plt.subplots(figsize=(12, 10), dpi=200)
    lat0 = dem["lat"].mean()
    ax.set_aspect(1 / math.cos(math.radians(lat0)))

    st = arcos.groupby("i").agg(coberto=("coberto", "min"), dmax=("dist_km", "max")).reset_index()
    d = dem.merge(st, on="i", how="left")
    d["coberto"] = d["coberto"].fillna(True).astype(bool)

    if zoom:
        pad = 0.012
        sel = ubs[ubs["status"] == "EXISTENTE"]
        x0, x1 = sel["lon"].min() - pad, sel["lon"].max() + pad
        y0, y1 = sel["lat"].min() - pad, sel["lat"].max() + pad
    else:
        x0, x1 = d["lon"].min() - 0.02, d["lon"].max() + 0.02
        y0, y1 = d["lat"].min() - 0.015, d["lat"].max() + 0.015

    # linhas de alocacao
    pos = {int(r.i): (r.lon, r.lat) for r in dem.itertuples()}
    up = {r.id_ubs: (r.lon, r.lat) for r in ubs.itertuples()}
    for r in arcos.itertuples():
        (xa, ya), (xb, yb) = pos[r.i], up[r.id_ubs]
        ax.plot([xa, xb], [ya, yb], color="#c0392b" if not r.coberto else "#95a5a6",
                lw=0.5 if r.coberto else 0.9, alpha=0.35 if r.coberto else 0.7, zorder=1)

    # areas de cobertura
    for r in ubs.itertuples():
        _ellipse(ax, r.lat, r.lon, args.raio,
                 fc=COR["nova"] if r.status == "NOVA" else COR["ex"],
                 ec=COR["nova"] if r.status == "NOVA" else COR["ex"],
                 alpha=0.10 if r.status == "NOVA" else 0.045, lw=1.0, zorder=0)

    for tipo, marker, cor in (("bairro", "o", COR["bairro"]), ("setor", "^", COR["setor"])):
        s = d[(d["tipo_ponto"] == tipo) & d["coberto"]]
        ax.scatter(s["lon"], s["lat"], s=np.sqrt(s["pessoas"]) * 2.2 + 10, c=cor, marker=marker,
                   alpha=0.75, edgecolors="white", linewidths=0.5, zorder=3,
                   label=f"{'Bairros' if tipo == 'bairro' else 'Setores'} (coberto ≤ {args.raio:g} km)")
    s = d[~d["coberto"]]
    if len(s):
        ax.scatter(s["lon"], s["lat"], s=np.sqrt(s["pessoas"]) * 2.2 + 25, facecolors="none",
                   edgecolors=COR["desc"], linewidths=1.6, zorder=4,
                   label=f"Fora do raio de {args.raio:g} km ({br(s['pessoas'].sum())} hab)")

    e = ubs[ubs["status"] == "EXISTENTE"]
    ax.scatter(e["lon"], e["lat"], s=60 + 35 * e["n_esf"], c=COR["ex"], marker="s", edgecolors="black",
               linewidths=0.9, zorder=5, label=f"UBS existentes ({len(e)})")
    n = ubs[ubs["status"] == "NOVA"]
    if len(n):
        ax.scatter(n["lon"], n["lat"], s=420, c=COR["nova"], marker="*", edgecolors="black",
                   linewidths=1.1, zorder=6, label=f"Novas UBS propostas ({len(n)})")
        for r in n.itertuples():
            ax.annotate(f"{nome_curto(r.nome.replace('NOVA UBS ', ''), 34)}\n{br(r.pop_atendida)} hab · {r.n_esf} eSF",
                        (r.lon, r.lat), fontsize=7.5, fontweight="bold", color="#78281f",
                        xytext=(12, 8), textcoords="offset points", zorder=7,
                        bbox=dict(boxstyle="round,pad=0.3", fc="#fcf3cf", ec=COR["nova"], lw=1, alpha=0.95))
    if zoom:
        for r in e.itertuples():
            ax.annotate(nome_curto(r.nome, 18), (r.lon, r.lat), fontsize=6.5, color="#145a32",
                        xytext=(5, -9), textcoords="offset points", zorder=6)

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_title(titulo or "Plano da Atenção Primária — Itaúna/MG", fontsize=13, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, ls=":", alpha=0.5)
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(caminho)
    plt.close(fig)


def painel(dem, ubs, arcos, m_base, m_plano, d_base, res, args, caminho):
    fig = plt.figure(figsize=(17, 12), dpi=160)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1], hspace=0.28, wspace=0.22)

    # A) carga por UBS
    ax = fig.add_subplot(gs[:, 0])
    u = ubs.sort_values("pop_atendida").reset_index(drop=True)
    cap = u["n_esf"] * args.hab_esf
    cores = [COR["nova"] if s == "NOVA" else COR["ex"] for s in u["status"]]
    ax.barh(range(len(u)), cap, color="none", edgecolor="#7f8c8d", hatch="///", lw=0.6, label="Capacidade (eSF × hab/eSF)")
    ax.barh(range(len(u)), u["pop_atendida"], color=cores, alpha=0.9, label="Pop. atendida")
    for k, r in u.iterrows():
        ax.text(max(cap[k], r["pop_atendida"]) + 60, k, f"{br(r['pop_atendida'])} · {r['n_esf']} eSF · {r['ocupacao']:.0%}",
                va="center", fontsize=7.5)
    ax.set_yticks(range(len(u)))
    ax.set_yticklabels([nome_curto(n, 28) for n in u["nome"].str.replace("NOVA UBS ", "NOVA ", regex=False)], fontsize=8)
    ax.set_xlim(0, cap.max() * 1.28)
    ax.set_title("Carga por UBS × capacidade (verde = existente, vermelho = nova)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Habitantes")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", ls=":", alpha=0.5)

    # B) curva de acesso
    ax = fig.add_subplot(gs[0, 1])
    for nome, d, w, cor in (("Base (só existentes)", d_base, dem["pessoas"].values, "#7f8c8d"),
                            ("Plano proposto", arcos["dist_km"].values, arcos["pessoas"].values, COR["ex"])):
        o = np.argsort(d)
        ax.plot(np.asarray(d)[o], np.cumsum(np.asarray(w)[o]) / np.asarray(w).sum() * 100, lw=2.2, label=nome, color=cor)
    ax.axvline(args.raio, color=COR["nova"], ls="--", lw=1.2)
    ax.text(args.raio + 0.1, 8, f"raio {args.raio:g} km", color=COR["nova"], fontsize=8)
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 101)
    ax.set_xlabel("Distância até a UBS (km)")
    ax.set_ylabel("% acumulado da população")
    ax.set_title("Acesso: população acumulada × distância", fontsize=11, fontweight="bold")
    ax.legend(loc="lower right", fontsize=8.5)
    ax.grid(True, ls=":", alpha=0.5)

    # C) custos
    ax = fig.add_subplot(gs[1, 1])
    c = res["custos"]
    itens = [("UBS existentes (fixo)", c["fixo_existentes"], "#85929e"), ("UBS novas (fixo)", c["fixo_novas"], COR["nova"]),
             ("Equipes eSF", c["esf"], "#2e86c1"), ("ACS", c["acs"], "#f39c12")]
    ini = 0
    for nome, v, cor in itens:
        if v <= 0:
            continue
        ax.barh([0], [v], left=ini, color=cor, edgecolor="white", label=f"{nome}: R$ {br(v)}")
        ax.text(ini + v / 2, 0, f"{v / c['operacional']:.0%}", ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")
        ini += v
    ax.set_yticks([])
    ax.set_xlabel("R$ por mês")
    ax.set_title(f"Custo operacional mensal: R$ {br(c['operacional'])}", fontsize=11, fontweight="bold")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, fontsize=8, frameon=False)
    fig.suptitle("Itaúna/MG — Painel de resultados da Atenção Primária", fontsize=14, fontweight="bold", y=0.94)
    fig.savefig(caminho, bbox_inches="tight")
    plt.close(fig)


def grafico_pareto(df, escolhido, caminho):
    fig, ax = plt.subplots(figsize=(9, 6), dpi=160)
    ax.plot(df["cobertura"] * 100, df["custo"] / 1000, "-o", color="#2e86c1", lw=2)
    for r in df.itertuples():
        ax.annotate(f"{r.novas} nova(s)", (r.cobertura * 100, r.custo / 1000), xytext=(6, -12),
                    textcoords="offset points", fontsize=8)
    if escolhido is not None:
        ax.scatter([escolhido[0] * 100], [escolhido[1] / 1000], s=220, marker="*", c=COR["nova"], zorder=5,
                   label="Plano escolhido")
        ax.legend()
    ax.set_xlabel("Cobertura da população a ≤ raio (%)")
    ax.set_ylabel("Custo operacional (R$ mil/mês)")
    ax.set_title("Troca entre cobertura e custo", fontweight="bold")
    ax.grid(True, ls=":", alpha=0.6)
    fig.tight_layout()
    fig.savefig(caminho)
    plt.close(fig)


def mapa_html(dem, ubs, arcos, args, caminho):
    try:
        import folium
    except ImportError:
        print("  (folium nao instalado: mapa interativo ignorado — pip install folium)")
        return
    m = folium.Map(location=[dem["lat"].mean(), dem["lon"].mean()], zoom_start=12, tiles="OpenStreetMap")
    st = arcos.groupby("i").agg(coberto=("coberto", "min"), ubs=("nome_ubs", "first"), dist=("dist_km", "max")).reset_index()
    d = dem.merge(st, on="i", how="left")
    g1 = folium.FeatureGroup("Demanda")
    for r in d.itertuples():
        cor = "#c0392b" if (r.coberto is False or r.coberto == 0) else ("#2e86c1" if r.tipo_ponto == "bairro" else "#e67e22")
        folium.CircleMarker([r.lat, r.lon], radius=max(3, math.sqrt(r.pessoas) / 6), color=cor, fill=True,
                            fill_opacity=0.6, weight=1,
                            tooltip=f"{r.NM_BAIRRO}: {br(r.pessoas)} hab ({r.tipo_ponto}) → {r.ubs} ({r.dist:.1f} km)").add_to(g1)
    g1.add_to(m)
    g2 = folium.FeatureGroup("UBS e raio de cobertura")
    for r in ubs.itertuples():
        nova = r.status == "NOVA"
        folium.Marker([r.lat, r.lon], icon=folium.Icon(color="red" if nova else "green", icon="plus-sign"),
                      tooltip=f"{r.nome} — {br(r.pop_atendida)} hab · {r.n_esf} eSF · ocupação {r.ocupacao:.0%} ({r.situacao})").add_to(g2)
        folium.Circle([r.lat, r.lon], radius=args.raio * 1000, color="#c0392b" if nova else "#1e8449",
                      weight=1, fill=True, fill_opacity=0.07 if nova else 0.03).add_to(g2)
    g2.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(caminho)


# ----------------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------------
def salvar_excel(caminho, resumo, ubs, arcos, desc, dem, params, pareto_df):
    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        resumo.to_excel(w, sheet_name="Resumo", index=False)
        cols = ["id_ubs", "nome", "status", "lat", "lon", "pop_atendida", "pop_coberta_raio", "n_esf", "medicos",
                "enfermeiros", "tecnicos", "acs", "porte", "ocupacao", "hab_por_esf", "situacao", "custo_fixo",
                "custo_equipes", "custo_mensal"]
        ubs[cols].round(2).to_excel(w, sheet_name="UBS", index=False)
        arcos[["i", "NM_BAIRRO", "tipo_ponto", "id_ubs", "nome_ubs", "pessoas", "dist_km", "coberto"]].round(2).to_excel(w, sheet_name="Alocacoes", index=False)
        desc[["i", "NM_BAIRRO", "tipo_ponto", "pessoas", "dist_km", "ubs_mais_proxima", "dist_mais_proxima_km"]].round(2).to_excel(w, sheet_name="Fora_do_raio", index=False)
        dem[["i", "NM_BAIRRO", "tipo_ponto", "lat", "lon", "pessoas_base", "crescimento_pct", "pessoas",
             "dist_ubs_existente_km"]].round(2).to_excel(w, sheet_name="Demanda", index=False)
        pd.DataFrame(params.items(), columns=["parametro", "valor"]).to_excel(w, sheet_name="Parametros", index=False)
        if pareto_df is not None:
            pareto_df.to_excel(w, sheet_name="Cobertura_x_Custo", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    45, max(10, max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2))


# ----------------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demanda", default="pontos_demanda_itauna.csv")
    ap.add_argument("--ubs", default="unidades_existentes_itauna.csv")
    ap.add_argument("--raio", type=float, default=3.0, help="raio de cobertura em km (padrao 3)")
    ap.add_argument("--fator-rota", type=float, default=1.0, help="multiplica a distancia em linha reta (ex.: 1.3)")
    ap.add_argument("--hab-esf", type=float, default=3000, help="habitantes por eSF (capacidade)")
    ap.add_argument("--hab-min-esf", type=float, default=2000, help="minimo de hab/eSF p/ nao ser 'subutilizada'")
    ap.add_argument("--esf-max", type=int, default=4, help="max. de eSF por UBS")
    ap.add_argument("--limites-equipes", default=None, help="CSV de limites por CNES; preserva equipes atuais e limita a expansao")
    ap.add_argument("--max-novas", type=int, default=None, help="teto opcional de novas UBS; omitido = sem teto adicional")
    ap.add_argument("--hab-min-nova", type=float, default=2000, help="pop. minima dentro do raio p/ abrir nova UBS")
    ap.add_argument("--hab-min-nova-rural", type=float, default=0, help="minimo rural; zero = sem minimo populacional")
    ap.add_argument("--dist-min-cand", type=float, default=1.0, help="distancia minima (km) das candidatas a UBS existentes")
    ap.add_argument("--custo-km", type=float, default=0.05, help="proxy R$/hab.km do deslocamento")
    ap.add_argument("--cobertura-min", type=float, default=None, help="meta de cobertura (0-1); omitido = lexicografico")
    ap.add_argument("--growth", type=float, default=None, help="crescimento %% uniforme da populacao")
    ap.add_argument("--growth-file", default=None, help="CSV (i,pct) com crescimento %% por ponto de demanda")
    ap.add_argument("--solver", default="auto", help="auto (Gurobi>HiGHS>CBC), GUROBI, HiGHS, PULP_CBC_CMD")
    ap.add_argument("--time-limit", type=float, default=300)
    ap.add_argument("--gap", type=float, default=1e-4)
    ap.add_argument("--pareto", action="store_true", help="gera a curva cobertura x custo")
    ap.add_argument("--saida", default="resultados_itauna")
    ap.add_argument("--quiet", action="store_true", help="oculta o log do solver")
    ap.add_argument("--folga-custo", type=float, default=0.02,
                    help="etapa 3: aceita ate X%% de custo a mais para reduzir a distancia (0.02 = 2%%)")
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    out = lambda f: os.path.join(args.saida, f)
    print("Carregando dados ...")
    dem, ex, sites, D = carregar_dados(args)
    limites = limites_equipes(sites, args)
    pd.DataFrame([dict(id_ubs=s['id'], nome=s['nome'], existente=bool(s['existente']),
                       esf_atuais=limites[j][0], esf_max=limites[j][1])
                  for j, s in sites.iterrows()]).to_csv(out('limites_equipes_aplicados.csv'), index=False)
    n_c = int((~sites["existente"]).sum())
    print(f"  {len(dem)} pontos de demanda ({br(dem['pessoas'].sum())} hab) | {len(ex)} UBS existentes | "
          f"{n_c} candidatas")
    solver, snome = escolher_solver(args.solver, args.time_limit, args.gap, not args.quiet)
    print(f"  solver: {snome}")

    print("Otimizando ...")
    res = otimizar(dem, sites, D, args, solver, cob_min=args.cobertura_min)
    if res["status"] != "Optimal":
        sys.exit(f"Sem solucao otima: {res['status']} (relaxe --cobertura-min, --max-novas ou --hab-min-nova).")

    ubs, arcos, desc, m_base, m_plano, d_base = montar_tabelas(res, dem, D, sites, args)

    pareto_df, escolhido = None, (res["cobertura"] / res["total"], res["custos"]["operacional"])
    if args.pareto:
        print("Curva cobertura x custo ...")
        # patamares: da cobertura base ate a maxima; cada ponto reotimiza o custo
        topo = res["cobertura"] / res["total"] if args.cobertura_min is None else None
        if topo is None:
            r0 = otimizar(dem, sites, D, args, solver, cob_min=None, log=lambda *_: None)
            topo = r0["cobertura"] / r0["total"]
        base = m_base["pct_raio"]
        metas = sorted({round(base + (topo - base) * f, 4) for f in (0, 0.25, 0.5, 0.75, 1.0)})
        linhas = []
        for meta in metas:
            r = otimizar(dem, sites, D, args, solver, cob_min=max(0.0, meta - 1e-6), log=lambda *_: None)
            if r["status"] == "Optimal":
                linhas.append(dict(meta=f"{meta:.1%}", cobertura=r["cobertura"] / r["total"],
                                   novas=int((r["ubs"]["status"] == "NOVA").sum()),
                                   esf=int(r["ubs"]["n_esf"].sum()), custo=r["custos"]["operacional"]))
        pareto_df = pd.DataFrame(linhas)
        grafico_pareto(pareto_df, escolhido, out("pareto_cobertura_custo.png"))

    relatorio = montar_relatorio(res, ubs, arcos, desc, m_base, m_plano, dem, args, snome, pareto_df)
    print("\n" + relatorio)
    with open(out("relatorio_itauna.txt"), "w", encoding="utf-8") as f:
        f.write(relatorio)

    print("\nGerando mapas e graficos ...")
    mapa(dem, ubs, arcos, args, out("mapa_itauna_ubs.png"), zoom=False,
         titulo="Plano da Atenção Primária — Itaúna/MG (visão do município)")
    mapa(dem, ubs, arcos, args, out("mapa_itauna_zoom_urbano.png"), zoom=True,
         titulo="Plano da Atenção Primária — Itaúna/MG (zoom na área urbana)")
    painel(dem, ubs, arcos, m_base, m_plano, d_base, res, args, out("painel_resultados.png"))
    mapa_html(dem, ubs, arcos, args, out("mapa_interativo.html"))

    c = res["custos"]
    resumo = pd.DataFrame([
        ("Populacao (cenario)", round(res["total"])), ("UBS existentes", int((ubs.status == "EXISTENTE").sum())),
        ("Novas UBS", int((ubs.status == "NOVA").sum())), ("eSF", int(ubs.n_esf.sum())), ("ACS", int(ubs.acs.sum())),
        (f"Cobertura base <= {args.raio:g} km", round(m_base["pct_raio"], 4)),
        (f"Cobertura plano <= {args.raio:g} km", round(res["cobertura"] / res["total"], 4)),
        ("Distancia media base (km)", round(m_base["dist_media"], 2)),
        ("Distancia media plano (km)", round(m_plano["dist_media"], 2)),
        ("Custo fixo existentes (R$/mes)", round(c["fixo_existentes"])), ("Custo fixo novas (R$/mes)", round(c["fixo_novas"])),
        ("Custo eSF (R$/mes)", round(c["esf"])), ("Custo ACS (R$/mes)", round(c["acs"])),
        ("Custo operacional total (R$/mes)", round(c["operacional"])),
    ], columns=["indicador", "valor"])
    params = {k: v for k, v in vars(args).items()}
    params.update({f"custo_{k}": v for k, v in CUSTO.items()})
    salvar_excel(out("resultado_itauna.xlsx"), resumo, ubs, arcos, desc, dem, params, pareto_df)
    print(f"Arquivos salvos em '{args.saida}/'.")
    # Dados sem arredondamento para conectar UBS existentes e novas a hierarquia.
    res["arcos"].to_csv(out("alocacao_completa.csv"), index=False)
    res["ubs"].to_csv(out("ubs_completas.csv"), index=False)
    dem.to_csv(out("demanda_cenario.csv"), index=False)
    return dict(dem=dem, sites=sites, args=args, res=res)


if __name__ == "__main__":
    main()
