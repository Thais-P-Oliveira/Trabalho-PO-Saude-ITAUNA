"""Gera as figuras do artigo a partir do plano de referencia salvo.

Uso: python codigos/figuras_artigo.py
Saida: documentacao/artigo/figuras/{mapa,distancias,internacoes,percursos,capacidades}.pdf
(e a versao PNG de cada em imagens/).
A figura do fluxo do metodo e a curva de cobertura x custo sao geradas por outros meios.
"""
import csv
import argparse
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PLANO = RAIZ / 'resultados' / 'atual' / 'plano'
FIG = RAIZ / 'documentacao' / 'artigo' / 'figuras'
PNG = RAIZ / 'imagens'
from caminhos import CACHE
os.environ.setdefault('MPLCONFIGDIR', str(CACHE / 'matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

AZUL, LARANJA, CINZA = '#255a7b', '#bc6e2a', '#d7dbdf'
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.color': '#eeeeee', 'grid.linewidth': 0.8, 'axes.axisbelow': True})


def br(v, casas=1):
    return f'{v:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def salvar(fig, nome):
    PNG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f'{nome}.pdf', bbox_inches='tight')
    fig.savefig(PNG / f'{nome}.png', dpi=200, bbox_inches='tight')
    plt.close(fig)


def ler(p):
    return pd.read_csv(p, sep=';', encoding='utf-8-sig')


def mapa():
    dem = pd.read_csv(PLANO / 'aps/demanda_cenario.csv')
    ubs = pd.read_csv(PLANO / 'aps/ubs_completas.csv')
    ex, nv = ubs[ubs.status == 'EXISTENTE'], ubs[ubs.status == 'NOVA']
    fig, ax = plt.subplots(figsize=(5.3, 5.6))
    ax.scatter(dem.lon, dem.lat, s=dem.pessoas / dem.pessoas.max() * 220 + 15, color=CINZA, edgecolor='white',
               linewidth=0.5, label='Pontos de demanda', zorder=1)
    ax.scatter(ex.lon, ex.lat, s=55, color=AZUL, edgecolor='white', linewidth=0.6, label=f'{len(ex)} UBS existentes', zorder=2)
    ax.scatter(nv.lon, nv.lat, s=70, marker='^', color=LARANJA, edgecolor='white', linewidth=0.6,
               label=f'{len(nv)} novas UBS', zorder=3)
    for r in nv.itertuples():
        ax.annotate('N' + r.id_ubs.split('_')[1], (r.lon, r.lat), xytext=(5, 5), textcoords='offset points', fontsize=8)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:.2f}'))
    ax.legend(frameon=False, loc='upper right', fontsize=9)
    salvar(fig, 'mapa')


def distancias(comp):
    amb = comp[comp.tipo == 'AMB']
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    vias = [25, 50, 75]
    for k, (cen, cor, rot) in enumerate([('unico', AZUL, 'Um nível'), ('multiplo', LARANJA, 'Múltiplos níveis')]):
        v = [amb[(amb.cenario == cen) & (amb.via_percentual == p)].distancia_media_por_percurso.iloc[0] for p in vias]
        x = [i + (k - 0.5) * 0.34 for i in range(3)]
        ax.bar(x, v, width=0.34, color=cor, label=rot)
        for xi, vi in zip(x, v):
            ax.text(xi, vi + 0.06, br(vi, 2), ha='center', va='bottom', fontsize=8.5)
    ax.set_xticks(range(3), [f'{p}%' for p in vias])
    ax.set_xlabel('Parcela da demanda terciária via secundária')
    ax.set_ylabel('Distância média por percurso (km)')
    ax.set_ylim(0, ax.get_ylim()[1] * 1.3)
    ax.grid(axis='x', visible=False)
    ax.legend(frameon=False, ncol=2, loc='upper center')
    salvar(fig, 'distancias')


def internacoes(comp):
    h = comp[comp.tipo == 'HOSP']
    linhas = [('Único\n25%', 'unico', 25), ('Único\n50%', 'unico', 50), ('Único\n75%', 'unico', 75), ('Múltiplo\n25–75%', 'multiplo', 50)]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
    for ax, nivel, titulo in [(axes[0], '2', 'Internações secundárias'), (axes[1], '3', 'Internações terciárias')]:
        for i, (rot, cen, p) in enumerate(linhas):
            r = h[(h.cenario == cen) & (h.via_percentual == p)].iloc[0]
            at, fa = r['atendido' + nivel], r['falta' + nivel]
            cor = AZUL if cen == 'unico' else LARANJA
            ax.bar(i, at, color=cor, width=0.8)
            ax.bar(i, fa, bottom=at, color=CINZA, width=0.8)
            ax.text(i, at + (at + fa) * 0.015, br(at), ha='center', va='bottom', fontsize=8)
        ax.set_xticks(range(len(linhas)), [l[0] for l in linhas])
        ax.set_title(titulo, fontsize=10)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.12)
        ax.set_ylabel('Internações estimadas por ano')
        ax.grid(axis='x', visible=False)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=AZUL, label='Atendidas único'), Patch(color=LARANJA, label='Atendidas múltiplo'),
                        Patch(color=CINZA, label='Não alocadas em Itaúna')], loc='upper center', ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 1.06), fontsize=9)
    fig.tight_layout()
    salvar(fig, 'internacoes')


