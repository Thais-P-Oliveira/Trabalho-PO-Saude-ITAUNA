"""Cobertura geografica e acessibilidade espacial da rede atual e do plano APS.

Uso independente: python diagnosticar.py [--plano resultados_sequenciais]
O calculo tambem e chamado pela APS ao terminar uma nova otimizacao.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
from collections import deque
from pathlib import Path

from caminhos import PASTA,BASE,ENTRADA,RESULTADOS


def ler(caminho, separador=','):
    with Path(caminho).open(encoding='utf-8-sig', newline='') as arquivo:
        return list(csv.DictReader(arquivo, delimiter=separador))


def salvar(caminho, linhas):
    if not linhas:
        return
    with Path(caminho).open('w', encoding='utf-8-sig', newline='') as arquivo:
        w = csv.DictWriter(arquivo, fieldnames=list(linhas[0]), delimiter=';')
        w.writeheader()
        w.writerows(linhas)


def distancia(a, b):
    """Haversine em km, com o mesmo raio terrestre usado na APS."""
    x, y = map(math.radians, [float(a['lat']), float(b['lat'])])
    h = math.sin((x-y)/2)**2 + math.cos(x)*math.cos(y)*math.sin(
        math.radians(float(a['lon'])-float(b['lon']))/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def zona(ponto):
    # Mesma identificacao rural utilizada na abertura de novas UBS.
    return 'rural' if '(rural)' in str(ponto['NM_BAIRRO']).lower() else 'urbana'


def acessibilidade(populacoes, capacidades, distancias, beta, distancia_minima):
    """Formula gravitacional ajustada pela demanda apresentada na Aula 8.

    V_j = soma_k P_k / d_kj^beta
    A_i = soma_j S_j / (d_ij^beta V_j)
    O piso de distancia evita divisao por zero em pontos coincidentes.
    Nao ha corte de 3 km nessa formula; o raio pertence ao indicador de cobertura.
    """
    if beta <= 0 or distancia_minima <= 0:
        raise ValueError('Beta e distancia minima devem ser positivos')
    pesos = [[1 / max(d, distancia_minima)**beta for d in linha] for linha in distancias]
    concorrencia = [sum(p*w[j] for p, w in zip(populacoes, pesos)) for j in range(len(capacidades))]
    ajustado = [sum(s*w/v for s, w, v in zip(capacidades, linha, concorrencia) if v > 0) for linha in pesos]
    simples = [sum(s*w for s, w in zip(capacidades, linha)) for linha in pesos]
    # Identidade da formula: soma_i P_i A_i = soma_j S_j.
    if not math.isclose(sum(p*a for p, a in zip(populacoes, ajustado)),
                        sum(capacidades), rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError('Falha na conservacao da oferta no indice de acessibilidade')
    return ajustado, simples, concorrencia


def cobertura_capacitada(populacoes, capacidades, distancias, raio):
    """Fluxo maximo: maior populacao alocavel dentro do raio, sem exceder oferta.

    Diagnostico com equipes atuais fixas. Nao abre UBS nem contrata equipes.
    A alocacao e fracionada, como no modelo de planejamento.
    """
    m, n = len(populacoes), len(capacidades)
    raios=[float(raio)]*m if isinstance(raio,(int,float)) else list(raio)
    if len(raios)!=m or any(not math.isfinite(v) or v<=0 for v in raios):
        raise ValueError('Raio invalido por ponto')
    fonte, destino = m+n, m+n+1
    residual = [dict() for _ in range(m+n+2)]
    def arco(a, b, capacidade):
        residual[a][b] = float(capacidade)
        residual[b][a] = 0.0
    for i, p in enumerate(populacoes):
        arco(fonte, i, p)
        for j in range(n):
            if distancias[i][j] <= raios[i] + 1e-9:
                arco(i, m+j, p)
    for j, s in enumerate(capacidades):
        arco(m+j, destino, s)
    total = 0.0
    while True:
        anterior = {fonte: None}
        fila = deque([fonte])
        while fila and destino not in anterior:
            a = fila.popleft()
            for b, valor in residual[a].items():
                if valor > 1e-8 and b not in anterior:
                    anterior[b] = a
                    fila.append(b)
        if destino not in anterior:
            break
        incremento, b = float('inf'), destino
        while b != fonte:
            a = anterior[b]
            incremento = min(incremento, residual[a][b])
            b = a
        b = destino
        while b != fonte:
            a = anterior[b]
            residual[a][b] -= incremento
            residual[b][a] += incremento
            b = a
        total += incremento
    return total


def gerar_diagnostico(pontos, existentes, plano, saida, raio=3, fator_rota=1,
                      hab_esf=3000, folga_custo=None, betas=(1, 2), distancia_minima=0.1,
                      raio_rural=None):
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    if raio <= 0 or fator_rota <= 0 or hab_esf <= 0 or not pontos or not existentes:
        raise ValueError('Diagnostico requer pontos, unidades e parametros positivos')
    raio_rural=raio if raio_rural is None else raio_rural
    if not math.isfinite(raio_rural) or raio_rural<=0:raise ValueError('Raio rural invalido')
    raios=[raio_rural if zona(p)=='rural' else raio for p in pontos]
    regra_raio=f'{raio:g} km urbano / {raio_rural:g} km rural'
    recursos = ler(BASE/'fontes_publicas/ubs_recursos_cnes_202607.csv', ';')
    por_cnes = {r['cnes']: r for r in recursos}
    atual = []
    for u in existentes:
        cnes = str(u['cnes'])
        if cnes not in por_cnes:
            raise ValueError('Faltam equipes CNES para '+cnes)
        r = por_cnes[cnes]
        atual.append(dict(id=cnes, nome=u['nome_fantasia'], lat=u['lat'], lon=u['lon'],
            esf=float(r['esf']), acs=float(r['acs_vinculos'])))
    redes = {'atual_cnes_202607': atual}
    if plano is not None:
        redes['plano_salvo'] = [dict(id=u['id_ubs'], nome=u['nome'], lat=u['lat'], lon=u['lon'],
                                    esf=float(u['n_esf']), acs=float(u['acs'])) for u in plano]
    pop = [float(p['pessoas']) for p in pontos]
    if any(p <= 0 for p in pop):
        raise ValueError('Populacoes precisam ser positivas')
    cobertura, indices, oferta, dist_por_ponto, limites, indices_zona = [], [], [], [], [], []
    for nome, unidades in redes.items():
        D = [[distancia(p, u)*fator_rota for u in unidades] for p in pontos]
        S = [hab_esf*u['esf'] for u in unidades]
        for i,(p, linha) in enumerate(zip(pontos, D)):
            j = min(range(len(unidades)), key=lambda j: linha[j])
            dist_por_ponto.append(dict(rede=nome, i=p['i'], nome=p['NM_BAIRRO'], zona=zona(p),
                populacao=float(p['pessoas']), ubs_mais_proxima=unidades[j]['nome'],
                distancia_km=linha[j], raio_km=raios[i], dentro_raio=int(linha[j] <= raios[i]+1e-9)))
        for grupo in ['total', 'urbana', 'rural']:
            pp = [i for i, p in enumerate(pontos) if grupo == 'total' or zona(p) == grupo]
            N = sum(pop[i] for i in pp)
            proximas = [min(D[i]) for i in pp]
            coberta = sum(pop[i] for i in pp if min(D[i]) <= raios[i]+1e-9)
            ordenados = sorted((min(D[i]), pop[i]) for i in pp)
            acumulada, p90 = 0, 0
            for d, p in ordenados:
                acumulada += p
                p90 = d
                if acumulada >= .9*N:
                    break
            cobertura.append(dict(rede=nome, zona=grupo, raio_km=raio_rural if grupo=='rural' else (raio if grupo=='urbana' or raio==raio_rural else None),
                raio_urbano_km=raio,raio_rural_km=raio_rural, pontos=len(pp),
                populacao=N, populacao_no_raio=coberta, populacao_fora_raio=N-coberta,
                cobertura_populacao_pct=100*coberta/N if N else None,
                pontos_no_raio=sum(min(D[i]) <= raios[i]+1e-9 for i in pp),
                cobertura_pontos_pct=100*sum(min(D[i]) <= raios[i]+1e-9 for i in pp)/len(pp) if pp else None,
                distancia_media_km=sum(pop[i]*min(D[i]) for i in pp)/N if N else None,
                distancia_p90_km=p90 if pp else None, distancia_maxima_km=max(proximas) if pp else None))
        for beta in betas:
            A, simples, V = acessibilidade(pop, S, D, beta, distancia_minima)
            referencia = sum(S)/sum(pop)
            for i, p in enumerate(pontos):
                indices.append(dict(rede=nome, beta=beta, distancia_minima_km=distancia_minima,
                    i=p['i'], nome=p['NM_BAIRRO'], zona=zona(p), populacao=pop[i],
                    acessibilidade_ajustada=A[i], acessibilidade_relativa=A[i]/referencia if referencia else None,
                    acessibilidade_sem_ajuste=simples[i]))
            for j, u in enumerate(unidades):
                oferta.append(dict(rede=nome, beta=beta, id=u['id'], nome=u['nome'], esf=u['esf'],
                    capacidade_habitantes=S[j], concorrencia_ponderada=V[j]))
            for grupo in ['total', 'urbana', 'rural']:
                pp = [i for i, p in enumerate(pontos) if grupo == 'total' or zona(p) == grupo]
                N = sum(pop[i] for i in pp)
                media = sum(pop[i]*A[i] for i in pp)/N if N else None
                indices_zona.append(dict(rede=nome, beta=beta, zona=grupo, populacao=N,
                    acessibilidade_media_ponderada=media,
                    acessibilidade_relativa_media=media/referencia if N and referencia else None,
                    minimo=min((A[i] for i in pp), default=None), maximo=max((A[i] for i in pp), default=None)))
        # Limite capacitado so para o diagnostico atual, nao substitui cobertura oficial.
        if nome.startswith('atual'):
            for criterio, capacidade in [('esf', S), ('esf_e_acs', [min(s, 750*u['acs']) for s, u in zip(S, unidades)])]:
                valor = cobertura_capacitada(pop, capacidade, D, raios)
                limites.append(dict(rede=nome, criterio=criterio, capacidade_total=sum(capacidade),
                    populacao_maxima_no_raio=valor, cobertura_maxima_pct=100*valor/sum(pop),
                    nota='Equipes atuais fixas; capacidade convencional, nao cobertura oficial nem atendimento observado'))
    salvar(saida/'cobertura_por_zona.csv', cobertura)
    salvar(saida/'distancias_por_ponto.csv', dist_por_ponto)
    salvar(saida/'acessibilidade_por_ponto.csv', indices)
    salvar(saida/'acessibilidade_por_zona.csv', indices_zona)
    salvar(saida/'oferta_e_concorrencia.csv', oferta)
    salvar(saida/'cobertura_com_capacidade_atual.csv', limites)
    # O indicador administrativo oficial (cobertura potencial do MS) foi removido do projeto: a cobertura
    # passa a ser a efetiva (acesso a 3 km combinado com a capacidade das eSF e dos ACS).
    ult = None
    atual_total = cobertura[0]
    comparacao = [dict(indicador='Proximidade geografica das UBS atuais',
        percentual=atual_total['cobertura_populacao_pct'], denominador=sum(pop),
        referencia='Populacao local da base; coordenadas das 22 UBS',
        metodo=f'Populacao dentro do criterio {regra_raio} de alguma UBS / populacao local',
        fonte='pontos_demanda_itauna.csv; unidades_existentes_itauna.csv')]
    efetiva = [l for l in limites if l['criterio'] == 'esf_e_acs']
    if efetiva:
        comparacao.append(dict(indicador='Cobertura efetiva da rede atual (3 km + capacidade eSF e ACS)',
            percentual=efetiva[0]['cobertura_maxima_pct'], denominador=sum(pop),
            referencia='Equipes e ACS do CNES 07/2026; 3.000 hab/eSF; 750 hab/ACS',
            metodo='Fluxo maximo: populacao alocavel dentro do raio sem exceder min(3000*eSF, 750*ACS) por UBS',
            fonte='ubs_recursos_cnes_202607.csv; pontos_demanda_itauna.csv'))
    salvar(saida/'comparacao_indicadores.csv', comparacao)
    resumo = dict(raio_km=raio, raio_rural_km=raio_rural, fator_rota=fator_rota, hab_esf=hab_esf, betas=list(betas),
        distancia_minima_km=distancia_minima, equipes_cnes=sum(u['esf'] for u in atual),
        acessibilidade_por_zona=indices_zona,
        ubs_atual=len(atual), populacao=sum(pop), cobertura=cobertura, limites_capacitados=limites,
        folga_custo_plano=folga_custo,
        nota='Ai e indice potencial, nao porcentagem de cobertura. Atual usa somente eSF da base '
             'de 22 UBS. Plano salvo pode ser de execucao anterior.')
    (saida/'resumo.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
    linhas = ['DIAGNOSTICO DE COBERTURA E ACESSIBILIDADE - ITAUNA', '',
        f'Rede atual: {len(atual)} UBS, {sum(u["esf"] for u in atual):g} eSF; CNES 202607.',
        f'Populacao da base: {sum(pop):,.0f}; raios: {regra_raio}; fator de rota: {fator_rota:g}.',
        '', 'COBERTURA GEOGRAFICA (sem restricao de capacidade)']
    for r in cobertura:
        linhas.append(f'{r["rede"]} / {r["zona"]}: {r["cobertura_populacao_pct"]:.2f}% da populacao; '
            f'{r["pontos_no_raio"]}/{r["pontos"]} pontos; media {r["distancia_media_km"]:.3f} km.' if r['populacao'] else f'{r["rede"]} / {r["zona"]}: sem populacao')
    linhas += ['', 'DIAGNOSTICO COM CAPACIDADE ATUAL FIXA (hipotese de capacidade)']
    for r in limites:
        linhas.append(f'{r["criterio"]}: maximo de {r["cobertura_maxima_pct"]:.2f}% conforme {regra_raio}.')
    linhas += ['', 'COBERTURA EFETIVA = acesso a 3 km combinado com capacidade (fluxo maximo, sem dupla contagem)',
        'Capacidade por UBS = min(3000 x eSF; 750 x ACS). Valores no bloco acima (esf_e_acs) e em resultados/cobertura_efetiva/.',
        'ACESSIBILIDADE ESPACIAL (Aula 8, paginas PDF 29 a 31)',
        'V_j = soma_k P_k / max(d_kj, d_min)^beta',
        'A_i = soma_j S_j / (max(d_ij, d_min)^beta * V_j)',
        f'S_j = eSF_j * {hab_esf:g}; d_min = {distancia_minima:g} km; beta = {list(betas)}.',
        'Beta e d_min sao hipoteses configuraveis, nao parametros calibrados de Itauna.',
        'A formula considera todas as UBS; nao aplica corte de 3 km.',
        'Maior A_i indica mais oferta potencial por habitante, considerando distancia e concorrencia.',
        'A_i nao e probabilidade nem porcentagem. Nao multiplicar por 100 para chamar de cobertura.',
        'A media ponderada de A_i e oferta total/populacao; beta muda a distribuicao territorial.',
        'Acessibilidade relativa divide A_i pela media municipal; 1 significa a media, nao cobertura plena.',
        'Oferta atual considera eSF; nao soma eAP, atendimentos especializados ou cadastros oficiais.',
        'Nao inclui demanda de outros municipios nem tempos de viagem.', '',
        'Zero de cobertura rural significa centroides rurais alem do raio, nao ausencia de atendimento rural.', '',
        'PLANO: cobertura geometrica usa UBS mais proxima, podendo diferir da cobertura por vinculacao.',
        ('Diagnostico somente da rede atual; nenhuma otimizacao foi executada.' if plano is None else
         f'Folga de custo registrada no plano: {folga_custo:.0%}. Resultado antigo nao e recalculado ao mudar o padrao.'),
        'Os dados e fluxos de secundaria/terciaria continuam no modelo hierarquico existente.']
    linhas += ['', 'ACESSIBILIDADE MEDIA POR ZONA (indice, nao percentual)']
    for r in indices_zona:
        if r['populacao']:
            linhas.append(f'{r["rede"]} / beta {r["beta"]:g} / {r["zona"]}: '
                f'A_i medio {r["acessibilidade_media_ponderada"]:.6f}; '
                f'relativo a media municipal {r["acessibilidade_relativa_media"]:.6f}.')
    (saida/'relatorio.txt').write_text('\n'.join(linhas)+'\n', encoding='utf-8')
    print(f'Diagnostico salvo: {saida}; cobertura atual {atual_total["cobertura_populacao_pct"]:.2f}%', flush=True)
    return resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plano', type=Path, help='Pasta com plano_aps.json e aps/; somente leitura')
    parser.add_argument('--saida', type=Path, default=RESULTADOS/'diagnostico')
    parser.add_argument('--raio', type=float, default=3)
    parser.add_argument('--raio-rural', type=float, default=None)
    parser.add_argument('--fator-rota', type=float, default=1)
    parser.add_argument('--hab-esf', type=float, default=3000)
    parser.add_argument('--betas', nargs='+', type=float, default=[1, 2])
    parser.add_argument('--distancia-minima', type=float, default=.1)
    args = parser.parse_args()
    plano, folga = None, None
    pontos = ler(BASE/'pontos_demanda_itauna.csv')
    if args.plano:
        meta = json.loads((args.plano/'plano_aps.json').read_text(encoding='utf-8'))
        if meta['status'] != 'plano_aps_validado':
            raise ValueError('Plano nao validado')
        for nome, esperado in meta['arquivos'].items():
            if hashlib.sha256((args.plano/'aps'/nome).read_bytes()).hexdigest() != esperado:
                raise ValueError('Arquivo do plano alterado: '+nome)
        plano = ler(args.plano/'aps/ubs_completas.csv')
        pontos = ler(args.plano/'aps/demanda_cenario.csv')
        parametros = meta['parametros']
        args.raio, args.fator_rota, args.hab_esf = (parametros[k] for k in ['raio','fator_rota','hab_esf'])
        args.raio_rural=parametros.get('raio_rural')
        folga = parametros['folga_custo']
    existentes = [r for r in ler(BASE/'unidades_existentes_itauna.csv') if r['nivel_sugerido'] == 'PHC']
    gerar_diagnostico(pontos, existentes, plano, args.saida, args.raio, args.fator_rota,
        args.hab_esf, folga, args.betas, args.distancia_minima, raio_rural=args.raio_rural)


if __name__ == '__main__':
    main()
