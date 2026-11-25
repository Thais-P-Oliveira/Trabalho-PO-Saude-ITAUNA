"""Monta os dados MathProg e confere os encaminhamentos especializados."""
import csv
import math
from collections import defaultdict
from preparar import salvar,distancia

def tabela(nome,rows):
    return 'param '+nome+' :=\n'+'\n'.join(' '.join(map(str,r)) for r in rows)+'\n;\n'

def dados(pontos,unidades,demanda,config,multiplo,r):
    U=[u for u in unidades if u['nivel_principal']=='1']
    S=[u for u in unidades if (u['novo_2'] if multiplo else u['nivel_principal']=='2')]
    T=[u for u in unidades if (u['novo_3'] if multiplo else u['nivel_principal']=='3')]
    F={u['cnes']:u for u in S+T}
    sets=dict(I=['p'+p['i'] for p in pontos],U=['u'+u['cnes'] for u in U],S=['f'+u['cnes'] for u in S],T=['f'+u['cnes'] for u in T],K=['AMB','HOSP'])
    txt='data;\n'+''.join('set '+k+' := '+' '.join(v)+';\n' for k,v in sets.items())
    txt+=f'param R := {r};\nparam TMP2 := {config["tmp2"]};\nparam TMP3 := {config["tmp3"]};\n'
    txt+=tabela('POP',[('p'+p['i'],p['pessoas']) for p in pontos])
    for nome,chave in [('ESF','esf'),('MAXE','max_esf')]:txt+=tabela(nome,[('u'+u['cnes'],u[chave]) for u in U])
    for nome,n in [('D2',2),('D3',3)]:txt+=tabela(nome,[('p'+p['i'],k,demanda[p['i'],k,n]) for p in pontos for k in ['AMB','HOSP']])
    for nome,chave in [('AMB','cap_amb_anual'),('LEITO','cap_leito_dias')]:txt+=tabela(nome,[('f'+c,u[chave]) for c,u in F.items()])
    for nome,chave,n in [('AMB2','cap_amb_2',2),('AMB3','cap_amb_3',3)]:
        txt+=tabela(nome,[('f'+c,u.get(chave,u['cap_amb_anual'])) for c,u in F.items()])
    txt+=tabela('HOSPITAL',[('f'+c,int(u['cap_leito_dias']>0)) for c,u in F.items()])
    dist={}
    for nome,origens,destinos,prefixo in [('DU',pontos,U,'p'),('US',U,S,'u'),('UT',U,T,'u'),('ST',S,T,'f')]:
        itens=[]
        for a in origens:
            for b in destinos:
                i=prefixo+(a['i'] if prefixo=='p' else a['cnes']);j=('u' if nome=='DU' else 'f')+b['cnes']
                v=0 if a.get('cnes')==b.get('cnes') and 'cnes' in a else distancia(a,b)
                dist[nome,i,j]=v;itens.append((i,j,v))
        txt+=tabela(nome,itens)
    # Sem raio/ligacoes proibidas, a vinculacao primaria fracionaria permite o minimo global.
    novas=max(math.ceil(sum(float(p['pessoas']) for p in pontos)/3000)-sum(u['esf'] for u in U),0)
    if novas>sum(u['max_esf']-u['esf'] for u in U):raise ValueError('Teto de equipes nao comporta a populacao')
    return txt,U,S,T,F,dist,novas

