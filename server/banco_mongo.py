"""Versão MongoDB do banco. As funções seguem o contrato de banco.py.

O "caminho" usado pelo resto do sistema vira o nome do banco no MongoDB: estacao.db usa o
banco "estacao", e estacao_sim.db, o "estacao_sim". O endereço do servidor vem de
ESTACAO_MONGO_URI (padrão: mongodb://127.0.0.1:27017).

Coleções:
- pacotes: um documento por recepção, com "seq" crescente para manter a ordem de chegada
- comandos: um documento por comando, com "id" inteiro (o ID do comando no rádio tem 16 bits)
- contadores: o próximo número de "seq" e de "id"
"""
import os
import re

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument

from banco_comum import (
    CAMPOS_COMANDO, CAMPOS_GRAVADOS, CAMPOS_LIDOS, CONFIRMADO, ENVIADO, EXPIRADO, PENDENTE, REJEITADO,
    SEM_RESPOSTA, agora,
)

URI = os.environ.get("ESTACAO_MONGO_URI", "mongodb://127.0.0.1:27017")
# Sem o servidor, falha em poucos segundos em vez de travar a ponte
ESPERA_SERVIDOR_MS = 3000
_clientes = {}


def _cliente():
    if URI not in _clientes:
        _clientes[URI] = MongoClient(URI, serverSelectionTimeoutMS=ESPERA_SERVIDOR_MS, tz_aware=False)
    return _clientes[URI]


def nome_do_banco(caminho):
    nome = os.path.splitext(os.path.basename(caminho))[0]
    return re.sub(r"[^A-Za-z0-9_-]", "_", nome)[:60] or "estacao"


def _banco(caminho):
    return _cliente()[nome_do_banco(caminho)]


def _proximo_numero(banco, nome):
    contador = banco.contadores.find_one_and_update(
        {"_id": nome}, {"$inc": {"valor": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    return contador["valor"]


def _so_campos(documento, campos):
    """Devolve os campos esperados, com None nos que faltarem, como faria uma linha da tabela."""
    return {campo: documento.get(campo) for campo in campos}


def preparar_banco(caminho):
    banco = _banco(caminho)
    banco.pacotes.create_index([("seq", ASCENDING)], unique=True)
    banco.pacotes.create_index([("data_hora", ASCENDING)])
    banco.pacotes.create_index([("receptor_id", ASCENDING), ("frequencia_mhz", ASCENDING)])
    banco.comandos.create_index([("id", ASCENDING)], unique=True)
    banco.comandos.create_index([("estado", ASCENDING)])


def apagar_banco(caminho):
    _cliente().drop_database(nome_do_banco(caminho))


def descrever(caminho):
    return f"MongoDB {nome_do_banco(caminho)}"


# ---------- Pacotes ----------

def gravar_pacote(caminho, dados):
    banco = _banco(caminho)
    documento = {campo: dados.get(campo) for campo in CAMPOS_GRAVADOS}
    documento["data_hora"] = agora()
    documento["seq"] = _proximo_numero(banco, "pacotes")
    banco.pacotes.insert_one(documento)


def _filtro_origem(receptor, frequencia):
    filtro = {}
    if receptor is not None:
        filtro["receptor_id"] = receptor
    if frequencia is not None:
        filtro["frequencia_mhz"] = frequencia
    return filtro


def buscar_pacotes(caminho, limite=None, receptor=None, frequencia=None):
    cursor = _banco(caminho).pacotes.find(_filtro_origem(receptor, frequencia)).sort("seq", DESCENDING)
    if limite is not None:
        cursor = cursor.limit(limite)
    return [_so_campos(d, CAMPOS_LIDOS) for d in reversed(list(cursor))]


def opcoes_de_filtro(caminho):
    pacotes = _banco(caminho).pacotes
    receptores = sorted(v for v in pacotes.distinct("receptor_id") if v is not None)
    frequencias = sorted(v for v in pacotes.distinct("frequencia_mhz") if v is not None)
    return {"receptores": receptores, "frequencias": frequencias}


def resumo_pacotes(caminho):
    pacotes = _banco(caminho).pacotes
    ultimo = pacotes.find_one(sort=[("seq", DESCENDING)])
    return {
        "total": pacotes.count_documents({}),
        "ultimo": _so_campos(ultimo, ("data_hora", "rssi", "snr")) if ultimo else None,
    }


def ler_periodo(caminho, desde=None):
    banco = _banco(caminho)
    pacotes = []
    for d in banco.pacotes.find({"data_hora": {"$gte": desde}} if desde else {}).sort("seq", ASCENDING):
        pacotes.append({"id": d.get("seq"), **_so_campos(d, CAMPOS_LIDOS)})
    contagem = banco.comandos.aggregate([
        {"$match": {"criado_em": {"$gte": desde}} if desde else {}},
        {"$group": {"_id": "$estado", "quantidade": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    return pacotes, [(c["_id"], c["quantidade"]) for c in contagem]


# ---------- Comandos ----------

def registrar_comando(caminho, cubesat_id, codigo, parametro=0):
    banco = _banco(caminho)
    identificador = _proximo_numero(banco, "comandos")
    banco.comandos.insert_one({
        "id": identificador, "cubesat_id": cubesat_id, "codigo": codigo, "parametro": parametro,
        "estado": PENDENTE, "criado_em": agora(),
    })
    return identificador


def listar_comandos(caminho, limite=10):
    cursor = _banco(caminho).comandos.find().sort("id", DESCENDING).limit(limite)
    return [_so_campos(d, CAMPOS_COMANDO) for d in cursor]


def expirar_comandos(caminho, espera_ack_s, validade_pendente_s):
    comandos = _banco(caminho).comandos
    comandos.update_many({"estado": ENVIADO, "enviado_em": {"$lte": agora(espera_ack_s)}},
                         {"$set": {"estado": SEM_RESPOSTA}})
    comandos.update_many({"estado": PENDENTE, "criado_em": {"$lte": agora(validade_pendente_s)}},
                         {"$set": {"estado": EXPIRADO}})


def proximo_comando(caminho):
    comandos = _banco(caminho).comandos
    if comandos.find_one({"estado": ENVIADO}) is not None:
        return None
    proximo = comandos.find_one({"estado": PENDENTE}, sort=[("id", ASCENDING)])
    return _so_campos(proximo, CAMPOS_COMANDO) if proximo else None


def marcar_enviado(caminho, comando_id):
    _banco(caminho).comandos.update_one({"id": comando_id}, {"$set": {"estado": ENVIADO, "enviado_em": agora()}})


def registrar_ack(caminho, comando_id, status, rssi=None, snr=None, receptor_id=None):
    comandos = _banco(caminho).comandos
    alvo = comandos.find_one(
        {"id": {"$mod": [65536, comando_id]}, "estado": {"$in": [ENVIADO, SEM_RESPOSTA]}},
        sort=[("id", DESCENDING)])
    if alvo is None:
        return False
    comandos.update_one({"_id": alvo["_id"]}, {"$set": {
        "estado": CONFIRMADO if status == 0 else REJEITADO, "ack_em": agora(), "ack_status": status,
        "ack_rssi": rssi, "ack_snr": snr, "receptor_id": receptor_id,
    }})
    return True
