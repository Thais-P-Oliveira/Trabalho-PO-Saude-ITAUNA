"""Compara cenarios de raio, crescimento, minimo rural e folga de custo."""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'modelos'))
SAIDA = RAIZ / 'resultados' / 'atual' / 'sensibilidade'
REFERENCIA = RAIZ / 'resultados' / 'atual' / 'plano' / 'plano_aps.json'

# (nome, grupo, alteracoes nos parametros, cobertura minima ou None = lexicografico)
# A curva usa folga 0 para que o custo reportado seja o da fase de custo.
CENARIOS = (
    [(f'curva_{int(round(c * 1000)):04d}', 'curva', dict(folga_custo=0.0), c)
     for c in (0.934, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995)]
    + [('curva_max', 'curva', dict(folga_custo=0.0), None),
       ('raio_2km', 'raio', dict(raio=2.0), None),
       ('raio_5km', 'raio', dict(raio=5.0), None),
       ('folga_5pct', 'folga', dict(folga_custo=0.05), None),
       ('rural_min_0', 'minimo_rural', dict(hab_min_nova_rural=0.0), None),
       ('rural_min_1000', 'minimo_rural', dict(hab_min_nova_rural=1000.0), None),
       ('crescimento_5pct', 'crescimento', dict(growth=5.0), None),
       ('crescimento_10pct', 'crescimento', dict(growth=10.0), None)]
    + [(f'rural{minimo}_{nome}', 'rural_raio',
        dict(hab_min_nova_rural=float(minimo), raio=urbano, raio_rural=rural), None)
       for minimo in (500,)
       for nome,urbano,rural in [('3km_todos',3.0,3.0),
                                ('3km_urbano_5km_rural',3.0,5.0),
                                ('5km_todos',5.0,5.0)]])


def parametros_referencia(referencia=REFERENCIA):
    from caminhos import resolver_caminho_plano
    p = json.loads(Path(referencia).read_text(encoding='utf-8'))['parametros']
    for chave in ['demanda','ubs','growth_file','limites_equipes']:
        if p.get(chave):p[chave]=resolver_caminho_plano(p[chave])
    # A referencia fornece custos/portes; a base da nova analise usa rural 500 e raio 3.
    from projecao_populacional import crescimento_aps
    p.update(pareto=False, quiet=True, hab_min_nova_rural=500.0, raio=3.0, raio_rural=None, growth=crescimento_aps(), growth_file=None)
    return p


def ajustar_crescimento(p,alteracoes):
    novo=dict(alteracoes)
    if 'growth' in novo:
        novo['growth']=100*((1+p['growth']/100)*(1+novo['growth']/100)-1)
    return novo


def chave_cache(alteracoes,cob_min,time_limit,referencia):
    p=parametros_referencia(referencia)
    p.update(ajustar_crescimento(p,alteracoes),time_limit=time_limit,cobertura_min=cob_min)
    fontes=[RAIZ/'modelos/aps_base.py',Path(referencia),Path(p['demanda']),Path(p['ubs']),
            RAIZ/'dados/fontes/custos_construcao_ubs_2025.csv',
            RAIZ/'codigos/rodar_sensibilidade.py',RAIZ/'codigos/projecao_populacional.py',
            RAIZ/'dados/fontes/fontes_publicas/populacao_ibge/projecao.json']
    fontes += [RAIZ/'codigos/pessoal_cnes.py',RAIZ/'dados/fontes/fontes_publicas/ubs_recursos_cnes_202607.csv',RAIZ/'codigos/integracao_resultados.py',RAIZ/'codigos/cobertura_efetiva.py']
    if p.get('limites_equipes'):fontes.append(Path(p['limites_equipes']))
    material=dict(parametros=p,arquivos={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in fontes})
    return hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()


