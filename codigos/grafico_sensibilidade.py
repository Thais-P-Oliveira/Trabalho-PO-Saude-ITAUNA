"""Graficos da nova sensibilidade rural e dos raios, a partir do resumo salvo.

Uso: python codigos/grafico_sensibilidade.py
Salva em resultados/sensibilidade_rural_500_raios/, preservando figuras antigas.
"""
import json
import argparse
import os
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / 'resultados' / 'atual' / 'sensibilidade'
from caminhos import CACHE
os.environ.setdefault('MPLCONFIGDIR', str(CACHE / 'matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

AZUL, LARANJA, CINZA = '#2a78d6', '#eb6834', '#52514e'
TINTA, GRADE, FUNDO = '#0b0b0b', '#e4e3df', '#fcfcfb'


def main():
    global SAIDA
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida',type=Path,default=SAIDA)
    args=ap.parse_args();SAIDA=args.saida.resolve()
    r = pd.read_csv(SAIDA / 'resumo.csv', sep=';')
    r = r[r['status'] == 'Optimal']
    # A analise extra tem somente tres raios; minimo rural fixo de 500 habitantes.
    comparacao=r[(r['grupo']=='rural_raio') & (r['minimo_abertura_rural']==500)].copy()
    if not comparacao.empty:
        import numpy as np
        comparacao=comparacao.sort_values(['raio_urbano_km','raio_rural_km'])
        if set(zip(comparacao.raio_urbano_km,comparacao.raio_rural_km))!={(3.,3.),(3.,5.),(5.,5.)}:
            raise ValueError('Conclua os tres cenarios 3/3, 3/5 e 5/5 antes de gerar a comparacao.')
        x=np.arange(len(comparacao))
        labels=[f'Urbano {a.raio_urbano_km:g} km\nRural {a.raio_rural_km:g} km'
                for a in comparacao.itertuples()]
        def salvar_extra(fig,ax,nome,titulo):
            ax.set_xticks(x,labels)
            ax.set_title(titulo)
            ax.grid(axis='y',color=GRADE,alpha=.6);ax.set_axisbelow(True)
            for lado in ['top','right']:ax.spines[lado].set_visible(False)
            fig.text(.5,.015,'Análise extra: mínimo rural 500 habitantes; folga de custo 2%.',
                     ha='center',fontsize=8,color=CINZA)
            fig.tight_layout(rect=(0,.05,1,1))
            fig.savefig(SAIDA/f'{nome}.png',dpi=200,facecolor=FUNDO)
            fig.savefig(SAIDA/f'{nome}.pdf',facecolor=FUNDO)
            plt.close(fig)
        fig,ax=plt.subplots(figsize=(7.6,4.7),facecolor=FUNDO)
        ax.bar(x,comparacao.custo_operacional_mensal/1e6,color=AZUL)
        for i,a in enumerate(comparacao.itertuples()):
            valor=a.custo_operacional_mensal/1e6
            marca='' if a.custo_otimo_comprovado else '*'
            ax.annotate(f'R$ {valor:.2f} mi{marca}\n{int(a.novas_ubs)} novas UBS'.replace('.',','),
                        (i,valor),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
        ax.set_ylim(0,comparacao.custo_operacional_mensal.max()/1e6*1.25)
        ax.set_ylabel('Custo operacional da rede (R$ milhões/mês)')
        if not comparacao.custo_otimo_comprovado.all():
            ax.text(.01,.98,'* Custo ótimo não comprovado no tempo disponível.',transform=ax.transAxes,
                    va='top',fontsize=8,color=CINZA)
        salvar_extra(fig,ax,'extra_raios_01_custo','Custo operacional nos três cenários de distância')
        fig,ax=plt.subplots(figsize=(7.6,4.7),facecolor=FUNDO)
        for deslocamento,coluna,nome,cor in [(-.25,'cobertura','Total',CINZA),
                                            (0,'cobertura_urbana','Urbana',AZUL),
                                            (.25,'cobertura_rural','Rural',LARANJA)]:
            valores=comparacao[coluna]*100
            barras=ax.bar(x+deslocamento,valores,width=.24,label=nome,color=cor)
            ax.bar_label(barras,labels=[f'{v:.1f}%'.replace('.',',') for v in valores],padding=3,fontsize=8)
        ax.set_ylim(0,112);ax.legend(loc='lower right')
        ax.set_ylabel('Cobertura conforme o raio de cada cenário (%)')
        salvar_extra(fig,ax,'extra_raios_02_cobertura','Cobertura total, urbana e rural')
        fig,ax=plt.subplots(figsize=(7.6,4.7),facecolor=FUNDO)
        for deslocamento,coluna,nome,cor in [(-.18,'distancia_media_urbana_km','Urbana',AZUL),
                                            (.18,'distancia_media_rural_km','Rural',LARANJA)]:
            valores=comparacao[coluna]
            barras=ax.bar(x+deslocamento,valores,width=.36,label=nome,color=cor)
            ax.bar_label(barras,labels=[f'{v:.2f}'.replace('.',',') for v in valores],padding=3,fontsize=9)
        ax.set_ylim(0,comparacao[['distancia_media_urbana_km','distancia_media_rural_km']].max().max()*1.2)
        ax.set_ylabel('Distância média ponderada pela população (km)');ax.legend()
        salvar_extra(fig,ax,'extra_raios_03_distancia','Deslocamento médio até a UBS de destino')
        imagens=[('extra_raios_01_custo','Custo operacional e quantidade de novas UBS'),
                 ('extra_raios_02_cobertura','Cobertura total, urbana e rural'),
                 ('extra_raios_03_distancia','Distância média até a UBS de destino')]
        cards=''.join(f'<section><h2>{titulo}</h2><a href="{nome}.png"><img src="{nome}.png" alt="{titulo}"></a></section>'
                      for nome,titulo in imagens)
        pagina='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Análise extra dos raios de cobertura</title><style>body{font:17px/1.6 system-ui;color:#202944;background:#f3f5fa;margin:0}
main{max-width:1050px;margin:auto;padding:24px}header,section{background:white;padding:24px;margin-bottom:20px;border-radius:12px}
img{width:100%;height:auto}a{color:#214da6}</style><main><header><h1>Análise extra dos raios de cobertura</h1>
<p>Três cenários: urbano/rural 3/3, 3/5 e 5/5 km. Mínimo rural de 500 habitantes em todos os casos.</p>
<p>A análise principal permanece em 3/3 km e folga de custo de 2%. Os demais parâmetros são mantidos.
Esta comparação da APS não repete os cenários de encaminhamento especializado.</p>
<p>A cobertura usa o limite de cada cenário. A distância média permite avaliar o deslocamento sem mudar a unidade de comparação.</p>
<p><a href="resumo.csv">Tabela completa dos cenários</a></p></header>'''+cards+'</main></html>'
        (SAIDA/'analise_extra_raios.html').write_text(pagina,encoding='utf-8')
    curva = r[r['grupo'] == 'curva'].sort_values('cobertura')
    if curva.empty:
        print('Comparacao rural/raios salva; curva de cobertura nao solicitada nesta execucao.')
        return
    config=json.loads((SAIDA/'configuracao_analise.json').read_text(encoding='utf-8'))
    referencia=Path(config['referencia'])
    ref = json.loads(referencia.read_text(encoding='utf-8'))
    ref_cob, ref_custo = ref['cobertura'] / ref['total'], ref['custos']['operacional']

    fig, ax = plt.subplots(figsize=(7.2, 4.2), facecolor=FUNDO)
    ax.set_facecolor(FUNDO)
    ax.plot(curva['cobertura'] * 100, curva['custo_operacional_mensal'] / 1e6, color=AZUL, lw=2, zorder=2)
    ax.scatter(curva['cobertura'] * 100, curva['custo_operacional_mensal'] / 1e6, s=42, color=AZUL,
               edgecolor=FUNDO, linewidth=2, zorder=3)
    for c in curva.itertuples():
        ax.annotate(f'{int(c.novas_ubs)} novas', (c.cobertura * 100, c.custo_operacional_mensal / 1e6),
                    xytext=(-6, 8), textcoords='offset points', ha='right', fontsize=8, color=CINZA)
    ax.scatter([ref_cob * 100], [ref_custo / 1e6], s=60, marker='D', color=LARANJA, edgecolor=FUNDO,
               linewidth=2, zorder=4)
    n_ref = int((pd.read_csv(referencia.parent/'aps/ubs_completas.csv')['status'] == 'NOVA').sum())
    minimo=ref['parametros'].get('hab_min_nova_rural',0)
    ax.annotate(f'Plano salvo anterior\n({n_ref} novas, mínimo rural {minimo:g})', (ref_cob * 100, ref_custo / 1e6), xytext=(-12, 14),
                textcoords='offset points', ha='right', fontsize=8.5, color=TINTA,
                arrowprops=dict(arrowstyle='-', color=CINZA, lw=0.8))
    ax.set_xlabel('População a até 3 km da UBS de destino (%)', color=TINTA, fontsize=9.5)
    ax.set_ylabel('Custo operacional (R$ milhões por mês)', color=TINTA, fontsize=9.5)
    ax.grid(axis='y', color=GRADE, lw=0.8)
    ax.set_axisbelow(True)
    for lado in ['top', 'right']:
        ax.spines[lado].set_visible(False)
    for lado in ['left', 'bottom']:
        ax.spines[lado].set_color(GRADE)
    ax.tick_params(colors=CINZA, labelsize=8.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:.2f}'.replace('.', ',')))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:.0f}'))
    fig.tight_layout()
    fig.savefig(SAIDA / 'curva_cobertura_custo.png', dpi=200, facecolor=FUNDO)
    fig.savefig(SAIDA/'curva_cobertura_custo.pdf', facecolor=FUNDO)
    print('Grafico salvo em', SAIDA)


if __name__ == '__main__':
    main()
