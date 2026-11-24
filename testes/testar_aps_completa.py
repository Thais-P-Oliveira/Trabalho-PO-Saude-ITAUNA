"""Verifica candidatas, ACS, crescimento, custos, cobertura e exportacoes da APS."""
import csv
import os
import sys
import unittest
import ast
from pathlib import Path
from caminhos import PASTA,MODELOS,DOCUMENTACAO,CACHE
os.environ.setdefault('MPLCONFIGDIR',str(CACHE/'matplotlib'))
import aps_base
from planejar import auditar_aps

class APSCompleta(unittest.TestCase):
    def test_equipes_atuais_preservadas_e_novas_limitadas(self):
        from argparse import Namespace
        from contextlib import nullcontext
        import pandas as pd
        import numpy as np
        temporarios=(PASTA.parent/'tmp').resolve()
        assert temporarios.is_relative_to(PASTA.parent.resolve())
        temporarios.mkdir(exist_ok=True)
        pasta_teste=temporarios/'teste_limites_equipes'
        pasta_teste.mkdir(exist_ok=True)
        with nullcontext(pasta_teste) as pasta:
            cadastro=Path(pasta)/'ubs.csv'
            cadastro.write_text('j,cnes\n1,0000001\n',encoding='utf-8')
            limites=Path(pasta)/'limites.csv'
            limites.write_text('cnes;esf_atuais;esf_max\n0000001;2;2\nNOVA;0;1\n',encoding='utf-8')
            dem=pd.DataFrame(dict(i=[0,1,2],pessoas=[1500,4500,3000]))
            sites=pd.DataFrame([dict(id='UBS1' if j==0 else f'NOVA_{j}',nome=str(j),
                                    lat=0,lon=j,existente=j==0,fixo=12000 if j==0 else 15000)
                                for j in range(3)])
            D=np.full((3,3),100.);np.fill_diagonal(D,0.)
            args=Namespace(raio=3,hab_esf=3000,esf_max=4,hab_min_nova=2000,
                           max_novas=None,custo_km=.05,folga_custo=.02,
                           limites_equipes=str(limites),ubs=str(cadastro))
            solver,_=aps_base.escolher_solver('auto',20,.0001,False)
            res=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
            existentes=res['ubs'].loc[res['ubs'].status=='EXISTENTE']
            novas=res['ubs'].loc[res['ubs'].status=='NOVA']
            self.assertEqual(list(existentes.n_esf),[2])
            self.assertTrue((novas.n_esf==1).all())
            self.assertAlmostEqual(res['cobertura'],7500,places=1)
            # Novas unidades maiores podem receber duas equipes e cobrir o ponto inteiro,
            # sem alterar o limite nem retirar as equipes da unidade existente.
            limites.write_text('cnes;esf_atuais;esf_max\n0000001;2;2\nNOVA;0;4\n',encoding='utf-8')
            maiores=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
            self.assertEqual(list(maiores['ubs'].loc[maiores['ubs'].status=='EXISTENTE','n_esf']),[2])
            self.assertEqual(int(maiores['ubs'].loc[maiores['ubs'].id_ubs=='NOVA_1','n_esf'].iloc[0]),2)
            self.assertAlmostEqual(maiores['cobertura'],9000,places=1)
            # O limite nao pode exigir a retirada de uma equipe atual.
            limites.write_text('cnes;esf_atuais;esf_max\n0000001;2;1\nNOVA;0;1\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Limites de equipes invalidos'):
                aps_base.limites_equipes(sites,args)

    def test_limites_reais_22_ubs_e_excecoes(self):
        from argparse import Namespace
        import pandas as pd
        from caminhos import BASE
        args=Namespace(demanda=str(BASE/'pontos_demanda_itauna.csv'),
                       ubs=str(BASE/'unidades_existentes_itauna.csv'),growth=None,growth_file=None,
                       fator_rota=1,dist_min_cand=1,esf_max=4,
                       limites_equipes=str(BASE/'fontes_publicas/estrutura_ubs_cnes/limites_equipes_modelo.csv'))
        _,_,sites,_=aps_base.carregar_dados(args)
        limites=aps_base.limites_equipes(sites,args)
        existentes=[limites[j] for j,s in sites.iterrows() if s['existente']]
        self.assertEqual(len(existentes),22)
        self.assertEqual(sum(a for a,b in existentes),23)
        self.assertEqual(sum(b for a,b in existentes),23)
        for j,s in sites.iterrows():
            if not s['existente']:self.assertEqual(limites[j],(0,1))
            elif s['id'] in ['UBS14','UBS34']:self.assertEqual(limites[j],(1,1))
            elif s['id']=='UBS27':self.assertEqual(limites[j],(2,2))
        # O novo cenario altera somente as candidatas, preservando a tabela anterior.
        args.limites_equipes=str(BASE/'fontes_publicas/estrutura_ubs_cnes/limites_equipes_novas_ate4.csv')
        ampliados=aps_base.limites_equipes(sites,args)
        for j,s in sites.iterrows():
            self.assertEqual(ampliados[j],limites[j] if s['existente'] else (0,4))

    def test_regras_e_opcoes_originais_preservadas(self):
        original=(DOCUMENTACAO/'versao_original/model.py').read_text(encoding='utf-8')
        copia=(MODELOS/'aps_base.py').read_text(encoding='utf-8')
        def funcao(txt,nome):return next(n for n in ast.parse(txt).body if isinstance(n,ast.FunctionDef) and n.name==nome)
        # Crescimento, candidatas e distancias mantem a mesma implementacao.
        self.assertEqual(ast.dump(funcao(original,'carregar_dados')),ast.dump(funcao(copia,'carregar_dados')))
        # Restricoes e termos de custo da formulacao original nao foram removidos.
        inicio='    for i in range(m_):'
        fim='    if cob_min is None:'
        bloco=copia[copia.index(inicio):copia.index(fim)]
        bloco=bloco[:bloco.index('    operacional=custo_fixo+custo_eq')]
        bloco=bloco.replace('    # Sem teto por padrao; o limite so vale quando informado explicitamente.\n    if args.max_novas is not None:\n        prob += pl.lpSum(y.values()) <= args.max_novas, \"max_novas\"', '    prob += pl.lpSum(y.values()) <= args.max_novas, \"max_novas\"')
        bloco=bloco.replace('minimo_nova(sites.iloc[j], dem, args) * y[j]', 'args.hab_min_nova * y[j]')
        bloco=bloco.replace('limites[j][1] * y[j]', 'args.esf_max * y[j]')
        self.assertEqual(original[original.index(inicio):original.index(fim)].rstrip(),bloco.rstrip())
        def opcoes(txt):
            return [ast.dump(n) for n in ast.walk(funcao(txt,'main')) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument' and n.args[0].value not in ['--hab-min-nova-rural','--limites-equipes','--raio-rural','--horizonte-anos','--folga-custo']]
        # A unica opcao alterada e max-novas: agora opcional, sem teto padrao.
        normalizada=copia.replace('ap.add_argument("--max-novas", type=int, default=None, help="teto opcional de novas UBS; omitido = sem teto adicional")', 'ap.add_argument("--max-novas", type=int, default=5, help="max. de novas UBS")')
        normalizada=normalizada.replace('help="pop. minima dentro do raio para abrir nova UBS urbana"', 'help="pop. minima dentro do raio para abrir nova UBS"')
        self.assertEqual(opcoes(original),opcoes(normalizada))

    def test_sem_teto_permite_mais_de_cinco_novas(self):
        from argparse import Namespace
        import pandas as pd
        import numpy as np
        dem=pd.DataFrame(dict(i=range(7),pessoas=[3000]*7))
        sites=pd.DataFrame([dict(id=str(j),nome=str(j),lat=0,lon=j,existente=j==0,fixo=12000 if j==0 else 15000) for j in range(7)])
        D=np.full((7,7),100.);np.fill_diagonal(D,0.)
        args=Namespace(raio=3,hab_esf=3000,esf_max=4,hab_min_nova=2000,max_novas=None,custo_km=.05,folga_custo=.02)
        solver,_=aps_base.escolher_solver('auto',20,.0001,False)
        livre=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertEqual(sum(livre['ubs'].status=='NOVA'),6)
        self.assertAlmostEqual(livre['cobertura'],21000,places=0)
        args.max_novas=5
        limitado=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertEqual(sum(limitado['ubs'].status=='NOVA'),5)
        self.assertAlmostEqual(limitado['cobertura'],18000,places=0)

    def test_abertura_rural_pequena_preserva_minimo_urbano(self):
        from argparse import Namespace
        import pandas as pd
        import numpy as np
        dem=pd.DataFrame(dict(i=[0,1,2],pessoas=[3000,400,400],NM_BAIRRO=['Centro','Setor A (rural)','Setor B (urbana)']))
        sites=pd.DataFrame([dict(id=str(j),nome=str(j),lat=0,lon=j,existente=j==0,fixo=12000 if j==0 else 15000,ponto=None if j==0 else j) for j in range(3)])
        D=np.full((3,3),100.);np.fill_diagonal(D,0.)
        args=Namespace(raio=3,hab_esf=3000,esf_max=4,hab_min_nova=2000,hab_min_nova_rural=0,max_novas=None,custo_km=.05,folga_custo=.02)
        solver,_=aps_base.escolher_solver('auto',20,.0001,False)
        res=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertEqual(set(res['ubs'].id_ubs),{'0','1'})
        self.assertAlmostEqual(res['cobertura'],3400,places=0)
        rural=res['ubs'].loc[res['ubs'].id_ubs=='1'].iloc[0]
        self.assertEqual(rural.minimo_pop_abertura,0)
        self.assertGreaterEqual(rural.n_esf,1)
        args.hab_min_nova_rural=2000
        antigo=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertAlmostEqual(antigo['cobertura'],3000,places=0)

    def test_fluxo_original_com_crescimento_e_pareto(self):
        pasta=CACHE/'testes_sinteticos/aps_completa';pasta.mkdir(parents=True,exist_ok=True)
        demanda=pasta/'demanda.csv';ubs=pasta/'ubs.csv'
        demanda.write_text('i,CD_BAIRRO,NM_BAIRRO,lon,lat,pessoas,domicilios,tipo_ponto\n1,1,A,0,0,3000,1000,bairro\n2,2,B,0.1,0,3000,1000,bairro\n',encoding='utf-8')
        ubs.write_text('j,nivel_sugerido,cnes,nome_fantasia,lon,lat\n1,PHC,0000001,UBS A,0,0\n',encoding='utf-8')
        antes=sys.argv[:]
        try:
            sys.argv=['aps_base.py','--demanda',str(demanda),'--ubs',str(ubs),'--saida',str(pasta/'saida'),'--growth','10','--max-novas','1','--pareto','--quiet','--time-limit','20']
            ctx=aps_base.main()
        finally:sys.argv=antes
        auditar_aps(ctx,pasta)
        self.assertAlmostEqual(ctx['res']['total'],6600)
        self.assertEqual(sum(ctx['res']['ubs']['status']=='NOVA'),1)
        self.assertEqual(int(ctx['res']['ubs']['acs'].sum()),10)
        self.assertAlmostEqual(ctx['res']['cobertura'],6600,places=2)
        for nome in ['resultado_itauna.xlsx','mapa_interativo.html','pareto_cobertura_custo.png','mapa_itauna_ubs.png','painel_resultados.png','alocacao_completa.csv']:
            self.assertTrue((pasta/'saida'/nome).stat().st_size>0,nome)
        # O plano salvo deve reproduzir locais, equipes e alocacoes sem novo solve.
        import shutil
        from planejar import salvar_plano,carregar_plano
        origem=pasta/'snapshot';destino=pasta/'reuso'
        origem.mkdir(exist_ok=True);destino.mkdir(exist_ok=True)
        shutil.copytree(pasta/'saida',origem/'aps',dirs_exist_ok=True)
        salvar_plano(ctx,origem)
        reuso=carregar_plano(origem,destino)
        auditar_aps(reuso,destino)
        self.assertEqual(list(reuso['res']['ubs'].id_ubs),list(ctx['res']['ubs'].id_ubs))
        self.assertAlmostEqual(reuso['res']['cobertura'],ctx['res']['cobertura'])
        alvo=origem/'aps/ubs_completas.csv';conteudo=alvo.read_bytes()
        try:
            alvo.write_bytes(conteudo+b'\n')
            with self.assertRaisesRegex(ValueError,'Plano APS alterado'):
                carregar_plano(origem,destino)
        finally:alvo.write_bytes(conteudo)
        # Tambem confere crescimento diferente por ponto.
        growth=pasta/'crescimento.csv';growth.write_text('i,pct\n1,20\n2,0\n',encoding='utf-8')
        args=ctx['args'];args.growth=None;args.growth_file=str(growth)
        dem,_,_,_=aps_base.carregar_dados(args)
        self.assertEqual(list(dem['pessoas']),[3600,3000])

if __name__=='__main__':unittest.main()
