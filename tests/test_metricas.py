import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))

from metricas import LIMITE_SALTO, calcular_enlace


def por_contador(*contadores):
    return [{"contador": c} for c in contadores]


def por_estacao(*pares):
    return [{"contador": i, "validos": v, "invalidos": inv} for i, (v, inv) in enumerate(pares)]


class TestRecepcao(unittest.TestCase):
    def test_sem_pacotes_nao_ha_taxa(self):
        r = calcular_enlace([])
        self.assertEqual((r["esperados"], r["recebidos"]), (0, 0))
        self.assertIsNone(r["taxa_recepcao"])

    def test_sequencia_completa(self):
        r = calcular_enlace(por_contador(0, 1, 2))
        self.assertEqual((r["esperados"], r["recebidos"], r["taxa_recepcao"]), (3, 3, 1.0))

    def test_lacunas_contam_como_nao_recebidos(self):
        r = calcular_enlace(por_contador(0, 2, 3, 7))
        self.assertEqual((r["esperados"], r["recebidos"], r["nao_chegaram"]), (8, 4, 4))
        self.assertEqual(r["taxa_recepcao"], 0.5)

    def test_contador_voltando_a_zero_nao_e_perda(self):
        r = calcular_enlace(por_contador(65534, 65535, 0, 1))
        self.assertEqual((r["esperados"], r["recebidos"]), (4, 4))

    def test_reinicio_do_cubesat_nao_e_perda(self):
        r = calcular_enlace(por_contador(100, 101, 0, 1))
        self.assertEqual((r["esperados"], r["recebidos"], r["interrupcoes"]), (4, 4, 1))

    def test_salto_grande_nao_e_perda(self):
        r = calcular_enlace(por_contador(10, 10 + LIMITE_SALTO + 1))
        self.assertEqual((r["esperados"], r["recebidos"], r["interrupcoes"]), (2, 2, 1))

    def test_salto_no_limite_ainda_e_perda(self):
        r = calcular_enlace(por_contador(10, 10 + LIMITE_SALTO))
        self.assertEqual((r["esperados"], r["interrupcoes"]), (LIMITE_SALTO + 1, 0))

    def test_pacote_repetido_conta_uma_vez(self):
        r = calcular_enlace(por_contador(5, 5, 6))
        self.assertEqual((r["esperados"], r["recebidos"]), (2, 2))


class TestCorrompidos(unittest.TestCase):
    def test_desde_o_inicio_da_estacao_conta_todos(self):
        self.assertEqual(calcular_enlace(por_estacao((1, 2), (2, 3)))["corrompidos"], 3)

    def test_janela_no_meio_da_sessao_conta_so_a_diferenca(self):
        self.assertEqual(calcular_enlace(por_estacao((50, 10), (51, 12)))["corrompidos"], 2)

    def test_reinicio_da_estacao_nao_gera_valor_negativo(self):
        linhas = por_estacao((50, 10), (51, 12), (1, 0), (2, 3))
        self.assertEqual(calcular_enlace(linhas)["corrompidos"], 5)

    def test_linhas_antigas_sem_contadores_sao_ignoradas(self):
        self.assertEqual(calcular_enlace(por_estacao((None, None), (1, 1)))["corrompidos"], 1)

    def test_corrompidos_saem_dos_que_nao_chegaram(self):
        linhas = [
            {"contador": 0, "validos": 1, "invalidos": 0},
            {"contador": 3, "validos": 2, "invalidos": 1},
        ]
        r = calcular_enlace(linhas)
        self.assertEqual((r["esperados"], r["corrompidos"], r["nao_chegaram"]), (4, 1, 1))


if __name__ == "__main__":
    unittest.main()
