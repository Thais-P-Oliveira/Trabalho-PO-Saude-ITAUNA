"""Mapas e graficos da APS de Itauna com limite municipal, coordenadas metricas e legenda inequivoca.

Distancias de cobertura por haversine; o mapa usa conversao local graus->km (somente desenho).
Elementos distintos (simbolo + cor + rotulo): UBS existente, NOVA UBS proposta (N1, N2, ...),
equipe movel (base e rota), pontos de demanda cobertos / sem cobertura geografica.
"""
import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon as MPoly
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

from caminhos import RESULTADOS,MODELOS
import sys
sys.path.insert(0,str(MODELOS))
from geografia import limite_municipal, projetar, circulo
import cobertura_efetiva as ce

VERDE, VERMELHO, ROXO, AZUL, LARANJA, CINZA = '#1e8449', '#c0392b', '#6c3483', '#2e86c1', '#e67e22', '#566573'


def _br(v, d=0):
    return f'{v:,.{d}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _poly(ax, geom, **kw):
    geoms = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
    for g in geoms:
        ax.add_patch(MPoly(np.asarray(g.exterior.coords)/1000.0, closed=True, **kw))


def codificar_novas(ubs):
    """Cria codigos N1..Nk para as novas UBS (ordem decrescente de populacao atendida)."""
    ubs = ubs.copy()
    ubs['codigo'] = ''
    novas = ubs[ubs['status'] == 'NOVA'].sort_values('pop_atendida', ascending=False)
    for k, idx in enumerate(novas.index, 1):
        ubs.loc[idx, 'codigo'] = f'N{k}'
    return ubs


def nome_amigavel(nome):
    import re
    t = str(nome).replace('NOVA UBS ', '').strip()
    m = re.fullmatch(r'\((.*)\)', t)
    return m.group(1) if m else t


