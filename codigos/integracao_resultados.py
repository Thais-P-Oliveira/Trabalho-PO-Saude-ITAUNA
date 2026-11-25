"""Fonte unica da cobertura e dos custos adicionais das equipes itinerantes."""
import json
import sys
from caminhos import MODELOS
sys.path.insert(0,str(MODELOS))
from pathlib import Path
import pandas as pd
from cobertura_efetiva import cobertura_efetiva, equipes_moveis, carregar_rede_atual


def custo_movel(resumo, custo_esf, custo_acs):
    """Pessoal adicional; transporte, veiculo e equipamentos nao possuem preco levantado."""
    mov = resumo['equipes_moveis']
    esf = mov['equipes'] * float(custo_esf)
    acs = mov['acs_necessarios'] * float(custo_acs)
    return dict(equipes=mov['equipes'], acs=mov['acs_necessarios'],
                equipes_mensal=esf, acs_mensal=acs, fixo_mensal=0.0,
                total_mensal=esf+acs, total_anual=12*(esf+acs),
                escopo='Pessoal adicional (eSF e ACS); veiculo, combustivel e equipamentos nao precificados')


def calcular_rede(pontos, rede, parametros, pasta_moveis=None):
    resumo, pp, pu, arcos = cobertura_efetiva(
        pontos, rede, parametros['raio'], parametros.get('raio_rural'),
        parametros['hab_esf'], 750.0, parametros['fator_rota'])
    from vinculos_moveis import ler_complemento
    salvo=ler_complemento(pasta_moveis,pp) if pasta_moveis is not None else None
    mov, bases, visitas, desc = salvo if salvo is not None else equipes_moveis(pontos, pp, rede)
    if len(bases):
        assert set(bases['id_ubs_base']).issubset(set(rede['id'])), 'Base movel fora da rede de UBS'
        assert len(visitas) == 0 or visitas['dist_base_km'].max() <= mov['raio_rota_km'] + 1e-6
    resumo['equipes_moveis'] = mov
    resumo['cobertura_efetiva_com_moveis_pct'] = 100*(resumo['pop_atendida_efetiva']+mov['atendida'])/resumo['populacao']
    return resumo, pp, pu, arcos, bases, visitas, desc


