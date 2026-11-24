"""Prepara entradas da nova versao. Somente le arquivos anteriores."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from caminhos import PASTA,BASE,ENTRADA,DOCUMENTACAO
FAIXAS=['0-4','5-9','10-14','15-19','20-24','25-29','30-39','40-49','50-59','60-69','70+']
GRUPOS=[[0,1],[2],[3],[4],[5],[6],[7,8],[9,10],[11,12],[13,14],[15,16,17]]
ORIGINAIS=['model.py','glpk/hc.mod','glpk/hc.dat','pontos_demanda_itauna.csv','unidades_existentes_itauna.csv']

def ler(p,separador=';'):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f,delimiter=separador))

def salvar(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';');w.writeheader();w.writerows(rows)

def hashes():
    return {n:hashlib.sha256(((DOCUMENTACAO/'versao_original'/n) if n in ['model.py','glpk/hc.mod','glpk/hc.dat'] else BASE/n).read_bytes()).hexdigest() for n in ORIGINAIS}

def numero(v):return 0 if v=='-' else int(v)

def distancia(a,b):
    lat1,lat2=map(math.radians,[float(a['lat']),float(b['lat'])])
    h=math.sin((lat1-lat2)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(float(a['lon'])-float(b['lon']))/2)**2
    return 6371*2*math.asin(math.sqrt(min(h,1)))

def preparar():
    ENTRADA.mkdir(exist_ok=True)
    guarda=DOCUMENTACAO/'originais_sha256.json'
    if not guarda.exists():guarda.write_text(json.dumps(hashes(),indent=2),encoding='utf-8')
    if json.loads(guarda.read_text())!=hashes():raise ValueError('Arquivos originais mudaram desde o inicio desta versao; conferir antes de continuar')
    pontos=ler(BASE/'pontos_demanda_itauna.csv',',')
    perfis=ler(BASE/'demanda_especializada/idades/CENARIO_perfil_etario_91_pontos.csv')
    pop={p['i']:float(p['pessoas']) for p in pontos};idades=defaultdict(dict)
    for r in perfis:idades[r['i']][r['faixa_etaria']]=float(r['populacao_estimada'])
    if set(idades)!=set(pop):raise ValueError('Pontos e perfis etarios diferentes')
    for i in pop:
        if set(idades[i])!=set(FAIXAS) or not math.isclose(sum(idades[i].values()),pop[i],abs_tol=1e-6):raise ValueError('Perfil etario nao conserva populacao '+i)
    denom={a:sum(idades[i][a] for i in pop) for a in FAIXAS}
    demanda=defaultdict(float);validacoes=[];taxas=[]
    clinicos={r['procedimento']:r['complexidade'] for r in ler(BASE/'demanda_especializada/demanda_ambulatorial_clinica_residentes_2025.csv')}
    fonte_sia=BASE/'demanda_especializada/sia_residentes_eletivo_procedimento_idade_2025.csv'
    if not fonte_sia.exists():raise ValueError('Execute coletar_idade_eletiva.py: falta perfil eletivo ambulatorial')
    dados=ler(fonte_sia);chave=next(iter(dados[0]));cols=list(dados[0])[1:-1]
    if len(cols)!=18:raise ValueError('Faixas DATASUS inesperadas')
    observado=defaultdict(int)
    for r in dados:
        codigo=r[chave][:10]
        if codigo not in clinicos:continue
        nivel=2 if clinicos[codigo].startswith('Média') else 3
        vals=[numero(r[c]) for c in cols]
        if sum(vals)!=numero(r['Total']):raise ValueError('Idades nao somam procedimento '+codigo)
        observado[nivel]+=sum(vals)
        for a,indices in zip(FAIXAS,GRUPOS):
            n=sum(vals[j] for j in indices)
            taxas.append(dict(sistema='AMB',servico=codigo,nivel=nivel,idade=a,volume_eletivo=n,populacao_referencia=denom[a],taxa=n/denom[a],nota='utilizacao registrada, nao probabilidade de encaminhamento'))
            for i in pop:demanda[i,'AMB',nivel]+=n*idades[i][a]/denom[a]
    if dict(observado)!={2:190856,3:15752}:raise ValueError('Totais SIA eletivos divergentes '+str(observado))

    # SIH tem idade eletiva por diagnostico, mas nao por complexidade nesta consulta.
    # Usamos esse perfil eletivo comum para media/alta, preservando os dois totais.
    fonte_h=BASE/'demanda_especializada/sih_residentes_eletivo_morbidade_idade_2025.csv'
    if not fonte_h.exists():raise ValueError('Falta perfil etario eletivo hospitalar')
    dados=ler(fonte_h);chave=next(iter(dados[0]));cols=list(dados[0])[1:-1]
    total=next(r for r in dados if r[chave]=='Total');vals=[numero(total[c]) for c in cols]
    if len(vals)!=18 or sum(vals)!=1415:raise ValueError('Total hospitalar etario eletivo divergente')
    for nivel,nivel_total in [(2,1065),(3,350)]:
        for a,indices in zip(FAIXAS,GRUPOS):
            n=sum(vals[j] for j in indices)*nivel_total/1415
            taxas.append(dict(sistema='HOSP',servico='perfil_eletivo_geral',nivel=nivel,idade=a,volume_eletivo=n,populacao_referencia=denom[a],taxa=n/denom[a],nota='HIPOTESE: mesmo perfil etario eletivo para media/alta; nao idade observada por complexidade'))
            for i in pop:demanda[i,'HOSP',nivel]+=n*idades[i][a]/denom[a]
    for k,nivel,esp in [('AMB',2,190856),('AMB',3,15752),('HOSP',2,1065),('HOSP',3,350)]:
        obt=sum(demanda[i,k,nivel] for i in pop)
        if not math.isclose(obt,esp,abs_tol=1e-6):raise ValueError('Rateio nao conserva demanda')
        validacoes.append(dict(verificacao='total_'+k+str(nivel),valor=obt,esperado=esp,passou=True))
        for i in pop:
            if demanda[i,k,2]+1e-8<.75*demanda[i,k,3]:raise ValueError('Demanda secundaria insuficiente para vincular a parcela via terciaria '+i)
    salvar(ENTRADA/'taxas_etarias.csv',taxas)
    salvar(ENTRADA/'demanda_por_ponto.csv',[dict(i=i,tipo=k,nivel=n,quantidade_anual=demanda[i,k,n],origem='SIA eletivo por procedimento e idade' if k=='AMB' else 'SIH perfil etario eletivo geral; complexidade rateada por hipotese') for i in pop for k in ['AMB','HOSP'] for n in [2,3]])
    salvar(ENTRADA/'validacoes_etarias.csv',validacoes)
    salvar(ENTRADA/'perfis_etarios_usados.csv',perfis)

    unidades=ler(BASE/'cenarios_niveis/classificacao_cenarios.csv')
    evidencias={r['cnes']:r for r in ler(BASE/'demanda_especializada/picos_historicos/evidencia_complexidades_por_local_2025.csv')}
    picos={r['cnes']:r for r in ler(BASE/'demanda_especializada/picos_historicos/picos_rede_2025.csv') if r['janela_meses']=='1'}
    equipes=defaultdict(set)
    for r in ler(BASE/'fontes_publicas/equipes_ubs_cnes_202607.csv'):
        if r['tipo'].startswith('70 -'):equipes[r['cnes']].add(r['ine'])
    # Leitos SUS cadastrados x dias do periodo, descontando outros atendimentos.
    # A reserva usa as contagens SIH e as mesmas permanencias do consumo modelado.
    carga_h={r['cnes']:r for r in ler(BASE/'cenarios_niveis/demanda_integrada/parametros_sus_2015/carga_hospitalar_observada_2025.csv')}
    from capacidade_hospitalar import preparar_capacidade
    hospital=preparar_capacidade()
    leitos={c:r['dias_disponiveis_modelo'] for c,r in hospital.items()}
    tmp=json.loads((BASE/'cenarios_niveis/demanda_integrada/parametros_sus_2015/configuracao.json').read_text(encoding='utf-8'))['tmp_dias']
    # Producao eletiva de nao residentes por prestador (SIA 2025): carga fixa que ocupa parte
    # da capacidade ambulatorial. Ver codigos/coleta/coletar_residencia_microdados.py.
    externo_amb=defaultdict(float)
    for r in ler(BASE/'demanda_especializada/residencia_prestador/producao_por_residencia_2025.csv'):
        if r['carater']=='eletivo':externo_amb[r['cnes']]+=float(r['nao_residentes'])
    for u in unidades:
        c=u['cnes'];e=evidencias[c];amb_total=float(picos[c]['anualizacao_total'])
        u['amb_capacidade_total']=amb_total;u['amb_carga_externa']=externo_amb[c]
        amb=max(amb_total-externo_amb[c],0.0)
        # Regra local explicita: duas complexidades com producao eletiva em >=6 meses.
        # Nao e norma oficial. Unidades sem evidencia mantem a classificacao anterior.
        dupla=int(e['meses_com_media'])>=6 and int(e['meses_com_alta'])>=6 and u['nivel_principal']!='1'
        u['novo_2']=int(u['oferta_2']=='1' or dupla);u['novo_3']=int(u['oferta_3']=='1' or dupla)
        u['justificativa_nova']='HIPOTESE: media e alta eletivas recorrentes em pelo menos6 meses' if dupla else 'mantida classificacao anterior; oferta adicional nao presumida'
        u['cap_amb_anual']=amb;u['mes_pico']=picos[c]['inicio']
        u['cap_leito_dias']=leitos.get(c,0)
        u['dias_leito_capacidade_observada']=float(carga_h[c]['dias_capacidade_observada']) if c in carga_h else 0.0
        u['dias_leito_carga_externa']=float(carga_h[c]['dias_carga_externa']) if c in carga_h else 0.0
        u['dias_leito_capacidade_bruta']=hospital[c]['dias_capacidade_bruta'] if c in hospital else 0.0
        u['leitos_sus_internacao']=hospital[c]['leitos_sus_internacao'] if c in hospital else 0
        u['leitos_sus_uti']=hospital[c]['leitos_sus_uti'] if c in hospital else 0
        if c in hospital:u['dias_leito_carga_externa']=hospital[c]['dias_carga_outros']
        u['esf']=len(equipes[c]);u['max_esf']=max(4,len(equipes[c]))
        u['situacao_capacidade']='pico eletivo observado, anualizado para cenario' if amb else 'sem pico eletivo identificavel; limite zero apenas neste cenario, nao ausencia comprovada de capacidade'
    salvar(ENTRADA/'estabelecimentos_revisados.csv',unidades)
    config=dict(proporcoes_via_secundaria=[.25,.5,.75],hab_por_esf=3000,tmp2=tmp['hospitalar_media'],tmp3=tmp['hospitalar_alta'],leitos='CNES 202607: leitos SUS de internacao e UTI x 365 dias menos carga estimada de nao residentes e residentes nao eletivos; disponibilidade anual e agregacao sao hipoteses',hospital_idade='perfil eletivo geral comum a media/alta',ambulatorio_capacidade='12 vezes pico mensal conjunto 2025 menos a producao eletiva anual de nao residentes no prestador; processamento, nao data de atendimento',deslocamento='linha reta; trajetos organizacionais completos a partir do ponto; nao viagens observadas',faixas=FAIXAS)
    (ENTRADA/'configuracao.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    if hashes()!=json.loads(guarda.read_text()):raise ValueError('Original alterado durante preparacao')
    return pontos,unidades,demanda,config

if __name__=='__main__':
    p,u,d,c=preparar();print('Preparados',len(p),'pontos;',len(u),'locais; idade eletiva conferida; originais preservados.')
