#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <lwip/def.h> // Para conversão Big-Endian (ntohs)

// =====================
// Pinagem da LION
// =====================
#define LORA_SS    5 
#define LORA_RST   16
#define LORA_DIO0  4

// SPI
#define LORA_SCK   18
#define LORA_MISO  19
#define LORA_MOSI  23

// =====================
// Configuração LoRa
// =====================
#define FREQUENCIA        915E6
#define SPREADING_FACTOR  7
#define BANDWIDTH         125E3
#define CODING_RATE       5

// =====================
// Estrutura do Protocolo (16 bytes)
// =====================
struct __attribute__((packed)) TelemetryPacket {
    uint8_t  header;
    uint8_t  versao;
    uint8_t  tipo;
    uint8_t  cubesat_id;
    uint16_t contador;
    int16_t  tensao;
    int16_t  temperatura;
    int16_t  corrente;
    uint8_t  modo_de_operacao;
    uint8_t  flag_erros;
    uint16_t crc;
};

// Contadores para métricas de confiabilidade de enlace
unsigned long pacotesValidos = 0;
unsigned long pacotesInvalidos = 0;

// Algoritmo de Cálculo do CRC-16 (CCITT)
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

void inicializarLoRa()
{
    Serial.println("Inicializando SPI...");
    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
    Serial.println("SPI OK");

    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

    Serial.println("Inicializando RFM95...");

    if (!LoRa.begin(FREQUENCIA))
    {
        Serial.println("Erro ao inicializar o RFM95.");
        while (1);
    }

    LoRa.setSpreadingFactor(SPREADING_FACTOR);
    LoRa.setSignalBandwidth(BANDWIDTH);
    LoRa.setCodingRate4(CODING_RATE);

    Serial.println("RFM95 inicializado com sucesso.");
    Serial.println();
}

void setup()
{
    Serial.begin(115200);
    while (!Serial);

    Serial.println("==============================");
    Serial.println(" Receptor LoRa - LION ");
    Serial.println("==============================");

    inicializarLoRa();

    Serial.println("Aguardando pacotes...");
    Serial.println();
}

void loop()
{
    int tamanhoPacote = LoRa.parsePacket();

    if (tamanhoPacote > 0)
    {
        // 1. Validação estrita do tamanho do pacote estruturado
        if (tamanhoPacote == sizeof(TelemetryPacket))
        {
            TelemetryPacket pacote;
            LoRa.readBytes((uint8_t*)&pacote, sizeof(TelemetryPacket));

            // 2. Validação do CRC
            size_t tamanho_payload = sizeof(TelemetryPacket) - sizeof(pacote.crc);
            uint16_t crc_calculado = calcular_crc16((uint8_t*)&pacote, tamanho_payload);
            uint16_t crc_recebido = ntohs(pacote.crc);

            if (crc_calculado == crc_recebido) {
                pacotesValidos++;

                // Extração e Conversão de Endianness e Escalas corretas
                uint16_t contador = ntohs(pacote.contador);
                float tensao = (float)ntohs(pacote.tensao) / 100.0f;
                float temperatura = (float)ntohs(pacote.temperatura) / 100.0f;
                float corrente = (float)ntohs(pacote.corrente) / 100.0f; // Assumindo ajuste de escala por 100 igual à tensão/temperatura
                uint8_t modo = pacote.modo_de_operacao;
                uint8_t flags = pacote.flag_erros;
                
                // Métricas do Rádio LoRa (Enlace)
                int rssi = LoRa.packetRssi();
                float snr = LoRa.packetSnr();

                // Exibição amigável formatada no Monitor Serial
                Serial.println("========================================");
                Serial.printf("Pacote #%d Recebido (Válidos: %lu | Inválidos: %lu)\n", contador, pacotesValidos, pacotesInvalidos);
                Serial.printf("CubeSat ID   : %d\n", pacote.cubesat_id);
                Serial.printf("Tensão       : %.2f V\n", tensao);
                Serial.printf("Corrente     : %.2f A (ou mA conforme escala)\n", corrente);
                Serial.printf("Temperatura  : %.2f °C\n", temperatura);
                Serial.printf("Modo         : %d\n", modo);
                Serial.printf("Flags de Erro: 0x%02X\n", flags);
                Serial.printf("RSSI         : %d dBm\n", rssi);
                Serial.printf("SNR          : %.1f dB\n", snr);
                Serial.println("Status       : Aprovado ✅");
                Serial.println("========================================");

                // Saída estruturada estritamente em JSON para a ponte serial (`serial_bridge.py`)
                Serial.printf("{\"cubesat_id\": %d, \"contador\": %d, \"tensao_bateria\": %.2f, \"corrente\": %.2f, \"temperatura\": %.2f, \"modo\": %d, \"flags\": %d, \"rssi\": %d, \"snr\": %.1f, \"validos\": %lu, \"invalidos\": %lu}\n",
                    pacote.cubesat_id, contador, tensao, corrente, temperatura, modo, flags, rssi, snr, pacotesValidos, pacotesInvalidos);

            } else {
                pacotesInvalidos++;
                Serial.println("========================================");
                Serial.println("ALERTA: Pacote corrompido (CRC Inválido). Descartado! ❌");
                Serial.printf("Recebido: 0x%04X | Calculado: 0x%04X\n", crc_recebido, crc_calculado);
                Serial.println("========================================");
            }
        } 
        else 
        {
            pacotesInvalidos++;
            Serial.printf("ALERTA: Pacote com tamanho incorreto descartado (%d bytes).\n", tamanhoPacote);
            // Esvazia o buffer do rádio
            while (LoRa.available()) {
                LoRa.read();
            }
        }
    }
}