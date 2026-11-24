"""Audita o plano completo salvo, sem resolver novamente a APS ou a hierarquia."""
import argparse
import csv
import json
import math
from types import SimpleNamespace
from planejar import PASTA,auditar_aps
from caminhos import DOCUMENTACAO,RESULTADOS,resolver_caminho_plano
from preparar import preparar,ler,salvar,hashes
from encaminhamentos import dados,validar
import aps_base
import pandas as pd
from projecao_populacional import projetar_demanda

def auditar(saida):
    estado=json.loads((saida/'status.json').read_text(encoding='utf-8'))
    if estado['status']!='plano_completo_validado':raise ValueError('Execucao incompleta')
    args=SimpleNamespace(**estado['parametros_aps'])
    args.demanda=resolver_caminho_plano(args.demanda)
    args.ubs=resolver_caminho_plano(args.ubs)
    if args.growth_file:args.growth_file=resolver_caminho_plano(args.growth_file)
    if getattr(args,'limites_equipes',None):args.limites_equipes=resolver_caminho_plano(args.limites_equipes)
    dem,_,sites,_=aps_base.carregar_dados(args)
    arcos=pd.read_csv(saida/'aps/alocacao_completa.csv')
    ubs=pd.read_csv(saida/'aps/ubs_completas.csv')
    comparacao=ler(saida/'comparacao_completa.csv');base=comparacao[0]
    ctx=dict(args=args,dem=dem,sites=sites,res=dict(ubs=ubs,arcos=arcos,total=float(dem['pessoas'].sum()),cobertura=float(base['cobertura_aps'])*float(dem['pessoas'].sum()),custos=dict(objetivo=float(base['custo_mensal_aps']))))
    plano_financeiro=json.loads((saida/'plano_aps.json').read_text(encoding='utf-8'))
    ctx['res']['custos']=plano_financeiro['custos']
    auditar_aps(ctx,saida)
    pontos,unidades,demanda,config=preparar()
    pop={str(int(r.i)):float(r.pessoas) for r in dem.itertuples()}
    base_pop={p['i']:float(p['pessoas']) for p in pontos}
    demanda=projetar_demanda(pontos,pop,demanda)
    pontos=[dict(p,pessoas=pop[p['i']]) for p in pontos]
    U=ler(saida/'ubs_ativas_da_aps.csv')
    for u in U:
        for k in ['esf','max_esf','novo_2','novo_3','acs']:u[k]=int(u[k])
        for k in ['lat','lon','cap_amb_anual','cap_leito_dias']:u[k]=float(u[k])
    unidades=[u for u in unidades if u['nivel_principal']!='1']+U
    ids={u['id_aps']:u['cnes'] for u in U};vinc={}
    for r in arcos.to_dict('records'):
        i=str(int(r['i']));c=ids[r['id_ubs']];vinc[i,c]=vinc.get((i,c),0)+float(r['pessoas'])/pop[i]
    config=dict(config,hab_por_esf=args.hab_esf)
    checks=[]
    for multi in [False,True]:
        for r in config['proporcoes_via_secundaria']:
            nome=('multiplo' if multi else 'unico')+f'_via_{int(r*100)}';pasta=saida/nome
            _,U,S,T,F,dist,_=dados(pontos,unidades,demanda,config,multi,r)
            dist={k:v*args.fator_rota for k,v in dist.items()}
            for fase in [1,3]:
                if 'OPTIMAL LP SOLUTION FOUND' not in (pasta/f'fase{fase}.log').read_text(encoding='utf-8',errors='replace'):raise ValueError('LP sem otimo')
            with (pasta/'fase3_display.csv').open() as f:rows=list(csv.reader(f,delimiter=';'))
            for row in rows:
                if row[0]=='X' and not math.isclose(float(row[3]),vinc.get((row[1][1:],row[2][1:]),0),abs_tol=1e-7):raise ValueError('Vinculo APS alterado na hierarquia')
            antes_ubs=ler(pasta/'ubs.csv')
            validar(rows,pontos,demanda,config,U,F,dist,r,pasta)
            salvar(pasta/'ubs.csv',antes_ubs)
            checks.append(dict(cenario=nome,plano_aps_preservado='PASSOU',demanda_e_capacidades='PASSOU',otimos_subproblemas='PASSOU'))
    if hashes()!=json.loads((DOCUMENTACAO/'originais_sha256.json').read_text()):raise ValueError('Original alterado')
    for n in ['relatorio_itauna.txt','resultado_itauna.xlsx','mapa_interativo.html','mapa_itauna_ubs.png','mapa_itauna_zoom_urbano.png','painel_resultados.png']:
        if not (saida/'aps'/n).exists():raise ValueError('Saida original nao gerada '+n)
    if args.pareto and not (saida/'aps/pareto_cobertura_custo.png').exists():raise ValueError('Pareto nao gerado')
    salvar(saida/'auditoria_integracao.csv',checks)
    estado.update(auditoria_integracao='PASSOU',originais_preservados=True)
    (saida/'status.json').write_text(json.dumps(estado,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASSOU: regras APS, vinculacao fixa, seis cenarios, capacidades, exportacoes e originais.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--saida',type=__import__('pathlib').Path,default=RESULTADOS/'plano_referencia_2pct');a=p.parse_args();auditar(a.saida.resolve())
