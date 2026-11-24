"""Executa demonstracoes em novas pastas, preservando o plano de referencia."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'resultados' / 'plano_referencia_2pct'
if (ROOT/'resultados/atual/plano/plano_aps.json').is_file():
    REF = ROOT/'resultados/atual/plano'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acao', choices=['verificar', 'testar', 'reproduzir', 'novo', 'diagnostico', 'auditar', 'investimento', 'imagens'])
    args = parser.parse_args()
    command = [sys.executable, str(ROOT / 'executar.py')]
    if args.acao == 'imagens':
        for nome in ['figuras_artigo.py', 'grafico_sensibilidade.py', 'organizar_resultados.py']:
            result = subprocess.call([sys.executable, '-B', str(ROOT/'codigos'/nome)], cwd=ROOT)
            if result:
                return result
        return 0
    if args.acao in ('verificar', 'testar'):
        command += ['--' + args.acao]
    else:
        dest = ROOT / 'resultados' / ('demonstracao_' + args.acao + '_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
        if args.acao == 'auditar':
            shutil.copytree(REF, dest)
            command += ['--auditar', '--saida', str(dest)]
        elif args.acao == 'diagnostico':
            dest.mkdir(parents=True, exist_ok=False)
            command += ['--diagnostico', '--plano', str(REF), '--saida', str(dest)]
        elif args.acao == 'investimento':
            dest.mkdir(parents=True, exist_ok=False)
            command += ['--investimento', '--saida', str(dest)]
        elif args.acao == 'reproduzir':
            dest.mkdir(parents=True, exist_ok=False)
            command += ['--plano-aps', str(REF), '--saida', str(dest)]
        else:
            dest.mkdir(parents=True, exist_ok=False)
            command += ['--time-limit', '300', '--quiet', '--saida', str(dest)]
        print('Nova pasta de demonstracao:', dest, flush=True)
    return subprocess.call(command, cwd=ROOT)

if __name__ == '__main__':
    raise SystemExit(main())
