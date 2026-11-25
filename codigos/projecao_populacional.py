"""Atualiza populacao e utilizacao com anos de referencia distintos."""
import json
import math
from caminhos import BASE

FONTE=BASE/'fontes_publicas/populacao_ibge/projecao.json'

def parametros():
    p=json.loads(FONTE.read_text(encoding='utf-8'))
    for k in ['populacao_base_territorial','populacao_ano_atendimentos','populacao_planejamento']:
        if not math.isfinite(p[k]) or p[k]<=0:raise ValueError('Populacao de referencia invalida')
    return p

def crescimento_aps():
    """Percentual acumulado da base territorial ate o ano de planejamento."""
    p=parametros()
    return 100*(p['populacao_planejamento']/p['populacao_base_territorial']-1)

def projetar_demanda(pontos,populacao,demanda):
    """Demanda 2025 / populacao municipal 2025 x moradores projetados do ponto.

    A demanda de entrada foi rateada pela populacao territorial original.
    Desfazemos esse denominador antes de aplicar a taxa por habitante de 2025.
    Assim o crescimento 2022-2026 nao e aplicado novamente aos atendimentos.
    """
    p=parametros();base={r['i']:float(r['pessoas']) for r in pontos}
    if not math.isclose(sum(base.values()),p['populacao_base_territorial'],abs_tol=.01):
        raise ValueError('Base territorial diferente da referencia da projecao')
    if set(base)!=set(populacao) or any(not math.isfinite(v) or v<=0 for v in populacao.values()):
        raise ValueError('Populacao projetada invalida')
    fator=sum(base.values())/p['populacao_ano_atendimentos']
    return {(i,k,n):v*populacao[i]/base[i]*fator for (i,k,n),v in demanda.items()}
