import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))

from metricas import LIMITE_SALTO, calcular_agregado, calcular_enlace, calcular_por_hora, calcular_por_origem


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


def pacote(receptor, contador, rssi=-90, snr=5.0, frequencia=915.0, hora="2026-11-04 10:15:00"):
    return {"receptor_id": receptor, "frequencia_mhz": frequencia, "contador": contador,
            "rssi": rssi, "snr": snr, "data_hora": hora}


class TestEstatisticas(unittest.TestCase):
    def test_medias_de_sinal_ignoram_valores_vazios(self):
        r = calcular_enlace([pacote(1, 0, -80, 4.0), pacote(1, 1, -100, 8.0), pacote(1, 2, None, None)])
        self.assertEqual((r["rssi_medio"], r["snr_medio"]), (-90, 6))

    def test_sem_pacotes_nao_ha_media(self):
        r = calcular_enlace([])
        self.assertIsNone(r["rssi_medio"])
        self.assertIsNone(r["snr_medio"])

    def test_um_receptor_nao_esconde_as_perdas_do_outro(self):
        # O receptor 1 recebe tudo; o 2 perde os pacotes 1 e 2
        linhas = [pacote(1, 0), pacote(2, 0), pacote(1, 1), pacote(1, 2), pacote(1, 3), pacote(2, 3)]
        r1, r2 = calcular_por_origem(linhas)
        self.assertEqual((r1["receptor_id"], r1["esperados"], r1["recebidos"]), (1, 4, 4))
        self.assertEqual((r2["receptor_id"], r2["esperados"], r2["recebidos"]), (2, 4, 2))

    def test_mesmo_receptor_em_frequencias_diferentes_fica_separado(self):
        linhas = [pacote(1, 0, frequencia=915.0), pacote(1, 0, frequencia=923.3)]
        self.assertEqual([r["frequencia_mhz"] for r in calcular_por_origem(linhas)], [915.0, 923.3])

    def test_agregado_soma_as_origens(self):
        linhas = [pacote(1, 0), pacote(2, 0), pacote(1, 1), pacote(1, 2), pacote(1, 3), pacote(2, 3)]
        r = calcular_agregado(linhas)
        self.assertEqual((r["esperados"], r["recebidos"], r["taxa_recepcao"]), (8, 6, 0.75))

    def test_agregado_nao_confunde_receptores_fora_de_ordem_com_interrupcao(self):
        # Sem separar por receptor, 5 depois de 6 pareceria um salto enorme
        linhas = [pacote(1, 5), pacote(1, 6), pacote(2, 5), pacote(2, 6)]
        self.assertEqual(calcular_agregado(linhas)["interrupcoes"], 0)

    def test_agregado_com_um_receptor_e_o_proprio_calculo(self):
        linhas = [pacote(1, 0), pacote(1, 2)]
        self.assertEqual(calcular_agregado(linhas), calcular_enlace(linhas))

    def test_linhas_antigas_sem_receptor_tem_grupo_proprio(self):
        linhas = [pacote(None, 0, frequencia=None), pacote(1, 1)]
        self.assertEqual([r["receptor_id"] for r in calcular_por_origem(linhas)], [1, None])

    def test_por_hora_separa_periodos_do_mais_recente_ao_mais_antigo(self):
        linhas = [
            pacote(1, 0, hora="2026-11-04 09:59:59"),
            pacote(1, 1, hora="2026-11-04 10:00:00"),
            pacote(2, 1, hora="2026-11-04 10:30:00"),
        ]
        r = calcular_por_hora(linhas)
        self.assertEqual(
            [(x["periodo"], x["receptor_id"], x["recebidos"]) for x in r],
            [("2026-11-04 10:00:00", 1, 1), ("2026-11-04 10:00:00", 2, 1), ("2026-11-04 09:00:00", 1, 1)],
        )


if __name__ == "__main__":
    unittest.main()
