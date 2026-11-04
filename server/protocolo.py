"""Pacote de telemetria de 16 bytes, igual ao usado nos firmwares do CubeSat e da estacao."""
import struct

HEADER = 0xAA
VERSAO = 1
TIPO_TELEMETRIA = 1

# Big-endian: Header, Versao, Tipo, ID, Contador, Tensao, Temperatura, Corrente, Modo, Flags
FORMATO_CORPO = ">BBBBHhhhBB"
TAMANHO_CORPO = struct.calcsize(FORMATO_CORPO)
TAMANHO_PACOTE = TAMANHO_CORPO + 2  # CRC


# Comando, 11 bytes: Header, Versao, Tipo, ID, ID do comando, Codigo, Parametro, CRC
TIPO_COMANDO = 2
FORMATO_COMANDO = ">BBBBHBH"
TAMANHO_COMANDO = struct.calcsize(FORMATO_COMANDO) + 2

# ACK, 10 bytes: Header, Versao, Tipo, ID, ID do comando, Codigo, Status, CRC
TIPO_ACK = 3
FORMATO_ACK = ">BBBBHBB"
TAMANHO_ACK = struct.calcsize(FORMATO_ACK) + 2

CMD_SOLICITAR_TELEMETRIA = 1
CMD_ALTERAR_INTERVALO = 2  # parametro: segundos entre pacotes
CMD_ENVIO_PERIODICO = 3    # parametro: 1 ativa, 0 desativa
CMD_REINICIAR = 4

STATUS_OK = 0
STATUS_COMANDO_DESCONHECIDO = 1
STATUS_PARAMETRO_INVALIDO = 2

INTERVALO_MINIMO_S = 1
INTERVALO_MAXIMO_S = 3600


def crc16(dados: bytes) -> int:
    crc = 0xFFFF
    for byte in dados:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc


def _com_crc(corpo: bytes) -> bytes:
    return corpo + struct.pack(">H", crc16(corpo))


def _sem_crc(pacote: bytes, tamanho: int) -> bytes:
    if len(pacote) != tamanho:
        raise ValueError(f"Pacote com tamanho inesperado (esperado {tamanho} bytes)")
    if crc16(pacote[:-2]) != struct.unpack(">H", pacote[-2:])[0]:
        raise ValueError("CRC inválido — pacote corrompido")
    return pacote[:-2]


def status_do_comando(codigo, parametro) -> int:
    """Mesma regra aplicada no firmware do CubeSat e na API do dashboard."""
    if codigo in (CMD_SOLICITAR_TELEMETRIA, CMD_REINICIAR):
        return STATUS_OK
    if codigo == CMD_ALTERAR_INTERVALO:
        return STATUS_OK if INTERVALO_MINIMO_S <= parametro <= INTERVALO_MAXIMO_S else STATUS_PARAMETRO_INVALIDO
    if codigo == CMD_ENVIO_PERIODICO:
        return STATUS_OK if parametro in (0, 1) else STATUS_PARAMETRO_INVALIDO
    return STATUS_COMANDO_DESCONHECIDO


def montar_comando(cubesat_id, comando_id, codigo, parametro=0) -> bytes:
    return _com_crc(struct.pack(FORMATO_COMANDO, HEADER, VERSAO, TIPO_COMANDO, cubesat_id, comando_id, codigo, parametro))


def decodificar_comando(pacote: bytes) -> dict:
    _, _, tipo, cubesat_id, comando_id, codigo, parametro = struct.unpack(FORMATO_COMANDO, _sem_crc(pacote, TAMANHO_COMANDO))
    if tipo != TIPO_COMANDO:
        raise ValueError("Pacote não é um comando")
    return {"cubesat_id": cubesat_id, "comando_id": comando_id, "codigo": codigo, "parametro": parametro}


def montar_ack(cubesat_id, comando_id, codigo, status) -> bytes:
    return _com_crc(struct.pack(FORMATO_ACK, HEADER, VERSAO, TIPO_ACK, cubesat_id, comando_id, codigo, status))


def decodificar_ack(pacote: bytes) -> dict:
    _, _, tipo, cubesat_id, comando_id, codigo, status = struct.unpack(FORMATO_ACK, _sem_crc(pacote, TAMANHO_ACK))
    if tipo != TIPO_ACK:
        raise ValueError("Pacote não é um ACK")
    return {"cubesat_id": cubesat_id, "comando_id": comando_id, "codigo": codigo, "status": status}


def montar_pacote(cubesat_id, contador, tensao, temperatura, corrente, modo, flags) -> bytes:
    corpo = struct.pack(
        FORMATO_CORPO,
        HEADER,
        VERSAO,
        TIPO_TELEMETRIA,
        cubesat_id,
        contador,
        round(tensao * 100),
        round(temperatura * 100),
        round(corrente * 100),
        modo,
        flags,
    )
    return corpo + struct.pack(">H", crc16(corpo))


def decodificar_pacote(pacote: bytes) -> dict:
    if len(pacote) != TAMANHO_PACOTE:
        raise ValueError(f"Pacote com tamanho inesperado (esperado {TAMANHO_PACOTE} bytes)")

    crc_recebido = struct.unpack(">H", pacote[TAMANHO_CORPO:])[0]
    if crc16(pacote[:TAMANHO_CORPO]) != crc_recebido:
        raise ValueError("CRC inválido — pacote corrompido")

    header, versao, tipo, cubesat_id, contador, tensao, temperatura, corrente, modo, flags = \
        struct.unpack(FORMATO_CORPO, pacote[:TAMANHO_CORPO])

    return {
        "header": header,
        "versao": versao,
        "tipo": tipo,
        "cubesat_id": cubesat_id,
        "contador": contador,
        "tensao_bateria": tensao / 100,
        "temperatura": temperatura / 100,
        "corrente": corrente / 100,
        "modo": modo,
        "flags": flags,
    }