def mapa(pontos, por_ponto, ubs, bases, visitas, caminho, titulo, raio=3.0, zoom=False, raio_rural=None, para_artigo=False):
    lim_m, _ = limite_municipal()
    fig, ax = plt.subplots(figsize=(6.4, 4.8) if para_artigo else (15, 10.5), dpi=180)
    ax.set_aspect('equal')
    _poly(ax, lim_m, fc='#f4f6f6', ec='#212f3d', lw=2.0, zorder=0)
    ux, uy = projetar(ubs['lon'], ubs['lat'])
    ubs = ubs.assign(x=ux/1000.0, y=uy/1000.0)
    px, py = projetar(por_ponto['lon'], por_ponto['lat'])
    pp = por_ponto.assign(x=px/1000.0, y=py/1000.0)
    for r in ubs.itertuples():
        cor = VERMELHO if r.status == 'NOVA' else VERDE
        _poly(ax, circulo(r.x*1000, r.y*1000, raio), fc=cor, ec=cor, alpha=0.07 if r.status == 'NOVA' else 0.05, lw=0.9, zorder=1)
    for r in ubs.itertuples():
        cor = VERMELHO if r.status == 'NOVA' else VERDE
        ax.add_patch(plt.Circle((r.x, r.y), raio, fc='none', ec=cor, lw=0.8, alpha=0.55, zorder=2))
        if raio_rural is not None and raio_rural != raio:
            ax.add_patch(plt.Circle((r.x,r.y), raio_rural, fc='none', ec=cor,
                                   ls='--', lw=0.8, alpha=0.55, zorder=2))
    cob = pp[pp['cobertura_geografica'] == 1]
    desc = pp[pp['cobertura_geografica'] == 0]
    ax.scatter(cob['x'], cob['y'], s=np.sqrt(cob['pessoas'])*1.8+8, c=AZUL, alpha=0.75, edgecolors='white', linewidths=0.4, zorder=3)
    atendidos = set(visitas['ponto']) if len(visitas) else set()
    if len(desc):
        ax.scatter(desc['x'], desc['y'], s=np.sqrt(desc['pessoas'])*1.8+30, facecolors='none', edgecolors=LARANJA, linewidths=1.8, zorder=4)
    if len(bases):
        bx, by = projetar(bases['lon'], bases['lat'])
        bases = bases.assign(x=bx/1000.0, y=by/1000.0)
        for v in visitas.itertuples():
            b = bases[bases['equipe_movel'] == v.equipe_movel].iloc[0]
            vx, vy = projetar([v.lon], [v.lat])
            ax.plot([b.x, vx[0]/1000.0], [b.y, vy[0]/1000.0], ls='--', color=ROXO, lw=1.0, alpha=0.8, zorder=4)
        ax.scatter(bases['x'], bases['y'], s=80 if para_artigo else 230, c=ROXO, marker='D', edgecolors='black', linewidths=1.0, zorder=7)
        for b in bases.itertuples():
            ax.annotate(b.equipe_movel, (b.x, b.y), xytext=(8, 8), textcoords='offset points', fontsize=8, fontweight='bold', color=ROXO, zorder=8)
    ex = ubs[ubs['status'] == 'EXISTENTE']
    ax.scatter(ex['x'], ex['y'], s=(25+10*ex['esf']) if para_artigo else (70+30*ex['esf']), c=VERDE, marker='s', edgecolors='black', linewidths=0.9, zorder=5)
    nv = ubs[ubs['status'] == 'NOVA']
    ax.scatter(nv['x'], nv['y'], s=150 if para_artigo else 520, c=VERMELHO, marker='*', edgecolors='black', linewidths=1.2, zorder=6)
    for r in nv.itertuples():
        ax.annotate(r.codigo, (r.x, r.y), xytext=(10, 10), textcoords='offset points', fontsize=10, fontweight='bold', color='#78281f', zorder=8,
                    bbox=dict(boxstyle='round,pad=0.2', fc='#fcf3cf', ec=VERMELHO, lw=1))
    minx, miny, maxx, maxy = np.array(lim_m.bounds)/1000.0
    if zoom:
        ax.set_xlim(ex['x'].min()-4, ex['x'].max()+4)
        ax.set_ylim(ex['y'].min()-4, ex['y'].max()+4)
    else:
        ax.set_xlim(minx-1.5, maxx+1.5)
        ax.set_ylim(miny-1.5, maxy+1.5)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.0f}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.0f}'))
    ax.set_xlabel('Distância Leste–Oeste a partir do centro de Itaúna (km)')
    ax.set_ylabel('Distância Norte–Sul a partir do centro de Itaúna (km)')
    ax.grid(True, ls=':', alpha=0.4)
    n_sem = float(pp.loc[pp['cobertura_geografica'] == 0, 'pessoas'].sum())
    handles = [Patch(fc='#f4f6f6', ec='#212f3d', lw=2, label='Limite municipal de Itaúna (IBGE)'),
               Line2D([], [], marker='s', ls='', mfc=VERDE, mec='black', ms=9, label=f'UBS existentes ({len(ex)})'),
               Line2D([], [], marker='*', ls='', mfc=VERMELHO, mec='black', ms=16, label=f'NOVAS UBS propostas ({len(nv)}), códigos N1…N{len(nv)}'),
               Line2D([], [], marker='D', ls='', mfc=ROXO, mec='black', ms=9, label=f'Equipes móveis — base em UBS ({int(bases["equipes"].sum()) if len(bases) else 0} equipe(s))'),
               Line2D([], [], ls='--', color=ROXO, label='Ligação base–ponto móvel (não é rota viária)'),
               Patch(fc=VERDE, ec=VERDE, alpha=0.25, label=f'Área a ≤ {raio:g} km de UBS existente'),
               Patch(fc=VERMELHO, ec=VERMELHO, alpha=0.25, label=f'Área a ≤ {raio:g} km de NOVA UBS'),
               Line2D([], [], marker='o', ls='', mfc=AZUL, mec='white', ms=8, label=f'Demanda com cobertura geográfica ({_br(cob["pessoas"].sum())} hab)'),
               Line2D([], [], marker='o', ls='', mfc='none', mec=LARANJA, mew=1.8, ms=9, label=f'Demanda SEM cobertura geográfica ({_br(n_sem)} hab)')]
    if para_artigo:
        rotulos=['Limite municipal (IBGE)',f'UBS existentes ({len(ex)})',f'Novas UBS: N1 a N{len(nv)}',
                 f'Base móvel ({int(bases["equipes"].sum()) if len(bases) else 0} equipes)',
                 'Ligação móvel (linha reta)',f'Raio {raio:g} km: existentes',f'Raio {raio:g} km: novas',
                 f'No raio: {_br(cob["pessoas"].sum())} hab',f'Fora: {_br(n_sem)} hab']
        for h,rotulo in zip(handles,rotulos):h.set_label(rotulo)
    ax.legend(handles=handles, loc='upper left', bbox_to_anchor=(1.01, 1.0), fontsize=9 if para_artigo else 8, frameon=True, title='Legenda', title_fontsize=9.5)
    if len(nv) and not para_artigo:
        txt = 'Novas UBS propostas\n' + '\n'.join(f'{r.codigo}: {nome_amigavel(r.nome)[:44]} — {int(r.esf)} eSF'
                                                  for r in nv.sort_values('codigo', key=lambda s: s.str[1:].astype(int)).itertuples())
    if para_artigo:
        ax.set_xlabel('Leste–Oeste (km)',fontsize=9)
        ax.set_ylabel('Norte–Sul (km)',fontsize=9)
        ax.tick_params(labelsize=9)
    fig.subplots_adjust(left=0.11 if para_artigo else 0.06, right=0.61 if para_artigo else 0.64, top=0.91 if para_artigo else 0.94, bottom=0.12 if para_artigo else 0.08)
    fig.savefig(caminho)
    plt.close(fig)


