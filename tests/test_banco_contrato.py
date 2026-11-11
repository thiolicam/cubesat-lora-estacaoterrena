"""As versões SQLite e MongoDB do banco precisam se comportar igual: mesmas verificações nas duas."""
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "server"))

import banco_sqlite
from banco_comum import CAMPOS_COMANDO, CAMPOS_LIDOS, CONFIRMADO, ENVIADO, EXPIRADO, PENDENTE, REJEITADO, SEM_RESPOSTA


def mongo_disponivel():
    try:
        import banco_mongo
        banco_mongo._cliente().admin.command("ping")
        return True
    except Exception:
        return False


def pacote(contador, receptor=1, frequencia=915.0, rssi=-90):
    return {"cubesat_id": 1, "tipo": 1, "contador": contador, "tensao_bateria": 3.7, "rssi": rssi, "snr": 9.0,
            "validos": contador + 1, "invalidos": 0, "estranhos": 0, "receptor_id": receptor,
            "frequencia_mhz": frequencia, "raw": f"AA{contador:04X}"}


class Contrato:
    """Verificações comuns; cada subclasse fornece a versão e como envelhecer um comando."""

    versao = None

    def test_pacotes_voltam_em_ordem_cronologica_com_limite(self):
        for c in range(5):
            self.versao.gravar_pacote(self.caminho, pacote(c))
        self.assertEqual([p["contador"] for p in self.versao.buscar_pacotes(self.caminho)], [0, 1, 2, 3, 4])
        self.assertEqual([p["contador"] for p in self.versao.buscar_pacotes(self.caminho, limite=2)], [3, 4])

    def test_pacote_tem_todos_os_campos_e_none_no_que_falta(self):
        self.versao.gravar_pacote(self.caminho, {"contador": 7})
        lido, = self.versao.buscar_pacotes(self.caminho)
        self.assertEqual(set(lido), set(CAMPOS_LIDOS))
        self.assertEqual(lido["contador"], 7)
        self.assertIsNone(lido["rssi"])
        self.assertRegex(lido["data_hora"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_filtros_por_receptor_e_frequencia(self):
        self.versao.gravar_pacote(self.caminho, pacote(0, receptor=1, frequencia=915.0))
        self.versao.gravar_pacote(self.caminho, pacote(0, receptor=2, frequencia=915.0))
        self.versao.gravar_pacote(self.caminho, pacote(0, receptor=3, frequencia=923.3))
        self.assertEqual([p["receptor_id"] for p in self.versao.buscar_pacotes(self.caminho, receptor=2)], [2])
        self.assertEqual([p["receptor_id"] for p in self.versao.buscar_pacotes(self.caminho, frequencia=915.0)], [1, 2])
        self.assertEqual(self.versao.buscar_pacotes(self.caminho, receptor=1, frequencia=923.3), [])
        self.assertEqual(self.versao.opcoes_de_filtro(self.caminho),
                         {"receptores": [1, 2, 3], "frequencias": [915.0, 923.3]})

    def test_resumo(self):
        self.assertEqual(self.versao.resumo_pacotes(self.caminho), {"total": 0, "ultimo": None})
        self.versao.gravar_pacote(self.caminho, pacote(0, rssi=-80))
        self.versao.gravar_pacote(self.caminho, pacote(1, rssi=-70))
        resumo = self.versao.resumo_pacotes(self.caminho)
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(set(resumo["ultimo"]), {"data_hora", "rssi", "snr"})
        self.assertEqual(resumo["ultimo"]["rssi"], -70)

    def test_ler_periodo(self):
        self.versao.gravar_pacote(self.caminho, pacote(0))
        self.versao.registrar_comando(self.caminho, 1, 1)
        self.versao.registrar_comando(self.caminho, 1, 1)
        pacotes, comandos = self.versao.ler_periodo(self.caminho)
        self.assertEqual([p["contador"] for p in pacotes], [0])
        self.assertEqual(comandos, [(PENDENTE, 2)])
        pacotes, comandos = self.versao.ler_periodo(self.caminho, "2999-01-01 00:00:00")
        self.assertEqual((pacotes, comandos), ([], []))

    def test_ciclo_do_comando(self):
        primeiro = self.versao.registrar_comando(self.caminho, 1, 2, 5)
        segundo = self.versao.registrar_comando(self.caminho, 1, 1)
        self.assertEqual(segundo, primeiro + 1)
        proximo = self.versao.proximo_comando(self.caminho)
        self.assertEqual(set(proximo), set(CAMPOS_COMANDO))
        self.assertEqual((proximo["id"], proximo["codigo"], proximo["parametro"], proximo["estado"]),
                         (primeiro, 2, 5, PENDENTE))

        self.versao.marcar_enviado(self.caminho, primeiro)
        self.assertIsNone(self.versao.proximo_comando(self.caminho))  # rádio ocupado
        self.assertTrue(self.versao.registrar_ack(self.caminho, primeiro, 0, -50, 9.5, 1))
        comando = self.versao.listar_comandos(self.caminho)[1]
        self.assertEqual((comando["estado"], comando["ack_status"], comando["ack_rssi"], comando["receptor_id"]),
                         (CONFIRMADO, 0, -50, 1))
        self.assertIsNotNone(comando["enviado_em"])
        self.assertIsNotNone(comando["ack_em"])

        self.assertEqual(self.versao.proximo_comando(self.caminho)["id"], segundo)
        self.versao.marcar_enviado(self.caminho, segundo)
        self.assertTrue(self.versao.registrar_ack(self.caminho, segundo, 2))
        self.assertEqual(self.versao.listar_comandos(self.caminho)[0]["estado"], REJEITADO)

    def test_ack_sem_comando_aguardando_e_ignorado(self):
        self.assertFalse(self.versao.registrar_ack(self.caminho, 99, 0))
        identificador = self.versao.registrar_comando(self.caminho, 1, 1)
        self.assertFalse(self.versao.registrar_ack(self.caminho, identificador, 0))  # ainda pendente

    def test_listar_comandos_do_mais_recente_com_limite(self):
        ids = [self.versao.registrar_comando(self.caminho, 1, 1) for _ in range(3)]
        self.assertEqual([c["id"] for c in self.versao.listar_comandos(self.caminho, limite=2)], ids[:0:-1])

    def test_expiracao_e_ack_atrasado(self):
        enviado = self.versao.registrar_comando(self.caminho, 1, 1)
        self.versao.marcar_enviado(self.caminho, enviado)
        antigo = self.versao.registrar_comando(self.caminho, 1, 4)
        self.envelhecer(enviado, "enviado_em")
        self.envelhecer(antigo, "criado_em")
        self.versao.expirar_comandos(self.caminho, 10, 30)
        estados = {c["id"]: c["estado"] for c in self.versao.listar_comandos(self.caminho)}
        self.assertEqual(estados, {enviado: SEM_RESPOSTA, antigo: EXPIRADO})
        self.assertIsNone(self.versao.proximo_comando(self.caminho))
        self.assertTrue(self.versao.registrar_ack(self.caminho, enviado, 0))

    def test_comando_recente_nao_expira(self):
        enviado = self.versao.registrar_comando(self.caminho, 1, 1)
        self.versao.marcar_enviado(self.caminho, enviado)
        self.versao.expirar_comandos(self.caminho, 10, 30)
        self.assertEqual(self.versao.listar_comandos(self.caminho)[0]["estado"], ENVIADO)

    def test_apagar_banco(self):
        self.versao.gravar_pacote(self.caminho, pacote(0))
        self.versao.apagar_banco(self.caminho)
        self.versao.preparar_banco(self.caminho)
        self.assertEqual(self.versao.resumo_pacotes(self.caminho)["total"], 0)


class TestSqlite(Contrato, unittest.TestCase):
    versao = banco_sqlite

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.caminho = os.path.join(self.pasta.name, "contrato.db")
        self.versao.preparar_banco(self.caminho)

    def tearDown(self):
        self.pasta.cleanup()

    def envelhecer(self, comando_id, campo):
        con = sqlite3.connect(self.caminho)
        con.execute(f"UPDATE comandos SET {campo} = datetime('now', '-1 hour') WHERE id = ?", (comando_id,))
        con.commit()
        con.close()


@unittest.skipUnless(mongo_disponivel(), "servidor MongoDB indisponível")
class TestMongo(Contrato, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import banco_mongo
        cls.versao = banco_mongo

    def setUp(self):
        # Um banco novo por teste, apagado no fim: nunca toca nos bancos estacao e estacao_sim
        self.caminho = f"teste_contrato_{uuid.uuid4().hex[:12]}.db"
        self.versao.preparar_banco(self.caminho)

    def tearDown(self):
        self.versao.apagar_banco(self.caminho)

    def envelhecer(self, comando_id, campo):
        from banco_comum import agora
        self.versao._banco(self.caminho).comandos.update_one({"id": comando_id}, {"$set": {campo: agora(3600)}})


if __name__ == "__main__":
    unittest.main()
