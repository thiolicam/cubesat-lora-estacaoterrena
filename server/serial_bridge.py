import json
import os
import sqlite3
import threading

import paho.mqtt.client as mqtt
import serial

from banco import preparar_banco

# 1. Porta serial da Estação Terrena
# Ex: "COM3" no Windows, "/dev/ttyUSB0" no Linux ou "socket://127.0.0.1:7000" no simulador
PORTA_SERIAL = os.environ.get("ESTACAO_SERIAL", "COM3")
BAUD_RATE = 115200

# 2. Broker MQTT local e tópicos definidos em docs/protocolo.md
BROKER = "localhost"
PORTA_MQTT = int(os.environ.get("ESTACAO_MQTT_PORTA", "1883"))
TOPICO_BRUTO = "cubesat/telemetry/raw"
TOPICO_DECODIFICADO = "cubesat/telemetry/parsed"
TOPICO_ENLACE = "groundstation/link/stats"
TOPICO_STATUS = "groundstation/status"
ESPERA_CONEXAO_MQTT = 2  # segundos

# 3. Banco de dados SQLite unificado (estacao.db na raiz do projeto)
DB_PATH = os.environ.get("ESTACAO_DB", os.path.join(os.path.dirname(__file__), '..', 'estacao.db'))

CAMPOS_ENLACE = ("receptor_id", "frequencia_mhz", "rssi", "snr", "validos", "invalidos")
CAMPOS_BANCO = (
    "cubesat_id", "tipo", "contador", "tensao_bateria", "corrente", "temperatura", "modo",
    "flags", "rssi", "snr", "validos", "invalidos", "frequencia_mhz", "receptor_id",
)


def mensagem_status(estado):
    return json.dumps({"estado": estado, "porta_serial": PORTA_SERIAL})


def mensagens_telemetria(dados):
    """Monta os pares (tópico, conteúdo) de um pacote recebido."""
    decodificado = {campo: valor for campo, valor in dados.items() if campo != "raw"}
    enlace = {campo: dados.get(campo) for campo in CAMPOS_ENLACE}
    mensagens = [
        (TOPICO_DECODIFICADO, json.dumps(decodificado)),
        (TOPICO_ENLACE, json.dumps(enlace)),
    ]
    if dados.get("raw"):
        mensagens.insert(0, (TOPICO_BRUTO, dados["raw"]))
    return mensagens


def salvar_no_banco(dados):
    """Insere o pacote no SQLite. Campo ausente fica vazio: nunca inventar um valor de telemetria."""
    try:
        conexao = sqlite3.connect(DB_PATH)
        marcadores = ", ".join("?" for _ in CAMPOS_BANCO)
        conexao.execute(
            f"INSERT INTO pacotes ({', '.join(CAMPOS_BANCO)}) VALUES ({marcadores})",
            [dados.get(campo) for campo in CAMPOS_BANCO],
        )
        conexao.commit()
        conexao.close()
        print(f"💾 [SQLite] Pacote gravado com sucesso em {os.path.basename(DB_PATH)}!")
    except Exception as e:
        print(f"❌ [Erro SQLite] Falha ao inserir o pacote: {e}")


def publicar_telemetria(cliente, dados):
    resultados = [cliente.publish(topico, conteudo) for topico, conteudo in mensagens_telemetria(dados)]
    if all(r.rc == mqtt.MQTT_ERR_SUCCESS for r in resultados):
        print(f"🔄 [MQTT] Telemetria publicada: pacote {dados.get('contador')}")
    else:
        print("⚠️ [MQTT] Pacote não publicado: broker indisponível.")


def criar_cliente_mqtt():
    """Conecta em segundo plano e reconecta sozinho se o broker cair ou iniciar depois."""
    conectado = threading.Event()

    def ao_conectar(cliente, _dados, _flags, codigo, _propriedades):
        if codigo.is_failure:
            print(f"⚠️ [MQTT] Broker recusou a conexão: {codigo}")
            return
        cliente.publish(TOPICO_STATUS, mensagem_status("online"), retain=True)
        print("✅ Conectado ao Broker MQTT com sucesso!")
        conectado.set()

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente.on_connect = ao_conectar
    # Se a ponte cair sem avisar, o próprio broker publica que a estação ficou offline
    cliente.will_set(TOPICO_STATUS, mensagem_status("offline"), retain=True)
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    cliente.connect_async(BROKER, PORTA_MQTT, 60)
    cliente.loop_start()
    if not conectado.wait(ESPERA_CONEXAO_MQTT):
        print(f"⚠️ Aviso: Broker MQTT indisponível em {BROKER}:{PORTA_MQTT}. "
              "Os dados serão salvos no SQLite, e a ponte seguirá tentando conectar.")
    return cliente


def encerrar_cliente_mqtt(cliente):
    if cliente.is_connected():
        aviso = cliente.publish(TOPICO_STATUS, mensagem_status("offline"), retain=True)
        aviso.wait_for_publish(timeout=1)
        cliente.disconnect()
    cliente.loop_stop()


def processar_linha(cliente, linha):
    # A estação imprime uma linha JSON por pacote válido; as demais são para leitura humana
    if not (linha.startswith("{") and linha.endswith("}")):
        return
    try:
        dados = json.loads(linha)
    except json.JSONDecodeError:
        print(f"⚠️ Aviso: Linha recebida não é um JSON válido: {linha}")
        return
    salvar_no_banco(dados)
    publicar_telemetria(cliente, dados)


def main():
    preparar_banco(DB_PATH)
    print("--- Iniciando Ponte Serial -> MQTT & SQLite ---")
    cliente = criar_cliente_mqtt()
    try:
        serial_esp32 = serial.serial_for_url(PORTA_SERIAL, BAUD_RATE, timeout=1)
        print(f"✅ Conectado à porta serial {PORTA_SERIAL}. Aguardando pacotes...")
        while True:
            # readline espera até o timeout, então o laço não ocupa a CPU sem necessidade
            linha = serial_esp32.readline().decode('utf-8', errors='ignore').strip()
            processar_linha(cliente, linha)
    except serial.SerialException as e:
        print(f"❌ Erro na porta serial {PORTA_SERIAL}: {e}. Verifique se a placa está conectada "
              "e se o Monitor Serial do PlatformIO está fechado.")
    except KeyboardInterrupt:
        print("\n🛑 Ponte Serial encerrada pelo utilizador.")
    finally:
        encerrar_cliente_mqtt(cliente)


if __name__ == "__main__":
    main()
