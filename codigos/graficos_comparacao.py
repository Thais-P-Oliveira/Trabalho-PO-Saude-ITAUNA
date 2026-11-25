"""Compara a pressao nas UBS existentes e identifica o porte das novas."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from caminhos import RAIZ

BASE=RAIZ/'resultados/atual/graficos_demanda'
OUT=RAIZ/'imagens/comparacao'
W=16/2.54
AZUL,CINZA,TEXTO='#16789a','#9ba7b0','#253443'
def br(v,n=0):return f'{v:,.{n}f}'.replace(',','X').replace('.',',').replace('X','.')
def gravar(fig,nome):
 fig.savefig(OUT/f'{nome}.pdf');fig.savefig(OUT/f'{nome}.png',dpi=300);plt.close(fig)

def existentes(t,somente_mudancas=False):
 t=t[t.status=='EXISTENTE'].copy();t['mudanca']=t.utilizacao_plano-t.utilizacao_atual
 mask=t.mudanca.abs()>.05
 t=pd.concat([t[mask].sort_values('mudanca'),t[~mask].sort_values('utilizacao_atual',ascending=False)])
 m=int(mask.sum())
 total_unidades=len(t)
 if somente_mudancas:t=t.iloc[:m].copy()
 t['grupo']=np.where(t.mudanca.abs()>.05,'Mudou','Sem mudança')
 nome_arquivo='mudancas_ubs_existentes' if somente_mudancas else 'ubs_existentes_comparacao'
 t.to_csv(OUT/(nome_arquivo+'.csv'),sep=';',index=False,encoding='utf-8-sig')
 fig,ax=plt.subplots(figsize=(W,3.5 if somente_mudancas else 7.1));fig.subplots_adjust(left=.42,right=.94,top=.85 if somente_mudancas else .94,bottom=.26 if somente_mudancas else .11)
 ax.axvspan(0,100,color='#f0f6f4',zorder=0);ax.axvline(100,color='#b86144',ls='--',lw=1)
 for i,r in enumerate(t.itertuples()):
  yi=i+(.8 if i>=m else 0)
  if abs(r.mudanca)>.05:
   ax.plot([r.utilizacao_plano,r.utilizacao_atual],[yi,yi],color=AZUL,lw=2.5,zorder=2)
   ax.scatter(r.utilizacao_atual,yi,s=45,facecolor='white',edgecolor=CINZA,lw=1.5,zorder=4)
   ax.scatter(r.utilizacao_plano,yi,s=34,color=AZUL,zorder=5)
   if abs(r.mudanca)<20:
    ax.text(max(r.utilizacao_atual,r.utilizacao_plano)+10,yi,br(r.utilizacao_atual)+' → '+br(r.utilizacao_plano)+'%',fontsize=9,va='center',color=AZUL)
   else:
    ax.text(r.utilizacao_atual+6,yi,br(r.utilizacao_atual)+'%',fontsize=9,va='center',color='#64727b')
    ax.text(r.utilizacao_plano-6,yi,br(r.utilizacao_plano)+'%',fontsize=9,va='center',ha='right',color=AZUL,fontweight='bold')
  else:
   ax.scatter(r.utilizacao_plano,yi,s=25,color='#7e8c96',zorder=4)
   ax.text(r.utilizacao_plano+6,yi,br(r.utilizacao_plano)+'%',fontsize=9,va='center',color='#7e8c96')
 nomes=[]
 for r in t.itertuples():
  s=r.unidade.replace('UBS Parque Jardim Santanense / Residencial Santanense','Parque Jd. Santanense')
  if s.startswith('UBS '):s=s[4:]
  nomes.append(s+(' [2 eSF]' if r.esf_plano==2 else ''))
 pos=np.arange(len(t))+np.where(np.arange(len(t))>=m,.8,0)
 ax.set_yticks(pos,nomes,fontsize=9);ax.set_ylim(len(t)+.45,-1.2)
 ax.set_xlim(0,335);ax.set_xticks([0,100,200,300]);ax.tick_params(axis='x',labelsize=9)
 ax.set_xlabel('Demanda potencial / capacidade (%)',fontsize=9)
 if not somente_mudancas:
  ax.axhline(m-.45,color='#d4dce0',lw=1)
 ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0,pad=8)
 ax.legend(handles=[Line2D([],[],marker='o',ls='',mfc='white',mec=CINZA,ms=6,label='Rede atual'),Line2D([],[],marker='o',ls='',color=AZUL,ms=6,label='Plano proposto')],loc='lower left',bbox_to_anchor=(-.78,1.025),frameon=False,ncol=2,fontsize=10)
 gravar(fig,nome_arquivo)
 return m

def existentes_colunas(t):
 t=t[t.status=='EXISTENTE'].copy()
 t['reducao_pp']=t.utilizacao_atual-t.utilizacao_plano
 t=t[t.reducao_pp>.05].sort_values('reducao_pp',ascending=False)
 t.to_csv(OUT/'mudancas_ubs_existentes_colunas.csv',sep=';',index=False,encoding='utf-8-sig')
 fig,ax=plt.subplots(figsize=(W,4.5));fig.subplots_adjust(left=.12,right=.98,top=.87,bottom=.19)
 x=np.arange(len(t));largura=.38
 ax.bar(x-largura/2,t.utilizacao_atual,width=largura,color='#aab6bf',label='Rede atual')
 ax.bar(x+largura/2,t.utilizacao_plano,width=largura,color=AZUL,label='Plano proposto')
 for i,r in enumerate(t.itertuples()):
  # Mesma altura por par, centralizado na coluna; unidade percentual no eixo.
  altura=max(r.utilizacao_atual,r.utilizacao_plano)+8
  ax.text(i-largura/2,altura,br(r.utilizacao_atual),ha='center',va='bottom',fontsize=8.5,color='#667681')
  ax.text(i+largura/2,altura,br(r.utilizacao_plano),ha='center',va='bottom',fontsize=8.5,color=AZUL)
 nomes={'UBS SANTANENSE':'Santanense','UBS MORRO DO ENGENHO':'Morro do\nEngenho',
        'UBS CIDADE NOVA':'Cidade\nNova','UBS VARZEA DA OLARIA':'Várzea da\nOlaria',
        'UBS JADIR MARINHO':'Jadir\nMarinho'}
 labels=[]
 for r in t.itertuples():
  n=r.unidade
  if 'Parque' in n:n='Parque Jd.\nSantanense'
  else:
   n=n.replace('UBS ','')
   n={'Morro do Engenho':'Morro do\nEngenho','Cidade Nova':'Cidade\nNova',
      'Várzea da Olaria':'Várzea da\nOlaria','Jadir Marinho':'Jadir\nMarinho'}.get(n,n)
  labels.append(n)
 ax.set_xticks(x,labels,fontsize=9)
 ax.set_ylabel('Demanda potencial / capacidade (%)',fontsize=9)
 ax.set_ylim(0,335);ax.set_yticks([0,100,200,300]);ax.tick_params(axis='y',labelsize=9)
 ax.axhline(100,color='#b86144',ls='--',lw=1)
 ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 ax.spines[['top','right']].set_visible(False)
 ax.legend(loc='lower left',bbox_to_anchor=(-.05,1.03),ncol=2,frameon=False,fontsize=10)
 gravar(fig,'mudancas_ubs_existentes_colunas')


def novas(t):
 t=t[t.status=='NOVA'].copy();t['porte']=t.esf_plano.astype(int).map({1:'I',2:'II',3:'III',4:'IV'})
 t=t.sort_values(['esf_plano','codigo'],ascending=[False,True]);t.to_csv(OUT/'novas_ubs_por_porte.csv',sep=';',index=False,encoding='utf-8-sig')
 cores={1:'#478b9a',2:'#a8b6be',3:'#4169a8',4:'#8b568c'}
 fig,ax=plt.subplots(figsize=(W,4.5));fig.subplots_adjust(left=.38,right=.93,top=.96,bottom=.13)
 y=np.arange(len(t));ax.barh(y,t.utilizacao_plano,height=.52,color=[cores[int(v)] for v in t.esf_plano])
 ax.set_yticks(y,[f'{r.codigo} · Porte {r.porte} · {int(r.esf_plano)} eSF' for r in t.itertuples()],fontsize=10)
 ax.set_ylim(len(t)-.5,-.8);ax.set_xlim(0,110);ax.set_xticks([0,25,50,75,100]);ax.tick_params(labelsize=9)
 ax.axvline(100,color='#b86144',ls='--',lw=1)
 for i,r in enumerate(t.itertuples()):ax.text(r.utilizacao_plano+2,i,br(r.utilizacao_plano)+'%',fontsize=9,va='center',color=TEXTO)
 ax.set_xlabel('Demanda potencial / capacidade (%)',fontsize=9)
 ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0,pad=8)
 vals=t.esf_plano.to_numpy()
 for j in range(1,len(vals)):
  if vals[j]!=vals[j-1]:ax.axhline(j-.5,color='#d4dce0',lw=1)
 gravar(fig,'novas_ubs_por_porte')

def resumo(t):
 fig,ax=plt.subplots(figsize=(W,2.4));ax.axis('off')
 capacidade=lambda cap,dem:100*t[dem].sum()/t[cap].sum()
 valores=[('UBS acima de 100%',int((t.utilizacao_atual>100).sum()),int((t.utilizacao_plano>100).sum())),('Utilização média da rede',capacidade('capacidade_atual','demanda_potencial_atual'),capacidade('capacidade_plano','demanda_potencial_plano'))]
 for i,(rot,a,b) in enumerate(valores):
  yy=.75-i*.48;ax.text(.02,yy,rot,fontsize=11,fontweight='bold',color=TEXTO,va='center')
  ax.text(.57,yy,br(a,0 if i==0 else 1)+('' if i==0 else '%'),fontsize=18,color='#788792',ha='center',va='center')
  ax.text(.73,yy,'→',fontsize=18,color=TEXTO,ha='center',va='center')
  ax.text(.91,yy,br(b,0 if i==0 else 1)+('' if i==0 else '%'),fontsize=18,color=AZUL,ha='center',va='center',fontweight='bold')
 ax.text(.57,.98,'Atual',fontsize=10,color='#788792',ha='center');ax.text(.91,.98,'Proposta',fontsize=10,color=AZUL,ha='center')
 gravar(fig,'resumo_pressao_rede')

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--dados',type=Path,default=BASE)
 parser.add_argument('--saida',type=Path,default=OUT)
 args=parser.parse_args()
 BASE,OUT=args.dados,args.saida
 OUT.mkdir(parents=True,exist_ok=True);plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
 t=pd.read_csv(BASE/'utilizacao_ubs_antes_depois.csv',sep=';')
 m=existentes(t);existentes(t,somente_mudancas=True);existentes_colunas(t);novas(t);resumo(t)
 texto=f'''COMPARAÇÃO DAS UBS
RECOMENDADO PARA APRESENTAR: mudancas_ubs_existentes_colunas + novas_ubs_por_porte. A versao curta mostra as seis unidades com mudanca; a completa permanece como apoio.
1. ubs_existentes_comparacao: pontos e linhas destacam a diferença atual -> proposta. Pontos cinza sem linha indicam valores iguais. Há {m} UBS com mudança de pressão. A unidade com duas equipes está identificada; as demais existentes têm uma equipe. Isso não comprova porte físico oficial do prédio.
2. novas_ubs_por_porte: N1 a N9 separados por porte planejado e equipes. Porte I: seis unidades; III: duas; IV: uma; II: nenhuma selecionada.
3. resumo_pressao_rede: quadro curto para abertura da apresentação.
Mesmos cálculos do CSV original: população da UBS mais próxima / min(3000*eSF;750*ACS). As novas não possuem comparação com a rede atual porque não existiam.
A baixa pressão por proximidade de uma nova UBS não é baixa ocupação no plano otimizado: o modelo transfere moradores de outras áreas para unidades com capacidade. Não confundir com população vinculada pelo modelo.
Arquivos separados do artigo: PDF vetorial e PNG 300 dpi. Use 16 cm de largura para preservar fontes.
'''
 (OUT/'LEIA-ME.txt').write_text(texto,encoding='utf-8')
 print('Gráficos salvos em',OUT)
