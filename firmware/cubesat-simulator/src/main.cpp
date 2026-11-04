#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>

#define LORA_SS    18
#define LORA_RST   14
#define LORA_DIO0  26

#define FREQUENCIA        915E6
#define SPREADING_FACTOR  7
#define BANDWIDTH         125E3
#define CODING_RATE       5

// Estrutura exata de 16 bytes:
// Header(1) + Versao(1) + Tipo(1) + ID(1) + Contador(2) + Tensao(2) + Temperatura(2) + Corrente(2) + Modo(1) + Flags(1) + CRC(2) = 16 bytes
#define TAMANHO_PACOTE 16

uint16_t contadorPacote = 0;

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

// ---------- Monta o pacote binário estruturado ----------
void montarPacote(uint8_t *buffer, uint8_t cubesatId, uint16_t contador,
                   float tensao, float temperatura, float corrente, uint8_t modo, uint8_t flags) {
  buffer[0] = 0xAA; // Header
  buffer[1] = 0x01; // Versao
  buffer[2] = 0x01; // Tipo (Telemetria)
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

  // Corrente (ex: 450.0 mA ou 0.45 A -> escalado por 100)
  int16_t correnteInt = (int16_t)round(corrente * 100);
  buffer[10] = (correnteInt >> 8) & 0xFF;
  buffer[11] = correnteInt & 0xFF;

  // Modo de operação (1 byte) e Flags de erro (1 byte)
  buffer[12] = modo;
  buffer[13] = flags;

  // CRC-16 calculado sobre os primeiros 14 bytes de payload
  uint16_t crc = crc16(buffer, 14);
  buffer[14] = (crc >> 8) & 0xFF;
  buffer[15] = crc & 0xFF;
}

void imprimirPacoteHex(uint8_t *buffer, uint8_t tamanho) {
  for (uint8_t i = 0; i < tamanho; i++) {
    if (buffer[i] < 0x10) Serial.print("0");
    Serial.print(buffer[i], HEX);
    Serial.print(" ");
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("Iniciando Transmissor CubeSat LoRa...");

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(FREQUENCIA)) {
    Serial.println("ERRO: Falha ao inicializar o RFM95. Verifique conexoes.");
    while (1);
  }

  LoRa.setSpreadingFactor(SPREADING_FACTOR);
  LoRa.setSignalBandwidth(BANDWIDTH);
  LoRa.setCodingRate4(CODING_RATE);

  Serial.println("RFM95 do CubeSat inicializado com sucesso.");
}

void loop() {
  uint8_t pacote[TAMANHO_PACOTE];

  // Valores simulados para preencher a telemetria estruturada
  float tensaoSimulada = 3.72;         // Volts
  float temperaturaSimulada = 25.22;   // °C
  float correnteSimulada = 1.25;       // Amperes (ou mA equivalentes)
  uint8_t modoSimulado = 0;            // Ex: 0 = Modo Normal
  uint8_t flagsSimuladas = 0x01;       // Ex: Sem erros críticos

  montarPacote(pacote, /*cubesatId=*/1, contadorPacote,
               tensaoSimulada, temperaturaSimulada, correnteSimulada,
               modoSimulado, flagsSimuladas);

  Serial.print("Pacote Hex [16 bytes]: ");
  imprimirPacoteHex(pacote, TAMANHO_PACOTE);

  LoRa.beginPacket();
  LoRa.write(pacote, TAMANHO_PACOTE);
  LoRa.endPacket();

  Serial.printf("Pacote #%d enviado via LoRa com sucesso.\n\n", contadorPacote);

  contadorPacote++;
  delay(2000);
}