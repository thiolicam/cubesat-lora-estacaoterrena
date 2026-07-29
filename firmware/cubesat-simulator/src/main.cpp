#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <lwip/def.h>

// Pinos SPI oficiais para a placa LION/ESP32 + RFM95
#define SCK_PIN   5
#define MISO_PIN  19
#define MOSI_PIN  27
#define SS_PIN    18
#define RST_PIN   14
#define DIO0_PIN  26

#define BAND      915E6 // 915 MHz

// Estrutura binária de 12 bytes do protocolo do CubeSat
struct __attribute__((packed)) TelemetryPacket {
    uint8_t  header;       // 0xAA
    uint8_t  versao;       // 0x01
    uint8_t  tipo;         // 0x01 (Telemetria)
    uint8_t  cubesat_id;   // 1
    uint16_t contador;     // Sequencial (Big-Endian)
    int16_t  tensao;       // Valor x 100
    int16_t  temperatura;  // Valor x 100
    uint16_t crc;          // CRC-16
};

uint16_t contador_pacotes = 0;

uint16_t calcular_crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (data[i] << 8);
        for (uint8_t bit = 0; bit < 8; bit++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

void setup() {
    Serial.begin(115200);
    while (!Serial);

    Serial.println("--- Inicializando CubeSat (Hardware Real) ---");

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
    LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);

    // Inicializa o rádio LoRa na frequência especificada
    if (!LoRa.begin(BAND)) {
        Serial.println("ERRO CRÍTICO: Falha ao inicializar o rádio RFM95! Verifique as conexões SPI.");
        while (1); // Trava se o rádio não responder
    }

    // Configurações avançadas de rádio para otimizar o alcance e robustez
    LoRa.setSpreadingFactor(7);     // SF7 (Taxa de transmissão padrão)
    LoRa.setSignalBandwidth(125E3); // 125 kHz
    LoRa.setCodingRate4(5);         // 4/5

    Serial.println("Rádio RFM95 inicializado com sucesso no canal LoRa!");
}

void loop() {
    TelemetryPacket pacote;
    pacote.header = 0xAA;
    pacote.versao = 0x01;
    pacote.tipo = 0x01;
    pacote.cubesat_id = 1;
    
    contador_pacotes++;
    pacote.contador = htons(contador_pacotes);
    pacote.tensao = htons(372);       // 3.72 V simulados
    pacote.temperatura = htons(2550); // 25.50 °C simulados

    // Calcula CRC sobre os primeiros 10 bytes
    uint16_t crc_calculado = calcular_crc16((uint8_t*)&pacote, 10);
    pacote.crc = htons(crc_calculado);

    // Envia o pacote de 12 bytes via ondas de rádio LoRa
    LoRa.beginPacket();
    LoRa.write((uint8_t*)&pacote, sizeof(TelemetryPacket));
    LoRa.endPacket();

    Serial.printf("Pacote #%d transmitido via LoRa (915 MHz)!\n", contador_pacotes);

    delay(5000); // Envia a cada 5 segundos
}