def validar(rows,pontos,demanda,config,U,F,dist,r,pasta):
    pop={p['i']:float(p['pessoas']) for p in pontos}
    vinc=defaultdict(float);aloc_pop=defaultdict(float);cap_ubs={}
    origem={(p['i'],k):[0.,0.,0.,0.,0.,0.] for p in pontos for k in ['AMB','HOSP']}
    # Ordem: termina, direto, via, falta_termina, falta_direto, falta_via.
    cargas=defaultdict(lambda:defaultdict(float));arcos=[];desloc=defaultdict(float);internos=defaultdict(float)
    for row in rows:
        tag=row[0]
        if tag=='UBS':
            c=row[1][1:];cap_ubs[c]=float(row[4]);novas=float(row[2])
            unidade=next(u for u in U if u['cnes']==c)
            if abs(novas-round(novas))>1e-6 or novas+unidade['esf']>unidade['max_esf']+1e-6:
                raise ValueError('Equipes nao inteiras ou teto excedido')
            if not math.isclose(cap_ubs[c],config.get('hab_por_esf',3000)*(unidade['esf']+novas),abs_tol=1e-5):raise ValueError('Capacidade diferente do limite por equipe')
        if tag=='X':
            i,u,z=row[1][1:],row[2][1:],float(row[3]);vinc[i]+=z;aloc_pop[u]+=pop[i]*z
        if tag not in ('F','D','V','N'):continue
        i,u,k=row[1][1:],row[2][1:],row[3];v=origem[i,k]
        if tag=='N':
            for j in range(3):v[j+3]+=float(row[j+4])
            continue
        if tag=='F':
            s=row[4][1:];n=float(row[5]);v[0]+=n;cargas[s][k+'2']+=n
            d=dist['DU','p'+i,'u'+u]+dist['US','u'+u,'f'+s];t=''
        elif tag=='D':
            t=row[4][1:];n=float(row[5]);v[1]+=n;cargas[t][k+'3']+=n;s=''
            d=dist['DU','p'+i,'u'+u]+dist['UT','u'+u,'f'+t]
        else:
            s,t=row[4][1:],row[5][1:];n=float(row[6]);v[2]+=n;cargas[s][k+'2']+=n;cargas[t][k+'3']+=n
            d=dist['DU','p'+i,'u'+u]+dist['US','u'+u,'f'+s]+dist['ST','f'+s,'f'+t]
            if s==t:internos[k]+=n
        desloc[k]+=d*n
        arcos.append(dict(ponto=i,ubs=u,tipo=k,percurso={'F':'termina_secundaria','D':'direto_terciaria','V':'via_secundaria'}[tag],secundaria=s,terciaria=t,quantidade=n,distancia_trajeto_km=d,trecho_23_interno=int(tag=='V' and s==t)))
    tol=1e-3
    for i in pop:
        if not math.isclose(vinc[i],1,abs_tol=1e-7):raise ValueError('Vinculo nao conserva populacao '+i)
        for k in ['AMB','HOSP']:
            a,b,c,na,nb,nc=origem[i,k]
            for obt,esp in [(a+na,demanda[i,k,2]-r*demanda[i,k,3]),(b+nb,(1-r)*demanda[i,k,3]),(c+nc,r*demanda[i,k,3])]:
                if not math.isclose(obt,esp,abs_tol=tol):raise ValueError('Caminho nao conserva demanda '+i+' '+k)
    if any(aloc_pop[u['cnes']]-config.get('carga_movel_ubs',{}).get(u['cnes'],0)>cap_ubs[u['cnes']]+tol for u in U):raise ValueError('Capacidade primaria excedida')
    auditoria=[]
    for c,u in F.items():
        amb=cargas[c]['AMB2']+cargas[c]['AMB3']
        leito=config['tmp2']*cargas[c]['HOSP2']+config['tmp3']*cargas[c]['HOSP3']
        if 'cap_amb_2' in u and 'cap_amb_3' in u:
            if any(cargas[c]['AMB'+str(n)]>u['cap_amb_'+str(n)]+tol for n in [2,3]):
                raise ValueError('Capacidade por complexidade excedida '+c)
        if amb>u['cap_amb_anual']+tol or leito>u['cap_leito_dias']+tol:raise ValueError('Capacidade duplicada ou excedida '+c)
        auditoria.append(dict(cnes=c,nome=u['nome'],ambulatorial_media=cargas[c]['AMB2'],ambulatorial_alta=cargas[c]['AMB3'],ambulatorial_total=amb,limite_pico_anualizado=u['cap_amb_anual'],limite_media=u.get('cap_amb_2',u['cap_amb_anual']),limite_alta=u.get('cap_amb_3',u['cap_amb_anual']),amb_capacidade_total=u.get('amb_capacidade_total',u['cap_amb_anual']),amb_carga_externa=u.get('amb_carga_externa',0),dias_leito_usados=leito,dias_leito_limite=u['cap_leito_dias'],dias_leito_carga_externa=u.get('dias_leito_carga_externa',0),dias_leito_capacidade_observada=u.get('dias_leito_capacidade_observada',0),dias_leito_capacidade_bruta=u.get('dias_leito_capacidade_bruta',0),leitos_sus_internacao=u.get('leitos_sus_internacao',0),leitos_sus_uti=u.get('leitos_sus_uti',0),passou=True))
    resumo=[]
    for k in ['AMB','HOSP']:
        v=[sum(a[j] for (i,g),a in origem.items() if g==k) for j in range(6)]
        a,b,c,na,nb,nc=v
        resumo.append(dict(tipo=k,demanda2=sum(demanda[i,k,2] for i in pop),demanda3=sum(demanda[i,k,3] for i in pop),termina2=a,direto3=b,via23=c,falta_termina2=na,falta_direto3=nb,falta_via23=nc,atendido2=a+c,atendido3=b+c,falta2=na+nc,falta3=nb+nc,proporcao_via_da_demanda=r,proporcao_via_efetivamente_atendida=c/(b+c) if b+c else 0,transferencias_internas=internos[k],distancia_media_por_percurso=desloc[k]/(a+b+c) if a+b+c else 0))
    salvar(pasta/'fluxos.csv',arcos);salvar(pasta/'capacidades.csv',auditoria);salvar(pasta/'demanda_e_percursos.csv',resumo)
    salvar(pasta/'ubs.csv',[dict(cnes=u['cnes'],nome=u['nome'],esf_existentes=u['esf'],esf_adicionais=cap_ubs[u['cnes']]/config.get('hab_por_esf',3000)-u['esf'],populacao_alocada=aloc_pop[u['cnes']],capacidade=cap_ubs[u['cnes']]) for u in U])
    return resumo
