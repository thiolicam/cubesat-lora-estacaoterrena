# Estação Terrena LoRa - CubeSat

Protótipo de estação terrena para recepção de telemetria e envio de comandos via LoRa (ESP32 + RFM95).

## Estrutura do Projeto
- `firmware/`: Código C/C++ do ESP32 para o CubeSat e Estação Terrena
- `server/`: Broker MQTT e scripts do banco de dados SQLite
- `dashboard/`: Interface gráfica em Flask
- `docs/`: Especificação do protocolo e documentação