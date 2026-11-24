"""Executa, valida e publica uma nova versao completa das imagens e resultados.

Use RODAR_TUDO.cmd com dois cliques. --conferir apenas le a configuracao,
confere a sintaxe e localiza dependencias; nao executa modelos nem testes.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
import venv

ROOT=Path(__file__).resolve().parent
RESULTADOS=ROOT/'resultados'
MODULOS=['numpy','pandas','pulp','highspy','matplotlib','folium','openpyxl']
LOG=None


def informar(texto):
    print(texto,flush=True)
    if LOG:LOG.write(texto+'\n');LOG.flush()


def dentro(caminho):
    """Toda remocao/movimentacao de resultados fica restrita a esta pasta."""
    p=Path(caminho).resolve()
    if p==ROOT or not p.is_relative_to(ROOT):raise ValueError('Destino fora do projeto: '+str(p))
    return p


def remover_pasta(caminho):
    p=dentro(caminho)
    if p.is_dir():shutil.rmtree(p)


def localizar_glpk():
    candidatos=[ROOT/'ferramentas/glpk/glpsol.exe',shutil.which('glpsol'),Path('C:/Solvers/glpsol.exe')]
    for p in candidatos:
        if p and Path(p).is_file():return Path(p).resolve()
    raise FileNotFoundError('GLPK nao encontrado. Mantenha ferramentas/glpk junto com o projeto.')


def conferir(config):
    if sys.version_info<(3,10):raise RuntimeError('Use Python 3.10 ou superior.')
    for nome in ['tempo_modelo_segundos','tempo_sensibilidade_segundos','processos_sensibilidade']:
        if not isinstance(config.get(nome),int) or config[nome]<=0:raise ValueError('Configuracao invalida: '+nome)
    for nome in ['rodar_testes','instalar_dependencias_ausentes','abrir_resultados_ao_concluir','remover_imagens_antigas']:
        if not isinstance(config.get(nome),bool):raise ValueError('Configuracao deve ser true/false: '+nome)
    arquivos=[*ROOT.glob('*.py')]
    for pasta in ['codigos','modelos','testes']:arquivos.extend((ROOT/pasta).glob('*.py'))
    for p in arquivos:compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
    glpk=localizar_glpk()
    faltam=[m for m in MODULOS if importlib.util.find_spec(m) is None]
    return glpk,faltam


def preparar_ambiente(faltam,config):
    if not faltam:return None
    if not config['instalar_dependencias_ausentes'] or os.environ.get('POS_AMBIENTE_PREPARADO')=='1':
        raise RuntimeError('Bibliotecas ausentes: '+', '.join(faltam)+'. Instale requirements.txt.')
    # O ambiente fica fora do projeto, evitando enviar milhares de arquivos ao Drive.
    cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'TrabalhoPOSaude'
    ambiente=cache/f'python_{sys.version_info.major}_{sys.version_info.minor}'
    python=ambiente/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    informar('Preparando as bibliotecas. A primeira vez precisa de internet...')
    if not python.is_file():venv.EnvBuilder(with_pip=True).create(ambiente)
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
    env=dict(os.environ,POS_AMBIENTE_PREPARADO='1')
    return subprocess.call([str(python),'-B',str(Path(__file__).resolve()),*sys.argv[1:]],cwd=ROOT,env=env)


@contextmanager
def trava():
    """Impede duas atualizacoes simultaneas; a trava e liberada ao fechar o processo."""
    f=(ROOT/'.rodar_tudo.lock').open('a+b')
    if f.tell()==0:f.write(b'0');f.flush()
    f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Ja existe uma atualizacao em andamento. Aguarde a janela terminar.')
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        f.close()


def executar(titulo,argumentos,env):
    informar('\n>>> '+titulo)
    informar('Comando: '+subprocess.list2cmdline([sys.executable,'-B',*map(str,argumentos)]))
    processo=subprocess.Popen([sys.executable,'-B',*map(str,argumentos)],cwd=ROOT,env=env,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    linhas=queue.Queue()
    def ler():
        for linha in processo.stdout:linhas.put(linha.rstrip())
        processo.stdout.close();linhas.put(None)
    threading.Thread(target=ler,daemon=True).start()
    inicio=ultimo=time.monotonic()
    try:
        while True:
            try:linha=linhas.get(timeout=1)
            except queue.Empty:linha=''
            if linha is None:break
            if linha:informar(linha)
            if time.monotonic()-ultimo>=30:
                informar(f'  Ainda em processamento: {titulo} ({int(time.monotonic()-inicio)} s).')
                ultimo=time.monotonic()
        codigo=processo.wait()
    except BaseException:
        processo.terminate();processo.wait();raise
    if codigo:raise RuntimeError(f'Etapa interrompida: {titulo}. Codigo {codigo}.')


def publicar(pasta):
    """Troca os quatro destinos somente apos concluir todas as etapas, com reversao em caso de erro."""
    backup=dentro(RESULTADOS/('.substituicao_'+uuid.uuid4().hex[:10]));backup.mkdir(parents=True)
    pares=[(pasta/'imagens',ROOT/'imagens'),(pasta/'figuras_artigo',ROOT/'documentacao/artigo/figuras'),
           (pasta/'ABRIR_RESULTADOS.html',ROOT/'ABRIR_RESULTADOS.html'),(pasta,RESULTADOS/'atual')]
    instalados=[];anteriores=[]
    try:
        for origem,destino in pares:
            origem=dentro(origem);destino=dentro(destino);destino.parent.mkdir(parents=True,exist_ok=True)
            if destino.exists():
                antigo=backup/str(len(anteriores));destino.rename(antigo);anteriores.append((destino,antigo))
            origem.rename(destino);instalados.append((origem,destino))
    except BaseException:
        for origem,destino in reversed(instalados):
            origem.parent.mkdir(parents=True,exist_ok=True);destino.rename(origem)
        for destino,antigo in reversed(anteriores):antigo.rename(destino)
        remover_pasta(backup)
        raise
    try:remover_pasta(backup)
    except OSError as e:informar('Atualizacao publicada; nao foi possivel remover o backup temporario: '+str(e))


def limpar_imagens_historicas():
    """Remove somente figuras geradas de execucoes antigas; conserva dados, fontes e registros."""
    removidos=0
    for pasta in RESULTADOS.iterdir():
        if not pasta.is_dir() or pasta.name=='atual' or pasta.name.startswith('.'):continue
        if pasta.is_symlink() or not pasta.resolve().is_relative_to(ROOT):continue
        for p in pasta.rglob('*'):
            if 'fontes_execucao' in p.parts or 'fontes_antes_limites_fisicos' in p.parts:continue
            if not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(ROOT) and p.suffix.lower() in ['.png','.jpg','.jpeg','.svg','.pdf']:
                try:dentro(p).unlink();removidos+=1
                except OSError as e:informar('Aviso: imagem antiga em uso, mantida: '+str(p)+'; '+str(e))
    informar(f'Figuras antigas removidas de pastas de resultados: {removidos}.')


def ajustar_caminhos_json(pasta):
    """Os metadados publicados nao devem apontar para a pasta temporaria."""
    origem=str(pasta.resolve());destino=str((RESULTADOS/'atual').resolve())
    def substituir(valor):
        if isinstance(valor,str):return destino+valor[len(origem):] if valor.startswith(origem) else valor
        if isinstance(valor,list):return [substituir(v) for v in valor]
        if isinstance(valor,dict):return {substituir(k):substituir(v) for k,v in valor.items()}
        return valor
    for arquivo in pasta.rglob('*.json'):
        dados=json.loads(arquivo.read_text(encoding='utf-8-sig'));novo=substituir(dados)
        if novo!=dados:arquivo.write_text(json.dumps(novo,ensure_ascii=False,indent=2),encoding='utf-8')


def fluxo(config,glpk):
    global LOG
    LOG=(ROOT/'ULTIMA_EXECUCAO.log').open('w',encoding='utf-8')
    pasta=dentro(RESULTADOS/('.execucao_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]))
    pasta.mkdir(parents=True)
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    env['PATH']=str(glpk.parent)+os.pathsep+env.get('PATH','')
    informar('Nova execucao completa. Nao feche esta janela.')
    informar('As imagens atuais so serao substituidas depois da validacao de tudo.')
    informar('Pasta de trabalho: '+str(pasta))
    try:
        if config['rodar_testes']:executar('Conferencias automaticas',['executar.py','--testar'],env)
        executar('Modelo principal e seis cenarios de encaminhamento',
                 ['executar.py','--time-limit',config['tempo_modelo_segundos'],'--quiet','--saida',pasta/'plano'],env)
        executar('Auditoria do novo plano',['executar.py','--auditar','--saida',pasta/'plano'],env)
        executar('Construcao por porte',['executar.py','--investimento','--plano',pasta/'plano','--saida',pasta/'investimento'],env)
        executar('Comparacao com o orcamento',['executar.py','--orcamento','--plano',pasta/'plano','--saida',pasta/'orcamento'],env)
        executar('Analises de sensibilidade e tres cenarios extras de raio',
                 ['codigos/rodar_sensibilidade.py','--referencia',pasta/'plano/plano_aps.json','--saida',pasta/'sensibilidade',
                  '--processos',config['processos_sensibilidade'],'--time-limit',config['tempo_sensibilidade_segundos']],env)
        executar('Graficos de sensibilidade',['codigos/grafico_sensibilidade.py','--saida',pasta/'sensibilidade'],env)
        executar('Imagens e figuras do artigo',['codigos/figuras_artigo.py','--plano',pasta/'plano',
                 '--figuras',pasta/'figuras_artigo','--imagens',pasta/'imagens'],env)
        for nome in ['painel_resultados.png','mapa_itauna_ubs.png','mapa_itauna_zoom_urbano.png']:
            shutil.copy2(pasta/'plano/aps'/nome,pasta/'imagens'/nome)
        for nome in ['curva_cobertura_custo','extra_raios_01_custo','extra_raios_02_cobertura','extra_raios_03_distancia']:
            for extensao,destino in [('png',pasta/'imagens'),('pdf',pasta/'figuras_artigo')]:
                shutil.copy2(pasta/'sensibilidade'/f'{nome}.{extensao}',destino/f'{nome}.{extensao}')
        executar('Pagina de apresentacao e imagens finais',['codigos/organizar_resultados.py','--resultado',pasta,
                 '--imagens',pasta/'imagens','--html',pasta/'ABRIR_RESULTADOS.html'],env)
        estado=json.loads((pasta/'plano/status.json').read_text(encoding='utf-8'))
        if estado.get('auditoria_integracao')!='PASSOU':raise ValueError('Auditoria final ausente.')
        # A verificacao usa apenas os resultados recem-gerados.
        with (pasta/'sensibilidade/resumo.csv').open(encoding='utf-8-sig') as arq:
            import csv
            sens=list(csv.DictReader(arq,delimiter=';'))
        from importlib.util import spec_from_file_location,module_from_spec
        sys.path.insert(0,str(ROOT/'codigos'))
        spec=spec_from_file_location('sensibilidade_conferencia',ROOT/'codigos/rodar_sensibilidade.py')
        modulo=module_from_spec(spec);spec.loader.exec_module(modulo)
        if len(sens)!=len(modulo.CENARIOS):raise ValueError('Faltam resultados de sensibilidade; publicacao cancelada.')
        ajustar_caminhos_json(pasta)
        (pasta/'manifesto_execucao.json').write_text(json.dumps(dict(status='concluida',
            data=datetime.now().astimezone().isoformat(),configuracao=config,
            plano='plano',pagina='../../ABRIR_RESULTADOS.html',
            nota='Resultados publicados juntos. A otimalidade de cada fase consta nos certificados.'),ensure_ascii=False,indent=2),encoding='utf-8')
        informar('Validacao concluida. Substituindo resultados e imagens...')
        publicar(pasta)
        if config['remover_imagens_antigas']:
            try:limpar_imagens_historicas()
            except OSError as e:informar('Resultados novos publicados; limpeza de figuras antigas incompleta: '+str(e))
        informar('\nCONCLUIDO. Resultados atuais: resultados/atual. Imagens: imagens/.')
        if config['abrir_resultados_ao_concluir'] and os.name=='nt':
            try:os.startfile(str(ROOT/'ABRIR_RESULTADOS.html'))
            except OSError:informar('Abra ABRIR_RESULTADOS.html manualmente.')
    except BaseException:
        informar('\nA atualizacao nao foi concluida. Confira o registro acima e a pasta de trabalho.')
        raise
    finally:
        LOG.close();LOG=None


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--conferir',action='store_true')
    a=ap.parse_args()
    config=json.loads((ROOT/'config_rodar_tudo.json').read_text(encoding='utf-8-sig'))
    glpk,faltam=conferir(config)
    if a.conferir:
        informar('Sintaxe e configuracao: OK. GLPK: '+str(glpk))
        informar('Bibliotecas: '+(', '.join(faltam)+' ausentes; serao instaladas ao executar.' if faltam else 'OK'))
        informar('Nenhum modelo, teste ou geracao de imagem foi executado.')
        return 0
    retorno=preparar_ambiente(faltam,config)
    if retorno is not None:return retorno
    with trava():fluxo(config,glpk)
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as erro:
        print('\nERRO: '+str(erro),flush=True);sys.exit(1)
