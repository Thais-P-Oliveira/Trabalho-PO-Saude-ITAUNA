"""Caminhos relativos a pasta do projeto, independentes do computador."""
from pathlib import Path
import tempfile
RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ
CODIGOS = RAIZ/'codigos'
MODELOS = RAIZ/'modelos'
BASE = RAIZ/'dados/fontes'
ENTRADA = RAIZ/'dados/preparados'
RESULTADOS = RAIZ/'resultados'
DOCUMENTACAO = RAIZ/'documentacao'
CACHE = Path(tempfile.gettempdir())/'projeto_pos_cache'

def resolver_caminho_plano(valor):
    """Resolve caminhos do plano salvo quando o projeto e movido de computador."""
    p=Path(valor)
    if not p.is_absolute():
        p=RAIZ/p
    if p.exists():return str(p)
    if p.name in ['pontos_demanda_itauna.csv','unidades_existentes_itauna.csv']:
        return str(BASE/p.name)
    if p.name in ['limites_equipes_modelo.csv','limites_equipes_novas_ate4.csv']:
        return str(BASE/'fontes_publicas/estrutura_ubs_cnes'/p.name)
    raise FileNotFoundError('Arquivo do plano nao encontrado: '+str(valor))
