import paho.mqtt.client as mqtt  # biblioteca cliente MQTT (fala com o broker, seja qual for)
import json

from teste_protocolo import montar_pacote, decodificar_pacote #importa as funcoes montar_pacote e decodificar_pacote do teste_protocolo

BROKER = "localhost" #broker (servidor) rodando na minha maquina 
PORTA = 1883 #port padrao do protocolo mqtt
TOPICO = "cubesat/telemetry/parsed" # topico onde a telemetria decodificada eh publicada

# cria o cliente MQTT (uso padrão da biblioteca Paho)
cliente = mqtt.Client()
cliente.connect(BROKER, PORTA)   # conecta no broker MQTT

# monta um pacote fake, igual fizemos no teste do protocolo
pacote = montar_pacote(cubesat_id=1, contador=42, tensao=3.72, temperatura=25.22)

# decodifica de volta (é isso que o script host vai fazer com pacotes reais)
telemetria = decodificar_pacote(pacote)

# adiciona RSSI e SNR simulados, já que no MVP real esses valores viriam
# do próprio módulo RFM95, e não do pacote em si (lembra do que vimos no protocolo.md)
telemetria["rssi"] = -87
telemetria["snr"] = 9.2

# converte o dicionário Python para uma string JSON, formato padrão pra
# trafegar dados estruturados via MQTT
mensagem = json.dumps(telemetria)

# publica no tópico
cliente.publish(TOPICO, mensagem)
print("Publicado:", mensagem)

cliente.disconnect()