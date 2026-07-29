#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <lwip/def.h>

// Pinos SPI do RFM95 na Estação Terrena
#define SCK_PIN    5
#define MISO_PIN   19
#define MOSI_PIN   27
#define SS_PIN     18
#define RST_PIN    14
#define DIO0_PIN   26

#define BAND       915E6

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

// Contadores de pacotes para a métrica de confiabilidade
unsigned long pacotesValidos = 0;
unsigned long pacotesInvalidos = 0;

// Função simples para cálculo de CRC-16 (Modbus/CCITT padrão para validação)
uint16_t calcularCRC16(const uint8_t *data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x0001) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

void setup() {
    Serial.begin(115200);
    while (!Serial);

    Serial.println("--- Estação Terrena LION Iniciada (com CRC e Validação) ---");

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
    LoRa.setPins(SS_PIN, RST_PIN, DIO0_PIN);

    if (!LoRa.begin(BAND)) {
        Serial.println("Erro ao inicializar o rádio RFM95 na Estação Terrena!");
    } else {
        // Ativa explicitamente o CRC no rádio LoRa de hardware
        LoRa.enableCrc();
        Serial.println("Rádio LoRa da Estação Terrena a escutar na frequência 915 MHz com CRC ativo...");
    }
}

void loop() {
    int packetSize = LoRa.parsePacket();
    
    if (packetSize > 0) {
        // 1. Verifica se o tamanho do pacote bate exatamente com a estrutura esperada
        if (packetSize == sizeof(TelemetryPacket)) {
            uint8_t buffer[sizeof(TelemetryPacket)];
            
            // Lê os bytes brutos para o buffer de verificação
            LoRa.readBytes(buffer, sizeof(TelemetryPacket));

            TelemetryPacket *pacote =entropy_cast: (TelemetryPacket*)buffer;

            // 2. Separa os bytes de dados (tudo exceto os últimos 2 bytes do CRC) e calcula o CRC local
            uint16_t crcRecebido = ntohs(pacote->crc);
            uint16_t crcCalculado = calcularCRC16(buffer, sizeof(TelemetryPacket) - 2);

            // 3. Validação de Integridade (CRC)
            if (crcCalculado == crcRecebido) {
                pacotesValidos++;

                // Converte os campos de rede (Big-Endian) para o formato local
                uint16_t contador = ntohs(pacote->contador);
                float tensao = (float)ntohs(pacote->tensao) / 100.0;
                float temperatura = (float)ntohs(pacote->temperatura) / 100.0;
                int rssi = LoRa.packetRssi();
                float snr = LoRa.packetSnr();

                // Imprime em formato JSON para o script Python e exibe as estatísticas de CRC
                Serial.printf("{\"cubesat_id\": %d, \"contador\": %d, \"tensao_bateria\": %.2f, \"temperatura\": %.2f, \"rssi\": %d, \"snr\": %.1f, \"validos\": %lu, \"invalidos\": %lu}\n",
                    pacote->cubesat_id, contador, tensao, temperatura, rssi, snr, pacotesValidos, pacotesInvalidos);
            } else {
                // CRC Inválido: Pacote corrompido no ar
                pacotesInvalidos++;
                Serial.printf("[ALERTA CRC] Pacote corrompido descartado! (Recebido: 0x%04X | Calculado: 0x%04X) | Válidos: %lu | Inválidos: %lu\n",
                    crcRecebido, crcCalculado, pacotesValidos, pacotesInvalidos);
            }
        } else {
            // Tamanho de pacote inválido (lixo ou interferência)
            pacotesInvalidos++;
            Serial.printf("[ALERTA TAMANHO] Pacote com tamanho incorreto descartado (%d bytes). | Válidos: %lu | Inválidos: %lu\n",
                packetSize, pacotesValidos, pacotesInvalidos);
            
            // Esvazia o buffer da biblioteca LoRa
            while (LoRa.available()) {
                LoRa.read();
            }
        }
    }
}