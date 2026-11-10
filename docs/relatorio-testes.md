# Relatório de testes

Rascunho de 10/11/2026. Cobre o MVP e os comandos. A diversidade (semana 7) e a campanha final (S9.3) entram depois.

## Sistema testado

- **Placas:** duas LION com RFM95, cada uma com um ESP32-D0WD-V3. A estação terrena usa um ESP32 com conversor USB CP2102; o CubeSat simulado, um com CH9102.
- **Pinagem da LION:** SCK 18, MISO 19, MOSI 23, SS 5, RST 16, DIO0 4, confirmada nas duas placas com `firmware/teste-pinos`.
- **Rádio:** 915 MHz, SF7, 125 kHz, CR 4/5, 17 dBm.
- **Servidor:** ponte serial gravando em SQLite e publicando no Mosquitto 2.1.2, com API e dashboard em Flask, no Windows 11.
- **Montagem:** as duas placas na mesma bancada, com antenas, próximas uma da outra.

## Resultados

| Teste | Resultado | Principais números |
|---|---|---|
| T1 Pinagem | Aprovado | Pinagem confirmada em duas placas; RST e DIO0 identificados sem transmitir |
| T2 Enlace | Aprovado | 13 de 14 pacotes em 30 s; RSSI -22 dBm; SNR 9,2 a 10 dB |
| T3 30 minutos | Aprovado | Coberto pelo T6 |
| T4 Ponta a ponta | Aprovado | 204 pacotes em 7 min no dashboard, no banco e no MQTT; temperatura de -20,38 a 30,41 °C |
| T5 Falhas | Aprovado após correção | Ver "Problemas encontrados" |
| T6 Aceitação | Aprovado | 1 h 2 min contínuos; 99,3% de recepção (1.809 de 1.822); no máximo 4 s sem pacotes |
| T7 Comandos | Aprovado | 5 comandos confirmados em menos de 1 s; ACK em cerca de -50 dBm; "sem resposta" em 10,5 s |
| S8.5 Teste de 2 horas | Em andamento | Iniciado às 18:54 de 10/11 |

Detalhes de cada teste em [TESTMVP.md](../TESTMVP.md); o relatório completo do ensaio de 1 hora está em [ensaio-mvp.md](ensaio-mvp.md).

## Problemas encontrados e o que foi feito

| Problema | Causa | Situação |
|---|---|---|
| O CubeSat não falava com o rádio | O firmware usava outra pinagem (SCK 5, MOSI 27, SS 18, RST 14, DIO0 26) | Corrigido para a pinagem da LION |
| Um ESP32 não iniciava na LION | O GPIO12 ficou em nível alto na inicialização, e a flash foi alimentada com 1,8 V | Funcionou depois de reencaixado na outra LION; a causa exata não foi confirmada |
| A ponte encerrava quando o cabo da estação se mexia | Não havia nova tentativa quando a porta serial sumia | Corrigido: a ponte reabre a porta a cada 2 s; retestado com o cabo desconectado |
| Pacotes de outro aparelho contavam como corrompidos | Havia outro transmissor LoRa em 915 MHz, com pacotes de 186 a 189 bytes | Corrigido: contados à parte como `estranhos` |
| Um ESP32 não aparecia no Windows | Faltava o driver do CP2102 | Driver instalado pelo Windows Update |
| Um ESP32 não entrava sozinho em modo de gravação | O circuito de reinicialização automática do CH9102 não funcionou | Gravação feita segurando o botão BOOT |

## Limitações

- **Alcance não medido:** as placas estavam próximas, com sinal muito forte. Os resultados mostram a confiabilidade do sistema, não o alcance do enlace.
- **Um receptor só:** a diversidade de antenas e de frequência ainda não foi testada no hardware.
- **Ambiente com interferência:** havia outro aparelho LoRa na mesma frequência durante todos os testes.
- **Firmwares anteriores:** as placas vieram com firmwares compilados fora do repositório. As cópias estão em `firmware/backups`, mas o código-fonte não.

## Pendente

- Concluir o teste de 2 horas (S8.5) e acrescentar o resultado.
- Testar a diversidade (S7.1 a S7.5), que depende de mais placas e de uma decisão sobre a diversidade de frequência.
- Campanha final de testes (S9.3).
