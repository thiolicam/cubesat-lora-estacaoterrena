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
| 2 | Comando | Implementado |
| 3 | ACK | Implementado |

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

## Pacote de comando (11 bytes)

| Byte | Campo | Tipo | Descrição |
|---|---|---|---|
| 0 | Header | `uint8` | Sempre `0xAA` |
| 1 | Versão | `uint8` | `1` |
| 2 | Tipo | `uint8` | `2` |
| 3 | ID | `uint8` | CubeSat de destino |
| 4-5 | ID do comando | `uint16` | Devolvido no ACK para ligar a resposta ao comando |
| 6 | Código | `uint8` | Ver tabela de comandos |
| 7-8 | Parâmetro | `uint16` | Depende do comando |
| 9-10 | CRC | `uint16` | Integridade dos bytes 0 a 8 |

### Comandos

| Código | Comando | Parâmetro | Efeito no CubeSat simulado |
|---|---|---|---|
| 1 | Solicitar telemetria | 0 | Envia um pacote de telemetria, além dos periódicos |
| 2 | Alterar intervalo | 1 a 3600 s | Muda o tempo entre os pacotes periódicos |
| 3 | Envio periódico | 1 ativa, 0 desativa | Liga ou desliga os pacotes periódicos |
| 4 | Reiniciar sistema simulado | 0 | Zera o contador e volta ao intervalo de 2 s, com envio periódico ativo; não reinicia o ESP32 |

Exemplo, comando 7 alterando o intervalo para 5 s:

```text
AA 01 02 01 00 07 02 00 05 E2 DC
```

## Pacote de ACK (10 bytes)

O CubeSat responde a todo comando íntegro endereçado a ele. Comando com CRC inválido é descartado sem resposta.

| Byte | Campo | Tipo | Descrição |
|---|---|---|---|
| 0 | Header | `uint8` | Sempre `0xAA` |
| 1 | Versão | `uint8` | `1` |
| 2 | Tipo | `uint8` | `3` |
| 3 | ID | `uint8` | CubeSat que responde |
| 4-5 | ID do comando | `uint16` | O mesmo recebido no comando |
| 6 | Código | `uint8` | O mesmo recebido no comando |
| 7 | Status | `uint8` | Ver tabela de status |
| 8-9 | CRC | `uint16` | Integridade dos bytes 0 a 7 |

| Status | Significado |
|---|---|
| 0 | Executado |
| 1 | Comando desconhecido |
| 2 | Parâmetro inválido |

Exemplo, ACK do comando acima:

```text
AA 01 03 01 00 07 02 00 19 89
```

## Ciclo de um comando

O rádio é half-duplex: não recebe enquanto transmite. Por isso, só um comando fica em andamento de cada vez, e o CubeSat escuta entre as transmissões.

1. O dashboard grava o comando na tabela `comandos`, como `pendente`.
2. A ponte serial pega o próximo pendente, envia à estação e o marca como `enviado`.
3. A estação transmite por LoRa, e o CubeSat responde com o ACK antes de executar o comando.
4. O ACK deixa o comando `confirmado` (status 0) ou `rejeitado` (demais status).
5. Sem ACK em 10 s, ele vira `sem_resposta`. Não há nova tentativa automática, porque o comando pode ter sido executado e só o ACK ter se perdido.
6. Um pendente não transmitido em 30 s vira `expirado`, para que um comando antigo não seja executado quando a ponte voltar.

A fila fica no banco, e não no MQTT, para os comandos funcionarem mesmo com o broker fora do ar. Os tópicos de comando registram o que aconteceu.

## Saída serial da estação terrena

Cada pacote válido gera uma linha JSON, lida pela ponte serial. As demais linhas são mensagens para leitura humana e são ignoradas pela ponte.

```json
{"cubesat_id": 1, "tipo": 1, "contador": 42, "tensao_bateria": 3.72, "corrente": -1.25, "temperatura": -5.25, "modo": 1, "flags": 1, "rssi": -87, "snr": 9.2, "validos": 8, "invalidos": 2, "frequencia_mhz": 915.0, "receptor_id": 1, "raw": "AA010101002A0174FDF3FF830101AEFF"}
```

- `validos`, `invalidos` e `estranhos` são acumulados desde que a estação ligou. `invalidos` conta pacotes do nosso formato com CRC errado; `estranhos` conta pacotes de tamanho que não existe no protocolo, vindos de outros aparelhos LoRa na mesma frequência.
- `receptor_id` identifica a estação terrena e é definido em `RECEPTOR_ID`, no firmware dela.
- `raw` traz os 16 bytes do pacote em hexadecimal.

O ACK também gera uma linha JSON:

