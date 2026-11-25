"""Sensibilidade hospitalar separada. Reutiliza exatamente os dados salvos dos seis cenários."""
import argparse,json,re,os,sys,hashlib
from pathlib import Path
import pandas as pd
from caminhos import RAIZ,MODELOS
os.environ['PATH']=str(RAIZ/'ferramentas/glpk')+os.pathsep+os.environ.get('PATH','')
sys.path.insert(0,str(MODELOS))
from planejar import resolver
from encaminhamentos import dados,validar
from preparar import ler,salvar

def executar(plano,saida):
 saida.mkdir(parents=True,exist_ok=True)
 config=json.loads((plano/'configuracao_especializada.json').read_text(encoding='utf-8'))
 pontos=ler(plano/'aps/demanda_cenario.csv',',')
 for p in pontos:p['pessoas']=float(p['pessoas'])
 demanda={(r['i'],r['tipo'],int(r['nivel'])):float(r['quantidade_anual']) for r in ler(plano/'demanda_especializada_cenario.csv')}
 u=ler(RAIZ/'dados/preparados/estabelecimentos_revisados.csv')
 u=[r for r in u if r['nivel_principal']!='1']+ler(plano/'ubs_ativas_da_aps.csv')
 inteiros=['novo_2','novo_3','esf','max_esf','leitos_sus_internacao','leitos_sus_uti']
 reais=['lat','lon','cap_amb_anual','cap_amb_2','cap_amb_3','cap_leito_dias','amb_capacidade_total','amb_carga_externa',
 'dias_leito_carga_externa','dias_leito_capacidade_observada','dias_leito_capacidade_bruta']
 for r in u:
  for k in inteiros:
   if k in r:r[k]=int(r[k])
  for k in reais:
   if k in r:r[k]=float(r[k])
 cap=pd.read_csv(RAIZ/'dados/preparados/capacidade_hospitalar_leitos.csv',sep=';').iloc[0]
 limite=float(cap.dias_gerais_disponiveis_superior)
 hospital=next(r for r in u if r['cnes']=='2105780');hospital['cap_leito_dias']=limite
 res=[];entradas={}
 for multi in [False,True]:
  for prop in [.25,.5,.75]:
   nome=('multiplo' if multi else 'unico')+f'_via_{int(prop*100)}'
   orig=plano/nome/'fase1.dat';texto=orig.read_text(encoding='utf-8')
   entradas[nome]=hashlib.sha256(orig.read_bytes()).hexdigest()
   texto=texto[:texto.index('param fase :=')]
   # Somente limite de leitos e habilitacao hospitalar passam do extremo inferior ao superior.
   for parametro,valor in [('LEITO',limite),('HOSPITAL',1)]:
    pat=r'(param '+parametro+r' :=\n)(.*?)(\n;)'
    m=re.search(pat,texto,re.S);assert m
    linhas=m.group(2).splitlines();contador=0
    for i,l in enumerate(linhas):
     if l.split()[0]=='f2105780':linhas[i]='f2105780 '+str(valor);contador+=1
    assert contador==1
    texto=texto[:m.start()]+m.group(1)+'\n'.join(linhas)+m.group(3)+texto[m.end():]
   pasta=saida/'execucoes'/nome;pasta.mkdir(parents=True,exist_ok=True)
   _,a=resolver(texto,pasta,1,120)
   rows,b=resolver(texto,pasta,3,120,a['falta']+1e-9)
   _,U,S,T,F,dist,_=dados(pontos,u,demanda,config,multi,prop)
   dist={k:v*config.get('fator_rota',1) for k,v in dist.items()}
   resumo=validar(rows,pontos,demanda,dict(config,multiplo=multi),U,F,dist,prop,pasta)
   h=next(r for r in resumo if r['tipo']=='HOSP')
   capacidade=pd.read_csv(pasta/'capacidades.csv',sep=';');hh=capacidade[capacidade.cnes==2105780].iloc[0]
   total=h['demanda2']+h['demanda3'];at=h['atendido2']+h['atendido3']
   dias=h['demanda2']*config['tmp2']+h['demanda3']*config['tmp3']
   res.append(dict(classificacao='Dois níveis' if multi else 'Única',via_secundaria_pct=prop*100,
    demanda_media=h['demanda2'],alocadas_media=h['atendido2'],percentual_media=100*h['atendido2']/h['demanda2'],
    demanda_alta=h['demanda3'],alocadas_alta=h['atendido3'],percentual_alta=100*h['atendido3']/h['demanda3'],
    demanda_total=total,alocadas_total=at,percentual_total=100*at/total,
    dias_leito_utilizados=hh.dias_leito_usados,dias_leito_limite=limite,dias_leito_demanda=dias,
    capacidade_sobre_dias_demanda_pct=100*limite/dias))
   print(nome,':',round(100*at/total,2),'% das internações alocadas',flush=True)
 salvar(saida/'internacoes_leitos_otimista.csv',res)
 (saida/'metodo.json').write_text(json.dumps(dict(limite_superior_dias_leito=limite,
  hipotese='Extremo favorável de disponibilidade geral sob a carga agregada estimada; não ocupação observada por tipo de leito.',
  alteracoes=['LEITO do hospital','HOSPITAL do hospital=1'],entradas_sha256=entradas,
  conservado='Demanda, capacidade ambulatorial, vinculos moveis/UBS, proporcoes, distancias e classificacoes dos seis cenarios.',
  unidade='Internacoes/ano e dias-leito; contagem alocada não e o mesmo percentual de dias-leito.'),ensure_ascii=False,indent=2),encoding='utf-8')
 return res

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plano',type=Path,default=RAIZ/'resultados/atual/plano');p.add_argument('--saida',type=Path,default=RAIZ/'resultados/atual/leitos_otimista')
 a=p.parse_args();executar(a.plano,a.saida)
