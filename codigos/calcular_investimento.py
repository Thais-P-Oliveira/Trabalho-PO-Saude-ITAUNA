"""Calcula a construcao do plano salvo sem modificar ou otimizar suas decisoes."""
import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from caminhos import BASE, RESULTADOS


def reais(valor):
    return 'R$ '+f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def calcular(plano=None, saida=None, percentuais=None):
    plano=Path(plano) if plano else RESULTADOS/'plano_referencia_2pct'
    saida=Path(saida) if saida else RESULTADOS/'investimento_construcao'
    meta=json.loads((plano/'plano_aps.json').read_text(encoding='utf-8'))
    if meta['status']!='plano_aps_validado':
        raise ValueError('O plano precisa estar validado')
    for nome, esperado in meta['arquivos'].items():
        if hashlib.sha256((plano/'aps'/nome).read_bytes()).hexdigest()!=esperado:
            raise ValueError('Arquivo do plano alterado: '+nome)
    with (BASE/'custos_construcao_ubs_2025.csv').open(encoding='utf-8',newline='') as f:
        custos={int(r['esf']):r for r in csv.DictReader(f)}
    with (plano/'aps/ubs_completas.csv').open(encoding='utf-8',newline='') as f:
        novas=[r for r in csv.DictReader(f) if r['status']=='NOVA']
    linhas=[]
    for r in novas:
        esf=int(r['n_esf'])
        if esf not in custos:
            raise ValueError('Porte sem referencia oficial: '+str(esf))
        linhas.append(dict(id_ubs=r['id_ubs'],nome=r['nome'],esf=esf,
                           porte=custos[esf]['porte'],valor_construcao=Decimal(custos[esf]['valor_construcao'])))
    investimento=sum((r['valor_construcao'] for r in linhas),Decimal(0))
    operacao=Decimal(str(meta['custos']['operacional']))*12
    cronograma=[]
    if percentuais is not None:
        parcelas=[Decimal(str(p)) for p in percentuais]
        if not parcelas or any(not p.is_finite() or p<0 for p in parcelas) or sum(parcelas)!=100:
            raise ValueError('Percentuais devem ser nao negativos e somar 100')
        # Exemplo de execucao por anos, sem juros ou reajuste, nao condicao contratual.
        restante=investimento
        for ano,pct in enumerate(parcelas,1):
            valor=(investimento*pct/100).quantize(Decimal('.01')) if ano<len(parcelas) else restante
            restante-=valor
            cronograma.append(dict(ano_relativo=ano,percentual=pct,desembolso_construcao=valor,
                natureza='Cenario ilustrativo; depende do cronograma fisico-financeiro e da previsao orcamentaria'))
    saida.mkdir(parents=True,exist_ok=True)
    def salvar(nome, registros):
        if not registros:return
        with (saida/nome).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(registros[0]),delimiter=';');w.writeheader();w.writerows(registros)
    salvar('construcao_por_ubs.csv',linhas)
    if cronograma:salvar('cronograma_ilustrativo.csv',cronograma)
    resultado=dict(plano=str(plano.resolve()),novas_ubs=len(novas),investimento_construcao=investimento,
        custo_operacional_anual_rede_implantada=operacao,otimizacao_alterada=False,
        fonte='Novo PAC Saude 2025, Sudeste, paginas 10-11',
        fonte_url='https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2025/manual-de-formalizacao-de-propostas-novo-pac-saude.pdf',
        cronograma_ilustrativo=cronograma,
        hipoteses=['Porte associado ao numero de eSF da nova UBS.',
            'Valores nominais de 2025, sem juros ou reajuste.',
            'Nao inclui terrenos, equipamentos ou mobiliario.',
            'Nao presume aprovacao ou repasse federal para as unidades propostas.',
            'Operacao anual refere-se a rede completa implantada; nao e gasto durante a obra.'])
    (saida/'calculos.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    texto=['INVESTIMENTO EM CONSTRUCAO - CALCULO SEPARADO DO MODELO','',
        'Plano mantido: '+str(plano.resolve()),
        f"Novas UBS: {len(novas)}; eSF: {sum(int(r['esf']) for r in linhas)}.",
        'Investimento total em construcao: '+reais(investimento)+'.',
        'Operacao anual da rede completa implantada (separada): '+reais(operacao)+'.',
        ('Construcao incluida no objetivo de cinco anos; folga somente operacional.' if 'custo_horizonte' in meta['custos'] else 'Plano historico: construcao calculada posteriormente.'),
        'Nao foi definido prazo contratual de pagamento nem atribuido o total a um ano especifico.','']
    if cronograma:
        texto+=['EXEMPLO DE DESEMBOLSO POR ANO - NAO E CRONOGRAMA APROVADO']
        texto += [f"Ano {r['ano_relativo']}: {r['percentual']}% = {reais(r['desembolso_construcao'])}." for r in cronograma]
        texto+=['Pagamentos dependem de etapas executadas e atestadas, contrato e regras orcamentarias.','']
    texto+=resultado['hipoteses']
    (saida/'relatorio.txt').write_text('\n'.join(texto)+'\n',encoding='utf-8')
    print('\n'.join(texto))
    return resultado


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plano',type=Path)
    ap.add_argument('--saida',type=Path)
    ap.add_argument('--percentuais',nargs='+',help='exemplo de distribuicao entre anos; deve somar 100')
    args=ap.parse_args();calcular(args.plano,args.saida,args.percentuais)
