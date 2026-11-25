import unittest
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace
import pandas as pd
from pessoal_cnes import estimar
from vinculos_moveis import construir,ler_complemento

class PessoalVinculos(unittest.TestCase):
    def test_horas_parciais_e_auxiliar_sem_duplicar_equipe(self):
        linha=dict(medicos_horas_cadastradas=20,enfermeiros_horas_cadastradas=40,
                   tecnicos_enfermagem_horas_cadastradas=80,auxiliares_enfermagem_horas_cadastradas=40)
        self.assertEqual(estimar(linha,dict(medico=100,enfermeiro=80,tecnico=50)),280)

    def test_demanda_movel_muda_de_ubs_sem_duplicar_pessoas(self):
        dem=pd.DataFrame(dict(i=[1,2],NM_BAIRRO=['Centro','Rural'],tipo_ponto=['bairro','setor'],
                              lon=[0,.1],lat=[0,0],pessoas=[1000.,500.]))
        ubs=pd.DataFrame(dict(id_ubs=['A','B'],nome=['UBS A','UBS B'],lon=[0,.4],lat=[0,0],n_esf=[1,1],acs=[4,4]))
        arcos=pd.DataFrame([dict(i=1,id_ubs='A',pessoas=1000.),dict(i=2,id_ubs='B',pessoas=500.)])
        args=SimpleNamespace(raio=3,raio_rural=None,hab_esf=3000,fator_rota=1)
        raiz=Path(__file__).resolve().parents[1]/'.cache/testes'
        raiz.mkdir(parents=True,exist_ok=True)
        d=raiz/'vinculos_moveis';d.mkdir(exist_ok=True)
        with nullcontext(d) as d:
            v,m=construir(dem,ubs,arcos,args,Path(d),{'A':'A','B':'B'})
            self.assertAlmostEqual(v['2','A'],1)
            self.assertEqual(m['A'],500)
            self.assertAlmostEqual(sum(x for (i,u),x in v.items() if i=='2'),1)
            salvo,_=construir(dem,ubs,arcos,args,Path(d),{'A':'A','B':'B'},usar_salvo=True)
            self.assertEqual(v,salvo)
            from cobertura_efetiva import cobertura_efetiva
            rede=ubs.rename(columns={'id_ubs':'id','n_esf':'esf'})
            _,pp,_,_=cobertura_efetiva(dem,rede)
            _,bases,_,_=ler_complemento(Path(d)/'vinculos_moveis',pp)
            self.assertEqual(bases.id_ubs_base.tolist(),['A'])


class LimitesComparaveis(unittest.TestCase):
    def test_mesmo_teto_por_complexidade_nos_dois_cenarios(self):
        from encaminhamentos import dados
        p=[dict(i='1',pessoas=1000,lat=0,lon=0)]
        u=[dict(cnes='A',nome='UBS',nivel_principal='1',novo_2=0,novo_3=0,
                lat=0,lon=0,esf=1,max_esf=1,cap_amb_anual=0,cap_leito_dias=0),
           dict(cnes='B',nome='Centro',nivel_principal='2',novo_2=1,novo_3=1,
                lat=0,lon=0,esf=0,max_esf=0,cap_amb_anual=100,cap_amb_2=90,cap_amb_3=10,cap_leito_dias=0)]
        d={('1',k,n):100 for k in ['AMB','HOSP'] for n in [2,3]}
        config=dict(tmp2=5,tmp3=3)
        a=dados(p,u,d,config,False,.5)[0]
        b=dados(p,u,d,config,True,.5)[0]
        for nome,esperado in [('AMB2',90),('AMB3',10)]:
            for txt in [a,b]:
                bloco=txt.split('param '+nome+' :=')[1].split(';')[0]
                self.assertIn('fB '+str(esperado),bloco)
