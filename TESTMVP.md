# Roteiro de teste do MVP

Testes de bancada com as placas LION, na ordem em que dependem uns dos outros. Os IDs (S1.3, S4.6...) são os do cronograma.

Para cada teste, anote a data, o resultado e guarde o log ou a captura de tela: eles servem de evidência para o relatório de testes.

## Preparação

Confira que o serviço do Mosquitto está rodando. Se houver um container Docker com broker na porta 1883, ele é outro broker, separado: use sempre `-h 127.0.0.1` nas ferramentas MQTT, ou você ficará assinando o broker errado sem nenhum erro.

```bash
Get-Service mosquitto
```

Rode os comandos a partir da raiz do repositório. Conecte uma placa por vez para identificar as portas e troque `COM3` pela porta de cada uma:

```bash
pio device list
```

**Sem as placas:** para testar só o software, use `python simular.py` (veja o README).

## T1. Descobrir a pinagem da LION (S1.3, S1.4)

O histórico do repositório traz pinagens diferentes. Este teste descobre a correta sem transmitir nada.

```bash
pio run -d firmware/teste-pinos -t upload --upload-port COM3
```

```bash
pio device monitor -b 115200 --port COM3
```

**Passa se:** uma pinagem mostra `[OK]` com `versao 0x12`, nas duas placas.

Se a pinagem correta for outra que não a do firmware, ajuste `LORA_SS`, `LORA_RST`, `LORA_DIO0`, `LORA_SCK`, `LORA_MISO` e `LORA_MOSI` no `main.cpp` do `cubesat-simulator` e do `ground-station`. O `DIO0` não é testado aqui; confira-o no esquema elétrico. Se ele estiver errado, o T2 mostrará o rádio iniciando, mas sem receber pacotes.

## T2. Enlace LoRa (S2.1, S2.2, S2.3)

Grave um firmware em cada placa:

```bash
pio run -d firmware/cubesat-simulator -t upload --upload-port COM3
```

```bash
pio run -d firmware/ground-station -t upload --upload-port COM4
```

Abra o monitor da estação terrena:

```bash
pio device monitor -b 115200 --port COM4
```

**Passa se:**
- As duas placas mostram frequência, SF, BW, CR e potência iguais ao iniciar.
- A estação mostra `Aprovado` a cada 2 s, com o contador subindo.
- Tensão, corrente e temperatura variam, inclusive com valores negativos.
- Cada pacote traz RSSI e SNR.

## T3. Coleta de 30 minutos (S2.6)

Deixe o T2 rodando por 30 minutos e salve o log.

**Passa se:** a estação não trava e os contadores de válidos e inválidos continuam coerentes.

## T4. Da placa ao dashboard (S4.6, S5.1)

Feche o monitor serial, porque só um programa pode usar a porta. No PowerShell, em dois terminais:

```bash
$env:ESTACAO_SERIAL = "COM4"; python server/serial_bridge.py
```

```bash
python dashboard/dashboard.py
```

Abra http://localhost:5000.

**Passa se:** cada pacote aceito aparece no dashboard e no `estacao.db`, e a linha do gráfico continua a cada novo pacote.

**MQTT:** o S5.1 prevê passar pelo broker. Com o serviço do Mosquitto rodando, assine todos os tópicos em outro terminal. Use `127.0.0.1`, e não `localhost`, para cair no mesmo broker da ponte:

```bash
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "cubesat/#" -t "groundstation/#" -v
```

**Passa se:** cada pacote aparece nos tópicos `raw`, `parsed` e `link/stats`, e o `groundstation/status` mostra `online`. Ao encerrar a ponte, o status deve mudar para `offline`.

## T5. Falhas previstas (S5.2)

Com o T4 rodando:

1. Desligue o CubeSat. O dashboard deve mostrar "Sem pacotes há..." depois de 15 s.
2. Religue o CubeSat. O contador recomeça, e a recepção não deve ser tratada como perda.
3. Afaste as antenas ou cubra uma delas. RSSI e SNR devem piorar.

