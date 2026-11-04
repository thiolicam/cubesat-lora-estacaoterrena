"""Simula a estacao terrena: entrega pela rede o mesmo texto que o ESP32 envia pela serial.

A ponte serial conecta com ESTACAO_SERIAL=socket://127.0.0.1:7000 e nao percebe a
diferenca. Cada pacote passa pelo protocolo real de 16 bytes, entao perda e corrupcao
seguem o mesmo caminho do firmware (firmware/ground-station/src/main.cpp).
"""
import argparse
import math
import random
import socket
import time

from protocolo import decodificar_pacote, montar_pacote

PACOTES_POR_ORBITA = 60
FREQUENCIA_MHZ = 915.0
RECEPTOR_ID = 1
ESPERA_ABERTURA_SERIAL = 0.5  # segundos

# Significados provisorios: o protocolo ainda nao define modos e flags.
MODO_NORMAL = 0
MODO_ECLIPSE = 1
FLAG_BATERIA_BAIXA = 0x01
TENSAO_BATERIA_BAIXA = 3.55


def gerar_telemetria(contador, rng):
    """Telemetria plausivel: luz solar e eclipse variam temperatura, carga e corrente."""
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
    """Inverte um bit, como uma interferencia no enlace que passasse pelo CRC do LoRa."""
    alterado = bytearray(pacote)
    alterado[rng.randrange(len(alterado))] ^= 1 << rng.randrange(8)
    return bytes(alterado)


def linhas_recebidas(pacote, validos, invalidos, rng):
    """Devolve o texto que a estacao imprimiria, ou levanta ValueError se o CRC falhar."""
    t = decodificar_pacote(pacote)
    rssi = rng.randint(-105, -80)
    snr = round(rng.uniform(-2.0, 10.0), 1)
    json_linha = (
        f'{{"cubesat_id": {t["cubesat_id"]}, "tipo": {t["tipo"]}, "contador": {t["contador"]}, '
        f'"tensao_bateria": {t["tensao_bateria"]:.2f}, "corrente": {t["corrente"]:.2f}, '
        f'"temperatura": {t["temperatura"]:.2f}, "modo": {t["modo"]}, "flags": {t["flags"]}, '
        f'"rssi": {rssi}, "snr": {snr:.1f}, "validos": {validos}, "invalidos": {invalidos}, '
        f'"frequencia_mhz": {FREQUENCIA_MHZ:.1f}, "receptor_id": {RECEPTOR_ID}, "raw": "{pacote.hex().upper()}"}}'
    )
    return [
        "========================================",
        f"Pacote #{t['contador']} Recebido (Válidos: {validos} | Inválidos: {invalidos})",
        "Status       : Aprovado ✅",
        "========================================",
        json_linha,
    ]


def transmitir(enviar, args):
    """Gera os pacotes e entrega as linhas; retorna (enviados, validos, invalidos, perdidos)."""
    rng = random.Random(args.semente)
    validos = invalidos = perdidos = contador = 0

    while args.pacotes is None or contador < args.pacotes:
        pacote = montar_pacote(cubesat_id=1, contador=contador, **gerar_telemetria(contador, rng))
        contador += 1

        if rng.random() < args.perda:
            perdidos += 1  # nunca chegou: a estacao nao tem como contar este pacote
        else:
            if rng.random() < args.corrupcao:
                pacote = corromper(pacote, rng)
            try:
                decodificar_pacote(pacote)
                validos += 1
                linhas = linhas_recebidas(pacote, validos, invalidos, rng)
            except ValueError:
                invalidos += 1
                linhas = ["ALERTA: Pacote corrompido (CRC Inválido). Descartado! ❌"]
            enviar("".join(linha + "\r\n" for linha in linhas).encode("utf-8"))

        if args.intervalo:
            time.sleep(args.intervalo)

    return contador, validos, invalidos, perdidos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=7000, help="porta TCP local (padrão: 7000)")
    parser.add_argument("--intervalo", type=float, default=2.0, help="segundos entre pacotes (padrão: 2)")
    parser.add_argument("--perda", type=float, default=0.05, help="fração de pacotes perdidos (padrão: 0.05)")
    parser.add_argument("--corrupcao", type=float, default=0.05, help="fração de pacotes corrompidos (padrão: 0.05)")
    parser.add_argument("--pacotes", type=int, default=None, help="encerra após N pacotes (padrão: sem limite)")
    parser.add_argument("--semente", type=int, default=None, help="semente aleatória, para repetir uma execução")
    args = parser.parse_args()

    with socket.create_server(("127.0.0.1", args.porta)) as servidor:
        print(f"Simulador aguardando a ponte em socket://127.0.0.1:{args.porta}", flush=True)
        conexao, _ = servidor.accept()

    with conexao:
        try:
            # Ao abrir um socket://, a pyserial descarta o que ja chegou; espera ela terminar
            time.sleep(ESPERA_ABERTURA_SERIAL)
            enviados, validos, invalidos, perdidos = transmitir(conexao.sendall, args)
        except (ConnectionError, KeyboardInterrupt):
            print("Simulador encerrado.")
            return

    print(f"Enviados: {enviados} | válidos: {validos} | inválidos: {invalidos} | perdidos: {perdidos}")


if __name__ == "__main__":
    main()