```json
{"cubesat_id": 1, "tipo": 3, "comando_id": 7, "codigo": 2, "status": 0, "rssi": -87, "snr": 9.2, "frequencia_mhz": 915.0, "receptor_id": 1, "raw": "AA010301000702001989"}
```

No sentido contrário, a ponte serial envia uma linha de texto por comando, no formato `CMD <id> <cubesat> <codigo> <parametro>`:

```text
CMD 7 1 2 5
```

## Tópicos MQTT

| Tópico | Função | Conteúdo | Situação |
|---|---|---|---|
| `cubesat/telemetry/raw` | Pacote bruto | Os 16 bytes em hexadecimal | Implementado |
| `cubesat/telemetry/parsed` | Telemetria decodificada | A linha JSON da serial, sem `raw` | Implementado |
| `groundstation/link/stats` | RSSI, SNR e estatísticas | JSON com `receptor_id`, `frequencia_mhz`, `rssi`, `snr`, `validos`, `invalidos` e `estranhos` | Implementado |
| `groundstation/status` | Estado da estação | JSON com `estado` (`online` ou `offline`) e `porta_serial`, retido no broker | Implementado |
| `cubesat/command/send` | Comando enviado | JSON com `comando_id`, `cubesat_id`, `codigo` e `parametro` | Implementado |
| `cubesat/command/ack` | Confirmação de comando | A linha JSON do ACK | Implementado |

Se a ponte cair sem avisar, o broker publica `offline` no lugar dela (mensagem "will").

O broker é o Mosquitto, com a configuração de `server/mosquitto.conf`. A ponte usa `127.0.0.1:1883` por padrão; `ESTACAO_MQTT_HOST` e `ESTACAO_MQTT_PORTA` mudam esses valores. Os tópicos foram testados com o Mosquitto 2.1.2 e assinantes reais, usando dados simulados.

## API de estatísticas

| Rota | Retorna |
|---|---|
| `GET /api/painel?limite=&receptor=&frequencia=` | Pacotes da janela, estatísticas da janela e do histórico, comandos e opções de filtro |
| `GET /api/estatisticas?receptor=&frequencia=` | Uma linha por receptor e frequência, em todo o histórico |
| `GET /api/estatisticas?periodo=hora` | O mesmo, hora a hora; o período está em UTC |

As estatísticas trazem `esperados`, `recebidos`, `corrompidos`, `nao_chegaram`, `interrupcoes`, `taxa_recepcao`, `rssi_medio` e `snr_medio`. Elas são calculadas na hora a partir da tabela `pacotes`, sem uma tabela própria, porque as perdas dependem da sequência dos contadores de cada receptor.

## Vários receptores

Cada recepção fica registrada em `pacotes`, com seu receptor, frequência, RSSI e SNR. Para evitar duplicidade, cópias com os mesmos bytes (`raw`), recebidas em até 60 s, contam como uma transmissão; linhas antigas sem `raw` usam o contador.

O `/api/painel` entrega por transmissão a cópia de melhor RSSI, com `copias` e `receptores`. Quando há mais de uma origem, as estatísticas trazem `combinado: true`, uma transmissão conta como recebida se qualquer receptor a recebeu, e `ganho_diversidade` é a diferença entre a taxa do conjunto e a do melhor receptor sozinho. Nesse caso, `corrompidos` soma as cópias descartadas, e `nao_chegaram` conta o que nenhum receptor recebeu íntegro.

## Banco de dados

A tabela `pacotes` é definida em `server/banco.py` e guarda uma linha por pacote válido.

| Coluna | Descrição |
|---|---|
| `id` | Chave da linha |
| `data_hora` | Momento da gravação, em UTC |
| `cubesat_id`, `tipo`, `contador` | Identificação do pacote |
| `tensao_bateria`, `corrente`, `temperatura`, `modo`, `flags` | Telemetria |
| `rssi`, `snr` | Qualidade do sinal medida na recepção |
| `validos`, `invalidos` | Contadores acumulados da estação |
| `frequencia_mhz`, `receptor_id` | Frequência e receptor utilizados |

A tabela `comandos` guarda uma linha por comando, com a confirmação recebida.

| Coluna | Descrição |
|---|---|
| `id` | Chave da linha; é também o ID do comando (módulo 65536) |
| `cubesat_id`, `codigo`, `parametro` | O comando |
| `estado` | `pendente`, `enviado`, `confirmado`, `rejeitado`, `sem_resposta` ou `expirado` |
| `criado_em`, `enviado_em`, `ack_em` | Momentos do ciclo, em UTC |
| `ack_status`, `ack_rssi`, `ack_snr`, `receptor_id` | Dados do ACK recebido |
