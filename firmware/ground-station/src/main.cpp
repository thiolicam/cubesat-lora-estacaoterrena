#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <lwip/def.h>

// Pinos SPI do RFM95 na Estação Terrena
#define SCK_PIN   5
#define MISO_PIN  19
#define MOSI_PIN  27
#define SS_PIN    18
#define RST_PIN   14
#define DIO0_PIN  26

#define BAND      915E6

// Estrutura binária de 12 bytes idêntica à do CubeSat
struct __attribute__((packed)) TelemetryPacket {
    uint8_t  header;       // 0xAA
    uint8_t  versao;       // 0x01
    uint8_t  tipo;         // 0x01 (Telemetria)
    uint8_t  cubesat_id;   // 1
    uint16_t contador;     // Sequencial
    int16_t  tensao;       // Valor x 100
    int16_t  temperatura;  // Valor x 100
    uint16_t crc;          // CRC-16
};

void setup() {
    Serial.begin(115200);
    while (!Serial);

    Serial.println("--- Estação Terrena LION Iniciada ---");

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
    LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);

    if (!LoRa.begin(BAND)) {
        Serial.println("Erro ao inicializar o rádio RFM95 na Estação Terrena!");
        // Em modo de testes sem o rádio físico, podemos remover o travamento se necessário
    } else {
        Serial.println("Rádio LoRa da Estação Terrena a escutar na frequência 915 MHz...");
    }
}

void loop() {
    // Tenta receber um pacote LoRa
    int packetSize = LoRa.parsePacket();
    
    if (packetSize > 0) {
        if (packetSize == sizeof(TelemetryPacket)) {
            TelemetryPacket pacote;
            
            // Lê os bytes diretamente para dentro da estrutura
            LoRa.readBytes((uint8_t*)&pacote, sizeof(TelemetryPacket));

            // Converte os campos de rede (Big-Endian) para o formato local
            uint16_t contador = ntohs(pacote.contador);
            float tensao = (float)ntohs(pacote.tensao) / 100.0;
            float temperatura = (float)ntohs(pacote.temperatura) / 100.0;
            int rssi = LoRa.packetRssi();
            float snr = LoRa.packetSnr();

            // Imprime no formato JSON legível pela porta Serial para o script Python recolher
            Serial.printf("{\"cubesat_id\": %d, \"contador\": %d, \"tensao_bateria\": %.2f, \"temperatura\": %.2f, \"rssi\": %d, \"snr\": %.1f}\n",
                pacote.cubesat_id, contador, tensao, temperatura, rssi, snr);
        } else {
            // Se vier lixo ou tamanho incorreto
            while (LoRa.available()) {
                LoRa.read();
            }
        }
    }
}