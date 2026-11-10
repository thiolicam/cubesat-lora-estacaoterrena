"""Simula a estação terrena e o CubeSat: conversa pela rede como o ESP32 conversa pela serial.

A ponte serial conecta com ESTACAO_SERIAL=socket://127.0.0.1:7000 e não percebe a diferença.
Telemetria, comandos e ACKs passam pelo protocolo real, então perda e corrupção seguem o mesmo
caminho dos firmwares (firmware/ground-station e firmware/cubesat-simulator).
"""
import argparse
import math
import random
import re
import select
import socket
import time

from protocolo import (
    CMD_ALTERAR_INTERVALO,
    CMD_ENVIO_PERIODICO,
    CMD_REINICIAR,
    CMD_SOLICITAR_TELEMETRIA,
    STATUS_OK,
    TIPO_ACK,
    decodificar_ack,
    decodificar_comando,
    decodificar_pacote,
    montar_ack,
    montar_comando,
    montar_pacote,
    status_do_comando,
)

PACOTES_POR_ORBITA = 60
# Com vários receptores: os dois primeiros simulam diversidade de antenas, e o terceiro, de frequência
FREQUENCIAS_MHZ = (915.0, 915.0, 923.3)
CUBESAT_ID = 1
ESPERA_ABERTURA_SERIAL = 0.5  # segundos

# Valores definidos em docs/protocolo.md
MODO_NORMAL = 0
MODO_ECLIPSE = 1
FLAG_BATERIA_BAIXA = 0x01
TENSAO_BATERIA_BAIXA = 3.55

LINHA_COMANDO = re.compile(r"CMD (\d+) (\d+) (\d+) (\d+)$")


def gerar_telemetria(contador, rng):
    """Telemetria plausível: luz solar e eclipse variam temperatura, carga e corrente."""
    fase = math.sin(2 * math.pi * contador / PACOTES_POR_ORBITA)
    no_sol = fase >= 0
    tensao = 3.7 + 0.2 * fase + rng.uniform(-0.01, 0.01)
    return {
        "tensao": tensao,
        "temperatura": 5 + 25 * fase + rng.uniform(-0.5, 0.5),
        "corrente": (0.9 * fase if no_sol else -0.4) + rng.uniform(-0.02, 0.02),
        "modo": MODO_NORMAL if no_sol else MODO_ECLIPSE,
        "flags": FLAG_BATERIA_BAIXA if tensao < TENSAO_BATERIA_BAIXA else 0,
    }


def corromper(pacote, rng):
    """Inverte um bit, como uma interferência no enlace que passasse pelo CRC do LoRa."""
    alterado = bytearray(pacote)
    alterado[rng.randrange(len(alterado))] ^= 1 << rng.randrange(8)
    return bytes(alterado)


def formatar(linhas):
    return "".join(linha + "\r\n" for linha in linhas).encode("utf-8")


class Receptor:
    """Cada estação terrena tem os próprios contadores."""

    def __init__(self, identificador):
        self.identificador = identificador
        self.frequencia_mhz = FREQUENCIAS_MHZ[identificador - 1]
        self.validos = 0
        self.invalidos = 0


