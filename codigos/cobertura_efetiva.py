"""Cobertura efetiva da APS: acesso geografico (3 km) combinado com capacidade de eSF e ACS.

Definicoes (todas calculadas, nenhuma inserida manualmente):
  P_i        populacao do ponto de demanda i
  d_ij       distancia (km) entre o ponto i e a UBS j, por haversine
  cob_ij     1 se d_ij <= raio_i (3 km por padrao)
  S_j        capacidade das equipes   = hab_esf * eSF_j          (3000 hab/eSF)
  A_j        capacidade dos ACS       = hab_acs * ACS_j          (750 hab/ACS, Portaria GM/MS 2.436/2017)
  C_j        capacidade efetiva da UBS = min(S_j, A_j)
  x_ij >= 0  populacao do ponto i atendida pela UBS j; so existe se cob_ij = 1

  max  soma x_ij   s.a.   soma_j x_ij <= P_i   (sem dupla contagem de populacao)
                          soma_i x_ij <= C_j   (sem dupla contagem de capacidade)

Cobertura geografica = soma P_i dos pontos com alguma UBS a <= raio / soma P_i.
Cobertura efetiva    = soma x_ij otimo / soma P_i      (sempre <= cobertura geografica).
Populacao sem cobertura efetiva = (sem acesso geografico) + (com acesso, mas sem capacidade).

Equipes moveis: dimensionadas apenas para a populacao SEM cobertura geografica, com capacidade
propria (hab_movel por equipe); a demanda excedente fica registrada como nao atendida.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pulp as pl

from caminhos import BASE, RESULTADOS
from geografia import distancias_haversine_km

HAB_ESF = 3000.0
HAB_ACS = 750.0
RAIO_KM = 3.0
RAIO_ROTA_KM = 15.0   # hipotese: raio maximo da rota semanal de uma equipe movel
MAX_PARADAS = 5       # hipotese: ate 5 pontos (um por dia util) por equipe movel
HAB_MOVEL = 2000.0   # hipotese de modelagem (limite inferior da faixa 2.000-3.500 hab/equipe da PNAB 2017)


def _solver():
    s = pl.HiGHS(msg=False) if 'HiGHS' in pl.listSolvers(onlyAvailable=True) else pl.PULP_CBC_CMD(msg=False)
    return s


def zona(nome):
    return 'rural' if '(rural)' in str(nome).lower() else 'urbana'


def carregar_rede_atual():
    """22 UBS (nivel PHC) com eSF e ACS do CNES 07/2026."""
    un = pd.read_csv(BASE/'unidades_existentes_itauna.csv', encoding='utf-8-sig', dtype={'cnes': str})
    un = un[un['nivel_sugerido'] == 'PHC'].copy()
    rec = pd.read_csv(BASE/'fontes_publicas/ubs_recursos_cnes_202607.csv', sep=';', encoding='utf-8-sig', dtype={'cnes': str})
    un = un.merge(rec[['cnes', 'esf', 'acs_vinculos']], on='cnes', how='left')
    if un['esf'].isna().any():
        raise ValueError('UBS sem equipes no CNES: ' + ', '.join(un.loc[un['esf'].isna(), 'cnes']))
    return pd.DataFrame(dict(id=un['cnes'], nome=un['nome_fantasia'], lat=un['lat'], lon=un['lon'],
                             esf=un['esf'].astype(float), acs=un['acs_vinculos'].astype(float), status='EXISTENTE'))


def carregar_plano(pasta_plano):
    u = pd.read_csv(Path(pasta_plano)/'aps/ubs_completas.csv', encoding='utf-8-sig')
    return pd.DataFrame(dict(id=u['id_ubs'], nome=u['nome'], lat=u['lat'], lon=u['lon'],
                             esf=u['n_esf'].astype(float), acs=u['acs'].astype(float), status=u['status']))


def cobertura_efetiva(pontos, ubs, raio=RAIO_KM, raio_rural=None, hab_esf=HAB_ESF, hab_acs=HAB_ACS, fator_rota=1.0):
    """Retorna (resumo, por_ponto, por_ubs, arcos)."""
    D = distancias_haversine_km(pontos['lon'], pontos['lat'], ubs['lon'], ubs['lat'], fator_rota)
    pop = pontos['pessoas'].astype(float).values
    if (pop <= 0).any():
        raise ValueError('Populacao nao positiva')
    rr = raio if raio_rural is None else raio_rural
    raios = np.array([rr if zona(n) == 'rural' else raio for n in pontos['NM_BAIRRO']])
    cob = D <= raios[:, None] + 1e-9
    S = hab_esf*ubs['esf'].values
    A = hab_acs*ubs['acs'].values
    C = np.minimum(S, A)
    m, n = D.shape
    prob = pl.LpProblem('cobertura_efetiva', pl.LpMaximize)
    x = {(i, j): pl.LpVariable(f'x_{i}_{j}', lowBound=0) for i in range(m) for j in range(n) if cob[i, j]}
    prob += pl.lpSum(x.values())
    for i in range(m):
        arcos_i = [x[i, j] for j in range(n) if (i, j) in x]
        if arcos_i:
            prob += pl.lpSum(arcos_i) <= float(pop[i])
    for j in range(n):
        arcos_j = [x[i, j] for i in range(m) if (i, j) in x]
        if arcos_j:
            prob += pl.lpSum(arcos_j) <= float(C[j])
    prob.solve(_solver())
    if pl.LpStatus[prob.status] != 'Optimal':
        raise RuntimeError('Fluxo de cobertura sem otimo: ' + pl.LpStatus[prob.status])
    fl = {k: (v.varValue or 0.0) for k, v in x.items()}
    atendida = np.array([sum(fl.get((i, j), 0.0) for j in range(n)) for i in range(m)])
    carga = np.array([sum(fl.get((i, j), 0.0) for i in range(m)) for j in range(n)])
    tem_acesso = cob.any(axis=1)
    N = pop.sum()
    geo = pop[tem_acesso].sum()
    efetiva = atendida.sum()
    # Verificacoes de consistencia (sem dupla contagem)
    assert (atendida <= pop + 1e-6).all() and (carga <= C + 1e-6).all() and efetiva <= geo + 1e-6
    por_ponto = pontos[['i', 'NM_BAIRRO', 'tipo_ponto', 'lon', 'lat', 'pessoas']].copy()
    por_ponto['zona'] = [zona(v) for v in por_ponto['NM_BAIRRO']]
    por_ponto['dist_ubs_mais_proxima_km'] = D.min(axis=1)
    por_ponto['ubs_mais_proxima'] = ubs['nome'].values[D.argmin(axis=1)]
    por_ponto['raio_km'] = raios
    por_ponto['cobertura_geografica'] = tem_acesso.astype(int)
    por_ponto['pop_atendida_efetiva'] = atendida
    por_ponto['pop_coberta_sem_capacidade'] = np.where(tem_acesso, pop-atendida, 0.0)
    por_ponto['pop_sem_cobertura_geografica'] = np.where(tem_acesso, 0.0, pop)
    por_ubs = ubs.copy()
    por_ubs['capacidade_esf'] = S
    por_ubs['capacidade_acs'] = A
    por_ubs['capacidade_efetiva'] = C
    por_ubs['fator_limitante'] = np.where(A < S, 'ACS', 'eSF')
    por_ubs['pop_geografica_no_raio'] = [pop[cob[:, j]].sum() for j in range(n)]
    por_ubs['carga_atendida'] = carga
    por_ubs['ocupacao_pct'] = 100*carga/np.where(C > 0, C, np.nan)
    arcos = pd.DataFrame([dict(i=int(pontos['i'].iloc[i]), ubs=ubs['nome'].iloc[j], pessoas=v, dist_km=D[i, j])
                          for (i, j), v in fl.items() if v > 1e-9])
    zonas = {}
    for z in ['total', 'urbana', 'rural']:
        k = np.array([True]*m) if z == 'total' else (por_ponto['zona'] == z).values
        zonas[z] = dict(populacao=float(pop[k].sum()), cobertura_geografica_pct=float(100*pop[k & tem_acesso].sum()/pop[k].sum()),
                        cobertura_efetiva_pct=float(100*atendida[k].sum()/pop[k].sum()))
    resumo = dict(populacao=float(N), pontos=int(m), ubs=int(n), esf_total=float(ubs['esf'].sum()), acs_total=float(ubs['acs'].sum()),
                  raio_km=raio, raio_rural_km=rr, fator_rota=fator_rota, hab_esf=hab_esf, hab_acs=hab_acs,
                  capacidade_esf_total=float(S.sum()), capacidade_acs_total=float(A.sum()), capacidade_efetiva_total=float(C.sum()),
                  pop_com_acesso_geografico=float(geo), pop_sem_cobertura_geografica=float(N-geo),
                  cobertura_geografica_pct=float(100*geo/N),
                  pop_atendida_efetiva=float(efetiva), cobertura_efetiva_pct=float(100*efetiva/N),
                  pop_coberta_sem_capacidade=float(geo-efetiva), perda_por_capacidade_pp=float(100*(geo-efetiva)/N),
                  razao_capacidade_populacao_pct=float(100*C.sum()/N),
                  ubs_limitadas_por_acs=int((A < S).sum()), zonas=zonas,
                  metodo_distancia='haversine')
    return resumo, por_ponto, por_ubs, arcos


def sensibilidade(pontos, ubs, raio=RAIO_KM):
    linhas = []
    for h in (2000, 2500, 3000, 3450):
        for a in (550, 750):
            r = cobertura_efetiva(pontos, ubs, raio, hab_esf=h, hab_acs=a)[0]
            linhas.append(dict(hab_esf=h, hab_acs=a, raio_km=raio, cobertura_geografica_pct=r['cobertura_geografica_pct'],
                               cobertura_efetiva_pct=r['cobertura_efetiva_pct']))
    for rk in (2.0, 2.5, 3.0, 3.5, 4.0):
        r = cobertura_efetiva(pontos, ubs, rk)[0]
        linhas.append(dict(hab_esf=HAB_ESF, hab_acs=HAB_ACS, raio_km=rk, cobertura_geografica_pct=r['cobertura_geografica_pct'],
                           cobertura_efetiva_pct=r['cobertura_efetiva_pct']))
    return pd.DataFrame(linhas).drop_duplicates()


def equipes_moveis(pontos, por_ponto, raio_rota=RAIO_ROTA_KM, hab_movel=HAB_MOVEL, max_paradas=MAX_PARADAS,
                   hab_acs=HAB_ACS, max_equipes=None):
    """Dimensiona e posiciona equipes moveis (itinerantes) para a populacao SEM cobertura geografica.

    Uma equipe movel tem base em um dos pontos descobertos e visita os pontos descobertos a ate
    `raio_rota` km da base (rota semanal), com no maximo `max_paradas` pontos por equipe e capacidade
    propria de `hab_movel` habitantes. Etapa 1: maximizar a populacao atendida; etapa 2: minimizar o
    numero de equipes. A populacao excedente permanece registrada como nao atendida.
    Parametros de rota e de capacidade sao hipoteses de modelagem (nao ha norma nacional especifica).
    """
    desc = por_ponto[por_ponto['cobertura_geografica'] == 0].reset_index(drop=True)
    if desc.empty:
        return dict(equipes=0, populacao_sem_cobertura=0.0, atendida=0.0, nao_atendida=0.0), pd.DataFrame(), pd.DataFrame()
    D = distancias_haversine_km(desc['lon'], desc['lat'], desc['lon'], desc['lat'])
    pop = desc['pessoas'].values.astype(float)
    m = len(desc)
    teto = max_equipes if max_equipes is not None else int(math.ceil(pop.sum()/hab_movel)) + m
    prob = pl.LpProblem('moveis', pl.LpMaximize)
    pares = [(i, s) for i in range(m) for s in range(m) if D[i, s] <= raio_rota + 1e-9]
    w = {p: pl.LpVariable(f'w_{p[0]}_{p[1]}', lowBound=0) for p in pares}
    z = {p: pl.LpVariable(f'z_{p[0]}_{p[1]}', cat='Binary') for p in pares}
    k = {s: pl.LpVariable(f'k_{s}', lowBound=0, upBound=teto, cat='Integer') for s in range(m)}
    atend = pl.lpSum(w.values())
    for i in range(m):
        prob += pl.lpSum(w[i, s] for s in range(m) if (i, s) in w) <= float(pop[i])
    for (i, s) in pares:
        prob += w[i, s] <= float(pop[i])*z[i, s]
    for s in range(m):
        prob += pl.lpSum(w[i, s] for i in range(m) if (i, s) in w) <= hab_movel*k[s]
        prob += pl.lpSum(z[i, s] for i in range(m) if (i, s) in z) <= max_paradas*k[s]
    if max_equipes is not None:
        prob += pl.lpSum(k.values()) <= max_equipes
    prob.setObjective(atend)
    prob.solve(_solver())
    alvo = pl.value(atend)
    prob += atend >= alvo - 1e-6
    prob.setObjective(pl.lpSum(k.values()))
    prob.sense = pl.LpMinimize
    prob.solve(_solver())
    if pl.LpStatus[prob.status] != 'Optimal':
        raise RuntimeError('Dimensionamento de equipes moveis sem otimo')
    bases, atrib = [], []
    for s in range(m):
        nk = int(round(k[s].varValue or 0))
        carga = sum((w[i, s].varValue or 0) for i in range(m) if (i, s) in w)
        if nk > 0 and carga > 1e-6:
            rotulo = f'EM{len(bases)+1}'
            visitas = [(i, w[i, s].varValue) for i in range(m) if (i, s) in w and (w[i, s].varValue or 0) > 1e-6]
            bases.append(dict(equipe_movel=rotulo, ponto_base=desc['NM_BAIRRO'][s], lon=desc['lon'][s], lat=desc['lat'][s],
                              equipes=nk, capacidade_hab=nk*hab_movel, pop_atendida=carga, ocupacao_pct=100*carga/(nk*hab_movel),
                              pontos_visitados=len(visitas), acs_necessarios=int(math.ceil(carga/hab_acs))))
            for i, v in visitas:
                atrib.append(dict(equipe_movel=rotulo, ponto=desc['NM_BAIRRO'][i], lon=desc['lon'][i], lat=desc['lat'][i],
                                  pessoas=v, dist_base_km=D[i, s]))
    bases = pd.DataFrame(bases)
    atrib = pd.DataFrame(atrib)
    atendida = float(bases['pop_atendida'].sum()) if len(bases) else 0.0
    ate_ponto = atrib.groupby('ponto')['pessoas'].sum() if len(atrib) else pd.Series(dtype=float)
    desc['pop_atendida_movel'] = desc['NM_BAIRRO'].map(ate_ponto).fillna(0.0)
    desc['pop_nao_atendida'] = desc['pessoas']-desc['pop_atendida_movel']
    res = dict(equipes=int(bases['equipes'].sum()) if len(bases) else 0, bases=int(len(bases)),
               populacao_sem_cobertura=float(pop.sum()), atendida=atendida, nao_atendida=float(pop.sum()-atendida),
               hab_movel=hab_movel, raio_rota_km=raio_rota, max_paradas_por_equipe=max_paradas, max_equipes=max_equipes,
               acs_necessarios=int(bases['acs_necessarios'].sum()) if len(bases) else 0)
    return res, bases, atrib, desc[['i', 'NM_BAIRRO', 'pessoas', 'pop_atendida_movel', 'pop_nao_atendida', 'lon', 'lat']]


def executar(rede, pontos, saida, rotulo, hab_movel=HAB_MOVEL, max_moveis=None):
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    resumo, por_ponto, por_ubs, arcos = cobertura_efetiva(pontos, rede)
    mov, paradas, atrib_mov, desc = equipes_moveis(pontos, por_ponto, hab_movel=hab_movel, max_equipes=max_moveis)
    resumo['equipes_moveis'] = mov
    resumo['cobertura_efetiva_com_moveis_pct'] = 100*(resumo['pop_atendida_efetiva']+mov['atendida'])/resumo['populacao']
    resumo['cobertura_geografica_com_moveis_pct'] = 100*(resumo['pop_com_acesso_geografico']+mov['atendida'])/resumo['populacao']
    # Nota de transparencia sobre o produto de razoes (nao usado)
    resumo['produto_geografica_x_capacidade_pct_NAO_ADOTADO'] = resumo['cobertura_geografica_pct']*min(1, resumo['razao_capacidade_populacao_pct']/100)
    sens = sensibilidade(pontos, rede)
    p = lambda nome: saida/f'{rotulo}_{nome}'
    (p('resumo.json')).write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
    for nome, df in [('por_ponto.csv', por_ponto), ('por_ubs.csv', por_ubs), ('alocacao.csv', arcos), ('sensibilidade.csv', sens),
                     ('moveis_bases.csv', paradas), ('moveis_visitas.csv', atrib_mov), ('moveis_pontos.csv', desc)]:
        if len(df):
            df.to_csv(p(nome), sep=';', index=False, encoding='utf-8-sig')
    return resumo, por_ponto, por_ubs, arcos, mov, paradas, atrib_mov, desc, sens


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plano', type=Path, default=RESULTADOS/'atual/plano')
    ap.add_argument('--demanda', type=Path, default=None)
    ap.add_argument('--saida', type=Path, default=RESULTADOS/'cobertura_efetiva')
    ap.add_argument('--hab-movel', type=float, default=HAB_MOVEL)
    ap.add_argument('--max-moveis', type=int, default=None)
    a = ap.parse_args()
    pontos = pd.read_csv(a.demanda or a.plano/'aps/demanda_cenario.csv', encoding='utf-8-sig')
    for rotulo, rede in [('atual', carregar_rede_atual()), ('plano', carregar_plano(a.plano))]:
        r = executar(rede, pontos, a.saida, rotulo, a.hab_movel, a.max_moveis)[0]
        print(f"{rotulo}: geografica {r['cobertura_geografica_pct']:.2f}% | efetiva {r['cobertura_efetiva_pct']:.2f}% | "
              f"moveis {r['equipes_moveis']['equipes']} eq ({r['equipes_moveis']['atendida']:.0f}/{r['equipes_moveis']['populacao_sem_cobertura']:.0f} hab)")


if __name__ == '__main__':
    main()