def executar(nome, grupo, alteracoes, cob_min, time_limit, referencia=REFERENCIA, saida=SAIDA):
    saida=Path(saida)
    os.chdir(RAIZ)
    os.environ.setdefault('MPLCONFIGDIR', str(saida / '.mpl'))
    import aps_base
    p = parametros_referencia(referencia)
    p.update(ajustar_crescimento(p,alteracoes), time_limit=time_limit, cobertura_min=cob_min)
    args = SimpleNamespace(**p)
    inicio = time.time()
    dem, _, sites, D = aps_base.carregar_dados(args)
    solver, _ = aps_base.escolher_solver(args.solver, args.time_limit, args.gap, False)
    res = aps_base.otimizar(dem, sites, D, args, solver, cob_min=cob_min, log=lambda *_: None)
    linha = dict(nome=nome, grupo=grupo, alteracoes=json.dumps(alteracoes), cobertura_min=cob_min,
                 cache_id=chave_cache(alteracoes,cob_min,time_limit,referencia),
                 raio_urbano_km=args.raio,raio_rural_km=args.raio_rural or args.raio,
                 minimo_abertura_rural=args.hab_min_nova_rural,
                 status=res['status'], segundos=round(time.time() - inicio, 1))
    if res['status'] == 'Optimal':
        ubs, arcos, c = res['ubs'], res['arcos'], res['custos']
        from integracao_resultados import calcular_rede, custo_movel
        rede=pd.DataFrame(dict(id=ubs.id_ubs,nome=ubs.nome,lat=ubs.lat,lon=ubs.lon,
                               esf=ubs.n_esf,acs=ubs.acs,status=ubs.status))
        cobertura_integrada=calcular_rede(dem,rede,vars(args))[0]
        mov=custo_movel(cobertura_integrada,aps_base.CUSTO_ESF,aps_base.CUSTO['acs'])
        novas = ubs[ubs['status'] == 'NOVA']
        custo_novas = (c['fixo_novas'] + aps_base.CUSTO_ESF * novas['n_esf'].sum()
                       + aps_base.CUSTO['acs'] * novas['acs'].sum())
        pop_novas = float(novas['pop_atendida'].sum())
        # Cobertura so com as UBS existentes, no mesmo raio do cenario.
        exist = [j for j in range(D.shape[1]) if sites.at[j, 'existente']]
        raios=aps_base.raios_por_ponto(dem,args)
        base = float(sum(dem['pessoas'].values[i] for i in range(D.shape[0])
                         if (D[i, exist] <= raios[i] + 1e-9).any()))
        with (RAIZ/'dados/fontes/custos_construcao_ubs_2025.csv').open(encoding='utf-8-sig') as f:
            precos={int(r['esf']):float(r['valor_construcao']) for r in csv.DictReader(f)}
        linha.update(
            populacao=res['total'], cobertura=res['cobertura'] / res['total'],
            cobertura_base_existentes=base / res['total'],
            novas_ubs=int(len(novas)),
            novas_rurais=int(novas['nome'].astype(str).str.contains('(rural)', case=False, regex=False).sum()),
            esf=int(ubs['n_esf'].sum()), acs=int(ubs['acs'].sum()),
            custo_operacional_ubs_mensal=c['operacional'], custo_moveis_mensal=mov['total_mensal'],
            equipes_moveis=mov['equipes'], acs_moveis=mov['acs'],
            cobertura_efetiva=cobertura_integrada['cobertura_efetiva_pct']/100,
            cobertura_com_moveis=cobertura_integrada['cobertura_efetiva_com_moveis_pct']/100,
            custo_operacional_mensal=c['operacional']+mov['total_mensal'], custo_objetivo_mensal=c['objetivo'],
            custo_mensal_novas=float(custo_novas), populacao_novas=pop_novas,
            custo_novas_por_hab_mes=float(custo_novas / pop_novas) if pop_novas else 0.0,
            construcao_estimativa_por_porte=sum(precos[int(n)] for n in novas['n_esf']),
            populacao_fora_raio=res['total']-res['cobertura'],
            cobertura_3km_comum=float(arcos.loc[arcos.dist_km<=3+1e-9,'pessoas'].sum()/res['total']),
            cobertura_5km_comum=float(arcos.loc[arcos.dist_km<=5+1e-9,'pessoas'].sum()/res['total']),
            distancia_media_km=float((arcos['pessoas'] * arcos['dist_km']).sum() / res['total']),
            ubs_lotadas=int(sum(r.pop_atendida >= 0.95 * args.hab_esf * r.n_esf for r in ubs.itertuples())),
            certificados=json.dumps(res['certificados']),
            custo_otimo_comprovado=all(x['sol_status'] == 'Optimal Solution Found' for x in res['certificados']))
        ids_rurais=set(dem.loc[dem.NM_BAIRRO.astype(str).str.contains('(rural)',case=False,regex=False),'i'])
        for zona,ids in [('rural',ids_rurais),('urbana',set(dem.i)-ids_rurais)]:
            fluxos=arcos.loc[arcos.i.isin(ids)]
            populacao=float(dem.loc[dem.i.isin(ids),'pessoas'].sum())
            linha['cobertura_'+zona]=float(fluxos.loc[fluxos.coberto,'pessoas'].sum()/populacao) if populacao else None
            linha['distancia_media_'+zona+'_km']=float((fluxos.pessoas*fluxos.dist_km).sum()/populacao) if populacao else None
    destino = saida / 'execucoes' / f'{nome}.json'
    destino.parent.mkdir(parents=True,exist_ok=True)
    destino.write_text(json.dumps(linha, ensure_ascii=False, indent=2), encoding='utf-8')
    return linha


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--processos', type=int, default=3)
    ap.add_argument('--time-limit', type=float, default=300)
    ap.add_argument('--referencia',type=Path,default=REFERENCIA)
    ap.add_argument('--saida',type=Path,default=SAIDA)
    ap.add_argument('--somente-rural-raios',action='store_true',help='compara apenas 3/3, 3/5 e 5/5 km, todos com minimo rural 500')
    a = ap.parse_args()
    saida=a.saida.resolve();referencia=a.referencia.resolve()
    (saida / 'execucoes').mkdir(parents=True, exist_ok=True)
    cenarios=[c for c in CENARIOS if c[1]=='rural_raio'] if a.somente_rural_raios else CENARIOS
    def atual(c):
        arquivo=saida/'execucoes'/f'{c[0]}.json'
        return arquivo.exists() and json.loads(arquivo.read_text(encoding='utf-8')).get('cache_id')==chave_cache(c[2],c[3],a.time_limit,referencia)
    pendentes = [c for c in cenarios if not atual(c)]
    (saida/'configuracao_analise.json').write_text(json.dumps(dict(referencia=str(referencia),parametros_base=parametros_referencia(referencia),cenarios=cenarios),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(cenarios) - len(pendentes)} execucoes reaproveitadas; {len(pendentes)} a calcular.', flush=True)
    with ProcessPoolExecutor(max_workers=a.processos) as ex:
        futuros = {ex.submit(executar, *c, a.time_limit, referencia, saida): c[0] for c in pendentes}
        for f in as_completed(futuros):
            try:
                r = f.result()
                print(f"{r['nome']}: {r['status']} em {r['segundos']} s", flush=True)
            except Exception as e:
                print(f'{futuros[f]}: ERRO {e}', flush=True)
    import pandas as pd
    linhas = [json.loads((saida / 'execucoes' / f'{c[0]}.json').read_text(encoding='utf-8'))
              for c in cenarios if atual(c)]
    pd.DataFrame(linhas).to_csv(saida / 'resumo.csv', sep=';', index=False, encoding='utf-8-sig')
    print('Resumo:', saida / 'resumo.csv')


if __name__ == '__main__':
    main()