class Simulacao:
    def __init__(self, enviar, args):
        self.enviar = enviar
        self.args = args
        self.rng = random.Random(args.semente)
        self.intervalo = args.intervalo
        self.periodico = True
        self.contador = 0
        self.proximo_envio = time.monotonic()
        self.receptores = [Receptor(i + 1) for i in range(args.receptores)]
        self.transmitidos = self.perdidos = 0
        self.pendente = b""

    @property
    def validos(self):
        return sum(r.validos for r in self.receptores)

    @property
    def invalidos(self):
        return sum(r.invalidos for r in self.receptores)

    def enlace(self, pacote):
        """Aplica perda e corrupção; retorna o que chegou, ou None se nada chegou."""
        if self.rng.random() < self.args.perda:
            self.perdidos += 1
            return None
        if self.rng.random() < self.args.corrupcao:
            return corromper(pacote, self.rng)
        return pacote

    def medir_sinal(self):
        return self.rng.randint(-105, -80), round(self.rng.uniform(-2.0, 10.0), 1)

    def transmitir_telemetria(self):
        pacote = montar_pacote(CUBESAT_ID, self.contador % 65536, **gerar_telemetria(self.contador, self.rng))
        self.contador += 1
        self.transmitidos += 1
        # Cada receptor sofre as próprias perdas: é o que torna a diversidade útil
        for receptor in self.receptores:
            self.receber_telemetria(receptor, pacote)

    def receber_telemetria(self, receptor, pacote):
        recebido = self.enlace(pacote)
        if recebido is None:
            return
        try:
            t = decodificar_pacote(recebido)
        except ValueError:
            receptor.invalidos += 1
            self.enviar(formatar(["ALERTA: Pacote corrompido (CRC Inválido). Descartado! ❌"]))
            return
        receptor.validos += 1
        rssi, snr = self.medir_sinal()
        self.enviar(formatar([
            "========================================",
            f"Pacote #{t['contador']} Recebido (Válidos: {receptor.validos} | Inválidos: {receptor.invalidos})",
            "Status       : Aprovado ✅",
            "========================================",
            f'{{"cubesat_id": {t["cubesat_id"]}, "tipo": {t["tipo"]}, "contador": {t["contador"]}, '
            f'"tensao_bateria": {t["tensao_bateria"]:.2f}, "corrente": {t["corrente"]:.2f}, '
            f'"temperatura": {t["temperatura"]:.2f}, "modo": {t["modo"]}, "flags": {t["flags"]}, '
            f'"rssi": {rssi}, "snr": {snr:.1f}, "validos": {receptor.validos}, "invalidos": {receptor.invalidos}, '
            f'"estranhos": 0, '
            f'"frequencia_mhz": {receptor.frequencia_mhz:.1f}, "receptor_id": {receptor.identificador}, '
            f'"raw": "{recebido.hex().upper()}"}}',
        ]))

    def responder_ack(self, comando, status):
        # Os comandos e as respostas passam só pelo primeiro receptor
        receptor = self.receptores[0]
        recebido = self.enlace(montar_ack(comando["cubesat_id"], comando["comando_id"], comando["codigo"], status))
        if recebido is None:
            return
        try:
            ack = decodificar_ack(recebido)
        except ValueError:
            receptor.invalidos += 1
            self.enviar(formatar(["ALERTA: ACK corrompido. Descartado! ❌"]))
            return
        rssi, snr = self.medir_sinal()
        self.enviar(formatar([
            f'{{"cubesat_id": {ack["cubesat_id"]}, "tipo": {TIPO_ACK}, "comando_id": {ack["comando_id"]}, '
            f'"codigo": {ack["codigo"]}, "status": {ack["status"]}, "rssi": {rssi}, "snr": {snr:.1f}, '
            f'"frequencia_mhz": {receptor.frequencia_mhz:.1f}, "receptor_id": {receptor.identificador}, '
            f'"raw": "{recebido.hex().upper()}"}}',
        ]))

    def executar_comando(self, comando):
        """O que o firmware do CubeSat faz ao receber um comando íntegro."""
        codigo, parametro = comando["codigo"], comando["parametro"]
        status = status_do_comando(codigo, parametro)
        self.responder_ack(comando, status)
        if status != STATUS_OK:
            return
        if codigo == CMD_SOLICITAR_TELEMETRIA:
            self.transmitir_telemetria()
        elif codigo == CMD_ALTERAR_INTERVALO:
            self.intervalo = parametro
            self.proximo_envio = time.monotonic() + self.intervalo
        elif codigo == CMD_ENVIO_PERIODICO:
            self.periodico = parametro == 1
            self.proximo_envio = time.monotonic() + self.intervalo
        elif codigo == CMD_REINICIAR:
            self.contador = 0
            self.intervalo = self.args.intervalo
            self.periodico = True
            self.proximo_envio = time.monotonic() + self.intervalo

    def receber_linha(self, linha):
        """O que o firmware da estação faz com uma linha vinda do computador."""
        encontrado = LINHA_COMANDO.match(linha)
        if not encontrado:
            self.enviar(formatar([f"Linha serial ignorada: {linha}"]))
            return
        comando_id, cubesat_id, codigo, parametro = map(int, encontrado.groups())
        self.enviar(formatar([f"Comando {comando_id} transmitido: código {codigo}, parâmetro {parametro}"]))
        recebido = self.enlace(montar_comando(cubesat_id, comando_id, codigo, parametro))
        if recebido is None:
            return
        try:
            comando = decodificar_comando(recebido)
        except ValueError:
            return  # o CubeSat descarta em silêncio: a estação ficará sem resposta
        if comando["cubesat_id"] == CUBESAT_ID:
            self.executar_comando(comando)

    def receber_bytes(self, dados):
        self.pendente += dados
        while b"\n" in self.pendente:
            linha, self.pendente = self.pendente.split(b"\n", 1)
            self.receber_linha(linha.decode("utf-8", errors="ignore").strip())

    def rodar(self, conexao):
        while self.args.pacotes is None or self.transmitidos < self.args.pacotes:
            espera = 1.0
            if self.periodico:
                espera = max(0.0, self.proximo_envio - time.monotonic())
            prontos, _, _ = select.select([conexao], [], [], espera)
            if prontos:
                dados = conexao.recv(4096)
                if not dados:
                    return
                self.receber_bytes(dados)
            if self.periodico and time.monotonic() >= self.proximo_envio:
                self.transmitir_telemetria()
                self.agendar_proximo_envio()

    def agendar_proximo_envio(self):
        """Nunca agenda no passado: depois de o computador dormir, não repõe os envios perdidos.

        O firmware do CubeSat também mede o intervalo a partir do último envio.
        """
        self.proximo_envio = max(self.proximo_envio + self.intervalo, time.monotonic())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=7000, help="porta TCP local (padrão: 7000)")
    parser.add_argument("--intervalo", type=float, default=2.0, help="segundos entre pacotes (padrão: 2)")
    parser.add_argument("--perda", type=float, default=0.05, help="fração de pacotes perdidos (padrão: 0.05)")
    parser.add_argument("--corrupcao", type=float, default=0.05, help="fração de pacotes corrompidos (padrão: 0.05)")
    parser.add_argument("--pacotes", type=int, default=None, help="encerra após N pacotes (padrão: sem limite)")
    parser.add_argument("--semente", type=int, default=None, help="semente aleatória, para repetir uma execução")
    parser.add_argument("--receptores", type=int, default=1, choices=range(1, len(FREQUENCIAS_MHZ) + 1),
                        help="quantos receptores simular, para diversidade (padrão: 1)")
    args = parser.parse_args()

    with socket.create_server(("127.0.0.1", args.porta)) as servidor:
        print(f"Simulador aguardando a ponte em socket://127.0.0.1:{args.porta}", flush=True)
        conexao, _ = servidor.accept()

    simulacao = Simulacao(conexao.sendall, args)
    with conexao:
        try:
            # Ao abrir um socket://, a pyserial descarta o que já chegou; espera ela terminar
            time.sleep(ESPERA_ABERTURA_SERIAL)
            simulacao.proximo_envio = time.monotonic()
            simulacao.rodar(conexao)
        except (ConnectionError, KeyboardInterrupt):
            print("Simulador encerrado.")
            return

    print(f"Enviados: {simulacao.transmitidos} | válidos: {simulacao.validos} | "
          f"inválidos: {simulacao.invalidos} | perdidos: {simulacao.perdidos}")


if __name__ == "__main__":
    main()
