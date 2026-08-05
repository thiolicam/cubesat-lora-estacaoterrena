import struct

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

def montar_pacote(cubesat_id, contador, tensao, temperatura):
    header = 0xAA
    versao = 1
    tipo = 1

    tensao_int = round(tensao * 100)
    temperatura_int = round(temperatura * 100)

    # Corpo com 10 bytes: Header(1) + Versao(1) + Tipo(1) + ID(1) + Contador(2) + Tensao(2) + Temperatura(2)
    corpo = struct.pack(
        ">BBBBHhh",
        header,
        versao,
        tipo,
        cubesat_id,
        contador,
        tensao_int,
        temperatura_int,
    )

    crc = crc16(corpo)
    pacote = corpo + struct.pack(">H", crc)
    return pacote

def decodificar_pacote(pacote: bytes) -> dict:
    if len(pacote) != 12:
        raise ValueError("Pacote com tamanho inesperado (esperado 12 bytes)")

    header, versao, tipo, cubesat_id, contador, tensao_int, temperatura_int, crc_recebido = \
        struct.unpack(">BBBBHhhH", pacote)

    crc_calculado = crc16(pacote[:10])

    if crc_calculado != crc_recebido:
        raise ValueError("CRC inválido — pacote corrompido")

    return {
        "header": header,
        "versao": versao,
        "tipo": tipo,
        "cubesat_id": cubesat_id,
        "contador": contador,
        "tensao_bateria": tensao_int / 100,
        "temperatura": temperatura_int / 100,
    }

if __name__ == "__main__":
    pacote = montar_pacote(cubesat_id=1, contador=42, tensao=3.72, temperatura=25.22)
    print("Pacote:", pacote.hex())
    telemetria = decodificar_pacote(pacote)
    print("Decodificado:", telemetria)