"""Ciclo comando -> ACK com simulador, ponte e API reais (S6.6)."""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))
sys.path.insert(0, os.path.join(RAIZ, "dashboard"))

import banco
import dashboard as painel
from protocolo import (
    CMD_ALTERAR_INTERVALO, CMD_ENVIO_PERIODICO, CMD_REINICIAR, CMD_SOLICITAR_TELEMETRIA,
    STATUS_COMANDO_DESCONHECIDO, STATUS_OK, STATUS_PARAMETRO_INVALIDO,
    decodificar_ack, decodificar_comando, montar_ack, montar_comando, status_do_comando,
)
from serial_bridge import LeitorDeLinhas


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sistema:
    """Sobe simulador e ponte com banco próprio."""

    def __init__(self, *argumentos_simulador, espera_ack=10):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.banco = os.path.join(self.pasta.name, "teste.db")
        porta = porta_livre()
        ambiente = dict(
            os.environ,
            ESTACAO_DB=self.banco,
            ESTACAO_SERIAL=f"socket://127.0.0.1:{porta}",
            ESTACAO_MQTT_PORTA=str(porta_livre()),
            ESTACAO_ESPERA_ACK=str(espera_ack),
            PYTHONIOENCODING="utf-8",
        )
        self.simulador = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "simulador_estacao.py"),
             "--porta", str(porta), *argumentos_simulador],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", env=ambiente,
        )
        self.simulador.stdout.readline()
        self.ponte = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "server", "serial_bridge.py")],
            stdout=subprocess.DEVNULL, env=ambiente,
        )
        banco.preparar_banco(self.banco)
        time.sleep(3)  # espera a ponte (2 s tentando o broker) e a abertura da serial

    def encerrar(self):
        for processo in (self.ponte, self.simulador):
            processo.terminate()
            processo.wait()
        self.simulador.stdout.close()
        self.pasta.cleanup()

    def estado(self, comando_id):
        con = sqlite3.connect(self.banco)
        linha = con.execute("SELECT estado FROM comandos WHERE id = ?", (comando_id,)).fetchone()
        con.close()
        return linha[0]

    def esperar_estado(self, comando_id, limite=15):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            estado = self.estado(comando_id)
            if estado not in (banco.PENDENTE, banco.ENVIADO):
                return estado
            time.sleep(0.05)
        return estado

    def contadores(self):
        con = sqlite3.connect(self.banco)
        linhas = [l[0] for l in con.execute("SELECT contador FROM pacotes ORDER BY id")]
        con.close()
        return linhas


