"""Roda simulador e ponte reais contra um broker MQTT minimo, que registra o que recebe.

O cliente MQTT e real e fala o protocolo pela rede. O broker daqui so aceita conexoes e
guarda as publicacoes: nao entrega mensagens, entao nao substitui um teste com o Mosquitto.
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))

from banco import preparar_banco
from protocolo import decodificar_pacote

PACOTES = 40


class BrokerDeTeste:
    def __init__(self):
        self.publicacoes = []
        self.conexoes = []
        self.servidor = socket.create_server(("127.0.0.1", 0))
        self.porta = self.servidor.getsockname()[1]
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while True:
            try:
                conexao, _ = self.servidor.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(conexao,), daemon=True).start()

    @staticmethod
    def _ler(conexao, tamanho):
        dados = b""
        while len(dados) < tamanho:
            parte = conexao.recv(tamanho - len(dados))
            if not parte:
                raise ConnectionError
            dados += parte
        return dados

    def _atender(self, conexao):
        with conexao:
            try:
                while True:
                    cabecalho = self._ler(conexao, 1)[0]
                    restante, multiplicador = 0, 1
                    while True:
                        byte = self._ler(conexao, 1)[0]
                        restante += (byte & 0x7F) * multiplicador
                        multiplicador *= 128
                        if not byte & 0x80:
                            break
                    corpo = self._ler(conexao, restante)
                    tipo = cabecalho >> 4
                    if tipo == 1:  # CONNECT
                        self.conexoes.append(corpo)
                        conexao.sendall(bytes([0x20, 0x02, 0x00, 0x00]))
                    elif tipo == 3:  # PUBLISH com QoS 0
                        tamanho = int.from_bytes(corpo[:2], "big")
                        self.publicacoes.append((
                            corpo[2:2 + tamanho].decode(), corpo[2 + tamanho:].decode(), bool(cabecalho & 1),
                        ))
                    elif tipo == 12:  # PINGREQ
                        conexao.sendall(bytes([0xD0, 0x00]))
            except (ConnectionError, OSError):
                pass

    def fechar(self):
        self.servidor.close()


class TestMqtt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.broker = BrokerDeTeste()
        cls.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta_serial = s.getsockname()[1]
        ambiente = dict(
            os.environ,
            ESTACAO_DB=os.path.join(cls.pasta.name, "teste.db"),
            ESTACAO_SERIAL=f"socket://127.0.0.1:{porta_serial}",
            ESTACAO_MQTT_PORTA=str(cls.broker.porta),
            PYTHONIOENCODING="utf-8",
        )
        simulador = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "simulador_estacao.py"),
             "--porta", str(porta_serial), "--pacotes", str(PACOTES), "--intervalo", "0.01",
             "--perda", "0.1", "--corrupcao", "0.1", "--semente", "2"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=ambiente,
        )
        simulador.stdout.readline()
        cls.saida_ponte = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "server", "serial_bridge.py")],
            capture_output=True, text=True, encoding="utf-8", env=ambiente, timeout=60,
        ).stdout
        resumo = simulador.communicate(timeout=10)[0]
        cls.validos = list(map(int, re.findall(r"\d+", resumo)))[1]

    @classmethod
    def tearDownClass(cls):
        cls.broker.fechar()
        cls.pasta.cleanup()

    def conteudos(self, topico):
        return [conteudo for t, conteudo, _ in self.broker.publicacoes if t == topico]

    def test_cada_pacote_valido_gera_uma_mensagem_por_topico(self):
        self.assertGreater(self.validos, 0)
        for topico in ("cubesat/telemetry/raw", "cubesat/telemetry/parsed", "groundstation/link/stats"):
            self.assertEqual(len(self.conteudos(topico)), self.validos, topico)

    def test_ponte_informa_a_publicacao(self):
        self.assertIn("Conectado ao Broker", self.saida_ponte)
        self.assertEqual(self.saida_ponte.count("Telemetria publicada"), self.validos)

    def test_pacote_bruto_e_decodificado_descrevem_o_mesmo_dado(self):
        for bruto, texto in zip(self.conteudos("cubesat/telemetry/raw"), self.conteudos("cubesat/telemetry/parsed")):
            original = decodificar_pacote(bytes.fromhex(bruto))
            parsed = json.loads(texto)
            self.assertNotIn("raw", parsed)
            for campo in ("contador", "tensao_bateria", "temperatura", "corrente", "modo", "flags"):
                self.assertEqual(original[campo], parsed[campo], campo)

    def test_estatisticas_de_enlace(self):
        enlace = json.loads(self.conteudos("groundstation/link/stats")[-1])
        self.assertEqual(set(enlace), {"receptor_id", "frequencia_mhz", "rssi", "snr", "validos", "invalidos"})
        self.assertEqual(enlace["validos"], self.validos)

    def test_status_online_e_offline_ficam_retidos(self):
        status = [(json.loads(c)["estado"], retido) for t, c, retido in self.broker.publicacoes
                  if t == "groundstation/status"]
        self.assertEqual(status, [("online", True), ("offline", True)])

    def test_broker_recebe_aviso_de_queda_inesperada(self):
        # O "will" viaja no CONNECT: o broker o publica se a ponte cair sem avisar
        self.assertIn(b"groundstation/status", self.broker.conexoes[0])
        self.assertIn(b"offline", self.broker.conexoes[0])


class TestBanco(unittest.TestCase):
    def test_banco_antigo_recebe_colunas_e_preserva_dados(self):
        import sqlite3
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
            caminho = os.path.join(pasta, "antigo.db")
            con = sqlite3.connect(caminho)
            con.execute("CREATE TABLE pacotes (id INTEGER PRIMARY KEY, contador INTEGER)")
            con.execute("INSERT INTO pacotes (contador) VALUES (42)")
            con.commit()
            con.close()

            preparar_banco(caminho)
            preparar_banco(caminho)  # repetir nao pode falhar

            con = sqlite3.connect(caminho)
            con.row_factory = sqlite3.Row
            linha = con.execute("SELECT * FROM pacotes").fetchone()
            con.close()
            self.assertEqual(linha["contador"], 42)
            self.assertIsNone(linha["receptor_id"])
            self.assertIn("frequencia_mhz", linha.keys())


if __name__ == "__main__":
    unittest.main()
