"""Gera uma proposta numerica separada, preservando os arquivos manuais do artigo."""
import argparse,json,re
from pathlib import Path
import pandas as pd

RAIZ=Path(__file__).resolve().parents[1]
MODELO=Path(__file__).with_name('templates')/'resultados_revisados.tex'
ROTULOS=['tab:cobertura','tab:unidades','tab:movel','tab:custos','tab:orcamento','tab:ambulatorial',
         'tab:internacoes','tab:acessibilidade','tab:sensibilidade','fig:mapa','fig:distancias',
         'fig:capacidades','fig:internacoes','fig:curva','fig:raios_custo','fig:raios_cobertura','fig:raios_distancia']

def br(v,n=2):return f'{float(v):,.{n}f}'.replace(',','X').replace('.',',').replace('X','.')
def escapar(s):return str(s).replace('&',r'\&').replace('_',r'\_').replace('%',r'\%')
def linha(*campos):return ' & '.join(map(str,campos))+r'\\'

def tabela(texto,rotulo,linhas):
    # Substitui somente os dados; conserva caption, label, fonte, nota e cabecalho revisados.
    inicio=texto.index(r'\label{'+rotulo+'}')
    fim=texto.index(r'\bottomrule',inicio)
    bloco=texto[inicio:fim]
    marcador=r'\endhead' if r'\endhead' in bloco else r'\midrule'
    a=inicio+bloco.index(marcador)+len(marcador)
    return texto[:a]+'\n'+'\n'.join(linhas)+'\n'+texto[fim:]

def nome_unidade(nome):
    # Retira so o parenteses EXTERNO, sem cortar o sufixo (rural) ou (urbana).
    if nome.startswith('NOVA UBS (') and nome.endswith(')'):nome=nome[len('NOVA UBS ('):-1]
    return nome

def assinatura(resultado):
    p=resultado/'plano'
    m=json.loads((p/'plano_aps.json').read_text(encoding='utf-8'))
    c=pd.read_csv(p/'comparacao_completa.csv',sep=';')
    return dict(parametros={k:m['parametros'].get(k) for k in ['raio','raio_rural','hab_esf','folga_custo','growth','hab_min_nova_rural']},
                total=m['total'],custos=m['custos']['operacional'],
                encaminhamentos=c[['cenario','via_percentual','tipo','atendido2','atendido3','distancia_media_por_percurso']].round(5).to_dict('records'))

