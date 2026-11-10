import json
import os
import sqlite3
import threading
import time

import paho.mqtt.client as mqtt
import serial

import banco

# 1. Porta serial da Estação Terrena
# Ex: "COM3" no Windows, "/dev/ttyUSB0" no Linux ou "socket://127.0.0.1:7000" no simulador
PORTA_SERIAL = os.environ.get("ESTACAO_SERIAL", "COM3")
BAUD_RATE = 115200
ESPERA_LEITURA_S = 0.2  # intervalo máximo para verificar se há comando na fila
ESPERA_RECONEXAO_S = 2  # se a porta cair, tenta reabrir nesse intervalo

# 2. Broker MQTT local e tópicos definidos em docs/protocolo.md
# Endereço IPv4 explícito: "localhost" pode cair em outro broker na mesma porta (como um container
# Docker em ::1), e as mensagens somem sem nenhum erro para quem assina no outro.
BROKER = os.environ.get("ESTACAO_MQTT_HOST", "127.0.0.1")
PORTA_MQTT = int(os.environ.get("ESTACAO_MQTT_PORTA", "1883"))
TOPICO_BRUTO = "cubesat/telemetry/raw"
TOPICO_DECODIFICADO = "cubesat/telemetry/parsed"
TOPICO_ENLACE = "groundstation/link/stats"
TOPICO_STATUS = "groundstation/status"
TOPICO_COMANDO = "cubesat/command/send"
TOPICO_ACK = "cubesat/command/ack"
ESPERA_CONEXAO_MQTT = 2  # segundos

# 3. Banco de dados SQLite unificado (estacao.db na raiz do projeto)
DB_PATH = os.environ.get("ESTACAO_DB", os.path.join(os.path.dirname(__file__), '..', 'estacao.db'))

# 4. Comandos: quanto esperar pelo ACK e por quanto tempo um pendente ainda pode ser enviado
ESPERA_ACK_S = int(os.environ.get("ESTACAO_ESPERA_ACK", "10"))
VALIDADE_PENDENTE_S = 30

TIPO_ACK = 3
CAMPOS_ENLACE = ("receptor_id", "frequencia_mhz", "rssi", "snr", "validos", "invalidos", "estranhos")
CAMPOS_BANCO = (
    "cubesat_id", "tipo", "contador", "tensao_bateria", "corrente", "temperatura", "modo",
    "flags", "rssi", "snr", "validos", "invalidos", "estranhos", "frequencia_mhz", "receptor_id", "raw",
)

# Com vários receptores há uma ponte por estação, mas só uma pode transmitir os comandos
ENVIA_COMANDOS = os.environ.get("ESTACAO_ENVIA_COMANDOS", "1") != "0"


class LeitorDeLinhas:
    """Só entrega linhas completas.

    O readline devolve o que tiver quando o tempo de espera acaba; sem guardar esse pedaço,
    uma linha que chegasse nesse instante seria dividida, e o pacote, perdido.
    """

    def __init__(self, porta):
        self.porta = porta
        self.parcial = b""

    def ler(self):
        self.parcial += self.porta.readline()
        if not self.parcial.endswith(b"\n"):
            return None
        linha, self.parcial = self.parcial, b""
        return linha.decode('utf-8', errors='ignore').strip()


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


def publicar(cliente, mensagens, descricao):
    resultados = [cliente.publish(topico, conteudo) for topico, conteudo in mensagens]
    if all(r.rc == mqtt.MQTT_ERR_SUCCESS for r in resultados):
        print(f"🔄 [MQTT] {descricao} publicada")
    else:
        print(f"⚠️ [MQTT] {descricao} não publicada: broker indisponível.")


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


