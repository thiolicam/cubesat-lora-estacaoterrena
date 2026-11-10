#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <lwip/def.h> // Para conversão Big-Endian (ntohs)

// =====================
// Pinagem da LION, confirmada na placa em 10/11/2026 com firmware/teste-pinos
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
// Pode ser definido na gravacao, para diversidade de frequencia (veja o README)
#ifndef FREQUENCIA
#define FREQUENCIA        915E6
#endif
#define SPREADING_FACTOR  7
#define BANDWIDTH         125E3
#define CODING_RATE       5
#define POTENCIA_DBM      17

// Identifica este receptor quando houver mais de uma estacao (diversidade, S7.1)
#ifndef RECEPTOR_ID
#define RECEPTOR_ID       1
#endif

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

// Comando enviado ao CubeSat (11 bytes)
struct __attribute__((packed)) CommandPacket {
    uint8_t  header;
    uint8_t  versao;
    uint8_t  tipo;
    uint8_t  cubesat_id;
    uint16_t comando_id;
    uint8_t  codigo;
    uint16_t parametro;
    uint16_t crc;
};

// Confirmação recebida do CubeSat (10 bytes)
struct __attribute__((packed)) AckPacket {
    uint8_t  header;
    uint8_t  versao;
    uint8_t  tipo;
    uint8_t  cubesat_id;
    uint16_t comando_id;
    uint8_t  codigo;
    uint8_t  status;
    uint16_t crc;
};

#define HEADER        0xAA
#define VERSAO        0x01
#define TIPO_COMANDO  0x02
#define TIPO_ACK      0x03

// Contadores para métricas de confiabilidade de enlace
unsigned long pacotesValidos = 0;
unsigned long pacotesInvalidos = 0;  // pacotes do nosso formato com CRC errado
// Pacotes de tamanho que nao existe no protocolo: vem de outros aparelhos LoRa na mesma frequencia
unsigned long pacotesEstranhos = 0;

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

// Escreve os bytes em hexadecimal; destino precisa de 2 * tamanho + 1 posicoes
void paraHex(const uint8_t *bytes, size_t tamanho, char *destino) {
    for (size_t i = 0; i < tamanho; i++) {
        sprintf(&destino[2 * i], "%02X", bytes[i]);
    }
}

void transmitirComando(uint16_t comandoId, uint8_t cubesatId, uint8_t codigo, uint16_t parametro) {
    CommandPacket comando;
    comando.header = HEADER;
    comando.versao = VERSAO;
    comando.tipo = TIPO_COMANDO;
    comando.cubesat_id = cubesatId;
    comando.comando_id = htons(comandoId);
    comando.codigo = codigo;
    comando.parametro = htons(parametro);
    comando.crc = htons(calcular_crc16((const uint8_t*)&comando, sizeof(comando) - sizeof(comando.crc)));

    LoRa.beginPacket();
    LoRa.write((const uint8_t*)&comando, sizeof(comando));
    LoRa.endPacket();
    Serial.printf("Comando %u transmitido: codigo %u, parametro %u\n", comandoId, codigo, parametro);
}

// A ponte serial envia uma linha por comando: CMD <id> <cubesat> <codigo> <parametro>
void interpretarLinhaSerial(const char *linha) {
    unsigned int comandoId, cubesatId, codigo, parametro;
    if (sscanf(linha, "CMD %u %u %u %u", &comandoId, &cubesatId, &codigo, &parametro) == 4
        && comandoId <= 0xFFFF && cubesatId <= 0xFF && codigo <= 0xFF && parametro <= 0xFFFF) {
        transmitirComando(comandoId, cubesatId, codigo, parametro);
    } else {
        Serial.printf("Linha serial ignorada: %s\n", linha);
    }
}

void lerSerial() {
    static char linha[48];
    static size_t tamanho = 0;
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            linha[tamanho] = '\0';
            tamanho = 0;
            interpretarLinhaSerial(linha);
        } else if (c != '\r' && tamanho < sizeof(linha) - 1) {
            linha[tamanho++] = c;
        }
    }
}

void receberAck() {
    AckPacket ack;
    LoRa.readBytes((uint8_t*)&ack, sizeof(ack));

    uint16_t crcCalculado = calcular_crc16((const uint8_t*)&ack, sizeof(ack) - sizeof(ack.crc));
    if (crcCalculado != ntohs(ack.crc) || ack.tipo != TIPO_ACK) {
        pacotesInvalidos++;
        Serial.println("ALERTA: ACK corrompido. Descartado! ❌");
        return;
    }

    char bruto[2 * sizeof(AckPacket) + 1];
    paraHex((const uint8_t*)&ack, sizeof(ack), bruto);
    Serial.printf("{\"cubesat_id\": %d, \"tipo\": %d, \"comando_id\": %u, \"codigo\": %d, \"status\": %d, \"rssi\": %d, \"snr\": %.1f, \"frequencia_mhz\": %.1f, \"receptor_id\": %d, \"raw\": \"%s\"}\n",
        ack.cubesat_id, ack.tipo, ntohs(ack.comando_id), ack.codigo, ack.status,
        LoRa.packetRssi(), LoRa.packetSnr(), FREQUENCIA / 1E6, RECEPTOR_ID, bruto);
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
    LoRa.setTxPower(POTENCIA_DBM);

    Serial.println("RFM95 inicializado com sucesso.");
    Serial.printf("Frequencia: %.1f MHz | SF: %d | BW: %.0f kHz | CR: 4/%d | Potencia: %d dBm\n",
                  FREQUENCIA / 1E6, SPREADING_FACTOR, BANDWIDTH / 1E3, CODING_RATE, POTENCIA_DBM);
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
    lerSerial();

    int tamanhoPacote = LoRa.parsePacket();

    if (tamanhoPacote > 0)
    {
        // 1. Validação estrita do tamanho do pacote estruturado
        if (tamanhoPacote == sizeof(AckPacket))
        {
            receberAck();
        }
        else if (tamanhoPacote == sizeof(TelemetryPacket))
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
                float tensao = (float)(int16_t)ntohs(pacote.tensao) / 100.0f;
                float temperatura = (float)(int16_t)ntohs(pacote.temperatura) / 100.0f;
                float corrente = (float)(int16_t)ntohs(pacote.corrente) / 100.0f; // Assumindo ajuste de escala por 100 igual à tensão/temperatura
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
                char bruto[2 * sizeof(TelemetryPacket) + 1];
                paraHex((const uint8_t*)&pacote, sizeof(pacote), bruto);
                Serial.printf("{\"cubesat_id\": %d, \"tipo\": %d, \"contador\": %d, \"tensao_bateria\": %.2f, \"corrente\": %.2f, \"temperatura\": %.2f, \"modo\": %d, \"flags\": %d, \"rssi\": %d, \"snr\": %.1f, \"validos\": %lu, \"invalidos\": %lu, \"estranhos\": %lu, \"frequencia_mhz\": %.1f, \"receptor_id\": %d, \"raw\": \"%s\"}\n",
                    pacote.cubesat_id, pacote.tipo, contador, tensao, corrente, temperatura, modo, flags, rssi, snr, pacotesValidos, pacotesInvalidos, pacotesEstranhos, FREQUENCIA / 1E6, RECEPTOR_ID, bruto);

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
            pacotesEstranhos++;
            Serial.printf("Pacote de outro aparelho ignorado (%d bytes; o protocolo usa 16 ou 10).\n", tamanhoPacote);
            // Esvazia o buffer do rádio
            while (LoRa.available()) {
                LoRa.read();
            }
        }
    }
}