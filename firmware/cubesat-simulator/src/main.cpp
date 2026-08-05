#include <SPI.h>
#include <LoRa.h>

// Ajuste conforme o pinout real da placa LION
#define LORA_SS   18
#define LORA_RST  14
#define LORA_DIO0 26

// Parâmetros de rádio
#define FREQUENCIA        915E6
#define SPREADING_FACTOR  7
#define BANDWIDTH         125E3
#define CODING_RATE       5

// --- Estrutura do pacote, seguindo docs/protocolo.md ---
// Header(1) + Versao(1) + Tipo(1) + ID(1) + Contador(2)
// + Tensao(2) + Temperatura(2) + CRC(2) = 12 bytes
#define TAMANHO_PACOTE 12

uint16_t contadorPacote = 0;

// ---------- CRC-16/CCITT, mesma lógica usada no teste_protocolo.py ----------
uint16_t crc16(uint8_t *dados, uint8_t tamanho) {
  uint16_t crc = 0xFFFF;
  for (uint8_t i = 0; i < tamanho; i++) {
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

// ---------- Monta o pacote em um buffer de bytes ----------
void montarPacote(uint8_t *buffer, uint8_t cubesatId, uint16_t contador,
                   float tensao, float temperatura) {
  uint8_t header = 0xAA;
  uint8_t versao = 1;
  uint8_t tipo = 1; // telemetria

  int16_t tensaoInt = (int16_t)round(tensao * 100);
  int16_t temperaturaInt = (int16_t)round(temperatura * 100);

  buffer[0] = header;
  buffer[1] = versao;
  buffer[2] = tipo;
  buffer[3] = cubesatId;

  // big-endian: byte mais significativo primeiro
  buffer[4] = (contador >> 8) & 0xFF;
  buffer[5] = contador & 0xFF;

  buffer[6] = (tensaoInt >> 8) & 0xFF;
  buffer[7] = tensaoInt & 0xFF;

  buffer[8] = (temperaturaInt >> 8) & 0xFF;
  buffer[9] = temperaturaInt & 0xFF;

  uint16_t crc = crc16(buffer, 10); // CRC sobre os 10 primeiros bytes
  buffer[10] = (crc >> 8) & 0xFF;
  buffer[11] = crc & 0xFF;
}

// ---------- Imprime o pacote em hexadecimal no serial ----------
void imprimirPacoteHex(uint8_t *buffer, uint8_t tamanho) {
  for (uint8_t i = 0; i < tamanho; i++) {
    if (buffer[i] < 0x10) Serial.print("0");
    Serial.print(buffer[i], HEX);
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("Iniciando teste do RFM95...");

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(FREQUENCIA)) {
    Serial.println("ERRO: Falha ao inicializar o RFM95. Verifique conexoes.");
    while (1);
  }

  LoRa.setSpreadingFactor(SPREADING_FACTOR);
  LoRa.setSignalBandwidth(BANDWIDTH);
  LoRa.setCodingRate4(CODING_RATE);

  Serial.println("RFM95 inicializado com sucesso.");
  Serial.print("Frequencia: ");
  Serial.print(FREQUENCIA / 1E6);
  Serial.println(" MHz");
  Serial.print("Spreading Factor: ");
  Serial.println(SPREADING_FACTOR);
  Serial.print("Bandwidth: ");
  Serial.print(BANDWIDTH / 1E3);
  Serial.println(" kHz");
  Serial.print("Coding Rate: 4/");
  Serial.println(CODING_RATE);
}

void loop() {
  uint8_t pacote[TAMANHO_PACOTE];

  // valores simulados de telemetria (equivalente aos testes em Python)
  float tensaoSimulada = 3.72;
  float temperaturaSimulada = 25.22;

  montarPacote(pacote, /*cubesatId=*/1, contadorPacote,
               tensaoSimulada, temperaturaSimulada);

  Serial.print("Pacote montado: ");
  imprimirPacoteHex(pacote, TAMANHO_PACOTE);

  LoRa.beginPacket();
  LoRa.write(pacote, TAMANHO_PACOTE);
  LoRa.endPacket();

  Serial.println("Pacote enviado via LoRa.");

  contadorPacote++;
  delay(2000);
} 