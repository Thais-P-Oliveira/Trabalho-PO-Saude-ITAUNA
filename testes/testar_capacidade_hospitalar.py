"""Verifica contagem SUS, exclusao de observacao e reserva de outros atendimentos."""
import unittest
from capacidade_hospitalar import PASTA, extrair_leitos, capacidade_disponivel, preparar_capacidade


class CapacidadeHospitalar(unittest.TestCase):
    def test_contagem_oficial_por_categoria(self):
        pagina=(PASTA/'2105780_202607.html').read_bytes().decode('latin-1')
        leitos=extrair_leitos(pagina)
        self.assertEqual(len(leitos),15)
        self.assertEqual(sum(r['existentes'] for r in leitos),150)
        self.assertEqual(sum(r['sus'] for r in leitos if r['grupo']=='internacao'),79)
        self.assertEqual(sum(r['sus'] for r in leitos if r['grupo']=='complementar_UTI'),19)
        self.assertFalse(any('OBSERVACAO' in r['descricao'] for r in leitos))

    def test_leitos_dias_e_reserva(self):
        self.assertEqual(capacidade_disponivel(10,30,80),(300,220,0))
        self.assertEqual(capacidade_disponivel(10,30,350),(300,0,50))
        with self.assertRaises(ValueError):capacidade_disponivel(10,30,-1)

    def test_calculo_real_e_fonte_ativa(self):
        cap=preparar_capacidade()['2105780']
        self.assertEqual(cap['leitos_sus_total'],98)
        self.assertEqual(cap['dias_capacidade_bruta'],79*365)
        self.assertEqual(cap['dias_uti_brutos'],19*365)
        self.assertIsNone(cap['dias_uti_disponiveis'])
        self.assertAlmostEqual(cap['dias_carga_outros'],29633.649682319272,places=6)
        self.assertEqual(cap['dias_disponiveis_modelo'],0)
        self.assertAlmostEqual(cap['dias_gerais_disponiveis_superior'],6136.350317680728,places=6)
        self.assertFalse(cap['ocupacao_por_tipo_identificada'])
        from preparar import preparar
        _,unidades,_,config=preparar()
        hospital=next(u for u in unidades if u['cnes']=='2105780')
        self.assertAlmostEqual(hospital['cap_leito_dias'],cap['dias_disponiveis_modelo'],places=6)
        self.assertEqual(hospital['leitos_sus_internacao']+hospital['leitos_sus_uti'],98)
        self.assertIn('CNES 202607',config['leitos'])


if __name__=='__main__':unittest.main()
