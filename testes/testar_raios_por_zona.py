"""Compara o mesmo ponto a 4 km com limites urbano de 3 e rural de 5 km."""
from argparse import Namespace
import unittest
import numpy as np
import pandas as pd
import aps_base
from diagnosticar import cobertura_capacitada


class RaiosPorZona(unittest.TestCase):
    def test_raio_misto_preserva_limite_urbano(self):
        dem=pd.DataFrame(dict(i=[1,2],pessoas=[500,500],NM_BAIRRO=['Centro','Comunidade (rural)']))
        sites=pd.DataFrame([dict(id='UBS1',nome='UBS A',lat=0,lon=0,existente=True,fixo=12000)])
        D=np.array([[4.],[4.]])
        args=Namespace(raio=3,raio_rural=5,hab_esf=3000,esf_max=4,
                       hab_min_nova=2000,hab_min_nova_rural=500,max_novas=None,
                       custo_km=.05,folga_custo=.02)
        solver,_=aps_base.escolher_solver('auto',20,.0001,False)
        resultado=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertAlmostEqual(resultado['cobertura'],500,places=4)
        arcos=resultado['arcos'].set_index('i')
        self.assertFalse(bool(arcos.loc[1,'coberto']))
        self.assertTrue(bool(arcos.loc[2,'coberto']))
        self.assertEqual(cobertura_capacitada([500,500],[3000],D,[3,5]),500)
        args.raio_rural=None
        uniforme=aps_base.otimizar(dem,sites,D,args,solver,log=lambda *_:None)
        self.assertAlmostEqual(uniforme['cobertura'],0,places=4)

    def test_raio_invalido(self):
        with self.assertRaises(ValueError):
            aps_base.raios_por_ponto(pd.DataFrame(dict(NM_BAIRRO=['X'])),Namespace(raio=3,raio_rural=-5))


if __name__=='__main__':unittest.main()