def processar_ack(cliente, dados):
    encontrado = banco.registrar_ack(
        DB_PATH, dados.get("comando_id"), dados.get("status"),
        dados.get("rssi"), dados.get("snr"), dados.get("receptor_id"),
    )
    if encontrado:
        print(f"📨 ACK do comando {dados.get('comando_id')}: status {dados.get('status')}")
    else:
        print(f"⚠️ ACK ignorado: nenhum comando {dados.get('comando_id')} aguardava resposta.")
    publicar(cliente, [(TOPICO_ACK, json.dumps(dados))], "Confirmação de comando")


def processar_linha(cliente, linha):
    # A estação imprime uma linha JSON por pacote válido; as demais são para leitura humana
    if not (linha.startswith("{") and linha.endswith("}")):
        return
    try:
        dados = json.loads(linha)
    except json.JSONDecodeError:
        print(f"⚠️ Aviso: Linha recebida não é um JSON válido: {linha}")
        return
    if dados.get("tipo") == TIPO_ACK:
        processar_ack(cliente, dados)
        return
    salvar_no_banco(dados)
    publicar(cliente, mensagens_telemetria(dados), f"Telemetria do pacote {dados.get('contador')}")


def atender_comandos(cliente, porta):
    """Transmite o próximo comando da fila, se o rádio estiver livre."""
    banco.expirar_comandos(DB_PATH, ESPERA_ACK_S, VALIDADE_PENDENTE_S)
    comando = banco.proximo_comando(DB_PATH)
    if comando is None:
        return
    comando_id = comando["id"] % 65536
    porta.write(f"CMD {comando_id} {comando['cubesat_id']} {comando['codigo']} {comando['parametro']}\n".encode())
    banco.marcar_enviado(DB_PATH, comando["id"])
    print(f"📤 Comando {comando_id} enviado à estação: código {comando['codigo']}, parâmetro {comando['parametro']}")
    conteudo = json.dumps({
        "comando_id": comando_id, "cubesat_id": comando["cubesat_id"],
        "codigo": comando["codigo"], "parametro": comando["parametro"],
    })
    publicar(cliente, [(TOPICO_COMANDO, conteudo)], "Envio de comando")


def atender_porta(cliente):
    """Lê a estação até a porta falhar; a falha sobe como SerialException."""
    serial_esp32 = serial.serial_for_url(PORTA_SERIAL, BAUD_RATE, timeout=ESPERA_LEITURA_S)
    try:
        print(f"✅ Conectado à porta serial {PORTA_SERIAL}. Aguardando pacotes...")
        leitor = LeitorDeLinhas(serial_esp32)
        while True:
            linha = leitor.ler()
            if linha:
                processar_linha(cliente, linha)
            if ENVIA_COMANDOS:
                atender_comandos(cliente, serial_esp32)
    finally:
        serial_esp32.close()


def main():
    banco.preparar_banco(DB_PATH)
    print("--- Iniciando Ponte Serial -> MQTT & SQLite ---")
    cliente = criar_cliente_mqtt()
    ultimo_erro = None
    try:
        while True:
            try:
                atender_porta(cliente)
            except serial.SerialException as e:
                # No simulador, a conexão encerrada é o fim da simulação
                if PORTA_SERIAL.startswith("socket://"):
                    print(f"❌ Erro na porta serial {PORTA_SERIAL}: {e}.")
                    break
                # Um cabo que mexe faz a porta sumir por um instante: a ponte não pode parar por isso
                if str(e) != ultimo_erro:
                    print(f"❌ Erro na porta serial {PORTA_SERIAL}: {e}. Verifique se a placa está conectada "
                          f"e se o Monitor Serial do PlatformIO está fechado. Tentando de novo a cada "
                          f"{ESPERA_RECONEXAO_S} s...")
                    ultimo_erro = str(e)
                time.sleep(ESPERA_RECONEXAO_S)
    except KeyboardInterrupt:
        print("\n🛑 Ponte Serial encerrada pelo utilizador.")
    finally:
        encerrar_cliente_mqtt(cliente)


if __name__ == "__main__":
    main()
