# Estação Terrena LoRa - CubeSat

Protótipo de estação terrena para recepção de telemetria e envio de comandos via LoRa (ESP32 + RFM95).

## Estrutura do Projeto
- `firmware/`: Código C/C++ do ESP32 para o CubeSat, a estação terrena e o teste de pinagem
- `server/`: Ponte serial (MQTT e SQLite), protocolo e simulador
- `dashboard/`: API e interface web em Flask
- `docs/`: Especificação do protocolo e tópicos MQTT
- `TESTMVP.md`: Roteiro de teste de bancada
- `tests/`: Testes automatizados

## Instalação
Você precisa de Python 3 e, para gravar as placas, do [PlatformIO](https://platformio.org/install/cli). Na raiz do repositório, no PowerShell:

```bash
python -m venv venv
```

```bash
venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

## Como rodar sem as placas
`simular.py` inicia o simulador da estação terrena, a ponte serial e o dashboard. Os dados vão para `estacao_sim.db`, recriado a cada execução, e não para o `estacao.db` real.

```bash
python simular.py
```

O dashboard fica em http://localhost:5000. Para testar um enlace pior, use por exemplo `python simular.py --perda 0.2 --corrupcao 0.1`. Para simular a diversidade, use `--receptores 3`. Sem o Mosquitto, os dados só não são publicados no MQTT.

## Broker MQTT
Instale o Mosquitto, que no Windows roda como serviço e já aceita conexões locais:

```bash
winget install EclipseFoundation.Mosquitto
```

Para rodar manualmente com a configuração do projeto, pare o serviço e use:

```bash
& "C:\Program Files\mosquitto\mosquitto.exe" -c server/mosquitto.conf -v
```

Para ver as mensagens, assine os tópicos em `127.0.0.1`, o mesmo endereço usado pela ponte:

```bash
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -t "cubesat/#" -t "groundstation/#" -v
```

Se um container Docker também usar a porta 1883, ele será outro broker, separado: `localhost` pode cair nele, e as mensagens da ponte não aparecerão, sem nenhum erro. Por isso, informe sempre `127.0.0.1`.

## Como rodar com as placas
Veja a porta de cada placa e grave um firmware em cada uma, trocando `COM3` e `COM4` pelas suas:

```bash
pio device list
```

```bash
pio run -d firmware/cubesat-simulator -t upload --upload-port COM3
```

```bash
pio run -d firmware/ground-station -t upload --upload-port COM4
```

Com o Monitor Serial fechado, inicie a ponte e o dashboard em terminais separados, e abra http://localhost:5000:

```bash
$env:ESTACAO_SERIAL = "COM4"; python server/serial_bridge.py
```

```bash
python dashboard/dashboard.py
```

Os testes de bancada estão em [TESTMVP.md](TESTMVP.md), a demonstração em [docs/demo-mvp.md](docs/demo-mvp.md) e o relatório de um teste sai de `server/relatorio_testes.py`.

## Como operar mais de um receptor
Cada receptor é uma placa com o próprio `RECEPTOR_ID`, definido na gravação. No PowerShell:

```bash
$env:PLATFORMIO_BUILD_FLAGS = "-DRECEPTOR_ID=2"; pio run -d firmware/ground-station -t upload --upload-port COM5
```

Para diversidade de frequência, inclua a frequência em hertz, como `-DRECEPTOR_ID=3 -DFREQUENCIA=923.3E6`. Depois, limpe a variável com `Remove-Item Env:PLATFORMIO_BUILD_FLAGS`.

Rode uma ponte por receptor, todas no mesmo banco. Só a primeira transmite comandos; nas demais, desative o envio:

```bash
$env:ESTACAO_SERIAL = "COM5"; $env:ESTACAO_ENVIA_COMANDOS = "0"; python server/serial_bridge.py
```

No dashboard, sem filtro de receptor, cada transmissão conta uma vez, e os gráficos mostram a cópia de melhor RSSI. O bloco "Ganho de diversidade" compara o conjunto com o melhor receptor sozinho. As estatísticas por receptor continuam separadas.

## Testes

```bash
python -m unittest discover tests
```