def percursos(comp):
    r = comp[(comp.tipo == 'AMB') & (comp.cenario == 'multiplo') & (comp.via_percentual == 50)].iloc[0]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.text(1, 3, 'UBS\nplano fixo', ha='center', va='center', fontsize=11)
    alvos = [(5, 'Termina na secundária\n' + br(r.termina2, 0) + ' eventos'),
             (3, 'Direto à terciária\n' + br(r.direto3, 0) + ' eventos'),
             (1, 'Secundária e terciária\n' + br(r.via23, 0) + ' percursos\n' + br(2 * r.via23, 0) + ' atendimentos')]
    for y, txt in alvos:
        ax.annotate('', xy=(5.4, y + 0.1), xytext=(2, 3), arrowprops=dict(arrowstyle='->', color=AZUL, lw=2))
        ax.text(5.8, y + 0.1, txt, va='center', fontsize=11)
    salvar(fig, 'percursos')


def capacidades():
    c = ler(PLANO / 'multiplo_via_50/capacidades.csv')
    c = c[c.limite_pico_anualizado > 0].copy()
    # Ordem importa: o CEO II tambem comeca com "CENTRO DE ESPEC".
    nomes = [('CENTRO DE ESPECIALIDADES ODONTOLOGICAS', 'CEO II'), ('CENTRO DE ESPEC', 'Centro de especialidades'),
             ('APAE', 'APAE'), ('CAPS 2', 'CAPS 2'), ('CAPS AD', 'CAPS AD'), ('HOSPITAL', 'Hospital')]
    c['rotulo'] = [next(v for k, v in nomes if n.upper().startswith(k)) for n in c.nome]
    c['uso'] = c.ambulatorial_total / c.limite_pico_anualizado * 100
    c = c.sort_values('rotulo', ascending=False)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    cores = [LARANJA if u >= 99.95 else AZUL for u in c.uso]
    y = list(range(len(c)))
    ax.barh(y, c.uso, color=cores)
    ax.set_yticks(y, c.rotulo)
    for yi, u in zip(y, c.uso):
        ax.text(u + 1, yi, br(u) + '%', va='center', fontsize=8.5)
    ax.set_xlim(0, 114)
    ax.set_xlabel('Utilização do limite ambulatorial disponível para residentes (%)')
    ax.grid(axis='y', visible=False)
    salvar(fig, 'capacidades')


def main():
    global PLANO,FIG,PNG
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plano',type=Path,default=PLANO)
    ap.add_argument('--figuras',type=Path,default=FIG)
    ap.add_argument('--imagens',type=Path,default=PNG)
    args=ap.parse_args()
    PLANO,FIG,PNG=args.plano.resolve(),args.figuras.resolve(),args.imagens.resolve()
    FIG.mkdir(parents=True,exist_ok=True);PNG.mkdir(parents=True,exist_ok=True)
    comp = ler(PLANO / 'comparacao_completa.csv')
    mapa()
    distancias(comp)
    internacoes(comp)
    percursos(comp)
    capacidades()
    # Fluxo do metodo tambem e renovado, sem reaproveitar a figura antiga.
    fig,ax=plt.subplots(figsize=(9,3.4));ax.axis('off')
    etapas=['Dados de população\ne demanda municipal','APS: cobertura,\ncusto e distância',
            'População e demanda\nvinculadas às UBS','Encaminhamentos\nsecundários e terciários']
    for i,rotulo in enumerate(etapas):
        xx=.12+i*.25
        ax.text(xx,.55,rotulo,ha='center',va='center',transform=ax.transAxes,fontsize=9,
                bbox=dict(boxstyle='round,pad=.7',facecolor='#eaf0f6',edgecolor=AZUL))
        if i<3:ax.annotate('',xy=(xx+.17,.55),xytext=(xx+.09,.55),xycoords='axes fraction',
                           arrowprops=dict(arrowstyle='->',color=AZUL,lw=1.7))
    ax.text(.5,.12,'A rede de UBS é fixada antes da otimização dos encaminhamentos.',
            ha='center',transform=ax.transAxes,fontsize=9)
    salvar(fig,'fluxo_metodo')
    print('Figuras salvas em', FIG)


if __name__ == '__main__':
    main()
