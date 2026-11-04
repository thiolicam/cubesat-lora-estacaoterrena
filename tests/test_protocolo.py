import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

from protocolo import TAMANHO_PACOTE, crc16, decodificar_pacote, montar_pacote


def pacote_exemplo(**alteracoes):
    campos = dict(
        cubesat_id=1, contador=42, tensao=3.72, temperatura=25.22,
        corrente=1.25, modo=0, flags=1,
    )
    campos.update(alteracoes)
    return montar_pacote(**campos)


class TestProtocolo(unittest.TestCase):
    def test_crc_usa_o_valor_de_referencia_ccitt(self):
        # Valor de verificacao publicado do CRC-16/CCITT-FALSE, o algoritmo do firmware
        self.assertEqual(crc16(b"123456789"), 0x29B1)

    def test_pacote_tem_16_bytes_em_big_endian(self):
        pacote = pacote_exemplo()
        self.assertEqual(TAMANHO_PACOTE, 16)
        self.assertEqual(len(pacote), 16)
        self.assertEqual(pacote[:4], bytes([0xAA, 0x01, 0x01, 0x01]))
        self.assertEqual(struct.unpack(">H", pacote[4:6])[0], 42)
        self.assertEqual(struct.unpack(">h", pacote[6:8])[0], 372)
        self.assertEqual(struct.unpack(">H", pacote[14:16])[0], crc16(pacote[:14]))

    def test_exemplo_de_docs_protocolo_esta_correto(self):
        pacote = bytes.fromhex("AA 01 01 01 00 2A 01 74 FD F3 FF 83 01 01 AE FF")
        t = decodificar_pacote(pacote)
        self.assertEqual(
            (t["cubesat_id"], t["contador"], t["tensao_bateria"], t["temperatura"],
             t["corrente"], t["modo"], t["flags"]),
            (1, 42, 3.72, -5.25, -1.25, 1, 1),
        )

    def test_ida_e_volta_preserva_os_valores(self):
        t = decodificar_pacote(pacote_exemplo())
        self.assertEqual(
            (t["cubesat_id"], t["contador"], t["tensao_bateria"], t["temperatura"],
             t["corrente"], t["modo"], t["flags"]),
            (1, 42, 3.72, 25.22, 1.25, 0, 1),
        )

    def test_valores_negativos_mantem_o_sinal(self):
        t = decodificar_pacote(pacote_exemplo(temperatura=-5.25, corrente=-1.25))
        self.assertEqual((t["temperatura"], t["corrente"]), (-5.25, -1.25))

    def test_qualquer_bit_invertido_e_rejeitado(self):
        original = pacote_exemplo()
        for byte in range(len(original)):
            for bit in range(8):
                alterado = bytearray(original)
                alterado[byte] ^= 1 << bit
                with self.assertRaises(ValueError):
                    decodificar_pacote(bytes(alterado))

    def test_tamanho_errado_e_rejeitado(self):
        with self.assertRaises(ValueError):
            decodificar_pacote(pacote_exemplo()[:12])


if __name__ == "__main__":
    unittest.main()
