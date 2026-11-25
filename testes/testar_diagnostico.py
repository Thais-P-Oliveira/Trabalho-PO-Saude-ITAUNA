"""Verifica propriedades matematicas do diagnostico sem executar a otimizacao APS."""
import math
import unittest
from diagnosticar import acessibilidade, cobertura_capacitada


class DiagnosticoTeste(unittest.TestCase):
    def test_exemplo_calculavel_a_mao(self):
        A, _, V = acessibilidade([100, 200], [150], [[1], [2]], 1, .1)
        self.assertEqual(V, [200])
        self.assertEqual(A, [.75, .375])

    def test_pontos_coincidentes_e_conservacao_da_oferta(self):
        for beta in [1, 2]:
            A, _, _ = acessibilidade([100, 200], [150, 300], [[0, 3], [2, 0]], beta, .1)
            self.assertTrue(all(math.isfinite(a) for a in A))
            self.assertAlmostEqual(100*A[0]+200*A[1], 450)

    def test_limite_da_capacidade(self):
        self.assertEqual(cobertura_capacitada([100, 100], [150], [[1], [2]], 3), 150)

    def test_fora_do_raio(self):
        self.assertEqual(cobertura_capacitada([100, 100], [150], [[1], [4]], 3), 100)

    def test_realocacao_entre_unidades(self):
        # O primeiro ponto pode usar duas UBS; o segundo so pode usar a primeira.
        self.assertEqual(cobertura_capacitada([100, 100], [100, 100], [[1, 1], [1, 4]], 3), 200)

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            acessibilidade([100], [150], [[0]], 1, 0)


if __name__ == '__main__':
    unittest.main()
