// Diagnostico: descobre qual pinagem conversa com o RFM95 de uma placa LION.
// Le o registrador de versao do chip, que no RFM95 sempre vale 0x12. Nao transmite nada.
#include <Arduino.h>
#include <SPI.h>

#define REG_VERSAO      0x42
#define VERSAO_RFM95    0x12

struct Pinagem {
  const char *origem;
  int sck, miso, mosi, ss, rst;
};

// As pinagens encontradas no historico do repositorio
const Pinagem PINAGENS[] = {
  {"ground-station atual ('Pinagem da LION')", 18, 19, 23, 5, 16},
  {"cubesat-simulator atual / 1o commit ('oficiais LION')", 5, 19, 27, 18, 14},
  {"cubesat-simulator de 29/07", 18, 19, 23, 5, 14},
};

uint8_t lerVersao(const Pinagem &p) {
  pinMode(p.ss, OUTPUT);
  digitalWrite(p.ss, HIGH);

  // Reinicia o radio antes de consultar
  pinMode(p.rst, OUTPUT);
  digitalWrite(p.rst, LOW);
  delay(10);
  digitalWrite(p.rst, HIGH);
  delay(10);

  SPI.begin(p.sck, p.miso, p.mosi, p.ss);
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(p.ss, LOW);
  SPI.transfer(REG_VERSAO & 0x7F);  // bit 7 em zero = leitura
  uint8_t versao = SPI.transfer(0x00);
  digitalWrite(p.ss, HIGH);
  SPI.endTransaction();
  SPI.end();

  // Devolve os pinos ao estado neutro antes da proxima tentativa
  pinMode(p.ss, INPUT);
  pinMode(p.rst, INPUT);
  return versao;
}

void setup() {
  Serial.begin(115200);
  delay(1500);
}

void loop() {
  Serial.println("\n=== Teste de pinagem do RFM95 ===");
  for (const Pinagem &p : PINAGENS) {
    uint8_t versao = lerVersao(p);
    Serial.printf("%s  SCK=%d MISO=%d MOSI=%d SS=%d RST=%d -> versao 0x%02X  %s\n",
                  versao == VERSAO_RFM95 ? "[OK]    " : "[FALHOU]",
                  p.sck, p.miso, p.mosi, p.ss, p.rst, versao, p.origem);
  }
  delay(5000);
}
