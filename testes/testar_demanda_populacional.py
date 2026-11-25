"""Confere rateio populacional, totais e ausencia de dependencia do perfil etario."""
import math
import unittest
from unittest.mock import patch
import preparar as modulo


class DemandaPopulacional(unittest.TestCase):
    def test_rateio_calculavel_a_mao(self):
        pontos=[dict(i='A',pessoas=200),dict(i='B',pessoas=800)]
        totais={('AMB',2):500,('AMB',3):100,('HOSP',2):20,('HOSP',3):5}
        d=modulo.distribuir_por_populacao(pontos,totais)
        self.assertEqual(d['A','AMB',2],100)
        self.assertEqual(d['B','AMB',2],400)
        self.assertEqual(d['A','HOSP',3],1)
        for (k,n),v in totais.items():
            self.assertAlmostEqual(sum(d[p['i'],k,n] for p in pontos),v)
        # Dividir um ponto entre UBS preserva o mesmo rateio por populacao vinculada.
        ubs=d['A','AMB',2]*.5+d['B','AMB',2]*.25
        self.assertEqual(ubs,500*(100+200)/1000)

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):modulo.distribuir_por_populacao([dict(i='A',pessoas=0)],{('AMB',2):10})
        with self.assertRaises(ValueError):modulo.distribuir_por_populacao([dict(i='A',pessoas=-1)],{('AMB',2):10})
        with self.assertRaises(ValueError):modulo.distribuir_por_populacao([dict(i='A',pessoas=1),dict(i='A',pessoas=2)],{('AMB',2):10})

    def test_preparacao_sem_ler_idades(self):
        original=modulo.ler
        def sem_idades(caminho,separador=';'):
            if caminho.name=='CENARIO_perfil_etario_91_pontos.csv':
                raise AssertionError('Perfil etario nao pode ser lido')
            rows=original(caminho,separador)
            if caminho.name.startswith(('sia_residentes_eletivo','sih_residentes_eletivo')):
                primeira=next(iter(rows[0]))
                return [{primeira:r[primeira],'Total':r['Total']} for r in rows]
            return rows
        with patch.object(modulo,'ler',side_effect=sem_idades):
            pontos,_,demanda,config=modulo.preparar()
        self.assertEqual(config['metodo_demanda'],'proporcional_populacao_sem_idade')
        pop=sum(float(p['pessoas']) for p in pontos)
        for k,n,total in [('AMB',2,190856),('AMB',3,15752),('HOSP',2,1065),('HOSP',3,350)]:
            self.assertAlmostEqual(sum(demanda[p['i'],k,n] for p in pontos),total,places=6)
            for p in pontos:
                self.assertAlmostEqual(demanda[p['i'],k,n],total*float(p['pessoas'])/pop,places=6)


if __name__=='__main__':unittest.main()
