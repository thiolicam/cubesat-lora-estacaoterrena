import json
import os
import sys
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit(
        "Erro: o pacote paho-mqtt não foi encontrado. Instale com: python -m pip install paho-mqtt==2.1.0"
    ) from exc

# Adiciona a raiz do projeto para importar teste_protocolo
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

from teste_protocolo import montar_pacote, decodificar_pacote

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORTA = int(os.getenv("MQTT_PORTA", "1883"))
TOPICO = os.getenv("MQTT_TOPICO", "cubesat/telemetry/parsed")

if __name__ == "__main__":
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    try:
        cliente.connect(BROKER, PORTA, keepalive=60)
        pacote = montar_pacote(cubesat_id=1, contador=42, tensao=3.72, temperatura=25.22)
        telemetria = decodificar_pacote(pacote)

        telemetria["rssi"] = -87
        telemetria["snr"] = 9.2

        payload = json.dumps(telemetria)
        cliente.publish(TOPICO, payload)
        print(f"✅ Telemetria simulada publicada no MQTT em {BROKER}:{PORTA} -> {TOPICO}: {payload}")
    except Exception as exc:
        print(f"Falha ao publicar no broker MQTT: {exc}")
        sys.exit(1)
    finally:
        cliente.disconnect()