**Passa se:** nenhuma falha exige reiniciar a ponte ou o dashboard.

## T6. Aceitação do MVP (S5.3)

Antes de começar, **desligue a suspensão do notebook** nas configurações de energia do Windows. Se ele dormir, o teste para. Anote o horário e deixe o T4 rodando por pelo menos 1 hora. No fim, gere o relatório, trocando o horário pelo de início:

```bash
python server/relatorio_testes.py --desde "2026-11-05 14:00" --minimo-horas 1 --saida docs/ensaio-mvp.md
```

**Passa se:** o relatório diz "Aprovado", ou seja, o sistema operou por 1 hora sem nenhum intervalo acima de 60 s sem pacotes. O dashboard também precisa continuar atualizando até o fim.

## T7. Ciclo comando e ACK (S6.6)

Com o T4 rodando, use os botões de "Comandos para o CubeSat" no dashboard:

| Comando | Resultado esperado |
|---|---|
| Desativar envio periódico | Confirmado; os pacotes param, e o dashboard mostra "Sem pacotes há..." depois de 15 s |
| Solicitar telemetria | Confirmado; chega um único pacote novo |
| Ativar envio periódico | Confirmado; os pacotes voltam a cada 2 s |
| Alterar intervalo para 5 s | Confirmado; os pacotes passam a chegar a cada 5 s |
| Reiniciar sistema simulado | Confirmado; o contador volta a 0, e o intervalo, a 2 s |
| Qualquer comando com o CubeSat desligado | "Sem resposta" depois de 10 s |

**Passa se:** todos os resultados acontecem. Se muitos comandos ficarem sem resposta com o enlace bom, aumente `ESPERA_ANTES_DE_RESPONDER_MS` no firmware do CubeSat.

## Registro

| Teste | Data | Resultado | Evidência |
|---|---|---|---|
| T1 Pinagem | 10/11/2026 | Aprovado com um ESP32 (CP2102) na LION: SCK 18, MISO 19, MOSI 23, SS 5, RST 16, DIO0 4. Outro ESP32 (CH9102) não iniciou na LION: o GPIO12 ficou alto e a flash não respondeu | Saída do `teste-pinos` |
| T2 Enlace | 10/11/2026 | Aprovado em 30 s, com as placas lado a lado: 13 de 14 pacotes recebidos (faltou o 11), RSSI -22 dBm, SNR 9,2 a 10 dB, parâmetros iguais nas duas placas. Valores negativos ainda não observados nesse intervalo | Leitura simultânea das duas portas |
| T3 30 minutos | 10/11/2026 | Aprovado dentro do ensaio de 1 hora: nenhuma trava, contadores coerentes | `docs/ensaio-mvp.md` |
| T4 Ponta a ponta | 10/11/2026 | Aprovado: em 7 min, 204 pacotes no dashboard, no `estacao.db` e no MQTT (assinante independente), com temperatura de -20,38 a 30,41 °C, corrente de -0,42 a 0,91 A e os dois modos. Faltaram 5 de 209 contadores; a estação descartou 24 pacotes, a maioria de outro aparelho em 915 MHz | Dashboard, banco e `mosquitto_sub` |
| T5 Falhas | 10/11/2026 | Aprovado depois de uma correção. CubeSat desligado: o dashboard ficou acessível e mostrou a falta de pacotes; religado, o contador recomeçou do 0 sem reiniciar nada. Sem a antena da estação, a recepção parou totalmente. Ao mexer no cabo da estação, a porta COM6 sumiu e a ponte encerrou; corrigida para reabrir a porta sozinha, e o teste repetido (cabo desconectado e reconectado) passou | Registro do dashboard a cada 2 s e saída da ponte |
| T6 Aceitação | 10/11/2026 | Aprovado: 1 h 2 min contínuos, maior intervalo sem pacotes de 4 s, 99,3% de recepção (1.809 de 1.822), RSSI médio -29 dBm, SNR 9,6 dB, com as placas lado a lado | `docs/ensaio-mvp.md` |
| T7 Comandos | | | |
