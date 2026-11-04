"""Filtros e estatísticas da API, com um banco alimentado por vários receptores."""
import os
import sqlite3
import subprocess
import socket
import sys
import tempfile
import time
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))
sys.path.insert(0, os.path.join(RAIZ, "dashboard"))

import banco
import dashboard as painel


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.original = painel.DB_PATH
        painel.DB_PATH = os.path.join(cls.pasta.name, "api.db")
        banco.preparar_banco(painel.DB_PATH)
        con = sqlite3.connect(painel.DB_PATH)
        linhas = [
            # receptor, frequência, contador, rssi
            (1, 915.0, 0, -80), (2, 915.0, 0, -90), (3, 923.3, 0, -100),
            (1, 915.0, 1, -80), (3, 923.3, 1, -100),
            (1, 915.0, 2, -80), (2, 915.0, 2, -90), (3, 923.3, 2, -100),
        ]
        con.executemany(
            "INSERT INTO pacotes (receptor_id, frequencia_mhz, contador, rssi, snr, tipo) VALUES (?, ?, ?, ?, 5.0, 1)",
            linhas,
        )
        con.commit()
        con.close()
        cls.cliente = painel.app.test_client()

    @classmethod
    def tearDownClass(cls):
        painel.DB_PATH = cls.original
        cls.pasta.cleanup()

    def painel(self, consulta=""):
        return self.cliente.get(f"/api/painel?{consulta}").get_json()

    def test_sem_filtro_soma_todos_os_receptores(self):
        dados = self.painel()
        self.assertEqual(len(dados["pacotes"]), 8)
        self.assertEqual((dados["enlace_total"]["esperados"], dados["enlace_total"]["recebidos"]), (9, 8))
        self.assertEqual(dados["enlace_total"]["interrupcoes"], 0)

    def test_filtro_por_receptor(self):
        dados = self.painel("receptor=2")
        self.assertEqual({p["receptor_id"] for p in dados["pacotes"]}, {2})
        self.assertEqual((dados["enlace_total"]["esperados"], dados["enlace_total"]["recebidos"]), (3, 2))
        self.assertEqual(dados["enlace_total"]["rssi_medio"], -90)

    def test_filtro_por_frequencia(self):
        dados = self.painel("frequencia=923.3")
        self.assertEqual({p["receptor_id"] for p in dados["pacotes"]}, {3})

    def test_filtros_combinados_sem_resultado(self):
        dados = self.painel("receptor=1&frequencia=923.3")
        self.assertEqual(dados["pacotes"], [])
        self.assertIsNone(dados["enlace_total"]["taxa_recepcao"])

    def test_filtro_nao_reduz_as_opcoes(self):
        opcoes = self.painel("receptor=1")["opcoes"]
        self.assertEqual(opcoes, {"receptores": [1, 2, 3], "frequencias": [915.0, 923.3]})

    def test_filtro_invalido_e_ignorado_sem_injetar_sql(self):
        dados = self.painel("receptor=1%20OR%201=1&frequencia=abc")
        self.assertEqual(len(dados["pacotes"]), 8)

    def test_estatisticas_por_origem(self):
        linhas = self.cliente.get("/api/estatisticas").get_json()
        resumo = [(l["receptor_id"], l["frequencia_mhz"], l["recebidos"], l["esperados"]) for l in linhas]
        self.assertEqual(resumo, [(1, 915.0, 3, 3), (2, 915.0, 2, 3), (3, 923.3, 3, 3)])
        self.assertEqual(linhas[1]["rssi_medio"], -90)

    def test_estatisticas_por_hora_respeitam_o_filtro(self):
        linhas = self.cliente.get("/api/estatisticas?periodo=hora&receptor=3").get_json()
        self.assertEqual({l["receptor_id"] for l in linhas}, {3})
        self.assertRegex(linhas[0]["periodo"], r"^\d{4}-\d{2}-\d{2} \d{2}:00:00$")


class TestVariosReceptoresDePontaAPonta(unittest.TestCase):
    def test_simulador_ponte_e_api(self):
        pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        caminho = os.path.join(pasta.name, "teste.db")
        porta = porta_livre()
        ambiente = dict(
            os.environ,
            ESTACAO_DB=caminho,
            ESTACAO_SERIAL=f"socket://127.0.0.1:{porta}",
            ESTACAO_MQTT_PORTA=str(porta_livre()),
            PYTHONIOENCODING="utf-8",
        )
        simulador = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "simulador_estacao.py"), "--porta", str(porta),
             "--pacotes", "150", "--intervalo", "0", "--perda", "0.2", "--corrupcao", "0", "--semente", "4",
             "--receptores", "3"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=ambiente,
        )
        simulador.stdout.readline()
        subprocess.run([sys.executable, os.path.join(RAIZ, "server", "serial_bridge.py")],
                       stdout=subprocess.DEVNULL, env=ambiente, timeout=60)
        simulador.communicate(timeout=10)

        original = painel.DB_PATH
        painel.DB_PATH = caminho
        try:
            linhas = painel.app.test_client().get("/api/estatisticas").get_json()
        finally:
            painel.DB_PATH = original
            time.sleep(0.1)
            pasta.cleanup()

        self.assertEqual([(l["receptor_id"], l["frequencia_mhz"]) for l in linhas],
                         [(1, 915.0), (2, 915.0), (3, 923.3)])
        # Perdas independentes: cada receptor recebe pacotes diferentes, perto de 80%
        for linha in linhas:
            self.assertGreater(linha["taxa_recepcao"], 0.65)
            self.assertLess(linha["taxa_recepcao"], 0.95)
            self.assertEqual(linha["interrupcoes"], 0)


if __name__ == "__main__":
    unittest.main()
