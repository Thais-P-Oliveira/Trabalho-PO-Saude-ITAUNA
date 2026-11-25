"""Vincula a demanda especializada da populacao movel a sua UBS-base."""
import pandas as pd
from cobertura_efetiva import cobertura_efetiva,equipes_moveis


def construir(dem,ubs,arcos,args,saida,por_id,usar_salvo=False):
    pasta=saida/'vinculos_moveis';pasta.mkdir(exist_ok=True)
    if usar_salvo:
        tabela=pd.read_csv(pasta/'populacao_por_ubs.csv',sep=';',dtype={'i':str,'ubs':str})
        mov=tabela[tabela.origem=='movel'].groupby('ubs').pessoas.sum().to_dict()
        return {(str(r.i),str(r.ubs)):float(r.pessoas)/float(dem.loc[dem.i==int(r.i),'pessoas'].iloc[0])
                for r in tabela.groupby(['i','ubs'],as_index=False).pessoas.sum().itertuples()},mov
    rede=pd.DataFrame(dict(id=ubs.id_ubs,nome=ubs.nome,lon=ubs.lon,lat=ubs.lat,esf=ubs.n_esf,acs=ubs.acs))
    _,pp,_,_=cobertura_efetiva(dem,rede,args.raio,args.raio_rural,args.hab_esf,750,args.fator_rota)
    mov,bases,visitas,_=equipes_moveis(dem,pp,rede)
    bases.to_csv(pasta/'bases.csv',sep=';',index=False)
    visitas.to_csv(pasta/'visitas.csv',sep=';',index=False)
    pop={str(int(r.i)):float(r.pessoas) for r in dem.itertuples()}
    nomes={r.NM_BAIRRO:str(int(r.i)) for r in dem.itertuples()}
    quant={};qmov={}
    if len(visitas):
        b=bases.set_index('equipe_movel').id_ubs_base.to_dict()
        for v in visitas.itertuples():
            i=nomes[v.ponto];u=por_id[b[v.equipe_movel]]
            qmov[i,u]=qmov.get((i,u),0)+float(v.pessoas)
    atend={i:sum(v for (j,u),v in qmov.items() if j==i) for i in pop}
    linhas=[]
    for a in arcos.to_dict('records'):
        i=str(int(a['i']));u=por_id[a['id_ubs']]
        n=float(a['pessoas'])*max(0,1-atend[i]/pop[i])
        linhas.append(dict(i=i,ubs=u,origem='fixa',pessoas=n))
    linhas += [dict(i=i,ubs=u,origem='movel',pessoas=n) for (i,u),n in qmov.items()]
    tabela=pd.DataFrame(linhas)
    tabela.to_csv(pasta/'populacao_por_ubs.csv',sep=';',index=False)
    for r in tabela.groupby(['i','ubs'],as_index=False).pessoas.sum().itertuples():
        quant[str(r.i),str(r.ubs)]=float(r.pessoas)/pop[str(r.i)]
    for i in pop:
        if abs(sum(v for (j,u),v in quant.items() if j==i)-1)>1e-6:
            raise ValueError('Integracao movel nao conserva populacao '+i)
    carga={u:sum(n for (i,b),n in qmov.items() if b==u) for u in por_id.values()}
    return quant,carga


def ler_complemento(pasta,por_ponto):
    """Reutiliza as bases ja usadas nos encaminhamentos; evita outro otimo equivalente."""
    arquivo=pasta/'bases.csv'
    if not arquivo.exists():return None
    bases=pd.read_csv(arquivo,sep=';') if arquivo.stat().st_size>3 else pd.DataFrame()
    arquivo_v=pasta/'visitas.csv'
    visitas=pd.read_csv(arquivo_v,sep=';') if len(bases) else pd.DataFrame()
    desc=por_ponto[por_ponto.cobertura_geografica==0].copy()
    carga=visitas.groupby('ponto').pessoas.sum() if len(visitas) else pd.Series(dtype=float)
    desc['pop_atendida_movel']=desc.NM_BAIRRO.map(carga).fillna(0.)
    desc['pop_nao_atendida']=desc.pessoas-desc.pop_atendida_movel
    atendida=float(desc.pop_atendida_movel.sum());pop=float(desc.pessoas.sum())
    mov=dict(equipes=int(bases.equipes.sum()) if len(bases) else 0,bases=len(bases),
             acs_necessarios=int(bases.acs_necessarios.sum()) if len(bases) else 0,
             populacao_sem_cobertura=pop,atendida=atendida,nao_atendida=max(0,pop-atendida),
             hab_movel=2000.,raio_rota_km=15.,max_paradas_por_equipe=5,max_equipes=None,
             origem='Mesmo complemento usado na vinculacao especializada')
    return mov,bases,visitas,desc
