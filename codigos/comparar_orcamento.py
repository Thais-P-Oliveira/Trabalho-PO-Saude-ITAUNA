"""Compara o custo operacional APS do plano de 2% com dados oficiais de 2026.

Uso: python comparar_orcamento.py
Le as fontes locais, sem alterar o plano nem impor nova restricao orcamentaria.
"""
import csv
import hashlib
import argparse
import json
from decimal import Decimal
from pathlib import Path

from caminhos import PASTA,BASE,RESULTADOS
FONTES = BASE/'fontes_publicas/orcamento'
LOA = 'https://sapl.itauna.mg.leg.br/media/sapl/public/normajuridica/2025/11182/lei_6273-2026_-_loa_2026.pdf'


def reais(v):
    return 'R$ '+f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def comparar(plano_pasta=None,saida_pasta=None):
    plano_path = (Path(plano_pasta) if plano_pasta else RESULTADOS/'atual/plano')/'plano_aps.json'
    plano = json.loads(plano_path.read_text(encoding='utf-8'))
    if plano['status'] != 'plano_aps_validado' or plano['parametros']['folga_custo'] != .02:
        raise ValueError('A comparacao requer o plano validado com folga de 2%')
    for nome, esperado in plano['arquivos'].items():
        if hashlib.sha256((plano_path.parent/'aps'/nome).read_bytes()).hexdigest() != esperado:
            raise ValueError('Arquivo do plano alterado: '+nome)
    fonte_path = FONTES/'siconfi_rreo_2026_b4_anexo02.json'
    resposta = json.loads(fonte_path.read_text(encoding='utf-8'), parse_float=Decimal)
    if resposta['hasMore']:
        raise ValueError('Resposta do Tesouro incompleta; falta paginacao')
    itens = resposta['items']
    if not itens or any(r['cod_ibge'] != 3133808 or r['exercicio'] != 2026 or r['periodo'] != 4 for r in itens):
        raise ValueError('Municipio ou periodo incorreto no RREO')
    colunas = ['DOTAÇÃO INICIAL', 'DOTAÇÃO ATUALIZADA (a)',
        'DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)', 'DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)']
    contas = ['Saúde', 'Atenção Básica', 'Assistência Hospitalar e Ambulatorial']
    linhas = []
    for conta in contas:
        for coluna in colunas:
            partes = []
            # Somam-se as duas categorias disjuntas, sem somar saude com subfuncoes.
            for codigo in ['RREO2TotalDespesas', 'RREO2TotalDespesasIntra']:
                registros = [r for r in itens if r['conta'] == conta and r['coluna'] == coluna and r['cod_conta'] == codigo]
                if len(registros) != 1:
                    raise ValueError(f'Registro ausente ou duplicado: {conta}, {coluna}, {codigo}')
                partes.append(Decimal(str(registros[0]['valor'])))
            linhas.append(dict(conta=conta, coluna=coluna, exceto_intra=partes[0],
                intra=partes[1], total= sum(partes)))
    from integracao_resultados import integrar
    integrado = integrar(plano_path.parent)
    mensal_ubs = Decimal(str(plano['custos']['operacional']))
    mensal = Decimal(str(integrado['operacional_integrado_mensal']))
    anual = mensal*12
    objetivo_anual = Decimal(str(plano['custos']['objetivo']))*12
    # Decompoe o funcionamento da rede inteira; as existentes nao sao acrescimo ao gasto atual.
    with (plano_path.parent/'aps/ubs_completas.csv').open(encoding='utf-8-sig',newline='') as f:
        unidades=list(csv.DictReader(f))
    custos=plano['custos']
    equipes=sum(Decimal(u['n_esf']) for u in unidades)
    agentes=sum(Decimal(u['acs']) for u in unidades)
    unit_esf=Decimal(str(custos['esf']))/equipes if equipes else Decimal(0)
    unit_acs=Decimal(str(custos['acs']))/agentes if agentes else Decimal(0)
    operacao_grupos=[]
    for status,rotulo,chave in [('EXISTENTE','UBS existentes','fixo_existentes'),('NOVA','UBS novas','fixo_novas')]:
        grupo=[u for u in unidades if u['status']==status]
        fixo=Decimal(str(custos[chave]))
        esf=sum((Decimal(u['custo_pessoal_sem_acs_mensal']) for u in grupo),Decimal(0))
        acs=sum((Decimal(u['acs'])*unit_acs for u in grupo),Decimal(0))
        operacao_grupos.append(dict(grupo=rotulo,unidades=len(grupo),fixo_mensal=fixo,
            equipes_mensal=esf,acs_mensal=acs,total_mensal=fixo+esf+acs,total_anual=12*(fixo+esf+acs)))
    if abs(sum(g['total_mensal'] for g in operacao_grupos)-mensal_ubs)>Decimal('.01'):
        raise ValueError('Decomposicao da operacao nao confere')
    mov = integrado['custos_moveis']['plano']
    operacao_grupos.append(dict(grupo='Equipes moveis adicionais', unidades=mov['equipes'],
        fixo_mensal=Decimal(0), equipes_mensal=Decimal(str(mov['equipes_mensal'])),
        acs_mensal=Decimal(str(mov['acs_mensal'])), total_mensal=Decimal(str(mov['total_mensal'])),
        total_anual=Decimal(str(mov['total_anual']))))
    if abs(sum(g['total_mensal'] for g in operacao_grupos)-mensal)>Decimal('.01'):
        raise ValueError('Total integrado nao confere')
    precos_path=BASE/'custos_construcao_ubs_2025.csv'
    with precos_path.open(encoding='utf-8-sig',newline='') as f:
        precos={int(x['esf']):Decimal(x['valor_construcao']) for x in csv.DictReader(f)}
    construcao=sum((precos[int(u['n_esf'])] for u in unidades if u['status']=='NOVA'),Decimal(0))
    if 'investimento_construcao' in custos and abs(construcao-Decimal(str(custos['investimento_construcao'])))>Decimal('.01'):
        raise ValueError('Construcao diferente do investimento otimizado')
    total_ano_implantacao=anual+construcao

    inicial_saude = next(r['total'] for r in linhas if r['conta']=='Saúde' and r['coluna']=='DOTAÇÃO INICIAL')
    # Valor conferido na pagina 7 da LOA aprovada, nao no projeto de lei.
    if inicial_saude != Decimal('173696487.13'):
        raise ValueError('Dotacao inicial do RREO difere da LOA aprovada')
    comparacoes = [dict(conta=r['conta'], referencia=r['coluna'],
        orcamento_anual=r['total'], custo_modelo_aps_anual=anual,
        proporcao_modelo_pct=100*anual/r['total'],
        investimento_construcao=construcao,total_ano_implantacao=total_ano_implantacao,
        proporcao_implantacao_pct=100*total_ano_implantacao/r['total']) for r in linhas
        if r['coluna'].startswith('DOTAÇÃO') and r['conta'] != 'Assistência Hospitalar e Ambulatorial']
    arquivos = [fonte_path, FONTES/'loa_2026_aprovada.pdf', plano_path,precos_path,plano_path.parent/'aps/ubs_completas.csv']
    meta = dict(plano=str(plano_path), folga_custo=.02,
        custo_aps_mensal=mensal, custo_aps_anual=anual,
        custo_ubs_sem_moveis_mensal=mensal_ubs, equipes_moveis=mov,
        operacao_por_grupo=operacao_grupos,investimento_construcao=construcao,
        total_ano_implantacao=total_ano_implantacao,
        hipotese_ano_implantacao='100% das obras e 12 meses de operacao da rede inteira no mesmo exercicio; cenario de comparacao, nao cronograma contratual',
        horizonte_otimizacao_anos=plano['parametros'].get('horizonte_anos',5),
        objetivo_com_proxy_anual=objetivo_anual,
        referencia_oficial='RREO 2026, 4o bimestre (janeiro a agosto), Anexo 02',
        fonte_rreo=(FONTES/'siconfi_rreo_2026_b4_anexo02_url.txt').read_text(encoding='utf-8').strip(),
        fonte_loa=LOA, dados_oficiais=linhas, comparacoes=comparacoes,
        sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in arquivos},
        limites=['Operacao e investimento da APS separados; valores estimados, nao despesas executadas.',
            'Custos unitarios do modelo sao premissas, sem atualizacao monetaria para 2026.',
            'Construcao incluida no cenario de implantacao; terrenos, equipamentos e outros servicos da atencao basica nao estao integralmente orcados.',
            'Nao inclui custo operacional da secundaria e terciaria.',
            'Dotacao atualizada nao e saldo livre nem garantia de disponibilidade financeira.',
            'Diferenca nao demonstra economia ou viabilidade financeira da implantacao.',
            'O modelo possui teto operacional; total com moveis e conferido antes da publicacao. Isso nao comprova saldo financeiro livre.',
            'Equipes moveis: inclui pessoal e encargos estimados; veiculo, combustivel e equipamentos nao precificados.'])
    saida = Path(saida_pasta) if saida_pasta else RESULTADOS/'orcamento'
    saida.mkdir(exist_ok=True)
    (saida/'calculos.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    texto = ['COMPARACAO ORCAMENTARIA - ITAUNA', '',
        'Plano: '+str(plano_path.parent)+'; folga operacional de 2%.',
        'Custo operacional planejado da APS: '+reais(mensal)+'/mes; '+reais(anual)+'/ano.',
        'Inclui todas as UBS do plano, existentes e novas, equipes, ACS e pessoal das equipes moveis adicionais.',
        'Nao somar esse custo ao gasto atual da prefeitura: ha despesas sobrepostas.',
        'Proxy de deslocamento excluido da comparacao principal. Objetivo anual com proxy: '+reais(objetivo_anual)+'.', '',
        'ORCAMENTO E EXECUCAO OFICIAIS - 2026',
        'Fonte: Tesouro Nacional/Siconfi, RREO Anexo 02, 4o bimestre.',
        'Soma das despesas exceto intraorcamentarias e intraorcamentarias, apresentadas separadamente no RREO.',
        'Dotacao inicial: orcamento de abertura do ano. Atualizada: autorizacao anual ate agosto.',
        'Empenhadas e liquidadas: valores acumulados ate agosto; nao sao totais de um ano completo.', '']
    detalhamento=['DETALHAMENTO DO FUNCIONAMENTO - TODA A REDE']
    for g in operacao_grupos:
        detalhamento.append(f"{g['grupo']} ({g['unidades']}): {reais(g['total_mensal'])}/mes; {reais(g['total_anual'])}/ano.")
    detalhamento += ['Total mensal da rede: '+reais(mensal)+'.',
        'Total anual de funcionamento: '+reais(anual)+'.',
        'Construcao das novas UBS, uma unica vez: '+reais(construcao)+'.',
        'ANO DE IMPLANTACAO: operacao anual + construcao = '+reais(total_ano_implantacao)+'.',
        'Hipotese: obras integralmente pagas no exercicio e 12 meses de funcionamento da rede implantada.',
        'Nao representa cronograma de entrada em funcionamento. Se a obra atravessar anos, distribuir o investimento pelo cronograma.',
        'Os cinco anos pertencem a otimizacao; nao sao comparados ao orcamento de um unico ano.', '']
    texto[2:2]=detalhamento
    for conta in contas:
        texto.append(conta.upper())
        for r in linhas:
            if r['conta']==conta:
                texto.append(r['coluna']+': '+reais(r['total']))
        texto.append('')
    texto += ['PROPORCAO DO CUSTO ANUAL APS DO MODELO EM RELACAO AO ORCAMENTO',
        'A proporcao em relacao a saude total e apenas contexto, pois os escopos sao diferentes.']
    for r in comparacoes:
        texto.append(f'{r["conta"]} / {r["referencia"]}: operacao {r["proporcao_modelo_pct"]:.2f}%; operacao + construcao {r["proporcao_implantacao_pct"]:.2f}%.')
    texto += ['', 'LOA APROVADA',
        'Lei 6.273, de 30/12/2025: funcao 10 - Saude = R$ 173.696.487,13 (pagina 7).',
        'Pagina 11: atencao basica R$ 29.559.322,78 e hospitalar/ambulatorial R$ 48.719.944,27',
        'integram o quadro de aplicacao com RECURSOS PROPRIOS. Nao sao o orcamento total dessas subfuncoes.',
        'O total de recursos proprios desse quadro e R$ 94.711.487,05, nao toda a saude.',
        'Nao usar o projeto de lei como substituto da LOA aprovada; houve emendas/veto.', '',
        'COMO INTERPRETAR']+meta['limites']+['', 'FONTES', LOA, meta['fonte_rreo']]
    def tabela(nome,registros):
        with (saida/nome).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(registros[0]),delimiter=';');w.writeheader();w.writerows(registros)
    tabela('funcionamento_existentes_e_novas.csv',operacao_grupos)
    tabela('comparacao_orcamentaria.csv',comparacoes)
    tabela('resumo_financeiro.csv',[
        dict(componente='Operacao mensal da rede',valor=mensal,periodo='mensal'),
        dict(componente='Operacao anual da rede',valor=anual,periodo='anual'),
        dict(componente='Construcao novas UBS',valor=construcao,periodo='investimento unico'),
        dict(componente='Operacao anual + construcao integral',valor=total_ano_implantacao,periodo='cenario ano implantacao')])
    (saida/'relatorio.txt').write_text('\n'.join(texto)+'\n',encoding='utf-8')
    print('\n'.join(texto[:8]))
    for r in comparacoes:
        print(r['conta'],r['referencia'],reais(r['orcamento_anual']),f'{r["proporcao_modelo_pct"]:.2f}%')
    print('Arquivos salvos:',saida)
    return meta


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plano',type=Path)
    ap.add_argument('--saida',type=Path)
    args=ap.parse_args()
    comparar(args.plano,args.saida)
