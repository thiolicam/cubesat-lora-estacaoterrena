# Demonstração do MVP

Roteiro de cerca de 10 minutos para apresentar a coleta via LoRa, o armazenamento e a visualização (S5.5).

## Antes da demonstração

Só apresente com as placas depois de aprovar os testes T1 a T6 do [roteiro de bancada](../TESTMVP.md).

- [ ] Duas placas LION com ESP32, antenas conectadas e firmware gravado
- [ ] Cabos micro-USB de dados, e um reserva
- [ ] Suspensão do notebook desligada nas configurações de energia do Windows
- [ ] Serviços do Mosquitto e do MongoDB rodando (`Get-Service mosquitto, MongoDB`)
- [ ] Monitor Serial do PlatformIO fechado, porque só um programa pode usar a porta
- [ ] Porta da estação terrena conhecida (`pio device list`)
- [ ] Relatório do ensaio de 1 hora aberto (`docs/ensaio-mvp.md`)

## Preparar

Em terminais separados, na raiz do repositório:

```bash
$env:ESTACAO_SERIAL = "COM4"; python server/serial_bridge.py
```

```bash
python dashboard/dashboard.py
```

```bash
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "cubesat/#" -t "groundstation/#" -v
```

Abra http://localhost:5000 e ligue o CubeSat.

## Roteiro

| Tempo | Mostrar | O que dizer |
|---|---|---|
| 1 min | As duas placas e o fluxo do sistema | "O CubeSat simulado transmite telemetria por LoRa. A estação recebe, valida o CRC e entrega ao computador por USB." |
| 2 min | Dashboard: status e gráficos | "Cada pacote aparece aqui em tempo real, com tensão, corrente, temperatura, RSSI e SNR." |
| 1 min | Terminal do `mosquitto_sub` | "Os mesmos dados são publicados no MQTT, em tópicos separados." |
| 2 min | Tabela de pacotes e banco | "Tudo fica gravado no MongoDB, um documento por pacote: é possível consultar o histórico e calcular a taxa de recepção." |
| 2 min | Cubra ou afaste uma antena | "RSSI e SNR pioram na hora. Se um pacote se perde, a linha do gráfico é interrompida." |
| 1 min | Desligue o CubeSat | "O dashboard avisa que não há pacotes, em vez de continuar mostrando o último valor como atual." |
| 1 min | Relatório do ensaio de 1 hora | Apresente os números medidos. |

## Depois do MVP

Se houver tempo e o teste T7 tiver sido aprovado, mostre os comandos: desative o envio periódico, solicite uma telemetria e reative.

## Se algo der errado

| Problema | O que fazer |
|---|---|
| A placa não aparece em `pio device list` | Troque o cabo; muitos só carregam |
| A ponte não abre a porta | Feche o Monitor Serial e confira o número da porta |
| A placa imprime `Erro ao inicializar o RFM95` | Rode o T1 e confira a pinagem |
| O rádio inicia, mas nenhum pacote chega | Confira as antenas, o pino `DIO0` e se as duas placas mostram os mesmos parâmetros |
| O `mosquitto_sub` não mostra nada | Use `-h 127.0.0.1`, porque `localhost` pode cair em outro broker |
| O hardware não funciona a tempo | Rode `python simular.py` e **avise que os dados são simulados** |

## Evidências para guardar

- Relatório do ensaio: `docs/ensaio-mvp.md`
- Foto das placas durante a recepção
- Captura do dashboard e do `mosquitto_sub`
- Tabela de resultados do [roteiro de bancada](../TESTMVP.md) preenchida
