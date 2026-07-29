#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>

// Pinos padrão para o rádio RFM95 no ESP32 (ajuste se a sua placa usar outros pinos)
const int ss = 5;
const int rst = 14;
const int dio0 = 26;

unsigned int packetCounter = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial);
  
  // Inicialização do barramento SPI para o LoRa
  SPI.begin(18, 19, 23, ss);
  LoRa.setPins(ss, rst, dio0);

  // Frequência LoRa (Ex: 915E6 para 915MHz ou 433E6 para 433MHz)
  if (!LoRa.begin(915E6)) {
    Serial.println("Erro ao iniciar o rádio LoRa!");
    while (1);
  }
  
  LoRa.setTxPower(20);
  Serial.println("CubeSat Simulator - Transmissor LoRa Iniciado.");
}

void loop() {
  packetCounter++; // Contador sequencial obrigatório

  // Simulação de dados variáveis da missão
  float voltage = 3.65 + (random(0, 15) / 100.0);   // Tensão entre 3.65V e 3.80V
  float current = 120.0 + random(-15, 15);         // Corrente em mA
  float temperature = 24.5 + (random(-10, 10) / 10.0); // Temperatura flutuante
  int mode = 1;                                    // 1 = Modo Normal de Operação
  int errorFlags = 0;                              // 0 = Sem erros

  // Montagem do pacote de telemetria
  String payload = "PKT:" + String(packetCounter) + 
                   ",V:" + String(voltage, 2) + 
                   ",C:" + String(current, 1) + 
                   ",T:" + String(temperature, 1) + 
                   ",M:" + String(mode) + 
                   ",ERR:" + String(errorFlags);

  // Transmissão via LoRa
  LoRa.beginPacket();
  LoRa.print(payload);
  LoRa.endPacket();

  Serial.println("Enviado: " + payload);

  delay(5000); // Envia a cada 5 segundos
}