"""Copia os pacotes e comandos de um banco SQLite para o MongoDB, preservando datas e ordem.

Uso: python server/migrar_para_mongo.py [estacao.db]
O arquivo SQLite não é alterado. Se o banco de destino no MongoDB já tiver dados, nada é copiado.
"""
import os
import sys

import banco_mongo
import banco_sqlite


def migrar(caminho):
    destino = banco_mongo._banco(caminho)
    if destino.pacotes.count_documents({}) or destino.comandos.count_documents({}):
        sys.exit(f"O banco {banco_mongo.nome_do_banco(caminho)} no MongoDB já tem dados; nada foi copiado.")

    pacotes, _ = banco_sqlite.ler_periodo(caminho)
    banco_mongo.preparar_banco(caminho)
    if pacotes:
        destino.pacotes.insert_many([
            {**{campo: p.get(campo) for campo in banco_mongo.CAMPOS_LIDOS}, "seq": posicao}
            for posicao, p in enumerate(pacotes, start=1)
        ])
        destino.contadores.update_one({"_id": "pacotes"}, {"$set": {"valor": len(pacotes)}}, upsert=True)

    comandos = banco_sqlite.listar_comandos(caminho, limite=10**9)
    if comandos:
        destino.comandos.insert_many([dict(c) for c in reversed(comandos)])
        destino.contadores.update_one({"_id": "comandos"}, {"$set": {"valor": max(c["id"] for c in comandos)}},
                                      upsert=True)
    return len(pacotes), len(comandos)


if __name__ == "__main__":
    origem = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "estacao.db")
    if not os.path.exists(origem):
        sys.exit(f"Arquivo não encontrado: {origem}")
    quantidade_pacotes, quantidade_comandos = migrar(os.path.abspath(origem))
    print(f"Copiados {quantidade_pacotes} pacotes e {quantidade_comandos} comandos para o MongoDB "
          f"(banco {banco_mongo.nome_do_banco(origem)}).")
