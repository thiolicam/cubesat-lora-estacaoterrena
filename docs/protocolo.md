# Protocolo LoRa e tópicos MQTT

## Configuração do rádio

| Parâmetro | Valor |
|---|---|
| Frequência | 915 MHz |
| Spreading factor | 7 |
| Bandwidth | 125 kHz |
| Coding rate | 4/5 |
| Potência | 17 dBm |

## Pacote de telemetria (16 bytes)

Os campos de mais de um byte são big-endian. O CRC é o CRC-16/CCITT-FALSE (polinômio `0x1021`, valor inicial `0xFFFF`), calculado sobre os 14 primeiros bytes.

| Byte | Campo | Tipo | Descrição |
|---|---|---|---|
| 0 | Header | `uint8` | Sempre `0xAA` |
| 1 | Versão | `uint8` | Versão do protocolo, hoje `1` |
| 2 | Tipo | `uint8` | Ver tabela de tipos |
| 3 | ID | `uint8` | Identificação do CubeSat |
| 4-5 | Contador | `uint16` | Sequencial; volta a 0 depois de 65535 |
| 6-7 | Tensão | `int16` | Volts × 100 |
| 8-9 | Temperatura | `int16` | °C × 100 |
| 10-11 | Corrente | `int16` | Ampères × 100; negativa quando a bateria descarrega |
| 12 | Modo | `uint8` | Ver tabela de modos |
| 13 | Flags | `uint8` | Ver tabela de flags |
| 14-15 | CRC | `uint16` | Integridade dos bytes 0 a 13 |

RSSI e SNR não viajam no pacote: a estação terrena os mede ao receber.

### Tipos

| Valor | Tipo | Situação |
|---|---|---|
| 1 | Telemetria | Implementado |
| 2 | Comando | Previsto (S6.1) |
| 3 | ACK | Previsto (S6.3) |

### Modos

| Valor | Modo |
|---|---|
| 0 | Normal, em luz solar |
| 1 | Eclipse |

### Flags

| Bit | Máscara | Significado |
|---|---|---|
| 0 | `0x01` | Bateria baixa (tensão abaixo de 3,55 V) |
| 1-7 | | Reservados, sempre 0 |

Os modos e as flags são uma proposta para a telemetria simulada e podem ser revistos pela equipe.

### Exemplo

CubeSat 1, pacote 42, 3,72 V, -5,25 °C, -1,25 A, modo eclipse, bateria baixa:

```text
AA 01 01 01 00 2A 01 74 FD F3 FF 83 01 01 AE FF
```

## Saída serial da estação terrena

Cada pacote válido gera uma linha JSON, lida pela ponte serial. As demais linhas são mensagens para leitura humana e são ignoradas pela ponte.

```json
{"cubesat_id": 1, "contador": 42, "tensao_bateria": 3.72, "corrente": -1.25, "temperatura": -5.25, "modo": 1, "flags": 1, "rssi": -87, "snr": 9.2, "validos": 8, "invalidos": 2}
```

`validos` e `invalidos` são acumulados desde que a estação ligou.

## Tópicos MQTT

| Tópico | Função | Situação |
|---|---|---|
| `cubesat/telemetry/raw` | Pacote bruto | A implementar: a serial ainda não entrega os bytes brutos |
| `cubesat/telemetry/parsed` | Telemetria decodificada | Implementado na ponte serial; não testado com broker |
| `cubesat/command/send` | Comando enviado | Previsto (S6.4) |
| `cubesat/command/ack` | Confirmação de comando | Previsto (S6.4) |
| `groundstation/link/stats` | RSSI, SNR e estatísticas | A implementar |
| `groundstation/status` | Estado da estação | A implementar |
