#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>

const int ss = 5;
const int rst = 14;
const int dio0 = 26;

unsigned int packetCounter = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial);
  
  SPI.begin(18, 19, 23, ss);
  LoRa.setPins(ss, rst, dio0);

  if (!LoRa.begin(915E6)) {
    Serial.println("Erro ao iniciar o rádio LoRa!");
    while (1);
  }
  
  LoRa.enableCrc(); // Garante o CRC ativo
  Serial.println("CubeSat Simulator - Nova Telemetria Iniciada.");
}

void loop() {
  packetCounter++;

  // Dados variáveis simulados para a nova telemetria
  float voltage = 3.70 + (random(0, 20) / 100.0);       // Tensão da bateria
  float temperature = 22.0 + (random(-15, 15) / 10.0);  // Temperatura
  int modoOperacao = 1;                                // 1 = Modo Normal
  int flagsErro = 0;                                   // 0 = Sem falhas
  float altitudeSimulada = 450.5 + (packetCounter * 0.2); // Altitude orbital simulada (km)

  // Montagem do pacote expandido
  String payload = "PKT:" + String(packetCounter) + 
                   ",V:" + String(voltage, 2) + 
                   ",T:" + String(temperature, 1) + 
                   ",MOD:" + String(modoOperacao) + 
                   ",ERR:" + String(flagsErro) + 
                   ",ALT:" + String(altitudeSimulada, 1);

  LoRa.beginPacket();
  LoRa.print(payload);
  LoRa.endPacket();

  Serial.println("Enviado Nova Telemetria: " + payload);

  delay(5000);
}