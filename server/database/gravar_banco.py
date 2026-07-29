import os
import sqlite3
import json
import sys

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit(
        "Erro: o pacote paho-mqtt não foi encontrado. Ative o ambiente virtual do projeto e execute: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from exc

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORTA = int(os.getenv("MQTT_PORTA", "1883"))
TOPICO = os.getenv("MQTT_TOPICO", "cubesat/telemetry/parsed")

def criar_tabela():
    conexao = sqlite3.connect("estacao.db")
    cursor = conexao.cursor()
    cursor.execute(""" 
        CREATE TABLE IF NOT EXISTS pacotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cubesat_id INTEGER,
            contador INTEGER,
            tensao_bateria REAL,
            temperatura REAL,
            rssi INTEGER,
            snr REAL,
            data_hora TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conexao.commit()
    conexao.close()

def salvar_no_banco(telemetria):
    conexao = sqlite3.connect("estacao.db")
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO pacotes (cubesat_id, contador, tensao_bateria, temperatura, rssi, snr)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        telemetria["cubesat_id"],
        telemetria["contador"],
        telemetria["tensao_bateria"],
        telemetria["temperatura"],
        telemetria["rssi"],
        telemetria["snr"],
    ))
    conexao.commit()
    conexao.close()

def ao_receber_mensagem(client, userdata, message):
    try:
        payload = message.payload.decode("utf-8")
        telemetria = json.loads(payload)
        print("Recebido:", telemetria)
        salvar_no_banco(telemetria)
    except Exception as exc:
        print(f"Erro ao processar mensagem: {exc}")

if __name__ == "__main__":
    criar_tabela()
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente.on_message = ao_receber_mensagem

    try:
        cliente.connect(BROKER, PORTA, keepalive=60)
        cliente.subscribe(TOPICO)
        print(f"Aguardando mensagens MQTT em {BROKER}:{PORTA} no tópico {TOPICO}...")
        cliente.loop_forever()
    except Exception as exc:
        print(f"Falha ao conectar no broker MQTT: {exc}")
        sys.exit(1)