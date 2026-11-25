"""Consulta a estrutura cadastrada das 22 UBS, sem alterar os modelos.

Consultorios cadastrados nao equivalem automaticamente ao limite de eSF.
O limite fisico confirmado permanece vazio quando nao ha documento que o informe.
"""
import argparse
import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def texto(fragmento):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', fragmento)).split())


def extrair(pagina):
    # Extrai somente as linhas da secao de instalacoes fisicas.
    inicio = re.search(r'Instala.{0,25}F.sicas para Assist.ncia', pagina, re.I)
    if not inicio:
        raise ValueError('Secao de instalacoes fisicas nao encontrada')
    trecho = pagina[inicio.end():]
    fim = re.search(r'Servi.{0,12}os de Apoio', trecho, re.I)
    if not fim:
        raise ValueError('Final da secao de instalacoes nao encontrado')
    trecho = trecho[:fim.start()]
    linhas = []
    ambito = ''
    for linha in re.findall(r'<tr\b[^>]*>(.*?)</tr>', trecho, re.I | re.S):
        celulas = [texto(c) for c in re.findall(r'<td\b[^>]*>(.*?)</td>', linha, re.I | re.S)]
        rotulo = unicodedata.normalize('NFKD', texto(linha)).encode('ascii', 'ignore').decode()
        if rotulo in ['AMBULATORIAL', 'URGENCIA E EMERGENCIA', 'HOSPITALAR']:
            ambito = rotulo
        if len(celulas) == 3 and celulas[1].isdigit() and celulas[2].isdigit():
            linhas.append({'ambito': ambito, 'instalacao': celulas[0], 'quantidade': int(celulas[1]),
                           'leitos_equipos': int(celulas[2])})
    if not linhas:
        raise ValueError('Nenhuma linha de ambientes reconhecida; revisar o HTML')
    seletor = re.search(r'<select\b[^>]*name="cboCompetencia"[^>]*>(.*?)</select>', pagina, re.I | re.S)
    competencia = ''
    if seletor:
        selecionado = re.search(r'<option\s+value=["\x27]?(\d{6})["\x27]?\s+selected', seletor.group(1), re.I)
        if selecionado:
            competencia = selecionado.group(1)
    return linhas, competencia


def gravar_csv(caminho, linhas):
    with caminho.open('w', encoding='utf-8-sig', newline='') as arq:
        w = csv.DictWriter(arq, fieldnames=list(linhas[0]), delimiter=';')
        w.writeheader()
        w.writerows(linhas)


def gerar_relatorio(destino):
    """Apresenta todas as instalacoes declaradas; nao estima capacidade fisica."""
    with (destino / 'estrutura_22_ubs.csv').open(encoding='utf-8-sig') as arq:
        unidades = list(csv.DictReader(arq, delimiter=';'))
    with (destino / 'instalacoes_detalhadas.csv').open(encoding='utf-8-sig') as arq:
        ambientes = list(csv.DictReader(arq, delimiter=';'))
    nomes = {'CLINICAS BASICAS': 'Consultórios de clínicas básicas',
             'CLINICAS ESPECIALIZADAS': 'Consultórios de clínicas especializadas',
             'ODONTOLOGIA': 'Consultórios odontológicos',
             'OUTROS CONSULTORIOS NAO MEDICOS': 'Outros consultórios não médicos',
             'SALA DE CURATIVO': 'Salas de curativo',
             'SALA DE ENFERMAGEM (SERVICOS)': 'Salas de enfermagem',
             'SALA DE IMUNIZACAO': 'Salas de vacinação',
             'SALA DE NEBULIZACAO': 'Salas de nebulização',
             'CONSULTORIOS MEDICOS': 'Consultórios médicos',
             'SALA REPOUSO/OBSERVACAO - INDIFERENCIADO': 'Salas de repouso/observação — indiferenciado'}
    setores = {'AMBULATORIAL': 'Ambulatório', 'URGENCIA E EMERGENCIA': 'Urgência e emergência',
               'HOSPITALAR': 'Hospitalar'}
    totais = Counter()
    for a in ambientes:
        totais[(a['ambito'], a['instalacao'])] += int(a['quantidade'])
    resumo = ''.join(f'<tr><td>{html.escape(setores.get(s, s))}</td>'
                     f'<td>{html.escape(nomes.get(n, n))}</td><td class="numero">{q}</td></tr>'
                     for (s, n), q in sorted(totais.items()))
    cartoes = []
    for unidade in unidades:
        linhas = []
        for a in ambientes:
            if a['cnes'] != unidade['cnes']:
                continue
            linhas.append(f'<tr><td>{html.escape(setores.get(a["ambito"], a["ambito"]))}</td>'
                          f'<td>{html.escape(nomes.get(a["instalacao"], a["instalacao"]))}</td>'
                          f'<td class="numero">{int(a["quantidade"])}</td>'
                          f'<td class="numero">{int(a["leitos_equipos"])}</td></tr>')
        cartoes.append(f'<section class="unidade"><h2>{html.escape(unidade["nome"])}</h2>'
                       f'<p>CNES {unidade["cnes"]} · {unidade["esf_cadastradas_202607"]} eSF cadastrada(s) · '
                       f'Competência {unidade["competencia_exibida"][4:]}/{unidade["competencia_exibida"][:4]}</p>'
                       '<div class="rolagem"><table><thead><tr><th>Âmbito</th><th>Ambiente cadastrado</th>'
                       '<th>Quantidade</th><th>Leitos/equipos*</th></tr></thead><tbody>'
                       + ''.join(linhas) + '</tbody></table></div>'
                       f'<p><a href="{html.escape(unidade["fonte"], quote=True)}">Ficha oficial do CNES</a> · '
                       f'<a href="../dados/fontes/fontes_publicas/estrutura_ubs_cnes/fichas/{unidade["cnes"]}.html">Cópia consultada</a></p></section>')
    pagina = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Estrutura cadastrada das 22 UBS de Itaúna</title>
