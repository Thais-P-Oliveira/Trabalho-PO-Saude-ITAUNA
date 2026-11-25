"""Conservacao da demanda potencial e independencia do otimizador."""
import unittest
import pandas as pd
import numpy as np
from graficos_demanda import atribuicao_proxima,NOVAS

class GraficosPedido(unittest.TestCase):
    def test_cada_ponto_inteiro_vai_ao_mais_proximo(self):
        p=pd.DataFrame(dict(lon=[0,.01,.2],lat=[0,0,0],pessoas=[500,1000,1500]))
        u=pd.DataFrame(dict(lon=[0,.2],lat=[0,0]))
        carga,dist,proximas=atribuicao_proxima(p,u)
        np.testing.assert_allclose(carga,[1500,1500])
        self.assertEqual(carga.sum(),3000)
        self.assertEqual(list(proximas),[0,0,1])
        self.assertEqual(dist[0],0)

    def test_demanda_potencial_nao_e_limitada_por_raio(self):
        p=pd.DataFrame(dict(lon=[1],lat=[0],pessoas=[5000]))
        u=pd.DataFrame(dict(lon=[0],lat=[0]))
        carga,dist,_=atribuicao_proxima(p,u)
        self.assertEqual(carga[0],5000)
        self.assertGreater(dist[0],3)
        self.assertEqual(NOVAS['NOVA_77'],'N2')
        self.assertEqual(NOVAS['NOVA_64'],'N3')
        self.assertEqual(set(NOVAS.values()),{f'N{i}' for i in range(1,10)})
