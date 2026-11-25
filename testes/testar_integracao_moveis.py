"""Conservacao da cobertura e soma dos custos adicionais itinerantes."""
import unittest
import pandas as pd
from cobertura_efetiva import cobertura_efetiva, equipes_moveis
from integracao_resultados import custo_movel


class IntegracaoMoveis(unittest.TestCase):
    def test_capacidade_e_distancia_sem_contar_duas_vezes(self):
        pontos=pd.DataFrame(dict(i=[1,2],NM_BAIRRO=['Centro','Comunidade (rural)'],
                                 tipo_ponto=['bairro','rural'],lon=[0,.1],lat=[0,0],pessoas=[4000,1000]))
        ubs=pd.DataFrame(dict(id=['A'],nome=['UBS A'],lon=[0],lat=[0],esf=[1],acs=[3]))
        r,pp,_,_=cobertura_efetiva(pontos,ubs)
        self.assertAlmostEqual(r['pop_atendida_efetiva'],2250)
        self.assertAlmostEqual(r['cobertura_efetiva_pct'],45)
        mov,bases,visitas,_=equipes_moveis(pontos,pp,ubs)
        self.assertEqual(set(bases['id_ubs_base']), {'A'})
        self.assertEqual(set(bases['ponto_base']), {'UBS A'})
        self.assertAlmostEqual(float(bases.iloc[0]['lon']), 0)
        self.assertAlmostEqual(mov['atendida'],1000,places=4)
        # A falta de capacidade do Centro nao vira cobertura movel indevida.
        self.assertAlmostEqual(r['pop_atendida_efetiva']+mov['atendida'],3250,places=4)
        c=custo_movel({'equipes_moveis':mov},30000,4000)
        self.assertEqual(c['total_mensal'],30000+mov['acs_necessarios']*4000)
        self.assertEqual(c['total_anual'],12*c['total_mensal'])

    def test_ponto_distante_nao_pode_ser_sua_propria_base(self):
        pontos=pd.DataFrame(dict(i=[1],NM_BAIRRO=['Distante'],tipo_ponto=['rural'],
                                 lon=[.3],lat=[0],pessoas=[1000]))
        ubs=pd.DataFrame(dict(id=['A'],nome=['UBS A'],lon=[0],lat=[0],esf=[1],acs=[4]))
        _,pp,_,_=cobertura_efetiva(pontos,ubs)
        mov,b,v,d=equipes_moveis(pontos,pp,ubs)
        self.assertEqual(mov['atendida'],0)
        self.assertEqual(mov['nao_atendida'],1000)
        self.assertEqual(mov['equipes'],0)

    def test_sem_area_descoberta(self):
        pp=pd.DataFrame(dict(cobertura_geografica=[1]))
        r,b,v,d=equipes_moveis(None,pp,None)
        self.assertEqual(r['equipes'],0)
        self.assertEqual(r['acs_necessarios'],0)
        self.assertEqual(custo_movel({'equipes_moveis':r},30000,4000)['total_mensal'],0)


if __name__=='__main__':unittest.main()
