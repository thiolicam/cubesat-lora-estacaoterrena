# Relatório de teste

Banco: `estacao.db`

- **Início:** 10/11/2026 17:19:33
- **Fim:** 10/11/2026 18:21:41
- **Duração:** 1 h 2 min 8 s
- **Maior intervalo sem pacotes:** 0 h 0 min 4 s
- **Taxa de recepção:** 99,3% (1809 de 1822 transmissões)
- **Corrompidos:** 52
- **Não chegaram:** 0
- **Interrupções fora da conta:** 0
- **Sinal médio:** RSSI -29 dBm, SNR 9,6 dB

## Critério de 1 h de operação contínua

**Aprovado**

## Por receptor

| Receptor | Frequência (MHz) | Recebidos | Esperados | Recepção | Corrompidos | Não chegaram | RSSI médio (dBm) | SNR médio (dB) |
|---|---|---|---|---|---|---|---|---|
| 1 | 915,0 | 1809 | 1822 | 99,3% | 52 | 0 | -29 | 9,6 |

## Comandos

Nenhum comando no período.

## Condições e observações

- **Montagem:** CubeSat e estação terrena em duas placas LION com ESP32, com antenas e próximas uma da outra, na bancada. Por isso o sinal é muito forte, e o resultado não representa o alcance do enlace.
- **Firmware:** versão da `main` no commit `af4f3d8`. Pinagem da LION: SCK 18, MISO 19, MOSI 23, SS 5, RST 16, DIO0 4.
- **Servidor:** ponte serial na COM6 gravando no `estacao.db` e publicando no Mosquitto 2.1.2, com o dashboard aberto durante todo o ensaio.
- **Corrompidos superestimados:** a estação conta como inválido qualquer pacote descartado. Durante o ensaio havia outro aparelho LoRa transmitindo em 915 MHz, com pacotes de 186 a 189 bytes, que entram nessa contagem. Por isso o valor de corrompidos passa das 13 transmissões que faltaram, e "Não chegaram" fica em 0. O número confiável é a taxa de recepção.
