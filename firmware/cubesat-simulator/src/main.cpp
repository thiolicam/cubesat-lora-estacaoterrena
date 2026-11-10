#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>

// Pinagem da LION, confirmada na placa em 10/11/2026 com firmware/teste-pinos.
// E a mesma da estacao terrena: as duas usam a mesma placa.
#define LORA_SS    5
#define LORA_RST   16
#define LORA_DIO0  4

#define LORA_SCK   18
#define LORA_MISO  19
#define LORA_MOSI  23

#ifndef FREQUENCIA
#define FREQUENCIA        915E6
#endif
#define SPREADING_FACTOR  7
#define BANDWIDTH         125E3
#define CODING_RATE       5
#define POTENCIA_DBM      17

#define CUBESAT_ID        1

// Telemetria simulada: uma "orbita" a cada 60 pacotes, alternando sol e eclipse
#define PACOTES_POR_ORBITA    60
#define TENSAO_BATERIA_BAIXA  3.55f

// Valores definidos em docs/protocolo.md
#define HEADER              0xAA
#define VERSAO              0x01
#define TIPO_TELEMETRIA     0x01
#define TIPO_COMANDO        0x02
#define TIPO_ACK            0x03

#define MODO_NORMAL         0
#define MODO_ECLIPSE        1
#define FLAG_BATERIA_BAIXA  0x01

#define CMD_SOLICITAR_TELEMETRIA  1
#define CMD_ALTERAR_INTERVALO     2
#define CMD_ENVIO_PERIODICO       3
#define CMD_REINICIAR             4

#define STATUS_OK                    0
#define STATUS_COMANDO_DESCONHECIDO  1
#define STATUS_PARAMETRO_INVALIDO    2

#define INTERVALO_PADRAO_S  2
#define INTERVALO_MINIMO_S  1
#define INTERVALO_MAXIMO_S  3600

#define TAMANHO_PACOTE   16  // Header(1) Versao(1) Tipo(1) ID(1) Contador(2) Tensao(2) Temperatura(2) Corrente(2) Modo(1) Flags(1) CRC(2)
#define TAMANHO_COMANDO  11  // Header(1) Versao(1) Tipo(1) ID(1) IdComando(2) Codigo(1) Parametro(2) CRC(2)
#define TAMANHO_ACK      10  // Header(1) Versao(1) Tipo(1) ID(1) IdComando(2) Codigo(1) Status(1) CRC(2)

// A estacao precisa voltar a escutar depois de transmitir antes de receber a resposta
#define ESPERA_ANTES_DE_RESPONDER_MS  50
#define ESPERA_ENTRE_RESPOSTAS_MS     150

uint16_t contadorPacote = 0;
uint32_t intervaloMs = INTERVALO_PADRAO_S * 1000UL;
bool envioPeriodico = true;
unsigned long ultimoEnvio = 0;

// Algoritmo de Cálculo do CRC-16 (CCITT padrão)
uint16_t crc16(const uint8_t *dados, size_t tamanho) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < tamanho; i++) {
    crc ^= (uint16_t)dados[i] << 8;
    for (uint8_t bit = 0; bit < 8; bit++) {
      if (crc & 0x8000) {
        crc = (crc << 1) ^ 0x1021;
      } else {
        crc = crc << 1;
      }
    }
  }
  return crc;
}

// Grava o CRC nos dois ultimos bytes do pacote
void acrescentarCrc(uint8_t *buffer, size_t tamanho) {
  uint16_t crc = crc16(buffer, tamanho - 2);
  buffer[tamanho - 2] = (crc >> 8) & 0xFF;
  buffer[tamanho - 1] = crc & 0xFF;
}