def integrar(plano):
    """Recalcula as duas redes com a mesma populacao, raios e capacidades."""
    plano = Path(plano)
    meta = json.loads((plano/'plano_aps.json').read_text(encoding='utf-8'))
    pontos = pd.read_csv(plano/'aps/demanda_cenario.csv', encoding='utf-8-sig')
    u = pd.read_csv(plano/'aps/ubs_completas.csv', encoding='utf-8-sig')
    rede = pd.DataFrame(dict(id=u.id_ubs, nome=u.nome, lat=u.lat, lon=u.lon,
                             esf=u.n_esf, acs=u.acs, status=u.status))
    pasta = plano/'aps/cobertura_efetiva'
    pasta.mkdir(parents=True, exist_ok=True)
    resumos = {}
    for rotulo, unidades in [('atual', carregar_rede_atual()), ('plano', rede)]:
        resumo, pp, pu, arcos, bases, visitas, desc = calcular_rede(pontos, unidades, meta['parametros'],plano/'vinculos_moveis' if rotulo=='plano' else None)
        for nome, df in [('por_ponto', pp), ('por_ubs', pu), ('alocacao', arcos),
                         ('moveis_bases', bases), ('moveis_visitas', visitas), ('moveis_pontos', desc)]:
            df.to_csv(pasta/f'{rotulo}_{nome}.csv', sep=';', index=False, encoding='utf-8-sig')
        (pasta/f'{rotulo}_resumo.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
        resumos[rotulo] = resumo
    resumos['plano']['pop_coberta_alocacao_escolhida'] = meta['cobertura']
    resumos['plano']['pop_coberta_potencial_rede'] = resumos['plano']['pop_atendida_efetiva']
    c = meta['custos']
    from aps_base import CUSTO_ESF, CUSTO
    unit_esf, unit_acs = CUSTO_ESF, CUSTO['acs']
    moveis = {r: custo_movel(s, unit_esf, unit_acs) for r, s in resumos.items()}
    total = c['operacional']+moveis['plano']['total_mensal']
    orc = c.get('orcamento', {})
    teto = orc.get('orcamento_ap_anual')
    adicional = float(orc.get('comprometimento_adicional_anual', 0))
    if teto is not None and total*12+adicional > float(teto)+0.01:
        raise ValueError('Operacao de UBS + equipes moveis excede o teto orcamentario; reveja o plano.')
    linhas = [dict(rede=r, populacao=s['populacao'], geografica_pct=s['cobertura_geografica_pct'],
                   efetiva_pct=s['cobertura_efetiva_pct'],
                   efetiva_com_moveis_pct=s['cobertura_efetiva_com_moveis_pct'],
                   equipes_moveis=moveis[r]['equipes'], acs_moveis=moveis[r]['acs']) for r,s in resumos.items()]
    pd.DataFrame(linhas).to_csv(pasta/'comparacao_cobertura.csv', sep=';', index=False, encoding='utf-8-sig')
    saida = dict(redes=resumos, custos_moveis=moveis, operacional_ubs_mensal=c['operacional'],
                 operacional_integrado_mensal=total, operacional_integrado_anual=total*12,
                 investimento_construcao=c['investimento_construcao'],
                 implantacao_integrada=total*12+c['investimento_construcao'],
                 custo_horizonte_integrado=c['investimento_construcao']+total*12*meta['parametros'].get('horizonte_anos',5),
                 nota='Rede atual + moveis e contrafactual; nao representa equipes ja existentes. '
                      'Movel e complemento posterior a APS; demanda especializada vinculada a UBS-base. '
                      'Orcamento e teto de autorizacao, nao saldo livre. Veiculos e transporte das moveis nao precificados.')
    comparacao=plano/'comparacao_completa.csv'
    if comparacao.exists():
        tab=pd.read_csv(comparacao,sep=';')
        tab['cobertura_aps_alocacao']=meta['cobertura']/meta['total']
        tab['cobertura_aps_potencial']=resumos['plano']['cobertura_efetiva_pct']/100
        tab['cobertura_aps']=tab['cobertura_aps_potencial']
        tab['custo_operacional_ubs_mensal']=c['operacional']
        tab['custo_pessoal_movel_mensal']=moveis['plano']['total_mensal']
        tab['custo_operacional_integrado_mensal']=total
        tab['proxy_deslocamento_aps_mensal']=c['deslocamento_proxy']
        tab['custo_mensal_aps']=total
        tab['escopo']='custo_mensal_aps = operacao UBS + pessoal movel; proxy separado; classificacao unica principal'
        tab.to_csv(comparacao,sep=';',index=False,encoding='utf-8-sig')
    (plano/'integracao.json').write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding='utf-8')
    texto=['RESULTADOS INTEGRADOS - UBS E COMPLEMENTO MOVEL',
           'Mesma populacao, distancias e capacidades nas duas redes.']
    for rotulo,r in resumos.items():
        texto.append(f"{rotulo}: geografica {r['cobertura_geografica_pct']:.4f}%; "
                     f"efetiva UBS {r['cobertura_efetiva_pct']:.4f}%; "
                     f"UBS + moveis propostas {r['cobertura_efetiva_com_moveis_pct']:.4f}%. "
                     f"Moveis adicionais: {moveis[rotulo]['equipes']} equipes e {moveis[rotulo]['acs']} ACS.")
    texto += [f"Operacao UBS: R$ {c['operacional']:.2f}/mes.",
              f"Pessoal movel adicional do plano: R$ {moveis['plano']['total_mensal']:.2f}/mes.",
              f"Operacao integrada: R$ {total:.2f}/mes; R$ {total*12:.2f}/ano.",
              f"Construcao separada: R$ {c['investimento_construcao']:.2f}.", saida['nota']]
    texto.append(f"Construcao + operacao integrada em {meta['parametros'].get('horizonte_anos',5):g} anos: "
                 f"R$ {saida['custo_horizonte_integrado']:.2f} (sem desconto/reajuste; nao e orcamento de um ano).")
    (plano/'relatorio_integrado.txt').write_text('\n'.join(texto)+'\n',encoding='utf-8')
    relatorio_ubs=plano/'aps/relatorio_itauna.txt'
    if relatorio_ubs.exists():
        conteudo=relatorio_ubs.read_text(encoding='utf-8')
        cabecalho='ESCOPO: UBS FIXAS, SEM O COMPLEMENTO MOVEL.\n'
        if not conteudo.startswith(cabecalho):
            relatorio_ubs.write_text(cabecalho+'Total integrado com pessoal movel: ../relatorio_integrado.txt\n\n'+conteudo,encoding='utf-8')
    return saida


def auditar_publicacao(pasta):
    """Impede publicar tabelas financeiras ou coberturas de execucoes distintas."""
    pasta=Path(pasta)
    dados=json.loads((pasta/'plano/integracao.json').read_text(encoding='utf-8'))
    financeiro=json.loads((pasta/'orcamento/calculos.json').read_text(encoding='utf-8'))
    esperado=dados['operacional_integrado_mensal']
    assert abs(float(financeiro['custo_aps_mensal'])-esperado)<.01
    assert abs(sum(float(g['total_mensal']) for g in financeiro['operacao_por_grupo'])-esperado)<.01
    assert abs(float(financeiro['total_ano_implantacao'])-dados['implantacao_integrada'])<.01
    redes=dados['redes']
    assert redes['atual']['populacao']==redes['plano']['populacao']
    for rotulo,r in redes.items():
        assert r['cobertura_efetiva_pct']<=r['cobertura_geografica_pct']+1e-6
        assert r['cobertura_efetiva_com_moveis_pct']<=100+1e-6
        assert r['equipes_moveis']['atendida']<=r['pop_sem_cobertura_geografica']+.01
        assert r['hab_esf']==redes['atual']['hab_esf'] and r['hab_acs']==redes['atual']['hab_acs']
        assert r['raio_km']==redes['atual']['raio_km'] and r['raio_rural_km']==redes['atual']['raio_rural_km']
    (pasta/'auditoria_resultados_integrados.json').write_text(json.dumps(
        dict(status='PASSOU',cobertura_comparavel=True,custos_moveis_incluidos=True,
             operacional_mensal=esperado,nota=dados['nota']),ensure_ascii=False,indent=2),encoding='utf-8')
