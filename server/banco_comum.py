"""Definições compartilhadas pelas versões SQLite e MongoDB do banco."""
from datetime import datetime, timedelta, timezone

# Campos que a ponte grava a cada pacote recebido
CAMPOS_GRAVADOS = (
    "cubesat_id", "tipo", "contador", "tensao_bateria", "corrente", "temperatura", "modo",
    "flags", "rssi", "snr", "validos", "invalidos", "estranhos", "frequencia_mhz", "receptor_id", "raw",
)
# Campos que as consultas devolvem: os gravados e o momento da gravação
CAMPOS_LIDOS = CAMPOS_GRAVADOS + ("data_hora",)

# Campos de um comando, na ordem da tabela
CAMPOS_COMANDO = (
    "id", "cubesat_id", "codigo", "parametro", "estado", "criado_em", "enviado_em",
    "ack_em", "ack_status", "ack_rssi", "ack_snr", "receptor_id",
)

# Ciclo de um comando: pendente -> enviado -> confirmado, rejeitado ou sem_resposta.
# Um pendente que ninguém transmitiu a tempo vira expirado.
PENDENTE, ENVIADO, CONFIRMADO, REJEITADO, SEM_RESPOSTA, EXPIRADO = (
    "pendente", "enviado", "confirmado", "rejeitado", "sem_resposta", "expirado",
)

# Datas são texto em UTC, no mesmo formato nas duas versões, para comparar como texto
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


def agora(menos_segundos=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=menos_segundos)).strftime(FORMATO_DATA)
