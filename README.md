# Estação Terrena LoRa - CubeSat

Protótipo de estação terrena para recepção de telemetria e envio de comandos via LoRa (ESP32 + RFM95).

## Estrutura do Projeto
- `firmware/`: Código C/C++ do ESP32 para o CubeSat, a estação terrena e o teste de pinagem
- `server/`: Ponte serial (MQTT e SQLite), protocolo e simulador
- `dashboard/`: API e interface web em Flask
- `docs/`: Especificação do protocolo e tópicos MQTT
- `TESTMVP.md`: Roteiro de teste de bancada
- `tests/`: Testes automatizados

## Como rodar sem as placas
`simular.py` inicia o simulador da estação terrena, a ponte serial e o dashboard. Os dados vão para `estacao_sim.db`, recriado a cada execução, e não para o `estacao.db` real.

```bash
pip install -r requirements.txt
python simular.py
```

O dashboard fica em http://localhost:5000. Para testar um enlace pior, use por exemplo `python simular.py --perda 0.2 --corrupcao 0.1`. O Mosquitto é opcional: sem ele, os dados só não são publicados no MQTT.

## Como rodar com as placas
Com a estação terrena conectada e o Monitor Serial fechado, informe a porta e inicie a ponte e o dashboard em terminais separados:

```bash
ESTACAO_SERIAL=COM3 python server/serial_bridge.py
```

```bash
python dashboard/dashboard.py
```

No PowerShell, defina a porta antes com `$env:ESTACAO_SERIAL = "COM3"`.

## Testes

```bash
python -m unittest discover tests
```