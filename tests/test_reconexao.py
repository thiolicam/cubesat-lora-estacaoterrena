"""A ponte precisa sobreviver a uma porta serial que some e volta, como num cabo que mexe (T5)."""
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))

import serial

import serial_bridge

LINHA = (b'{"cubesat_id": 1, "tipo": 1, "contador": 7, "tensao_bateria": 3.7, "rssi": -45, "snr": 9.5, '
         b'"validos": 1, "invalidos": 0, "receptor_id": 1, "frequencia_mhz": 915.0}\r\n')


class PortaQueCai:
    """Entrega algumas linhas e depois falha, como uma porta USB desconectada."""

    def __init__(self, linhas, depois):
        self.linhas = list(linhas)
        self.depois = depois
        self.fechada = False

    def readline(self):
        if self.linhas:
            return self.linhas.pop(0)
        raise self.depois

    def write(self, _dados):
        pass

    def close(self):
        self.fechada = True


class ClienteFalso:
    def publish(self, *_args, **_kwargs):
        return mock.Mock(rc=0)


class TestReconexao(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.banco = os.path.join(self.pasta.name, "teste.db")

    def tearDown(self):
        self.pasta.cleanup()

    def rodar(self, porta, aberturas):
        saida = io.StringIO()
        with mock.patch.object(serial_bridge, "DB_PATH", self.banco), \
                mock.patch.object(serial_bridge, "PORTA_SERIAL", porta), \
                mock.patch.object(serial_bridge, "ESPERA_RECONEXAO_S", 0), \
                mock.patch.object(serial_bridge, "ENVIA_COMANDOS", False), \
                mock.patch.object(serial_bridge, "criar_cliente_mqtt", ClienteFalso), \
                mock.patch.object(serial_bridge, "encerrar_cliente_mqtt", lambda _c: None), \
                mock.patch.object(serial_bridge.serial, "serial_for_url", side_effect=aberturas), \
                redirect_stdout(saida):
            serial_bridge.main()
        return saida.getvalue()

    def contadores(self):
        con = sqlite3.connect(self.banco)
        linhas = [c for (c,) in con.execute("SELECT contador FROM pacotes ORDER BY id")]
        con.close()
        return linhas

    def test_porta_que_cai_e_volta_nao_para_a_ponte(self):
        primeira = PortaQueCai([LINHA], serial.SerialException("ClearCommError failed (Acesso negado)"))
        terceira = PortaQueCai([LINHA], KeyboardInterrupt())
        aberturas = [
            primeira,
            serial.SerialException("could not open port 'COM6'"),  # a porta ainda não voltou
            terceira,
        ]
        saida = self.rodar("COM6", aberturas)
        self.assertEqual(self.contadores(), [7, 7])
        self.assertTrue(primeira.fechada)
        self.assertIn("Tentando de novo", saida)
        self.assertEqual(saida.count("✅ Conectado à porta serial"), 2)

    def test_erro_repetido_aparece_uma_vez(self):
        erro = serial.SerialException("could not open port 'COM6'")
        saida = self.rodar("COM6", [erro, erro, erro, PortaQueCai([], KeyboardInterrupt())])
        self.assertEqual(saida.count("could not open port"), 1)

    def test_no_simulador_a_conexao_encerrada_termina_a_ponte(self):
        porta = PortaQueCai([LINHA], serial.SerialException("socket disconnected"))
        saida = self.rodar("socket://127.0.0.1:7000", [porta])
        self.assertEqual(self.contadores(), [7])
        self.assertNotIn("Tentando de novo", saida)


if __name__ == "__main__":
    unittest.main()
