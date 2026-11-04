import serial
import json
import sqlite3
import os
import paho.mqtt.client as mqtt

# 1. Configurações da Porta Serial (Ajuste para a porta real do seu ESP32 da Estação Terrena)
PORTA_SERIAL = "COM3"  # Ex: "COM3" no Windows ou "/dev/ttyUSB0" no Linux
BAUD_RATE = 115200

# 2. Configurações do MQTT Broker local
BROKER = "localhost"
PORTA = 1883
TOPICO_MQTT = "cubesat/telemetry/parsed"

# 3. Caminho do banco de dados SQLite unificado (estacao.db na raiz do projeto)
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'estacao.db')

def inicializar_banco():
    """Garante que a tabela 'pacotes' existe no SQLite com todas as colunas reais."""
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cubesat_id TEXT,
            contador INTEGER,
            tensao_bateria REAL,
            corrente REAL,
            temperatura REAL,
            modo TEXT,
            flags INTEGER,
            rssi REAL,
            snr REAL,
            validos INTEGER,
            invalidos INTEGER,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Bancos criados antes destas colunas existirem precisam recebe-las aqui
    colunas = {coluna[1] for coluna in cursor.execute("PRAGMA table_info(pacotes)")}
    for nova_coluna in ("validos", "invalidos"):
        if nova_coluna not in colunas:
            cursor.execute(f"ALTER TABLE pacotes ADD COLUMN {nova_coluna} INTEGER")
    conexao.commit()
    conexao.close()

def salvar_no_banco(dados):
    """Insere o pacote real de telemetria decodificado pelo ESP32 no SQLite."""
    try:
        conexao = sqlite3.connect(DB_PATH)
        cursor = conexao.cursor()
        cursor.execute('''
            INSERT INTO pacotes (cubesat_id, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, validos, invalidos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(dados.get("cubesat_id", "LION-1")),
            int(dados.get("contador", 0)),
            float(dados.get("tensao_bateria", 0.0)),
            float(dados.get("corrente", 0.0)),
            float(dados.get("temperatura", 0.0)),
            str(dados.get("modo", "IDLE")),
            int(dados.get("flags", 0)),
            float(dados.get("rssi", 0.0)),
            float(dados.get("snr", 0.0)),
            dados.get("validos"),
            dados.get("invalidos")
        ))
        conexao.commit()
        conexao.close()
        print("💾 [SQLite] Pacote real gravado com sucesso no estacao.db!")
    except Exception as e:
        print(f"❌ [Erro SQLite] Falha ao inserir dados reais: {e}")

# Inicializa o banco de dados antes de iniciar a ponte
inicializar_banco()

print("--- Iniciando Ponte Serial (Dados Reais) -> MQTT & SQLite ---")

# Inicializa cliente MQTT compatível com Paho MQTT v2.0+
cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    cliente_mqtt.connect(BROKER, PORTA, 60)
    cliente_mqtt.loop_start()
    print("✅ Conectado ao Broker MQTT com sucesso!")
except Exception as e:
    print(f"⚠️ Aviso: Não foi possível conectar ao Broker MQTT ({e}). Os dados ainda serão salvos no SQLite.")

try:
    # Abre a conexão com a porta USB do ESP32 da Estação Terrena
    serial_esp32 = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    print(f"✅ Conectado à porta serial física {PORTA_SERIAL} com sucesso! Aguardando pacotes reais do rádio LoRa...")

    while True:
        if serial_esp32.in_waiting > 0:
            linha = serial_esp32.readline().decode('utf-8', errors='ignore').strip()
            
            # O ESP32 da Estação Terrena deve imprimir o payload em formato JSON puro na serial
            if linha.startswith("{") and linha.endswith("}"):
                try:
                    dados = json.loads(linha)
                    
                    # 1. Salva os dados reais coletados no Banco de Dados SQLite
                    salvar_no_banco(dados)

                    # 2. Publica no Broker MQTT para outros módulos ouvirem
                    payload = json.dumps(dados)
                    cliente_mqtt.publish(TOPICO_MQTT, payload)
                    print(f"🔄 [MQTT] Telemetria real publicada: {payload}")
                    
                except json.JSONDecodeError:
                    print(f"⚠️ Aviso: Linha recebida não é um JSON válido: {linha}")
                    
except serial.SerialException as e:
    print(f"❌ Erro na porta serial {PORTA_SERIAL}: {e}. Verifique se a placa está conectada e se o Monitor Serial do PlatformIO está fechado.")
except KeyboardInterrupt:
    print("\n🛑 Ponte Serial encerrada pelo utilizador.")
    try:
        cliente_mqtt.loop_stop()
        cliente_mqtt.disconnect()
    except:
        pass