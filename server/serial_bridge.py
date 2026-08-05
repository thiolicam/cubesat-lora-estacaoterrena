import serial
import json
import paho.mqtt.client as mqtt

# Configurações da Porta Serial (ajuste conforme o seu Gerenciador de Dispositivos, ex: "COM3")
PORTA_SERIAL = "COM3" 
BAUD_RATE = 115200

# Configurações do MQTT Broker local
BROKER = "localhost"
PORTA = 1883
TOPICO_MQTT = "cubesat/telemetry/parsed"

print("--- Iniciando Ponte Serial -> MQTT ---")

# Inicializa cliente MQTT compatível com Paho MQTT v2.0+
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cliente_mqtt.connect(BROKER, PORTA, 60)
cliente_mqtt.loop_start()

try:
    # Abre a conexão com a porta USB do ESP32
    serial_esp32 = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    print(f"Conectado à porta serial {PORTA_SERIAL} com sucesso!")

    while True:
        if serial_esp32.in_waiting > 0:
            linha = serial_esp32.readline().decode('utf-8', errors='ignore').strip()
            
            # Verifica se a linha recebida é um JSON válido vindo do ESP32
            if linha.startswith("{") and linha.endswith("}"):
                try:
                    dados = json.loads(linha)
                    # Publica no Broker MQTT
                    payload = json.dumps(dados)
                    cliente_mqtt.publish(TOPICO_MQTT, payload)
                    print(f"🔄 Ponte Serial MQTT enviada: {payload}")
                except json.JSONDecodeError:
                    print(f"Aviso: JSON corrompido recebido da serial: {linha}")
                    
except serial.SerialException as e:
    print(f"Erro na porta serial {PORTA_SERIAL}: {e}")
except KeyboardInterrupt:
    print("\nPonte Serial encerrada pelo utilizador.")
    cliente_mqtt.loop_stop()
    cliente_mqtt.disconnect()