def painel(resumos, ubs, arcos_plano, custos, caminho, hab_esf=3000, populacao=None, criterio='3 km'):
    """Quatro graficos com eixos e unidades explicitos."""
    fig = plt.figure(figsize=(17, 12), dpi=150)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1], hspace=0.32, wspace=0.28)
    # A) Carga por UBS
    ax = fig.add_subplot(gs[:, 0])
    u = ubs.sort_values('pop_atendida').reset_index(drop=True).copy()
    u['carga_atendida'] = u['pop_atendida']  # vinculacao da APS usada na hierarquia
    rot = [f"{r.codigo} (NOVA)" if r.status == 'NOVA' else str(r.nome).title()[:26] for r in u.itertuples()]
    cap = u['capacidade_efetiva'].values
    ax.barh(range(len(u)), cap, color='none', edgecolor='#7f8c8d', hatch='///', lw=0.6, label='Capacidade efetiva = mín(3.000 × eSF; 750 × ACS)')
    cores = [VERMELHO if s == 'NOVA' else VERDE for s in u['status']]
    ax.barh(range(len(u)), u['carga_atendida'], color=cores, alpha=0.9)
    for k, r in u.iterrows():
        ax.text(max(cap[k], r['carga_atendida'])+120, k, f"{_br(r['carga_atendida'])} hab · {int(r['esf'])} eSF · {int(r['acs'])} ACS", va='center', fontsize=7.5)
    ax.set_yticks(range(len(u)))
    ax.set_yticklabels(rot, fontsize=8)
    ax.set_xlim(0, cap.max()*1.45)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _br(v)))
    ax.set_xlabel('População vinculada (habitantes, inclusive fora do raio)')
    ax.set_ylabel('Unidade Básica de Saúde')
    ax.legend(handles=[Patch(fc=VERDE, label='População vinculada — UBS existente'), Patch(fc=VERMELHO, label='População vinculada — NOVA UBS'),
                       Patch(fc='none', ec='#7f8c8d', hatch='///', label='Capacidade efetiva (tracejado)')], loc='lower right', fontsize=8)
    ax.grid(axis='x', ls=':', alpha=0.5)
    # B) Cobertura
    ax = fig.add_subplot(gs[0, 1])
    nomes = [r['rotulo'] for r in resumos]
    y = np.arange(len(resumos))
    ax.barh(y+0.2, [r['geo'] for r in resumos], height=0.36, color='#85c1e9', label=f'Cobertura geográfica ({criterio})')
    ax.barh(y-0.2, [r['efetiva'] for r in resumos], height=0.36, color=AZUL, label=f'Cobertura efetiva ({criterio} + capacidade eSF/ACS)')
    for k, r in enumerate(resumos):
        ax.text(r['geo']+0.8, k+0.2, f"{r['geo']:.1f}%", va='center', fontsize=8.5)
        ax.text(r['efetiva']+0.8, k-0.2, f"{r['efetiva']:.1f}%", va='center', fontsize=8.5, fontweight='bold')
        if r.get('moveis'):
            ax.text(101, k, f"+{r['moveis']:.1f} pp\nequipes\nmóveis".replace('.', ','), va='center', fontsize=7.5, color=ROXO)
    ax.set_yticks(y)
    ax.set_yticklabels(nomes, fontsize=9)
    ax.set_xlim(0, 122)
    ax.set_xticks([0,20,40,60,80,100])  # margem a direita reservada para a anotacao das moveis
    ax.set_xlabel(f'% da população total do cenário ({_br(populacao)} hab)')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16), fontsize=8, frameon=False)
    ax.grid(axis='x', ls=':', alpha=0.5)
    # C) Custo mensal
    ax = fig.add_subplot(gs[1, 1])
    itens = [('UBS existentes (custo fixo)', custos['fixo_existentes'], '#85929e'), ('UBS novas (custo fixo)', custos['fixo_novas'], VERMELHO),
             ('Pessoal clínico e de enfermagem', custos['esf'], AZUL), ('ACS', custos['acs'], '#f39c12')]
    if custos.get('moveis', 0) > 0:
        itens.append(('Equipes móveis (eSF + ACS)', custos['moveis'], ROXO))
    tot = sum(v for _, v, _ in itens)
    ini = 0
    for nome, v, cor in itens:
        ax.barh([0], [v/1000], left=ini/1000, color=cor, edgecolor='white', label=f'{nome}: R$ {_br(v)}/mês')
        if v/tot >= 0.045:
            ax.text((ini+v/2)/1000, 0, f'{v/tot:.0%}', ha='center', va='center', color='white', fontsize=9, fontweight='bold')
        ini += v
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _br(v)))
    ax.set_xlabel('Custo operacional mensal (R$ mil)')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.25), ncol=1, fontsize=8, frameon=False)
    fig.savefig(caminho, bbox_inches='tight')
    plt.close(fig)


