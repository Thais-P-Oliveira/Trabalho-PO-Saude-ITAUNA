"""Protecao da revisao manual e consistencia das tabelas propostas."""
import unittest,re,hashlib
from pathlib import Path
from resultados_artigo import gerar,ROTULOS,nome_unidade
RAIZ=Path(__file__).resolve().parents[1]

class GeracaoArtigo(unittest.TestCase):
    def test_proibe_sobrescrever_artigo_manual(self):
        destino=RAIZ/'documentacao/artigo/resultados_artigo.tex'
        antes=hashlib.sha256(destino.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):gerar(RAIZ/'resultados/atual',destino)
        self.assertEqual(antes,hashlib.sha256(destino.read_bytes()).hexdigest())

    def test_rotulos_numeros_e_grupos_da_proposta(self):
        destino=RAIZ/'.cache/teste_resultados/resultados.tex'
        s=gerar(RAIZ/'resultados/atual',destino)
        for label in ROTULOS:self.assertEqual(s.count(r'\label{'+label+'}'),1)
        self.assertIn('2.010.004,00',s)
        self.assertIn('Total & 39 & 192 & 104.002 & 101.617',s)
        self.assertNotIn('rural500_3km_todos',s)
        self.assertIn('Índice relativo',s)
        self.assertIn('Nível 3 atendido',s)

    def test_nome_nao_corta_parentese_interno(self):
        self.assertEqual(nome_unidade('NOVA UBS (Setor 123 (rural))'),'Setor 123 (rural)')
