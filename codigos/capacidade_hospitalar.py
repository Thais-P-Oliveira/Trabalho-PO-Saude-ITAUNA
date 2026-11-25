"""Leitos SUS cadastrados x dias do periodo, menos carga fixa de outros atendimentos.

O modelo usa um teto hospitalar agregado: internacao e UTI nao sao separados
por especialidade. A disponibilidade por 365 dias e uma hipotese de planejamento.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import re
import urllib.request

from caminhos import BASE, ENTRADA

PASTA = BASE / 'fontes_publicas/leitos_hospital_cnes'
URL = ('https://cnes2.datasus.gov.br/Cabecalho_Reduzido_Competencia.asp'
       '?VCod_Unidade=3133802105780&VComp=202607')
CARGA = BASE / 'cenarios_niveis/demanda_integrada/parametros_sus_2015/carga_hospitalar_observada_2025.csv'
PARAMETROS = BASE / 'cenarios_niveis/demanda_integrada/parametros_sus_2015/configuracao.json'


def ler_csv(caminho):
    with caminho.open(encoding='utf-8-sig', newline='') as arq:
        return list(csv.DictReader(arq, delimiter=';'))


def salvar_csv(caminho, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open('w', encoding='utf-8-sig', newline='') as arq:
        w = csv.DictWriter(arq, fieldnames=list(linhas[0]), delimiter=';')
        w.writeheader()
        w.writerows(linhas)


def extrair_leitos(pagina):
    """Le apenas a tabela de leitos; nao inclui camas das instalacoes de observacao."""
    comp = re.search(r'<option\s+value=["\x27]?(\d{6})["\x27]?\s+selected', pagina, re.I)
    if not comp or comp.group(1) != '202607':
        raise ValueError('Competencia da ficha diferente de julho/2026')
    if '2105780' not in pagina:
        raise ValueError('Hospital solicitado nao identificado')
    inicio = re.search(r'>\s*Leitos\s*<', pagina, re.I)
    if not inicio:
        raise ValueError('Tabela de leitos nao encontrada')
    trecho = pagina[inicio.start():]
    fim = re.search(r'>\s*Equipamentos\s*<', trecho, re.I)
    if not fim:
        raise ValueError('Final da tabela de leitos nao encontrado')
    trecho = trecho[:fim.start()]
    limpar = lambda s: ' '.join(html.unescape(re.sub('<[^>]+>', ' ', s)).split())
    linhas = []
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', trecho, re.I | re.S):
        c = [limpar(x) for x in re.findall(r'<td\b[^>]*>(.*?)</td>', tr, re.I | re.S)]
        if (len(c) == 4 and c[0].isdigit() and len(c[0]) == 2
                and re.fullmatch(r'\d+\*?', c[2]) and re.fullmatch(r'\d+\*?', c[3])):
            # A ficha deste hospital possui somente UTI entre os complementares.
            grupo = 'complementar_UTI' if c[1].startswith('UTI') else 'internacao'
            linhas.append(dict(cnes='2105780', competencia='202607', codigo_leito=c[0],
                               descricao=c[1], grupo=grupo, existentes=int(c[2].strip('*')),
                               sus=int(c[3].strip('*')), sus_texto_original=c[3], fonte=URL))
    if not linhas or len({r['codigo_leito'] for r in linhas}) != len(linhas):
        raise ValueError('Tabela de leitos vazia ou com codigos repetidos')
    if any(r['sus'] > r['existentes'] for r in linhas):
        raise ValueError('Leitos SUS superiores ao total cadastrado')
    return linhas


def capacidade_disponivel(leitos_sus, dias, carga_outros):
    """Devolve dias disponiveis e eventual excesso da carga fixa sobre a oferta."""
    if (not all(math.isfinite(v) for v in [leitos_sus, dias, carga_outros])
            or leitos_sus < 0 or dias <= 0 or carga_outros < 0):
        raise ValueError('Parametros hospitalares invalidos')
    bruto = leitos_sus * dias
    return bruto, max(bruto - carga_outros, 0), max(carga_outros - bruto, 0)


def preparar_capacidade():
    """Recalcula a reserva por residencia/carater e aplica o teto dos leitos SUS."""
    leitos = ler_csv(PASTA / 'leitos_sus_202607.csv')
    if not leitos or any(r['cnes'] != '2105780' or r['competencia'] != '202607' for r in leitos):
        raise ValueError('Cadastro de leitos do hospital/competencia inconsistente')
    carga = next(r for r in ler_csv(CARGA) if r['cnes'] == '2105780')
    tmp = json.loads(PARAMETROS.read_text(encoding='utf-8'))['tmp_dias']
    dias_nao_residentes = 0.0
    dias_residentes_nao_eletivos = 0.0
    for nivel, chave_tmp in [('media', 'hospitalar_media'), ('alta', 'hospitalar_alta')]:
        permanencia = float(tmp[chave_tmp])
        residentes = float(carga['residentes_' + nivel])
        eletivos = float(carga['residentes_eletivos_estimados_' + nivel])
        if eletivos < 0 or eletivos > residentes:
            raise ValueError('Estimativa eletiva inconsistente')
        dias_nao_residentes += float(carga['nao_residentes_' + nivel]) * permanencia
        dias_residentes_nao_eletivos += (residentes - eletivos) * permanencia
    reserva = dias_nao_residentes + dias_residentes_nao_eletivos
    gerais = sum(int(r['sus']) for r in leitos if r['grupo'] == 'internacao')
    uti = sum(int(r['sus']) for r in leitos if r['grupo'] == 'complementar_UTI')
    # Recursos separados: UTI nao aumenta o teto de internacao geral.
    bruto, disponivel, deficit = capacidade_disponivel(gerais, 365, reserva)
    # A carga dos outros atendimentos nao foi separada por tipo de leito.
    # Deduzir toda a carga dos gerais e um limite inferior conservador.
    superior = min(bruto, max(0, bruto + uti*365 - reserva))
    linha = dict(cnes='2105780', competencia_leitos='202607', dias_periodo=365,
                 leitos_sus_internacao=gerais, leitos_sus_uti=uti, leitos_sus_total=gerais + uti,
                 dias_capacidade_bruta=bruto, dias_uti_brutos=uti*365,
                 dias_gerais_disponiveis_inferior=disponivel, dias_gerais_disponiveis_superior=superior,
                 dias_uti_disponiveis=None, ocupacao_por_tipo_identificada=False,
                 dias_nao_residentes=dias_nao_residentes,
                 dias_residentes_nao_eletivos=dias_residentes_nao_eletivos,
                 dias_carga_outros=reserva, dias_disponiveis_modelo=disponivel,
                 deficit_carga_outros=deficit,
                 dias_disponiveis_metodo_anterior=float(carga['dias_livres_demanda_modelo']),
                 metodo='Gerais SUS x 365 menos toda a carga estimada: limite inferior conservador; UTI separada',
                 hipotese='Disponibilidade anual; sem reparticao da carga entre gerais e UTI. Intervalo de disponibilidade geral; cenario principal usa extremo conservador, nao ausencia comprovada de leitos livres',
                 reserva='Nao residentes SUS e residentes nao eletivos; eletivos locais estimados pela proporcao municipal por complexidade',
                 fonte_leitos=URL, fonte_carga=str(CARGA.relative_to(BASE)))
    salvar_csv(ENTRADA / 'capacidade_hospitalar_leitos.csv', [linha])
    return {'2105780': linha}


def coletar(consultar=False):
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / '2105780_202607.html'
    if consultar:
        with urllib.request.urlopen(URL, timeout=45) as resposta:
            arquivo.write_bytes(resposta.read())
    conteudo = arquivo.read_bytes()
    linhas = extrair_leitos(conteudo.decode('latin-1'))
    salvar_csv(PASTA / 'leitos_sus_202607.csv', linhas)
    fonte = dict(url=URL, competencia='202607', cnes='2105780',
                 consulta_utc=datetime.now(timezone.utc).isoformat(),
                 sha256_html=hashlib.sha256(conteudo).hexdigest(),
                 total_existentes=sum(r['existentes'] for r in linhas),
                 total_sus=sum(r['sus'] for r in linhas),
                 observacao='Leitos de internacao e complementares. Exclui observacao, repouso e camas de instalacoes ambulatoriais.')
    (PASTA / 'fonte.json').write_text(json.dumps(fonte, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coletar', action='store_true', help='Atualiza a ficha publica antes de calcular')
    args = parser.parse_args()
    coletar(args.coletar)
    print(json.dumps(preparar_capacidade(), ensure_ascii=False, indent=2))