def curva_acesso(por_ponto_atual, por_ponto_plano, caminho, raio=3.0):
    fig, ax = plt.subplots(figsize=(8.5, 5.8), dpi=170)
    for pp, nome, cor in [(por_ponto_atual, 'Rede atual (22 UBS)', CINZA), (por_ponto_plano, 'Plano proposto (22 + novas UBS)', VERDE)]:
        d = pp.sort_values('dist_ubs_mais_proxima_km')
        ax.step(d['dist_ubs_mais_proxima_km'], 100*d['pessoas'].cumsum()/d['pessoas'].sum(), where='post', lw=2.2, color=cor, label=nome)
    ax.axvline(raio, color=VERMELHO, ls='--')
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 102)
    ax.set_xlabel('Distância em linha reta (haversine) até a UBS mais próxima (km)')
    ax.set_ylabel('% acumulado da população do cenário')
    ax.legend(loc='lower right')
    ax.grid(True, ls=':', alpha=0.5)
    fig.tight_layout()
    fig.savefig(caminho)
    plt.close(fig)


def gerar_de_dados(pontos, plano_ubs, custos, saida, dir_csv=None, hab_movel=ce.HAB_MOVEL, raio=3.0, raio_rural=None,
                   hab_esf=ce.HAB_ESF, fator_rota=1.0, nomes=None):
    """Gera mapas, painel e curva de acesso a partir dos dados do plano.

    plano_ubs: colunas id_ubs, nome, lat, lon, status, n_esf, acs, pop_atendida (formato de ubs_completas.csv).
    custos: dicionario de custos mensais do plano (fixo_existentes, fixo_novas, esf, acs).
    """
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    dir_csv = Path(dir_csv) if dir_csv else saida
    nomes = nomes or dict(atual='mapa_rede_atual_cobertura.png', plano='mapa_plano_proposto.png',
                          zoom='mapa_plano_proposto_zoom_urbano.png', painel='painel_cobertura_capacidade_custo.png',
                          curva='curva_acesso_geografico.png')
    plano_ubs = plano_ubs.copy()
    rede_plano = pd.DataFrame(dict(id=plano_ubs['id_ubs'], nome=plano_ubs['nome'], lat=plano_ubs['lat'], lon=plano_ubs['lon'],
                                   esf=plano_ubs['n_esf'].astype(float), acs=plano_ubs['acs'].astype(float), status=plano_ubs['status']))
    out = {}
    for rotulo, rede in [('atual', ce.carregar_rede_atual()), ('plano', rede_plano)]:
        # os parametros do modelo (raio, hab/eSF, fator de rota) valem para as duas redes
        resumo, por_ponto, por_ubs, arcos = ce.cobertura_efetiva(pontos, rede, raio, raio_rural, hab_esf, ce.HAB_ACS, fator_rota)
        from vinculos_moveis import ler_complemento
        salvo=ler_complemento(dir_csv.parent.parent/'vinculos_moveis',por_ponto) if rotulo=='plano' else None
        mov, bases, visitas, desc = salvo if salvo is not None else ce.equipes_moveis(pontos, por_ponto, rede, hab_movel=hab_movel)
        resumo['equipes_moveis'] = mov
        resumo['cobertura_efetiva_com_moveis_pct'] = 100*(resumo['pop_atendida_efetiva']+mov['atendida'])/resumo['populacao']
        dir_csv.mkdir(parents=True, exist_ok=True)
        (dir_csv/f'{rotulo}_resumo.json').write_text(__import__('json').dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
        for nome, df in [('por_ponto', por_ponto), ('por_ubs', por_ubs), ('alocacao', arcos), ('moveis_bases', bases), ('moveis_visitas', visitas), ('moveis_pontos', desc)]:
            if len(df):
                df.to_csv(dir_csv/f'{rotulo}_{nome}.csv', sep=';', index=False, encoding='utf-8-sig')
        out[rotulo] = dict(resumo=resumo, por_ponto=por_ponto, por_ubs=por_ubs, bases=bases, visitas=visitas, mov=mov, rede=rede)
    po = out['plano']['por_ubs'].merge(plano_ubs[['id_ubs', 'pop_atendida']].rename(columns={'id_ubs': 'id'}), on='id', how='left')
    po = codificar_novas(po.assign(pop_atendida=po['pop_atendida'].fillna(0)))
    po.loc[po.status=='NOVA',['codigo','id','nome','esf','acs']].to_csv(
        saida/'novas_ubs_codigos.csv',sep=';',index=False,encoding='utf-8-sig')
    out['plano']['por_ubs'] = po
    a_atual = codificar_novas(out['atual']['rede'].assign(pop_atendida=0))
    mapa(pontos, out['atual']['por_ponto'], a_atual, out['atual']['bases'], out['atual']['visitas'], saida/nomes['atual'], raio=raio, raio_rural=raio_rural,
         titulo='Rede atual de UBS de Itaúna — equipes móveis propostas para a população descoberta')
    mapa(pontos, out['plano']['por_ponto'], po, out['plano']['bases'], out['plano']['visitas'], saida/nomes['plano'], raio=raio, raio_rural=raio_rural,
         titulo='Plano proposto — UBS existentes, NOVAS UBS (N1…) e equipes móveis, com limite municipal')
    mapa(pontos, out['plano']['por_ponto'], po, out['plano']['bases'], out['plano']['visitas'], saida/nomes['zoom'], raio=raio, raio_rural=raio_rural,
         titulo='Plano proposto — zoom na área urbana', zoom=True)
    ra, rp = out['atual']['resumo'], out['plano']['resumo']
    resumos = [dict(rotulo='Rede atual\n(22 UBS, 23 eSF)', geo=ra['cobertura_geografica_pct'], efetiva=ra['cobertura_efetiva_pct'],
                    moveis=ra['equipes_moveis']['atendida']/ra['populacao']*100),
               dict(rotulo='Plano proposto\n(com novas UBS)', geo=rp['cobertura_geografica_pct'], efetiva=rp['cobertura_efetiva_pct'],
                    moveis=rp['equipes_moveis']['atendida']/rp['populacao']*100)]
    cj = dict(custos)
    from aps_base import CUSTO_ESF, CUSTO
    unit = (CUSTO_ESF, CUSTO['acs'])
    mv = out['plano']['mov']
    cj['moveis'] = mv['equipes']*unit[0]+mv['acs_necessarios']*unit[1]
    criterio=f'{raio:g} km' if raio_rural is None or raio_rural==raio else f'{raio:g} km urbano / {raio_rural:g} km rural'
    painel(resumos, po, None, cj, saida/nomes['painel'], hab_esf, rp['populacao'], criterio)
    curva_acesso(out['atual']['por_ponto'], out['plano']['por_ponto'], saida/nomes['curva'], raio)
    return out


def gerar(plano, saida, hab_movel=ce.HAB_MOVEL):
    import json
    plano = Path(plano)
    pontos = pd.read_csv(plano/'aps/demanda_cenario.csv', encoding='utf-8-sig')
    ubs = pd.read_csv(plano/'aps/ubs_completas.csv', encoding='utf-8-sig')
    custos = json.loads((plano/'plano_aps.json').read_text(encoding='utf-8'))['custos']
    parametros=json.loads((plano/'plano_aps.json').read_text(encoding='utf-8'))['parametros']
    resultado=gerar_de_dados(pontos, ubs, custos, saida, plano/'aps/cobertura_efetiva', hab_movel,
                         raio=parametros['raio'],raio_rural=parametros.get('raio_rural'),
                         hab_esf=parametros['hab_esf'],fator_rota=parametros['fator_rota'],
                         nomes=dict(atual='mapa_itauna_rede_atual.png',plano='mapa_itauna_ubs.png',
                                    zoom='mapa_itauna_zoom_urbano.png',painel='painel_resultados.png',
                                    curva='curva_acesso_geografico.png'))
    from types import SimpleNamespace
    import sys
    from caminhos import MODELOS
    sys.path.insert(0,str(MODELOS))
    from aps_base import mapa_html
    ubs['ocupacao']=ubs.pop_atendida/(parametros['hab_esf']*ubs.n_esf)
    ubs['situacao']='Vinculacao do plano APS'
    args=SimpleNamespace(**dict(parametros,saida=str(plano/'aps')))
    mapa_html(pontos,ubs,pd.read_csv(plano/'aps/alocacao_completa.csv'),args,plano/'aps/mapa_interativo.html')
    return resultado


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--plano', type=Path, default=RESULTADOS/'atual/plano')
    ap.add_argument('--saida', type=Path, default=RESULTADOS/'figuras_novas')
    a = ap.parse_args()
    gerar(a.plano, a.saida)
    print('Figuras salvas em', a.saida)