// ---------- Monta o pacote binário estruturado ----------
void montarPacote(uint8_t *buffer, uint8_t cubesatId, uint16_t contador,
                   float tensao, float temperatura, float corrente, uint8_t modo, uint8_t flags) {
  buffer[0] = HEADER;
  buffer[1] = VERSAO;
  buffer[2] = TIPO_TELEMETRIA;
  buffer[3] = cubesatId;

  // Contador (Big-Endian / Network Byte Order)
  buffer[4] = (contador >> 8) & 0xFF;
  buffer[5] = contador & 0xFF;

  // Tensão (ex: 3.72V -> 372)
  int16_t tensaoInt = (int16_t)round(tensao * 100);
  buffer[6] = (tensaoInt >> 8) & 0xFF;
  buffer[7] = tensaoInt & 0xFF;

  // Temperatura (ex: 25.22 °C -> 2522)
  int16_t temperaturaInt = (int16_t)round(temperatura * 100);
  buffer[8] = (temperaturaInt >> 8) & 0xFF;
  buffer[9] = temperaturaInt & 0xFF;

  // Corrente (ex: 1.25 A -> 125)
  int16_t correnteInt = (int16_t)round(corrente * 100);
  buffer[10] = (correnteInt >> 8) & 0xFF;
  buffer[11] = correnteInt & 0xFF;

  // Modo de operação (1 byte) e Flags de erro (1 byte)
  buffer[12] = modo;
  buffer[13] = flags;

  acrescentarCrc(buffer, TAMANHO_PACOTE);
}

// Variacao aleatoria entre -amplitude e +amplitude
float ruido(float amplitude) {
  return random(-100, 101) / 100.0f * amplitude;
}

