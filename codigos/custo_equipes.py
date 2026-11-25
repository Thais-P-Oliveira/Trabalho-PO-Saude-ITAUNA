"""Custo atual de manutencao das equipes da Atencao Primaria de Itauna e percentual do orcamento.

Fontes (todas locais, rastreaveis):
  SIOPS 2025, subfuncao 301 Atencao Basica  -> dados/fontes/fontes_publicas/orcamento/SIOPS_Itauna_2025_filtrado.csv
  CNES 07/2026 (eSF e ACS por UBS)          -> dados/fontes/fontes_publicas/ubs_recursos_cnes_202607.csv
  SICONFI RREO 2026 b4 Anexo 02             -> dados/fontes/fontes_publicas/orcamento/siconfi_rreo_2026_b4_anexo02.json
  Salarios, encargos e custo fixo por UBS   -> parametros do modelo (aps_base.py), hipoteses nao oficiais

Duas medidas, sempre separadas e nunca somadas:
  (A) TETO OBSERVADO (SIOPS 2025): Pessoal e Encargos Sociais da Atencao Basica. Inclui todo o pessoal da
      AB (equipes, odontologia, apoio, administrativo); o SIOPS nao separa equipes. E um limite superior.
  (B) ESTIMATIVA ASCENDENTE (modelo): Horas dos profissionais CNES / 40 x remuneracao de referencia; ACS separados.
      Nao inclui eSB, eAP, NASF/eMulti, vigilancia, medicamentos e transferencias de incentivo (sem dado).
Percentual = custo das equipes / orcamento da Atencao Primaria (dotacao atualizada), por fase da despesa.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

from caminhos import BASE, RESULTADOS, MODELOS
sys.path.insert(0, str(MODELOS))
from aps_base import CUSTO, CUSTO_ESF  # parametros de custo do modelo

SIOPS = BASE/'fontes_publicas/orcamento/SIOPS_Itauna_2025_filtrado.csv'
RREO = BASE/'fontes_publicas/orcamento/siconfi_rreo_2026_b4_anexo02.json'
FASES = ['Dotação Inicial', 'Dotação Atualizada', 'Despesas Empenhadas', 'Despesas Liquidadas', 'Despesas Pagas']
GRUPOS = {'3.0.00.00.00.00': 'Despesas correntes (total)', '3.1.00.00.00.00': 'Pessoal e encargos sociais',
          '3.3.00.00.00.00': 'Outras despesas correntes', '4.0.00.00.00.00': 'Despesas de capital'}
PESSOAL = {'3.1.90.04.00.00': 'Contratação por tempo determinado', '3.1.90.11.00.00': 'Vencimentos e vantagens fixas',
           '3.1.90.16.00.00': 'Outras despesas variáveis', '3.1.90.94.00.00': 'Indenizações e restituições trabalhistas',
           '3.1.90.99.00.00': 'A classificar'}


def reais(v):
    return 'R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def siops_ab():
    d = pd.read_csv(SIOPS)
    d = d[(d['Cód.Município'] == 313380) & (d['Ano'] == 2025) & d['Subfuncao'].str.contains('301 Atenção Básica')]
    if d.empty:
        raise ValueError('SIOPS sem a subfuncao 301 de Itauna/2025')
    return d


def tabela_grupos(d):
    x = d[d['Codigo'].isin(GRUPOS) & d['Fase'].isin(FASES)]
    t = x.pivot_table(index='Codigo', columns='Fase', values='Valor', aggfunc='sum')[FASES]
    t.index = [GRUPOS[c] for c in t.index]
    t.loc['TOTAL (correntes + capital)'] = t.loc['Despesas correntes (total)'].fillna(0) + t.loc['Despesas de capital'].fillna(0)
    return t.fillna(0.0)


def tabela_por_fonte(d):
    x = d[d['Codigo'].isin(['3.1.00.00.00.00', '3.0.00.00.00.00', '4.0.00.00.00.00']) & d['Fase'].isin(FASES)]
    x = x.assign(grupo=x['Codigo'].map({'3.1.00.00.00.00': 'Pessoal e encargos', '3.0.00.00.00.00': 'Correntes (total)', '4.0.00.00.00.00': 'Capital'}))
    return x.pivot_table(index=['Fonte', 'grupo'], columns='Fase', values='Valor', aggfunc='sum')[FASES].fillna(0.0)


def tabela_pessoal(d):
    x = d[d['Codigo'].isin(PESSOAL) & d['Fase'].isin(FASES[2:])]
    t = x.pivot_table(index='Codigo', columns='Fase', values='Valor', aggfunc='sum')[FASES[2:]].fillna(0.0)
    t.index = [PESSOAL[c] for c in t.index]
    return t


def rreo_ab():
    r = json.loads(RREO.read_text(encoding='utf-8'), parse_float=Decimal)
    out = {}
    for coluna in ['DOTAÇÃO INICIAL', 'DOTAÇÃO ATUALIZADA (a)', 'DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)', 'DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)']:
        v = [Decimal(str(i['valor'])) for i in r['items'] if i['conta'] == 'Atenção Básica' and i['coluna'] == coluna
             and i['cod_conta'] in ('RREO2TotalDespesas', 'RREO2TotalDespesasIntra')]
        if len(v) != 2:
            raise ValueError('RREO AB incompleto: ' + coluna)
        out[coluna] = float(sum(v))
    return out


def estimativa_ascendente():
    rec = pd.read_csv(BASE/'fontes_publicas/ubs_recursos_cnes_202607.csv', sep=';', encoding='utf-8-sig')
    esf, acs = float(rec['esf'].sum()), float(rec['acs_vinculos'].sum())
    from pessoal_cnes import total_atual
    pessoal = total_atual(CUSTO)
    fixo = len(rec)*CUSTO['ubs_existente']
    return dict(ubs=int(len(rec)), esf=esf, acs=acs, esb=float(rec['esb'].sum()), eap=float(rec['eap'].sum()),
                custo_esf_unit_mensal=CUSTO_ESF, custo_acs_unit_mensal=CUSTO['acs'], custo_fixo_ubs_unit_mensal=CUSTO['ubs_existente'],
                esf_anual=12*pessoal, acs_anual=12*acs*CUSTO['acs'], fixo_ubs_anual=12*fixo,
                equipes_anual=12*(pessoal+acs*CUSTO['acs']),
                equipes_mais_fixo_anual=12*(pessoal+acs*CUSTO['acs']+fixo))


def calcular(saida=None):
    saida = Path(saida) if saida else RESULTADOS/'financeiro'
    saida.mkdir(parents=True, exist_ok=True)
    d = siops_ab()
    grupos = tabela_grupos(d)
    fonte = tabela_por_fonte(d)
    pessoal = tabela_pessoal(d)
    asc = estimativa_ascendente()
    from pessoal_cnes import cadastro,CATEGORIAS
    detalhe=[]
    for _,r in cadastro().iterrows():
        for categoria,prefixo in CATEGORIAS.items():
            horas=float(r[prefixo+'_horas_cadastradas'])
            detalhe.append(dict(cnes=r['cnes'],nome=r['nome'],categoria=categoria,
                vinculos=r[prefixo+'_vinculos'],horas_semanais=horas,equivalentes_40h=horas/40,
                custo_unitario_40h=CUSTO['tecnico' if categoria=='auxiliar' else categoria],
                custo_mensal=horas/40*CUSTO['tecnico' if categoria=='auxiliar' else categoria],
                natureza='Estimativa; salarios e encargos de referencia, nao folha paga'))
    pd.DataFrame(detalhe).to_csv(saida/'pessoal_horas_por_ubs.csv',sep=';',index=False,encoding='utf-8-sig')
    rreo = rreo_ab()
    orc25 = grupos.loc['TOTAL (correntes + capital)', 'Dotação Atualizada']
    linhas = []
    # (A) teto observado - SIOPS 2025, mesma fase no numerador e no denominador de dotacao atualizada e de despesa total
    for fase in FASES[2:]:
        num = grupos.loc['Pessoal e encargos sociais', fase]
        linhas.append(dict(medida='A. Teto observado (SIOPS 2025): pessoal e encargos da AB', fase_numerador=fase, custo=num,
                           orcamento_referencia='Dotação atualizada AB 2025 (SIOPS)', orcamento=orc25, percentual=100*num/orc25))
        den = grupos.loc['TOTAL (correntes + capital)', fase]
        linhas.append(dict(medida='A. Teto observado (SIOPS 2025): pessoal e encargos da AB', fase_numerador=fase, custo=num,
                           orcamento_referencia=f'{fase} total da AB 2025 (SIOPS)', orcamento=den, percentual=100*num/den))
    # (B) estimativa ascendente com custos unitarios do modelo (precos 2026) contra o RREO 2026
    dot26 = rreo['DOTAÇÃO ATUALIZADA (a)']
    for nome, valor in [('Pessoal CNES + ACS', asc['equipes_anual']), ('Pessoal CNES + ACS + custo fixo das 22 UBS', asc['equipes_mais_fixo_anual'])]:
        linhas.append(dict(medida=f'B. Estimativa ascendente (modelo, CNES 07/2026): {nome}', fase_numerador='Custo anualizado (12 meses)', custo=valor,
                           orcamento_referencia='Dotação atualizada AB 2026 (RREO b4)', orcamento=dot26, percentual=100*valor/dot26))
        linhas.append(dict(medida=f'B. Estimativa ascendente (modelo, CNES 07/2026): {nome}', fase_numerador='Custo anualizado (12 meses)', custo=valor,
                           orcamento_referencia='Dotação inicial AB 2026 (RREO b4)', orcamento=rreo['DOTAÇÃO INICIAL'], percentual=100*valor/rreo['DOTAÇÃO INICIAL']))
        linhas.append(dict(medida=f'B. Estimativa ascendente (modelo, CNES 07/2026): {nome}', fase_numerador='Custo anualizado (12 meses)', custo=valor,
                           orcamento_referencia='Dotação atualizada AB 2025 (SIOPS) — comparação entre anos, apenas indicativa', orcamento=orc25, percentual=100*valor/orc25))
    res = pd.DataFrame(linhas)
    comprometido = asc['equipes_mais_fixo_anual']
    meta = dict(orcamento_ap_2025_siops_dotacao_atualizada=orc25, orcamento_ap_2026_rreo=rreo, ascendente=asc,
                despesa_total_ab_2025_empenhada_liquidada_paga={f: grupos.loc['TOTAL (correntes + capital)', f] for f in FASES[2:]},
                pessoal_ab_2025={f: grupos.loc['Pessoal e encargos sociais', f] for f in FASES},
                parametros_modelo_orcamento=dict(
                    orcamento_ap_anual=dot26, custo_comprometido_anual=comprometido,
                    disponivel_para_expansao_anual=dot26-comprometido,
                    comprometimento_adicional_conservador_anual=max(0.0, rreo['DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)']*12/8-comprometido),
                    nota_conservador='cenário conservador: toda a despesa empenhada da AB em jan-ago/2026, anualizada (x12/8), é compromisso; o que excede eSF+ACS+fixo das UBS entra como comprometimento adicional (não só equipes)'),
                limitacoes=[
                    'O SIOPS informa despesa por subfunção/natureza, não por equipe: não há como isolar eSF, ACS, eSB ou apoio. A medida A é um teto, não o custo das equipes.',
                    'A medida B usa salários e encargos HIPOTÉTICOS do modelo (preços 2026); não são folha de pagamento do município. Não inclui eSB, eAP, NASF/eMulti, vigilância, vacinas, medicamentos.',
                    'Incentivos e transferências do FNS (Previne Brasil/ custeio de equipes) não estão no arquivo SIOPS fornecido; os recursos federais entram apenas como fonte de financiamento das despesas, sem separar o incentivo por equipe.',
                    'Não há dado de remuneração efetiva (Portal da Transparência de Itaúna) neste projeto: custo de pessoal por categoria não foi levantado e não foi inventado.',
                    'Despesas empenhadas, liquidadas e pagas foram mantidas separadas. RREO 2026 cobre apenas jan–ago (4º bimestre): não comparar execução parcial com orçamento anual.',
                    'Pessoal temporário (3.1.90.04) e "A classificar" (3.1.90.99) estão dentro do total de pessoal; parte pode não ser de equipes.'])
    (saida/'custo_equipes_resumo.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=float), encoding='utf-8')
    res.to_csv(saida/'percentual_orcamento_comprometido.csv', sep=';', index=False, encoding='utf-8-sig', float_format='%.2f')
    grupos.to_csv(saida/'siops_ab_2025_por_grupo_e_fase.csv', sep=';', encoding='utf-8-sig', float_format='%.2f')
    fonte.to_csv(saida/'siops_ab_2025_por_fonte_e_fase.csv', sep=';', encoding='utf-8-sig', float_format='%.2f')
    pessoal.to_csv(saida/'siops_ab_2025_pessoal_detalhe.csv', sep=';', encoding='utf-8-sig', float_format='%.2f')
    t = ['CUSTO ATUAL DAS EQUIPES DA ATENCAO PRIMARIA - ITAUNA/MG', '',
         'ORCAMENTO DA ATENCAO PRIMARIA (subfuncao 301)',
         f'SIOPS 2025 - dotacao inicial: {reais(grupos.loc["TOTAL (correntes + capital)", "Dotação Inicial"])}; atualizada: {reais(orc25)}.',
         f'SIOPS 2025 - empenhada: {reais(grupos.loc["TOTAL (correntes + capital)", "Despesas Empenhadas"])}; liquidada: {reais(grupos.loc["TOTAL (correntes + capital)", "Despesas Liquidadas"])}; paga: {reais(grupos.loc["TOTAL (correntes + capital)", "Despesas Pagas"])}.',
         f'RREO 2026 (b4, jan-ago) - dotacao inicial: {reais(rreo["DOTAÇÃO INICIAL"])}; atualizada: {reais(dot26)}; empenhada ate agosto: {reais(rreo["DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)"])}; liquidada: {reais(rreo["DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)"])}.', '',
         'PESSOAL E ENCARGOS DA AB EM 2025 (SIOPS) - TETO, nao e o custo isolado das equipes']
    for f in FASES:
        t.append(f'  {f}: {reais(grupos.loc["Pessoal e encargos sociais", f])}')
    t += ['', 'PERCENTUAL DO ORCAMENTO COMPROMETIDO']
    for r in res.itertuples():
        t.append(f'  [{r.medida}] {r.fase_numerador} {reais(r.custo)} / {r.orcamento_referencia} {reais(r.orcamento)} = {r.percentual:.2f}%')
    t += ['', 'ESTIMATIVA ASCENDENTE (CNES 07/2026 x custos unitarios do modelo)',
          f'  Medicos, enfermagem, tecnicos e auxiliares: horas CNES / 40 x salarios de referencia x 12 = {reais(asc["esf_anual"])}',
          f'  {asc["acs"]:.0f} ACS (vinculos CNES) x {reais(CUSTO["acs"])}/mes x 12 = {reais(asc["acs_anual"])}',
          f'  Custo anual das equipes (Pessoal CNES + ACS) = {reais(asc["equipes_anual"])}',
          f'  Custo fixo das {asc["ubs"]} UBS ({reais(asc["custo_fixo_ubs_unit_mensal"])}/mes cada) = {reais(asc["fixo_ubs_anual"])}',
          f'  Outras categorias (odontologia, apoio e administracao) nao precificadas. Os vinculos das categorias consideradas podem pertencer a diferentes equipes; nao se soma custo de equipe novamente.', '',
          'COMPROMISSO PARA O MODELO (item 7)',
          f'  Orcamento AP anual (RREO 2026, dotacao atualizada): {reais(dot26)}',
          f'  Custo anual comprometido (Pessoal CNES + ACS + custo fixo das UBS existentes): {reais(comprometido)}',
           f'  Diferenca contabil antes das demais despesas da APS: {reais(dot26-comprometido)}',
           '  Essa diferenca nao e saldo livre: demais servicos e insumos da APS tambem consomem o orcamento.', '', 'LIMITACOES'] + ['  - '+l for l in meta['limitacoes']]
    (saida/'relatorio_custo_equipes.txt').write_text('\n'.join(t)+'\n', encoding='utf-8')
    print('\n'.join(t))
    return meta, res


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida', type=Path, default=RESULTADOS/'atual/financeiro')
    calcular(ap.parse_args().saida)