<style>body{margin:0;background:#f3f5fa;color:#202944;font:16px/1.55 system-ui,sans-serif}
main{max-width:1050px;margin:auto;padding:24px}header,section{background:white;border-radius:12px;padding:24px;margin-bottom:20px}
h1{font-size:30px;line-height:1.2}h2{font-size:21px}a{color:#214da6}table{width:100%;border-collapse:collapse}
th,td{padding:10px 12px;border-bottom:1px solid #dce2ec;text-align:left}th{background:#edf2fc}tr:nth-child(even){background:#f7f9fc}
.numero{text-align:right;font-variant-numeric:tabular-nums}.nota{padding:14px;background:#fff7df;border-left:4px solid #c49831}
.rolagem{overflow:auto}input{box-sizing:border-box;width:100%;font:inherit;padding:12px;border:1px solid #98a7be;border-radius:7px}
[hidden]{display:none!important}@media print{body{background:white}main{padding:0}header,section{padding:12px 0;border-radius:0}
.busca,.voltar{display:none}section{break-inside:avoid}a{color:inherit}}</style>
<main><header><p class="voltar"><a href="../ABRIR_RESULTADOS.html">← Resultados do projeto</a></p>
<h1>Estrutura cadastrada das 22 UBS de Itaúna</h1>
<p>Fonte: CNES/DATASUS · competência julho/2026 · consulta em 17/11/2026.</p>
<p>Todas as categorias de instalações físicas para assistência encontradas nas fichas das 22 unidades.
As quantidades abaixo são ambientes declarados no cadastro, separados por âmbito.</p>
<p class="nota">O CNES consultado não é um inventário completo do prédio: recepção, banheiros, copa,
áreas administrativas e outros espaços podem não aparecer. Ausência de registro não comprova inexistência.
As categorias não foram convertidas em porte ou limite máximo de equipes. Também não se presume que ambientes
de categorias ou âmbitos diferentes sejam sempre espaços físicos distintos.</p>
<p><a href="../dados/fontes/fontes_publicas/estrutura_ubs_cnes/instalacoes_detalhadas.csv">Dados completos em CSV</a> ·
<a href="../dados/fontes/fontes_publicas/estrutura_ubs_cnes/fontes.json">Fontes e identificação das fichas</a></p>
<h2>Quantidades por categoria nas 22 UBS</h2><div class="rolagem"><table><thead><tr><th>Âmbito</th>
<th>Ambiente cadastrado</th><th>Quantidade</th></tr></thead><tbody>''' + resumo + '''</tbody></table></div>
<p>* “Leitos/equipos” reproduz a coluna original do CNES. Não representa salas adicionais nem número de equipes.
Os valores foram preservados como declarados, sem reinterpretar categorias.</p>
<div class="busca"><label for="buscar"><strong>Localizar UBS por nome ou CNES</strong></label>
<input id="buscar" type="search" placeholder="Ex.: Central, Graças ou 2161028"><p id="contagem" aria-live="polite">22 unidades</p></div>
</header>''' + ''.join(cartoes) + '''</main><script>
const normalizar=t=>t.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
document.getElementById('buscar').addEventListener('input',e=>{
const filtro=normalizar(e.target.value.trim());let visiveis=0;
document.querySelectorAll('.unidade').forEach(s=>{s.hidden=!normalizar(s.querySelector('h2').textContent+' '+s.querySelector('p').textContent).includes(filtro);if(!s.hidden)visiveis++;});
document.getElementById('contagem').textContent=visiveis+' de 22 unidades';});</script></html>'''
    saida = ROOT / 'resultados/estrutura_fisica_ubs.html'
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(pagina, encoding='utf-8')
    print('Relatório completo:', saida, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--competencia', default='202607')
    parser.add_argument('--somente-relatorio', action='store_true', help='Usa os dados já coletados, sem internet')
    args = parser.parse_args()
    destino = ROOT / 'dados/fontes/fontes_publicas/estrutura_ubs_cnes'
    if args.somente_relatorio:
        gerar_relatorio(destino)
        return
    brutos = destino / 'fichas'
    brutos.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'dados/fontes/fontes_publicas/ubs_recursos_cnes_202607.csv').open(encoding='utf-8-sig') as arq:
        unidades = list(csv.DictReader(arq, delimiter=';'))

    def consultar(unidade):
        codigo = unidade['cnes']
        url = ('https://cnes2.datasus.gov.br/Cabecalho_Reduzido_Competencia.asp'
               f'?VCod_Unidade=313380{codigo}&VComp={args.competencia}')
        erro = None
        for tentativa in range(3):
            try:
                with urllib.request.urlopen(url, timeout=45) as resposta:
                    conteudo = resposta.read()
                pagina = conteudo.decode('latin-1')
                ambientes, competencia = extrair(pagina)
                if codigo not in texto(pagina):
                    raise ValueError('CNES solicitado nao identificado na pagina')
                (brutos / f'{codigo}.html').write_bytes(conteudo)
                por_nome = {a['instalacao']: a['quantidade'] for a in ambientes
                            if a['ambito'] == 'AMBULATORIAL'}
                linha = {'cnes': codigo, 'nome': unidade['nome'],
                         'competencia_solicitada': args.competencia,
                         'competencia_exibida': competencia,
                         'esf_cadastradas_202607': int(unidade['esf']),
                         'consultorios_clinicas_basicas': por_nome.get('CLINICAS BASICAS', ''),
                         'consultorios_odontologia': por_nome.get('ODONTOLOGIA', ''),
                         'outros_consultorios_nao_medicos': por_nome.get('OUTROS CONSULTORIOS NAO MEDICOS', ''),
                         'salas_enfermagem': por_nome.get('SALA DE ENFERMAGEM (SERVICOS)', ''),
                         'salas_imunizacao': por_nome.get('SALA DE IMUNIZACAO', ''),
                         'porte_fisico_documentado': '', 'limite_esf_fisico_confirmado': '',
                         'situacao_limite': 'nao_identificado_na_ficha', 'fonte': url}
                print(codigo, unidade['nome'], 'competencia:', competencia,
                      'clinicas basicas:', linha['consultorios_clinicas_basicas'], flush=True)
                return linha, ambientes, {'cnes': codigo, 'url': url,
                        'sha256_html': hashlib.sha256(conteudo).hexdigest(),
                        'competencia_exibida': competencia}
            except Exception as exc:
                erro = exc
                time.sleep(1 + tentativa)
        raise RuntimeError(f'Falha ao consultar {codigo}: {erro}')

    with ThreadPoolExecutor(max_workers=3) as executor:
        resultados = list(executor.map(consultar, unidades))
    resumo = [r[0] for r in resultados]
    detalhe = [dict(cnes=r[0]['cnes'], nome=r[0]['nome'], **ambiente)
               for r in resultados for ambiente in r[1]]
    gravar_csv(destino / 'estrutura_22_ubs.csv', resumo)
    gravar_csv(destino / 'instalacoes_detalhadas.csv', detalhe)
    manifesto = {'consulta_utc': datetime.now(timezone.utc).isoformat(),
                 'competencia_solicitada': args.competencia,
                 'quantidade_unidades': len(resumo),
                 'observacao': 'Competencia exibida deve ser conferida; nao inferir porte ou maximo de equipes apenas das salas.',
                 'fontes': [r[2] for r in resultados]}
    (destino / 'fontes.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Dados coletados em:', destino, flush=True)
    gerar_relatorio(destino)


if __name__ == '__main__':
    main()