void imprimirPacoteHex(const uint8_t *buffer, uint8_t tamanho) {
  for (uint8_t i = 0; i < tamanho; i++) {
    if (buffer[i] < 0x10) Serial.print("0");
    Serial.print(buffer[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
}

void transmitir(const uint8_t *buffer, size_t tamanho) {
  LoRa.beginPacket();
  LoRa.write(buffer, tamanho);
  LoRa.endPacket();
}

void enviarTelemetria() {
  uint8_t pacote[TAMANHO_PACOTE];

  // Telemetria simulada: mesmo modelo de server/simulador_estacao.py
  float fase = sin(2 * PI * contadorPacote / PACOTES_POR_ORBITA);
  bool noSol = fase >= 0;
  float tensaoSimulada = 3.70f + 0.20f * fase + ruido(0.01f);          // Volts
  float temperaturaSimulada = 5.0f + 25.0f * fase + ruido(0.5f);       // °C
  float correnteSimulada = (noSol ? 0.90f * fase : -0.40f) + ruido(0.02f);  // Amperes
  uint8_t modoSimulado = noSol ? MODO_NORMAL : MODO_ECLIPSE;
  uint8_t flagsSimuladas = tensaoSimulada < TENSAO_BATERIA_BAIXA ? FLAG_BATERIA_BAIXA : 0;

  montarPacote(pacote, CUBESAT_ID, contadorPacote,
               tensaoSimulada, temperaturaSimulada, correnteSimulada,
               modoSimulado, flagsSimuladas);

  Serial.print("Pacote Hex [16 bytes]: ");
  imprimirPacoteHex(pacote, TAMANHO_PACOTE);

  transmitir(pacote, TAMANHO_PACOTE);

  Serial.printf("Pacote #%d enviado via LoRa com sucesso.\n\n", contadorPacote);

  contadorPacote++;
  ultimoEnvio = millis();
}

// Reinicia o sistema simulado, nao o ESP32: o CubeSat continua apto a receber comandos
void reiniciarSistemaSimulado() {
  contadorPacote = 0;
  intervaloMs = INTERVALO_PADRAO_S * 1000UL;
  envioPeriodico = true;
  ultimoEnvio = millis();
}

uint8_t avaliarComando(uint8_t codigo, uint16_t parametro) {
  switch (codigo) {
    case CMD_SOLICITAR_TELEMETRIA:
    case CMD_REINICIAR:
      return STATUS_OK;
    case CMD_ALTERAR_INTERVALO:
      return (parametro >= INTERVALO_MINIMO_S && parametro <= INTERVALO_MAXIMO_S) ? STATUS_OK : STATUS_PARAMETRO_INVALIDO;
    case CMD_ENVIO_PERIODICO:
      return parametro <= 1 ? STATUS_OK : STATUS_PARAMETRO_INVALIDO;
    default:
      return STATUS_COMANDO_DESCONHECIDO;
  }
}

void enviarAck(uint16_t comandoId, uint8_t codigo, uint8_t status) {
  uint8_t ack[TAMANHO_ACK] = {HEADER, VERSAO, TIPO_ACK, CUBESAT_ID,
                              (uint8_t)(comandoId >> 8), (uint8_t)(comandoId & 0xFF), codigo, status};
  acrescentarCrc(ack, TAMANHO_ACK);
  delay(ESPERA_ANTES_DE_RESPONDER_MS);
  transmitir(ack, TAMANHO_ACK);
}

void processarComando(const uint8_t *comando) {
  uint16_t crcRecebido = ((uint16_t)comando[9] << 8) | comando[10];
  if (crc16(comando, TAMANHO_COMANDO - 2) != crcRecebido) {
    Serial.println("Comando descartado: CRC invalido.");
    return;
  }
  if (comando[0] != HEADER || comando[1] != VERSAO || comando[2] != TIPO_COMANDO || comando[3] != CUBESAT_ID) {
    return;  // pacote de outro tipo ou de outro CubeSat
  }

  uint16_t comandoId = ((uint16_t)comando[4] << 8) | comando[5];
  uint8_t codigo = comando[6];
  uint16_t parametro = ((uint16_t)comando[7] << 8) | comando[8];
  uint8_t status = avaliarComando(codigo, parametro);

  Serial.printf("Comando %u recebido: codigo %u, parametro %u, status %u\n", comandoId, codigo, parametro, status);
  enviarAck(comandoId, codigo, status);

  if (status != STATUS_OK) {
    return;
  }
  switch (codigo) {
    case CMD_SOLICITAR_TELEMETRIA:
      delay(ESPERA_ENTRE_RESPOSTAS_MS);
      enviarTelemetria();
      break;
    case CMD_ALTERAR_INTERVALO:
      intervaloMs = parametro * 1000UL;
      break;
    case CMD_ENVIO_PERIODICO:
      envioPeriodico = parametro == 1;
      ultimoEnvio = millis();
      break;
    case CMD_REINICIAR:
      reiniciarSistemaSimulado();
      break;
  }
}

void verificarComandoRecebido() {
  int tamanho = LoRa.parsePacket();
  if (tamanho == 0) {
    return;
  }
  if (tamanho == TAMANHO_COMANDO) {
    uint8_t comando[TAMANHO_COMANDO];
    LoRa.readBytes(comando, TAMANHO_COMANDO);
    processarComando(comando);
  } else {
    while (LoRa.available()) {
      LoRa.read();
    }
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("Iniciando Transmissor CubeSat LoRa...");

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(FREQUENCIA)) {
    Serial.println("ERRO: Falha ao inicializar o RFM95. Verifique conexoes.");
    while (1);
  }

  LoRa.setSpreadingFactor(SPREADING_FACTOR);
  LoRa.setSignalBandwidth(BANDWIDTH);
  LoRa.setCodingRate4(CODING_RATE);
  LoRa.setTxPower(POTENCIA_DBM);

  Serial.println("RFM95 do CubeSat inicializado com sucesso.");
  Serial.printf("Frequencia: %.1f MHz | SF: %d | BW: %.0f kHz | CR: 4/%d | Potencia: %d dBm\n",
                FREQUENCIA / 1E6, SPREADING_FACTOR, BANDWIDTH / 1E3, CODING_RATE, POTENCIA_DBM);
}

void loop() {
  // Sem delay aqui: entre as transmissoes o radio fica escutando comandos
  verificarComandoRecebido();

  if (envioPeriodico && millis() - ultimoEnvio >= intervaloMs) {
    enviarTelemetria();
  }
}