def gerar(resultado,saida):
    resultado=Path(resultado);saida=Path(saida)
    # O texto do artigo e mantido manualmente e nao deve ser sobrescrito.
    if saida.resolve().is_relative_to((RAIZ/'documentacao/artigo').resolve()):
        raise ValueError('O artigo e manual: escolha uma pasta separada para a proposta de alteracoes.')
    plano=resultado/'plano'
    meta=json.loads((plano/'plano_aps.json').read_text(encoding='utf-8'))
    integ=json.loads((plano/'integracao.json').read_text(encoding='utf-8'))
    orc=json.loads((resultado/'orcamento/calculos.json').read_text(encoding='utf-8'))
    atual=json.loads((resultado/'financeiro/custo_equipes_resumo.json').read_text(encoding='utf-8'))
    u=pd.read_csv(plano/'aps/ubs_completas.csv')
    c=pd.read_csv(plano/'comparacao_completa.csv',sep=';')
    texto=MODELO.read_text(encoding='utf-8')
    r=integ['redes'];m=integ['custos_moveis']['plano']
    texto=tabela(texto,'tab:cobertura',[
        linha(f'Atual: {int((u.status=="EXISTENTE").sum())} UBS',br(r['atual']['cobertura_geografica_pct']),br(r['atual']['cobertura_efetiva_pct'])),
        linha(f'Proposta: {len(u)} UBS',br(r['plano']['cobertura_geografica_pct']),br(r['plano']['cobertura_efetiva_pct'])),
        linha(f'Proposta: {len(u)} UBS e equipes móveis','--',br(r['plano']['cobertura_efetiva_com_moveis_pct']))])
    linhas=[]
    rural=u.nome.str.contains('(rural)',case=False,regex=False)
    for titulo,grupo in [('UBS existentes',u[u.status=='EXISTENTE']),('Novas UBS urbanas',u[(u.status=='NOVA')&~rural]),('Novas UBS rurais',u[(u.status=='NOVA')&rural])]:
        if linhas:linhas.append(r'\midrule')
        linhas.append(r'\multicolumn{6}{l}{\textit{'+titulo+r'}}\\')
        for a in grupo.sort_values('pop_atendida',ascending=False).itertuples():
            linhas.append(linha(escapar(nome_unidade(a.nome)),int(a.n_esf),int(a.acs),br(a.pop_atendida,0),br(a.pop_coberta_raio,0),br(100*a.pop_atendida/(meta['parametros']['hab_esf']*a.n_esf),0)))
    linhas.extend([r'\midrule',linha('Total',int(u.n_esf.sum()),int(u.acs.sum()),br(u.pop_atendida.sum(),0),br(u.pop_coberta_raio.sum(),0),'')])
    texto=tabela(texto,'tab:unidades',linhas)
    b=pd.read_csv(plano/'vinculos_moveis/bases.csv',sep=';')
    texto=tabela(texto,'tab:movel',[linha(escapar(a.ponto_base),a.equipes,a.acs_necessarios,br(a.pop_atendida)) for a in b.itertuples()])
    grupos=orc['operacao_por_grupo']
    linhas=[linha(escapar(g['grupo'])+f" ({g['unidades']}), por mês",br(g['total_mensal'])) for g in grupos[:2]]
    linhas += [linha('Pessoal das equipes móveis, por mês',br(m['total_mensal'])),linha('Funcionamento total, por mês',br(integ['operacional_integrado_mensal'])),linha('Funcionamento total, por ano',br(integ['operacional_integrado_anual'])),linha('Construção das novas UBS (uma vez)',br(integ['investimento_construcao'])),linha('Funcionamento anual e construção integral',br(integ['implantacao_integrada']))]
    texto=tabela(texto,'tab:custos',linhas)
    dot=atual['orcamento_ap_2026_rreo']['DOTAÇÃO ATUALIZADA (a)']
    valores=[('Dotação atualizada da Atenção Básica',dot),('Rede atual: pessoal estimado e custos fixos',atual['ascendente']['equipes_mais_fixo_anual']),('Rede proposta: funcionamento',integ['operacional_integrado_anual']),('Rede proposta: funcionamento e construção',integ['implantacao_integrada'])]
    texto=tabela(texto,'tab:orcamento',[linha(n,br(v),br(v/dot*100,1)) for n,v in valores])
    texto=tabela(texto,'tab:ambulatorial',[linha('Única' if a.cenario=='unico' else 'Dois níveis',a.via_percentual,br(a.atendido2,1),br(a.atendido3,1),br(100*a.atendido3/a.demanda3,1),br(a.distancia_media_por_percurso)) for a in c[c.tipo=='AMB'].itertuples()])
    h=c[(c.tipo=='HOSP')&(c.cenario=='unico')&(c.via_percentual==50)].iloc[0]
    texto=tabela(texto,'tab:internacoes',[linha(n,br(h['demanda'+str(k)],1),br(h['atendido'+str(k)],1),br(h['falta'+str(k)],1)) for k,n in [(2,'Média'),(3,'Alta')]])
    a=pd.read_csv(plano/'aps/diagnostico/acessibilidade_por_zona.csv',sep=';')
    texto=tabela(texto,'tab:acessibilidade',[linha('Atual' if q.rede.startswith('atual') else 'Proposta',q.zona.title(),f'{q.beta:g}',br(q.acessibilidade_media_ponderada,3),br(q.acessibilidade_relativa_media)) for q in a[a.zona!='total'].itertuples()])
    sen=pd.read_csv(resultado/'sensibilidade/resumo.csv',sep=';').set_index('nome')
    linhas=[linha(r'Principal (3 km, mínimo rural 500, folga 2\%)',int((u.status=='NOVA').sum()),br(r['plano']['cobertura_efetiva_pct']),m['equipes'],br(integ['operacional_integrado_mensal']/1000),br(integ['investimento_construcao']/1e6))]
    grupos=[('Curva de cobertura e custo (folga nula)',[(f'curva_{x:04d}',f'Cobertura mínima de {br(x/10,1)}'+r'\%') for x in [934,950,960,970]]+[('curva_max','Cobertura máxima')]),
      ('Raio de cobertura (urbano/rural)',[('raio_2km','2/2 km'),('rural500_3km_urbano_5km_rural','3/5 km'),('raio_5km','5/5 km')]),
      ('Mínimo de abertura rural',[('rural_min_0','Sem mínimo'),('rural_min_1000','1.000 habitantes')]),
      ('Outros parâmetros',[('folga_5pct',r'Folga operacional de 5\%'),('crescimento_5pct',r'População 5\% maior'),('crescimento_10pct',r'População 10\% maior')])]
    for titulo,itens in grupos:
        linhas.extend([r'\midrule',r'\multicolumn{6}{l}{\textit{'+titulo+r'}}\\'])
        for chave,nome in itens:
            a=sen.loc[chave]
            if a.status=='Optimal':linhas.append(linha(nome,int(a.novas_ubs),br(100*a.cobertura),int(a.equipes_moveis),br(a.custo_operacional_mensal/1000),br(a.construcao_estimativa_por_porte/1e6)))
    texto=tabela(texto,'tab:sensibilidade',linhas)
    # Atualiza somente o bloco numerico. A discussao do artigo permanece sob controle editorial.
    texto=texto.replace('A média complexidade é praticamente toda alocada;', 'A média complexidade é praticamente toda alocada;')
    for chave in ROTULOS:
        if texto.count(r'\label{'+chave+'}')!=1:raise ValueError('Rotulo ausente ou duplicado: '+chave)
    saida.parent.mkdir(parents=True,exist_ok=True)
    saida.write_text(texto,encoding='utf-8')
    referencia=Path(__file__).with_name('templates')/'referencia_editorial.json'
    atual_assinatura=assinatura(resultado)
    mudou=referencia.exists() and json.loads(referencia.read_text(encoding='utf-8'))!=atual_assinatura
    nota=('ATENCAO: resultados diferem da referencia editorial; revisar os textos numericos antes de copiar.' if mudou else 'Resultados coincidem com a referencia editorial. Conferir os ajustes descritos na nota de pendencias.')
    saida.with_suffix('.LEIA-ME.txt').write_text(nota+'\nProposta separada: nao foi aplicado nenhum texto ao artigo manual.\n',encoding='utf-8')
    return texto

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--resultado',type=Path,required=True);p.add_argument('--saida',type=Path,required=True)
    a=p.parse_args();gerar(a.resultado,a.saida)
