import struct

def calcular_crc16(dados: bytes) -> int:
    crc = 0xFFFF
    for byte in dados:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def montar_pacote(cubesat_id: int, contador: int, tensao: float, temperatura: float) -> bytes:
    header = 0xAA
    versao = 0x01
    tipo = 0x01
    
    tensao_int = int(tensao * 100)
    temp_int = int(temperatura * 100)
    
    pacote_sem_crc = struct.pack(">BBBBHHh", header, versao, tipo, cubesat_id, contador, tensao_int, temp_int)
    crc = calcular_crc16(pacote_sem_crc)
    return pacote_sem_crc + struct.pack(">H", crc)

def decodificar_pacote(pacote: bytes) -> dict:
    if len(pacote) != 12:
        raise ValueError("Tamanho inválido de pacote")
        
    header, versao, tipo, cubesat_id, contador, tensao_int, temp_int, crc = struct.unpack(">BBBBHHhH", pacote)
    
    return {
        "header": header,
        "versao": versao,
        "tipo": tipo,
        "cubesat_id": cubesat_id,
        "contador": contador,
        "tensao_bateria": round(tensao_int / 100.0, 2),
        "temperatura": round(temp_int / 100.0, 2),
        "crc": crc
    }