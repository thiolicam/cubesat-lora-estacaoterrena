import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))

import banco
from relatorio_testes import avaliar, contar_estranhos, gerar_relatorio, ler_dados, medir_periodo
from simulador_estacao import Simulacao


def pacote(contador, hora, receptor=1):
    return {"contador": contador, "data_hora": hora, "receptor_id": receptor, "frequencia_mhz": 915.0,
            "rssi": -90, "snr": 5.0, "validos": contador + 1, "invalidos": 0}


class TestAvaliacao(unittest.TestCase):
    def test_uma_hora_continua_e_aprovada(self):
        self.assertEqual(avaliar(3600, 2, 1), [])

    def test_duracao_curta_e_reprovada(self):
        self.assertIn("duração abaixo de 1 h", avaliar(3599, 2, 1))

    def test_parada_no_meio_e_reprovada_mesmo_com_duracao_suficiente(self):
        problemas = avaliar(18000, 3600, 1)
        self.assertEqual(len(problemas), 1)
        self.assertIn("1 h 0 min 0 s sem pacotes", problemas[0])

    def test_medir_periodo(self):
        pacotes = [pacote(0, "2026-11-04 10:00:00"), pacote(1, "2026-11-04 10:00:02"), pacote(2, "2026-11-04 10:05:02")]
        self.assertEqual(medir_periodo(pacotes), (302, 300))


class TestRelatorio(unittest.TestCase):
    def test_sem_pacotes(self):
        self.assertIn("Nenhum pacote", gerar_relatorio([], []))

    def test_conteudo(self):
        pacotes = [pacote(0, "2026-11-04 10:00:00"), pacote(2, "2026-11-04 10:00:04")]
        texto = gerar_relatorio(pacotes, [("confirmado", 3)], minimo_horas=1)
        self.assertIn("66,7% (2 de 3 transmissões)", texto)
        self.assertIn("**Reprovado:** duração abaixo de 1 h", texto)
        self.assertIn("| confirmado | 3 |", texto)
        self.assertNotIn("Ganho de diversidade", texto)

    def test_varios_receptores_mostram_o_ganho(self):
        pacotes = [pacote(0, "2026-11-04 10:00:00", 1), pacote(1, "2026-11-04 10:00:02", 2),
                   pacote(2, "2026-11-04 10:00:04", 1), pacote(2, "2026-11-04 10:00:04", 2)]
        texto = gerar_relatorio(pacotes, [])
        self.assertIn("Ganho de diversidade", texto)
        self.assertIn("100,0% (3 de 3 transmissões)", texto)

    def test_le_o_banco_sem_alterar_e_filtra_pelo_horario(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
            caminho = os.path.join(pasta, "t.db")
            banco.preparar_banco(caminho)
            con = sqlite3.connect(caminho)
            con.executemany("INSERT INTO pacotes (contador, data_hora) VALUES (?, ?)",
                            [(0, "2026-11-04 10:00:00"), (1, "2026-11-04 12:00:00")])
            con.execute("INSERT INTO comandos (cubesat_id, codigo, criado_em, estado) VALUES (1, 1, '2026-11-04 12:00:00', 'confirmado')")
            con.commit()
            con.close()
            modificado = os.path.getmtime(caminho)
            pacotes, comandos = ler_dados(caminho, "2026-11-04 11:00:00")
            self.assertEqual([p["contador"] for p in pacotes], [1])
            self.assertEqual(comandos, [("confirmado", 1)])
            self.assertEqual(os.path.getmtime(caminho), modificado)

    def test_linha_de_comando(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
            caminho, saida = os.path.join(pasta, "t.db"), os.path.join(pasta, "r.md")
            banco.preparar_banco(caminho)
            con = sqlite3.connect(caminho)
            con.execute("INSERT INTO pacotes (contador, receptor_id, data_hora) VALUES (0, 1, '2026-11-04 10:00:00')")
            con.commit()
            con.close()
            subprocess.run([sys.executable, os.path.join(RAIZ, "server", "relatorio_testes.py"), "--banco", caminho,
                            "--minimo-horas", "1", "--saida", saida], check=True, capture_output=True)
            with open(saida, encoding="utf-8") as f:
                self.assertIn("Reprovado", f.read())


class TestEstranhos(unittest.TestCase):
    def test_conta_so_o_que_aconteceu_no_periodo(self):
        pacotes = [dict(pacote(0, "2026-11-04 10:00:00"), validos=50, estranhos=10),
                   dict(pacote(1, "2026-11-04 10:00:02"), validos=51, estranhos=13)]
        self.assertEqual(contar_estranhos(pacotes), 3)

    def test_estacao_reiniciada_nao_gera_valor_negativo(self):
        pacotes = [dict(pacote(0, "2026-11-04 10:00:00"), validos=50, estranhos=10),
                   dict(pacote(1, "2026-11-04 10:00:02"), validos=51, estranhos=12),
                   dict(pacote(2, "2026-11-04 10:00:04"), validos=1, estranhos=4)]
        self.assertEqual(contar_estranhos(pacotes), 6)

    def test_firmware_antigo_nao_mede(self):
        self.assertIsNone(contar_estranhos([pacote(0, "2026-11-04 10:00:00")]))
        self.assertIn("não medido", gerar_relatorio([pacote(0, "2026-11-04 10:00:00")], []))


class TestSimuladorDepoisDeDormir(unittest.TestCase):
    def test_nao_repoe_os_envios_perdidos(self):
        args = types.SimpleNamespace(semente=1, intervalo=2.0, receptores=1, perda=0, corrupcao=0, pacotes=None)
        simulacao = Simulacao(lambda _dados: None, args)
        simulacao.proximo_envio = time.monotonic() - 18000  # como se o computador tivesse dormido 5 h
        simulacao.agendar_proximo_envio()
        self.assertGreaterEqual(simulacao.proximo_envio, time.monotonic() - 1)

    def test_em_ritmo_normal_mantem_o_intervalo(self):
        args = types.SimpleNamespace(semente=1, intervalo=2.0, receptores=1, perda=0, corrupcao=0, pacotes=None)
        simulacao = Simulacao(lambda _dados: None, args)
        base = time.monotonic()
        simulacao.proximo_envio = base
        simulacao.agendar_proximo_envio()
        self.assertEqual(simulacao.proximo_envio, base + 2.0)


if __name__ == "__main__":
    unittest.main()
