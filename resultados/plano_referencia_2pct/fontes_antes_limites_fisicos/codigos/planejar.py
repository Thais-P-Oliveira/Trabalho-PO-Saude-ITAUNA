"""Entrada principal completa: planejamento original das UBS + rede especializada.

Uso: python planejar.py [opcoes do model.py] [--pareto]
Os arquivos originais sao somente lidos. Resultados ficam em resultados/nova_execucao/.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import shutil
from types import SimpleNamespace
from pathlib import Path

from caminhos import PASTA,CODIGOS,MODELOS,RESULTADOS,DOCUMENTACAO,CACHE,resolver_caminho_plano
sys.path.insert(0,str(MODELOS))
os.environ.setdefault('MPLCONFIGDIR',str(CACHE/'matplotlib'))
from preparar import BASE,preparar,ler,salvar,hashes
from encaminhamentos import dados,tabela,validar

def resolver(txt,pasta,fase,limite,falta_max=1e9):
    entrada=pasta/f'fase{fase}.dat';display=pasta/f'fase{fase}_display.csv';log=pasta/f'fase{fase}.log'
    entrada.write_text(txt+f'param fase := {fase};\nparam falta_max := {falta_max};\nparam equipes_max := 0;\nend;\n',encoding='utf-8')
    # A APS ja esta fixada: o subproblema especializado e linear.
    r=subprocess.run(['glpsol','-m',str(MODELOS/'rede_completa.mod'),'-d',str(entrada),'-y',str(display),'--log',str(log),'--tmlim',str(limite),'--nomip'],capture_output=True)
    texto=log.read_text(encoding='utf-8',errors='replace')
    if r.returncode or 'OPTIMAL LP SOLUTION FOUND' not in texto:
        raise RuntimeError('Subproblema especializado sem otimo confirmado: '+str(log))
    with display.open() as f:rows=list(csv.reader(f,delimiter=';'))
    resumo={r[1]:float(r[2]) for r in rows if r[0]=='RESUMO'}
    return rows,resumo

def auditar_aps(ctx,saida):
    """Confere as regras do original antes de conectar a rede especializada."""
    from aps_base import CUSTO,CUSTO_ESF,HAB_POR_ACS,minimo_nova
    args=ctx['args'];res=ctx['res'];dem=ctx['dem'];sites=ctx['sites']
    arcos=res['arcos'].to_dict('records');ubs=res['ubs'].to_dict('records');tol=.01
    carga={u['id_ubs']:sum(a['pessoas'] for a in arcos if a['id_ubs']==u['id_ubs']) for u in ubs}
    for p in dem.to_dict('records'):
        if abs(sum(a['pessoas'] for a in arcos if int(a['i'])==int(p['i']))-p['pessoas'])>tol:raise ValueError('APS nao conserva demanda')
    for u in ubs:
        if carga[u['id_ubs']]>args.hab_esf*u['n_esf']+tol:raise ValueError('Capacidade eSF excedida')
        if carga[u['id_ubs']]>HAB_POR_ACS*u['acs']+tol:raise ValueError('Capacidade ACS excedida')
        if not 1<=u['n_esf']<=args.esf_max:raise ValueError('Equipes fora do limite')
        if u['status']=='NOVA':
            s=sites.iloc[int(u['idx'])]
            if u['pop_coberta_raio']+tol<minimo_nova(s,dem,args):raise ValueError('Nova UBS sem populacao minima da zona')
            ponto=dem.loc[dem['i']==int(s['ponto'])].iloc[0]
            if ponto['dist_ubs_existente_km']<=args.dist_min_cand:raise ValueError('Candidata nao respeita distancia minima')
    if args.max_novas is not None and sum(u['status']=='NOVA' for u in ubs)>args.max_novas:raise ValueError('Limite de novas UBS excedido')
    if sum(u['status']=='EXISTENTE' for u in ubs)!=sum(sites['existente']):raise ValueError('UBS existente removida')
    cobertura=sum(a['pessoas'] for a in arcos if a['coberto'])
    if abs(cobertura-res['cobertura'])>tol:raise ValueError('Cobertura inconsistente')
    if args.cobertura_min is not None and cobertura+tol<args.cobertura_min*res['total']:raise ValueError('Meta de cobertura nao atingida')
    custo=sum(CUSTO['ubs_nova'] if u['status']=='NOVA' else CUSTO['ubs_existente'] for u in ubs)
    custo+=sum(CUSTO_ESF*u['n_esf']+CUSTO['acs']*u['acs'] for u in ubs)
    custo+=args.custo_km*sum(a['dist_km']*a['pessoas'] for a in arcos)
    if abs(custo-res['custos']['objetivo'])>tol:raise ValueError('Custos nao conferem')
    checks=['conservacao_populacao','capacidade_esf','capacidade_acs','limites_equipes','novas_ubs_e_viabilidade','distancia_candidatas','existentes_mantidas','cobertura','custos']
    salvar(saida/'auditoria_aps.csv',[dict(regra=k,resultado='PASSOU') for k in checks])

def conectar(ctx,pontos,unidades,demanda,config,saida,limite):
    args=ctx['args'];res=ctx['res'];dem=ctx['dem']
    reais={str(r['j']):r for r in ler(Path(args.ubs),',')}
    por_id={};primarias=[]
    for r in res['ubs'].to_dict('records'):
        uid=r['id_ubs'];cnes=reais[uid[3:]]['cnes'] if uid.startswith('UBS') else uid
        por_id[uid]=cnes
        primarias.append(dict(cnes=cnes,id_aps=uid,nome=r['nome'],nivel_principal='1',novo_2=0,novo_3=0,lat=r['lat'],lon=r['lon'],esf=int(r['n_esf']),max_esf=args.esf_max,cap_amb_anual=0,cap_leito_dias=0,status_aps=r['status'],acs=int(r['acs'])))
    novas_unidades=[u for u in unidades if u['nivel_principal']!='1']+primarias
    vinculos={}
    pop={str(int(r.i)):float(r.pessoas) for r in dem.itertuples()}
    if set(pop)!={p['i'] for p in pontos}:raise ValueError('A integracao etaria requer os mesmos91 IDs de demanda; novas regioes precisam de novos dados especializados')
    for r in res['arcos'].to_dict('records'):
        i=str(int(r['i']));u=por_id[r['id_ubs']]
        vinculos[i,u]=vinculos.get((i,u),0)+float(r['pessoas'])/pop[i]
    for i in pop:
        if not math.isclose(sum(v for (a,u),v in vinculos.items() if a==i),1,abs_tol=1e-6):raise ValueError('Alocacao APS incompleta '+i)
    # Crescimento por ponto preserva o perfil etario e a taxa de utilizacao de referencia.
    # A oferta historica especializada nao cresce automaticamente com a populacao.
    base_pop={p['i']:float(p['pessoas']) for p in pontos}
    projetada={(i,k,n):v*pop[i]/base_pop[i] for (i,k,n),v in demanda.items()}
    pontos=[dict(p,pessoas=pop[p['i']]) for p in pontos]
    config=dict(config,hab_por_esf=args.hab_esf,fator_rota=args.fator_rota)
    salvar(saida/'demanda_especializada_cenario.csv',[dict(i=i,tipo=k,nivel=n,quantidade_anual=v,crescimento_populacional=pop[i]/base_pop[i]-1,hipotese='taxa etaria mantida; crescimento proporcional da demanda, sem crescer capacidade') for (i,k,n),v in projetada.items()])
    salvar(saida/'ubs_ativas_da_aps.csv',primarias)
    comparacao=[]
    for multi in [False,True]:
        nome='multiplo' if multi else 'unico'
        for r in config['proporcoes_via_secundaria']:
            pasta=saida/f'{nome}_via_{int(r*100)}';pasta.mkdir(exist_ok=True)
            txt,U,S,T,F,dist,_=dados(pontos,novas_unidades,projetada,config,multi,r)
            # O fator de rota do original vale tambem para os trechos especializados.
            if args.fator_rota!=1:
                # Substitui as quatro matrizes, sem alterar demandas/capacidades.
                for matriz in ['DU','US','UT','ST']:
                    inicio=txt.index('param '+matriz+' :=');fim=txt.index('\n;\n',inicio)+3
                    linhas=[(i,j,v*args.fator_rota) for (m,i,j),v in dist.items() if m==matriz]
                    txt=txt[:inicio]+tabela(matriz,linhas)+txt[fim:]
                dist={k:v*args.fator_rota for k,v in dist.items()}
            txt+=f'param HAB := {args.hab_esf};\n'
            txt+=tabela('VINC',[('p'+p['i'],'u'+u['cnes'],vinculos.get((p['i'],u['cnes']),0)) for p in pontos for u in U])
            _,a=resolver(txt,pasta,1,limite)
            rows,b=resolver(txt,pasta,3,limite,a['falta']+1e-9)
            resumo=validar(rows,pontos,projetada,config,U,F,dist,r,pasta)
            # O quadro de equipes vem da APS, nao de uma nova contratacao na hierarquia.
            salvar(pasta/'ubs.csv',[dict(id_local=u['cnes'],cnes_real=u['cnes'] if not u['cnes'].startswith('NOVA_') else '',nome=u['nome'],status=u['status_aps'],esf_planejadas_na_aps=u['esf'],acs_planejados_na_aps=u['acs'],capacidade=args.hab_esf*u['esf'],populacao_alocada=sum(pop[i]*z for (i,c),z in vinculos.items() if c==u['cnes'])) for u in U])
            for rr in resumo:comparacao.append(dict(cenario=nome,via_percentual=int(r*100),novas_ubs=sum(u['status_aps']=='NOVA' for u in U),esf_planejadas=sum(u['esf'] for u in U),acs_planejados=sum(u['acs'] for u in U),cobertura_aps=res['cobertura']/res['total'],custo_mensal_aps=res['custos']['objetivo'],**rr))
            print('Plano completo:',nome,int(r*100),'validado.',flush=True)
    salvar(saida/'comparacao_completa.csv',comparacao)
    return comparacao

def salvar_plano(ctx,saida):
    """Registra o plano APS auditado para reutilizar sem otimizar novamente."""
    r=ctx['res'];pasta=saida/'aps'
    nomes=['alocacao_completa.csv','ubs_completas.csv','demanda_cenario.csv']
    dados=dict(status='plano_aps_validado',parametros=vars(ctx['args']),
        total=r['total'],cobertura=r['cobertura'],custos=r['custos'],
        certificados=r.get('certificados',[]),
        otimalidade_confirmada=all(x.get('sol_status')=='Optimal Solution Found' for x in r.get('certificados',[])) and bool(r.get('certificados')),
        nota='Validacao de viabilidade nao significa prova de otimo; consultar certificados de cada fase.',
        arquivos={nome:hashlib.sha256((pasta/nome).read_bytes()).hexdigest() for nome in nomes})
    (saida/'plano_aps.json').write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf-8')


def carregar_plano(origem,saida):
    """Carrega locais, equipes e vinculacoes do plano, conferindo os arquivos."""
    import pandas as pd
    import aps_base
    origem=origem.resolve()
    meta=json.loads((origem/'plano_aps.json').read_text(encoding='utf-8'))
    if meta['status']!='plano_aps_validado':raise ValueError('Plano APS nao validado')
    for nome,h in meta['arquivos'].items():
        if hashlib.sha256((origem/'aps'/nome).read_bytes()).hexdigest()!=h:
            raise ValueError('Plano APS alterado: '+nome)
    args=SimpleNamespace(**meta['parametros'])
    args.demanda=resolver_caminho_plano(args.demanda)
    args.ubs=resolver_caminho_plano(args.ubs)
    if args.growth_file:args.growth_file=resolver_caminho_plano(args.growth_file)
    dem,_,sites,_=aps_base.carregar_dados(args)
    dem_salva=pd.read_csv(origem/'aps/demanda_cenario.csv')
    if list(dem['i'])!=list(dem_salva['i']) or not all(math.isclose(a,b,abs_tol=1e-6) for a,b in zip(dem['pessoas'],dem_salva['pessoas'])):
        raise ValueError('Demanda original diverge do plano salvo')
    if (origem/'aps').resolve()!=(saida/'aps').resolve():
        shutil.copytree(origem/'aps',saida/'aps',dirs_exist_ok=True)
    args.saida=str(saida/'aps')
    r=dict(ubs=pd.read_csv(saida/'aps/ubs_completas.csv'),arcos=pd.read_csv(saida/'aps/alocacao_completa.csv'),
        total=meta['total'],cobertura=meta['cobertura'],custos=meta['custos'],certificados=meta.get('certificados',[]))
    return dict(args=args,dem=dem,sites=sites,res=r)


def main():
    ap=argparse.ArgumentParser(description=__doc__,add_help=False)
    ap.add_argument('--saida',type=Path,default=RESULTADOS/'nova_execucao')
    ap.add_argument('--limite-hierarquia',type=int,default=120)
    ap.add_argument('--plano-aps',type=Path,help='pasta de uma execucao com plano_aps.json; reutiliza plano sem reotimizar UBS')
    a,opcoes_aps=ap.parse_known_args()
    if '--help' in opcoes_aps or '-h' in opcoes_aps:
        print('Plano completo: APS original + seis cenarios especializados.\nOpcoes adicionais: --saida PASTA; --limite-hierarquia SEGUNDOS; --plano-aps PASTA.\nA seguir, opcoes preservadas do model.py:')
        import aps_base
        antes=sys.argv[:]
        try:sys.argv=['aps_base.py','--help'];aps_base.main()
        finally:sys.argv=antes
        return
    saida=a.saida.resolve();saida.mkdir(parents=True,exist_ok=True)
    estado=saida/'status.json';estado.write_text(json.dumps(dict(status='em_execucao')),encoding='utf-8')
    pontos,unidades,demanda,config=preparar()
    import aps_base
    if a.plano_aps:
        if opcoes_aps:raise ValueError('Ao reutilizar plano APS, nao passe novas opcoes da APS; os parametros do plano ficam fixos')
        ctx=carregar_plano(a.plano_aps,saida)
        print('Plano APS reutilizado: locais, equipes, ACS e vinculacoes fixos.',flush=True)
    else:
        argumentos_anteriores=sys.argv[:]
        try:
            sys.argv=['aps_base.py','--demanda',str(BASE/'pontos_demanda_itauna.csv'),'--ubs',str(BASE/'unidades_existentes_itauna.csv'),'--saida',str(saida/'aps')]+opcoes_aps
            ctx=aps_base.main()
        finally:sys.argv=argumentos_anteriores
    auditar_aps(ctx,saida)
    # Gera o diagnostico do plano real, tanto no calculo novo quanto no reuso.
    from diagnosticar import gerar_diagnostico
    existentes=[r for r in ler(BASE/'unidades_existentes_itauna.csv',',') if r['nivel_sugerido']=='PHC']
    gerar_diagnostico(ctx['dem'].to_dict('records'), existentes,
        ctx['res']['ubs'].to_dict('records'), saida/'aps/diagnostico',
        raio=ctx['args'].raio, fator_rota=ctx['args'].fator_rota,
        hab_esf=ctx['args'].hab_esf, folga_custo=ctx['args'].folga_custo)
    salvar_plano(ctx,saida)
    resultados=conectar(ctx,pontos,unidades,demanda,config,saida,a.limite_hierarquia)
    if hashes()!=json.loads((DOCUMENTACAO/'originais_sha256.json').read_text()):raise ValueError('Original alterado')
    arquivos=[MODELOS/'aps_base.py',CODIGOS/'planejar.py',MODELOS/'rede_completa.mod',CODIGOS/'preparar.py']
    estado.write_text(json.dumps(dict(status='plano_completo_validado',originais_preservados=True,cenarios=6,etapas=['APS: cobertura, custo e distancia conforme original','hierarquia: menor falta e deslocamento no plano APS fixado'],otimizacao_conjunta=False,plano_aps_fixo=True,otimalidade_aps_confirmada=all(x.get('sol_status')=='Optimal Solution Found' for x in ctx['res'].get('certificados',[])) and bool(ctx['res'].get('certificados')),origem_plano=str(a.plano_aps.resolve()) if a.plano_aps else 'lexicografia_desta_execucao',certificados_solver_aps=ctx['res'].get('certificados',[]),parametros_aps=vars(ctx['args']),sha256={str(p.relative_to(PASTA)):hashlib.sha256(p.read_bytes()).hexdigest() for p in arquivos}),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Concluido:',saida/'comparacao_completa.csv')

def iniciar():
    try:main()
    except Exception as e:
        # Mantem o erro visivel; arquivos de uma tentativa parcial nao sao resultado final.
        ap=argparse.ArgumentParser(add_help=False);ap.add_argument('--saida',type=Path,default=RESULTADOS/'nova_execucao');a,_=ap.parse_known_args()
        a.saida.mkdir(parents=True,exist_ok=True)
        (a.saida/'status.json').write_text(json.dumps(dict(status='falhou_nao_usar_comparacao_anterior',erro=str(e)),ensure_ascii=False,indent=2),encoding='utf-8')
        raise

if __name__=='__main__':iniciar()
