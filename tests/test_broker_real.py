"""Roda ponte e simulador contra um Mosquitto real, com assinantes de verdade.

Usa uma instância própria em porta livre, com a configuração do repositório, para não
interferir em um broker que esteja rodando. É ignorado se o Mosquitto não estiver instalado.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import paho.mqtt.client as mqtt

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))

import banco
from protocolo import CMD_ALTERAR_INTERVALO, decodificar_ack, decodificar_comando, decodificar_pacote, montar_comando

EXECUTAVEL = shutil.which("mosquitto") or r"C:\Program Files\mosquitto\mosquitto.exe"
HOST = "127.0.0.1"


def porta_livre():
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def esperar(condicao, limite=10):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.05)
    return False


class Assinante:
    def __init__(self, porta):
        self.mensagens = []
        self.cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.cliente.on_connect = lambda c, *_: c.subscribe([("cubesat/#", 0), ("groundstation/#", 0)])
        self.cliente.on_message = lambda _c, _d, m: self.mensagens.append((m.topic, m.payload.decode(), m.retain))
        self.cliente.connect(HOST, porta)
        self.cliente.loop_start()

    def do_topico(self, topico):
        return [m for m in self.mensagens if m[0] == topico]

    def encerrar(self):
        self.cliente.loop_stop()
        self.cliente.disconnect()


@unittest.skipUnless(os.path.exists(EXECUTAVEL), "Mosquitto não instalado")
class TestBrokerReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.porta = porta_livre()
        with open(os.path.join(RAIZ, "server", "mosquitto.conf"), encoding="utf-8") as f:
            configuracao = f.read().replace("listener 1883", f"listener {cls.porta}")
        caminho_conf = os.path.join(cls.pasta.name, "mosquitto.conf")
        with open(caminho_conf, "w", encoding="utf-8") as f:
            f.write(configuracao)
        cls.broker = subprocess.Popen([EXECUTAVEL, "-c", caminho_conf],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def aberto():
            with socket.socket() as s:
                return s.connect_ex((HOST, cls.porta)) == 0
        assert esperar(aberto), "o Mosquitto não abriu a porta"

        cls.assinante = Assinante(cls.porta)
        time.sleep(0.3)

        cls.banco = os.path.join(cls.pasta.name, "teste.db")
        banco.preparar_banco(cls.banco)
        porta_serial = porta_livre()
        cls.ambiente = dict(
            os.environ,
            ESTACAO_DB=cls.banco,
            ESTACAO_SERIAL=f"socket://{HOST}:{porta_serial}",
            ESTACAO_MQTT_PORTA=str(cls.porta),
            PYTHONIOENCODING="utf-8",
        )
        cls.simulador = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "simulador_estacao.py"), "--porta", str(porta_serial),
             "--intervalo", "0.1", "--perda", "0", "--corrupcao", "0"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=cls.ambiente,
        )
        cls.simulador.stdout.readline()
        cls.ponte = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "serial_bridge.py")],
            stdout=subprocess.DEVNULL, env=cls.ambiente,
        )
        esperar(lambda: len(cls.assinante.do_topico("cubesat/telemetry/parsed")) >= 5)
        cls.comando = banco.registrar_comando(cls.banco, 1, CMD_ALTERAR_INTERVALO, 1)
        esperar(lambda: cls.assinante.do_topico("cubesat/command/ack"))

    @classmethod
    def tearDownClass(cls):
        cls.assinante.encerrar()
        for processo in (cls.ponte, cls.simulador, cls.broker):
            processo.terminate()
            processo.wait()
        cls.simulador.stdout.close()
        cls.pasta.cleanup()

    def test_a_telemetria_chega_em_todos_os_topicos(self):
        for topico in ("cubesat/telemetry/raw", "cubesat/telemetry/parsed", "groundstation/link/stats"):
            self.assertGreaterEqual(len(self.assinante.do_topico(topico)), 5, topico)

    def test_a_bruto_e_decodificado_coincidem(self):
        bruto = self.assinante.do_topico("cubesat/telemetry/raw")[0][1]
        parsed = json.loads(self.assinante.do_topico("cubesat/telemetry/parsed")[0][1])
        self.assertEqual(decodificar_pacote(bytes.fromhex(bruto))["contador"], parsed["contador"])

    def test_a_comando_e_ack_trafegam_pelo_broker(self):
        enviado = json.loads(self.assinante.do_topico("cubesat/command/send")[0][1])
        self.assertEqual((enviado["comando_id"], enviado["codigo"], enviado["parametro"]),
                         (self.comando, CMD_ALTERAR_INTERVALO, 1))
        ack = json.loads(self.assinante.do_topico("cubesat/command/ack")[0][1])
        self.assertEqual((ack["comando_id"], ack["status"]), (self.comando, 0))
        self.assertEqual(decodificar_ack(bytes.fromhex(ack["raw"]))["comando_id"], self.comando)

    def test_b_quem_assina_depois_recebe_o_status_retido(self):
        tardio = Assinante(self.porta)
        try:
            self.assertTrue(esperar(lambda: tardio.do_topico("groundstation/status")))
            _, conteudo, retido = tardio.do_topico("groundstation/status")[0]
            self.assertTrue(retido)
            self.assertEqual(json.loads(conteudo)["estado"], "online")
        finally:
            tardio.encerrar()

    def test_c_queda_inesperada_da_ponte_vira_status_offline(self):
        # Por último: derruba a ponte sem dar chance de ela avisar; quem publica é o broker
        self.ponte.kill()
        self.ponte.wait()
        self.assertTrue(esperar(lambda: json.loads(
            self.assinante.do_topico("groundstation/status")[-1][1])["estado"] == "offline", limite=15))


if __name__ == "__main__":
    unittest.main()
