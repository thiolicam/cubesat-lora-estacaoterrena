"""Roda simulador e ponte serial reais, em processos separados, com um banco temporario."""
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACOTES = 200


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestSimulacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.banco = os.path.join(cls.pasta.name, "teste.db")
        porta = porta_livre()
        ambiente = dict(
            os.environ,
            ESTACAO_DB=cls.banco,
            ESTACAO_SERIAL=f"socket://127.0.0.1:{porta}",
            PYTHONIOENCODING="utf-8",
        )
        simulador = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "simulador_estacao.py"),
             "--porta", str(porta), "--pacotes", str(PACOTES), "--intervalo", "0",
             "--perda", "0.1", "--corrupcao", "0.1", "--semente", "1"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=ambiente,
        )
        # A primeira linha so aparece com o servidor ja escutando
        simulador.stdout.readline()
        ponte = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "server", "serial_bridge.py")],
            capture_output=True, text=True, encoding="utf-8", env=ambiente, timeout=60,
        )
        cls.saida_ponte = ponte.stdout
        resumo = simulador.communicate(timeout=10)[0]
        cls.enviados, cls.validos, cls.invalidos, cls.perdidos = map(int, re.findall(r"\d+", resumo))

        con = sqlite3.connect(cls.banco)
        con.row_factory = sqlite3.Row
        cls.linhas = [dict(l) for l in con.execute("select * from pacotes order by id")]
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_simulacao_exercita_perda_e_corrupcao(self):
        self.assertEqual(self.enviados, PACOTES)
        self.assertGreater(self.invalidos, 0)
        self.assertGreater(self.perdidos, 0)

    def test_grava_uma_linha_por_pacote_valido(self):
        self.assertEqual(len(self.linhas), self.validos)

    def test_contadores_de_enlace_sao_gravados(self):
        ultima = self.linhas[-1]
        self.assertEqual(ultima["validos"], self.validos)
        self.assertLessEqual(ultima["invalidos"], self.invalidos)

    def test_lacunas_no_contador_revelam_os_pacotes_que_nao_chegaram(self):
        contadores = [l["contador"] for l in self.linhas]
        self.assertEqual(contadores, sorted(contadores))
        self.assertLess(len(contadores), contadores[-1] + 1)

    def test_tipos_e_sinais_chegam_corretos_ao_banco(self):
        self.assertTrue(any(l["temperatura"] < 0 for l in self.linhas))
        self.assertTrue(any(l["corrente"] < 0 for l in self.linhas))
        self.assertIsInstance(self.linhas[0]["cubesat_id"], int)
        self.assertIsInstance(self.linhas[0]["modo"], int)
        self.assertIsInstance(self.linhas[0]["rssi"], int)

    def test_ponte_nao_afirma_publicar_sem_broker(self):
        conectado = "Conectado ao Broker" in self.saida_ponte
        self.assertEqual("Telemetria real publicada" in self.saida_ponte, conectado)

    def test_dashboard_le_o_que_a_ponte_gravou(self):
        codigo = (
            "import sys, json; sys.path.insert(0, 'dashboard'); import dashboard as d;"
            "c = d.app.test_client();"
            "print(json.dumps([c.get('/api/estacao/status').get_json(),"
            " c.get('/api/telemetria/ultima').get_json(), c.get('/').status_code,"
            " c.get('/api/painel?limite=1000').get_json()]))"
        )
        saida = subprocess.run(
            [sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True,
            env=dict(os.environ, ESTACAO_DB=self.banco), check=True,
        ).stdout
        status, ultima, codigo_http, painel = json.loads(saida)
        self.assertEqual(status["total_pacotes_armazenados"], self.validos)
        self.assertEqual(ultima["contador"], self.linhas[-1]["contador"])
        self.assertEqual(codigo_http, 200)

        # O que a simulação perdeu de fato deve bater com o que o painel deduz do banco.
        # Só as pontas ficam de fora: antes do primeiro e depois do último pacote válido
        # não existe referência no contador.
        enlace = painel["enlace_total"]
        self.assertEqual(painel["enlace_janela"], enlace)
        self.assertEqual(enlace["recebidos"], self.validos)
        faltaram = enlace["esperados"] - enlace["recebidos"]
        self.assertLessEqual(faltaram, self.perdidos + self.invalidos)
        self.assertGreaterEqual(faltaram, self.perdidos + self.invalidos - 5)
        self.assertLessEqual(abs(enlace["corrompidos"] - self.invalidos), 5)


if __name__ == "__main__":
    unittest.main()