class TestCicloDeComando(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sistema = Sistema("--intervalo", "0.05", "--perda", "0", "--corrupcao", "0")

    @classmethod
    def tearDownClass(cls):
        cls.sistema.encerrar()

    def executar(self, codigo, parametro=0):
        comando_id = banco.registrar_comando(self.sistema.banco, 1, codigo, parametro)
        return self.sistema.esperar_estado(comando_id)

    def teste_1_desativar_para_o_envio_e_ativar_retoma(self):
        self.assertEqual(self.executar(CMD_ENVIO_PERIODICO, 0), banco.CONFIRMADO)
        time.sleep(0.3)
        antes = len(self.sistema.contadores())
        time.sleep(0.6)
        self.assertEqual(len(self.sistema.contadores()), antes)

        self.assertEqual(self.executar(CMD_ENVIO_PERIODICO, 1), banco.CONFIRMADO)
        time.sleep(0.6)
        self.assertGreater(len(self.sistema.contadores()), antes)

    def teste_2_solicitar_telemetria_gera_um_pacote_sem_envio_periodico(self):
        self.assertEqual(self.executar(CMD_ENVIO_PERIODICO, 0), banco.CONFIRMADO)
        time.sleep(0.3)
        antes = len(self.sistema.contadores())
        self.assertEqual(self.executar(CMD_SOLICITAR_TELEMETRIA), banco.CONFIRMADO)
        time.sleep(0.4)
        self.assertEqual(len(self.sistema.contadores()), antes + 1)
        self.executar(CMD_ENVIO_PERIODICO, 1)

    def teste_3_alterar_intervalo_muda_o_ritmo(self):
        self.assertEqual(self.executar(CMD_ALTERAR_INTERVALO, 2), banco.CONFIRMADO)
        time.sleep(0.3)
        antes = len(self.sistema.contadores())
        time.sleep(1)
        self.assertLessEqual(len(self.sistema.contadores()) - antes, 1)

    def teste_4_reiniciar_zera_o_contador_e_volta_ao_padrao(self):
        contador_antes = self.sistema.contadores()[-1]
        self.assertGreater(contador_antes, 0)
        self.assertEqual(self.executar(CMD_REINICIAR), banco.CONFIRMADO)
        pacotes_antes = len(self.sistema.contadores())
        time.sleep(0.5)
        depois = self.sistema.contadores()[pacotes_antes:]
        # Contador voltou a zero e o intervalo de 2 s do teste anterior voltou ao padrão de 0,05 s
        self.assertGreater(len(depois), 2)
        self.assertLess(depois[0], contador_antes)
        self.assertLess(depois[0], 5)

    def teste_5_parametro_invalido_e_rejeitado_pelo_cubesat(self):
        # Insere direto no banco: a API recusaria este comando antes de chegar ao rádio
        self.assertEqual(self.executar(CMD_ALTERAR_INTERVALO, 0), banco.REJEITADO)

    def teste_6_codigo_desconhecido_e_rejeitado(self):
        comando_id = banco.registrar_comando(self.sistema.banco, 1, 99)
        self.assertEqual(self.sistema.esperar_estado(comando_id), banco.REJEITADO)
        con = sqlite3.connect(self.sistema.banco)
        status = con.execute("SELECT ack_status FROM comandos WHERE id = ?", (comando_id,)).fetchone()[0]
        con.close()
        self.assertEqual(status, STATUS_COMANDO_DESCONHECIDO)

    def teste_7_comandos_em_fila_saem_um_de_cada_vez(self):
        ids = [banco.registrar_comando(self.sistema.banco, 1, CMD_SOLICITAR_TELEMETRIA) for _ in range(3)]
        for comando_id in ids:
            self.assertEqual(self.sistema.esperar_estado(comando_id), banco.CONFIRMADO)


class TestSemResposta(unittest.TestCase):
    def test_comando_perdido_fica_sem_resposta(self):
        sistema = Sistema("--intervalo", "1", "--perda", "1", "--corrupcao", "0", espera_ack=1)
        try:
            comando_id = banco.registrar_comando(sistema.banco, 1, CMD_SOLICITAR_TELEMETRIA)
            self.assertEqual(sistema.esperar_estado(comando_id), banco.SEM_RESPOSTA)
        finally:
            sistema.encerrar()


class TestFila(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.banco = os.path.join(self.pasta.name, "fila.db")
        banco.preparar_banco(self.banco)

    def tearDown(self):
        self.pasta.cleanup()

    def test_nao_libera_outro_comando_enquanto_um_aguarda_ack(self):
        primeiro = banco.registrar_comando(self.banco, 1, 1)
        banco.registrar_comando(self.banco, 1, 1)
        self.assertEqual(banco.proximo_comando(self.banco)["id"], primeiro)
        banco.marcar_enviado(self.banco, primeiro)
        self.assertIsNone(banco.proximo_comando(self.banco))
        banco.registrar_ack(self.banco, primeiro, STATUS_OK)
        self.assertEqual(banco.proximo_comando(self.banco)["id"], primeiro + 1)

    def test_comando_antigo_expira_e_nao_e_transmitido(self):
        comando = banco.registrar_comando(self.banco, 1, CMD_REINICIAR)
        con = sqlite3.connect(self.banco)
        con.execute("UPDATE comandos SET criado_em = datetime('now', '-1 hour') WHERE id = ?", (comando,))
        con.commit()
        con.close()
        banco.expirar_comandos(self.banco, 10, 30)
        self.assertIsNone(banco.proximo_comando(self.banco))
        self.assertEqual(banco.listar_comandos(self.banco)[0]["estado"], banco.EXPIRADO)

    def test_ack_atrasado_ainda_e_registrado(self):
        comando = banco.registrar_comando(self.banco, 1, 1)
        banco.marcar_enviado(self.banco, comando)
        con = sqlite3.connect(self.banco)
        con.execute("UPDATE comandos SET enviado_em = datetime('now', '-1 hour') WHERE id = ?", (comando,))
        con.commit()
        con.close()
        banco.expirar_comandos(self.banco, 10, 30)
        self.assertEqual(banco.listar_comandos(self.banco)[0]["estado"], banco.SEM_RESPOSTA)
        self.assertTrue(banco.registrar_ack(self.banco, comando, STATUS_OK))
        self.assertEqual(banco.listar_comandos(self.banco)[0]["estado"], banco.CONFIRMADO)

    def test_ack_de_comando_inexistente_e_ignorado(self):
        self.assertFalse(banco.registrar_ack(self.banco, 999, STATUS_OK))


class TestApi(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.original = painel.DB_PATH
        painel.DB_PATH = os.path.join(self.pasta.name, "api.db")
        self.cliente = painel.app.test_client()

    def tearDown(self):
        painel.DB_PATH = self.original
        self.pasta.cleanup()

    def test_comando_valido_entra_na_fila(self):
        resposta = self.cliente.post("/api/comandos", json={"codigo": CMD_ALTERAR_INTERVALO, "parametro": 5})
        self.assertEqual(resposta.status_code, 201)
        comandos = self.cliente.get("/api/painel").get_json()["comandos"]
        self.assertEqual(
            (comandos[0]["codigo"], comandos[0]["parametro"], comandos[0]["estado"]),
            (CMD_ALTERAR_INTERVALO, 5, banco.PENDENTE),
        )

    def test_comandos_invalidos_sao_recusados(self):
        casos = [
            {"codigo": 99},
            {"codigo": CMD_ALTERAR_INTERVALO, "parametro": 0},
            {"codigo": CMD_ALTERAR_INTERVALO, "parametro": 3601},
            {"codigo": CMD_ENVIO_PERIODICO, "parametro": 2},
            {"codigo": CMD_REINICIAR, "parametro": 1},
            {"codigo": "1"},
            {"codigo": True},
            {"parametro": 1},
            [1, 2],
        ]
        for caso in casos:
            self.assertEqual(self.cliente.post("/api/comandos", json=caso).status_code, 400, caso)
        self.assertEqual(self.cliente.get("/api/comandos").get_json(), [])

    def test_formulario_de_outro_site_e_recusado(self):
        resposta = self.cliente.post("/api/comandos", data={"codigo": CMD_REINICIAR})
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(self.cliente.get("/api/comandos").get_json(), [])


class TestProtocolo(unittest.TestCase):
    def test_comando_tem_11_bytes_e_ida_e_volta(self):
        pacote = montar_comando(1, 7, CMD_ALTERAR_INTERVALO, 300)
        self.assertEqual(len(pacote), 11)
        self.assertEqual(
            decodificar_comando(pacote),
            {"cubesat_id": 1, "comando_id": 7, "codigo": CMD_ALTERAR_INTERVALO, "parametro": 300},
        )

    def test_ack_tem_10_bytes_e_ida_e_volta(self):
        pacote = montar_ack(1, 7, CMD_ALTERAR_INTERVALO, STATUS_PARAMETRO_INVALIDO)
        self.assertEqual(len(pacote), 10)
        self.assertEqual(
            decodificar_ack(pacote),
            {"cubesat_id": 1, "comando_id": 7, "codigo": CMD_ALTERAR_INTERVALO, "status": STATUS_PARAMETRO_INVALIDO},
        )

    def test_exemplos_de_docs_protocolo(self):
        self.assertEqual(
            montar_comando(1, 7, CMD_ALTERAR_INTERVALO, 5), bytes.fromhex("AA 01 02 01 00 07 02 00 05 E2 DC"))
        self.assertEqual(
            montar_ack(1, 7, CMD_ALTERAR_INTERVALO, STATUS_OK), bytes.fromhex("AA 01 03 01 00 07 02 00 19 89"))

    def test_bit_invertido_e_rejeitado(self):
        for montar, decodificar in ((lambda: montar_comando(1, 7, 1), decodificar_comando),
                                    (lambda: montar_ack(1, 7, 1, 0), decodificar_ack)):
            original = montar()
            for byte in range(len(original)):
                alterado = bytearray(original)
                alterado[byte] ^= 0x01
                with self.assertRaises(ValueError):
                    decodificar(bytes(alterado))

    def test_regras_de_status(self):
        self.assertEqual(status_do_comando(CMD_SOLICITAR_TELEMETRIA, 0), STATUS_OK)
        self.assertEqual(status_do_comando(CMD_ALTERAR_INTERVALO, 3600), STATUS_OK)
        self.assertEqual(status_do_comando(CMD_ALTERAR_INTERVALO, 3601), STATUS_PARAMETRO_INVALIDO)
        self.assertEqual(status_do_comando(CMD_ENVIO_PERIODICO, 2), STATUS_PARAMETRO_INVALIDO)
        self.assertEqual(status_do_comando(0, 0), STATUS_COMANDO_DESCONHECIDO)


class PortaFalsa:
    def __init__(self, *pedacos):
        self.pedacos = list(pedacos)

    def readline(self):
        return self.pedacos.pop(0) if self.pedacos else b""


class TestLeitorDeLinhas(unittest.TestCase):
    def test_linha_dividida_pelo_tempo_de_espera_nao_se_perde(self):
        leitor = LeitorDeLinhas(PortaFalsa(b'{"contador"', b"", b': 1}\r\n', b"proxima\n"))
        self.assertEqual([leitor.ler() for _ in range(4)], [None, None, '{"contador": 1}', "proxima"])


if __name__ == "__main__":
    unittest.main()
