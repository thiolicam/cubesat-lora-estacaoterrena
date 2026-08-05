import sqlite3 # módulo padrão do Python para bancos SQLite (já vem embutido)
import json 
import paho.mqtt.client as mqtt

BROKER = "localhost"  # broker MQTT rodando na própria máquina
PORTA = 1883  # porta padrão do protocolo MQTT
TOPICO = "cubesat/telemetry/parsed" # tópico onde a telemetria decodificada é publicada


def criar_tabela(): #define funcao criar tabela 
    conexao = sqlite3.connect("estacao.db") # cria uma conexão com o banco de dados estacao.db
    cursor = conexao.cursor() # cria um cursor para executar comandos SQL
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
    """) # define a estrutura da tabela "pacotes": nome e tipo de cada coluna (sem inserir dados ainda)
    conexao.commit() #salva definitivamente as alteracoes no banco de dados
    conexao.close() #fecha a conexao com o banco de dados


def salvar_no_banco(telemetria): #define a funcao salvar_no_banco 
    conexao = sqlite3.connect("estacao.db") # cria uma conexão com o banco de dados estacao.db
    cursor = conexao.cursor() # cria um cursor para executar comandos SQL
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
    )) # insere um novo registro na tabela "pacotes" com os dados de telemetria
    conexao.commit() #salva definitivamente as alteracoes no banco de dados
    conexao.close()  #fecha a conexao com o banco de dados


def ao_receber_mensagem(client, userdata, message): # define uma funcao que será chamada sempre que receber uma mensagem 
    payload = message.payload.decode() # decodifica o payload (em bytes) em uma string 
    telemetria = json.loads(payload)   # converte a string JSON em um dicionário Python
    print("Recebido:", telemetria) 
    salvar_no_banco(telemetria) # insere uma telemetria recebida como nova linha na tabela

if __name__ == "__main__":
    criar_tabela()  # garante que a tabela existe antes de começar a escutar

    # cria o cliente MQTT (uso padrão da biblioteca Paho)
    cliente = mqtt.Client()
    cliente.on_message = ao_receber_mensagem  # registra o callback: chamado automaticamente a cada mensagem
    cliente.connect(BROKER, PORTA)  # conecta no broker
    cliente.subscribe(TOPICO)  # inscreve no tópico de telemetria

    print("Escutando... (Ctrl+C para parar)")
    cliente.loop_forever()  # fica rodando indefinidamente, esperando mensagens chegarem    