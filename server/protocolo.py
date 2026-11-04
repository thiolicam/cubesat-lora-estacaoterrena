"""Pacote de telemetria de 16 bytes, igual ao usado nos firmwares do CubeSat e da estacao."""
import struct

HEADER = 0xAA
VERSAO = 1
TIPO_TELEMETRIA = 1

# Big-endian: Header, Versao, Tipo, ID, Contador, Tensao, Temperatura, Corrente, Modo, Flags
FORMATO_CORPO = ">BBBBHhhhBB"
TAMANHO_CORPO = struct.calcsize(FORMATO_CORPO)
TAMANHO_PACOTE = TAMANHO_CORPO + 2  # CRC


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
