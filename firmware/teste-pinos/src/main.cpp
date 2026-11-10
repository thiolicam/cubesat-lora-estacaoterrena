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
  // SPI alternativo do ESP32 (HSPI), que usa o GPIO12; a reinicializacao fica no 2 para nao repetir um pino
  {"SPI alternativo (HSPI)", 14, 12, 13, 15, 2},
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

// ---------- Etapa 2: com o SPI confirmado, descobre RST e DIO0 ----------
#define REG_OP_MODE      0x01
#define REG_IRQ_FLAGS    0x12
#define REG_DIO_MAPPING1 0x40
#define MODO_LORA_SLEEP  0x80
#define MODO_LORA_STANDBY 0x81
#define MODO_LORA_CAD    0x87  // so escuta o canal; nao transmite
#define DIO0_CAD_DONE    0x80

const int CANDIDATOS_RST[] = {14, 16};
// GPIOs que podem estar ligados ao DIO0 (sem os do SPI, da flash e da serial)
const int CANDIDATOS_DIO[] = {2, 4, 13, 14, 15, 16, 17, 21, 22, 25, 26, 27, 32, 33, 34, 35, 36, 39};

void escrever(const Pinagem &p, uint8_t registrador, uint8_t valor) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(p.ss, LOW);
  SPI.transfer(registrador | 0x80);  // bit 7 em um = escrita
  SPI.transfer(valor);
  digitalWrite(p.ss, HIGH);
  SPI.endTransaction();
}

uint8_t ler(const Pinagem &p, uint8_t registrador) {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(p.ss, LOW);
  SPI.transfer(registrador & 0x7F);
  uint8_t valor = SPI.transfer(0x00);
  digitalWrite(p.ss, HIGH);
  SPI.endTransaction();
  return valor;
}

void identificarRstEDio0(const Pinagem &p) {
  pinMode(p.ss, OUTPUT);
  digitalWrite(p.ss, HIGH);
  SPI.begin(p.sck, p.miso, p.mosi, p.ss);

  // RST: com o pino certo em nivel baixo, o radio fica em reset e para de responder
  for (int rst : CANDIDATOS_RST) {
    pinMode(rst, OUTPUT);
    digitalWrite(rst, LOW);
    delay(5);
    uint8_t emReset = ler(p, REG_VERSAO);
    pinMode(rst, INPUT);  // solta o pino; o modulo volta sozinho
    delay(10);
    Serial.printf("RST candidato GPIO%d: %s (versao 0x%02X com o pino em nivel baixo)\n", rst,
                  emReset == VERSAO_RFM95 ? "nao e o reset" : "[OK] e o reset", emReset);
  }

  // DIO0: pede uma deteccao de atividade no canal e ve qual GPIO sobe quando ela termina
  for (int pino : CANDIDATOS_DIO) pinMode(pino, INPUT);
  escrever(p, REG_OP_MODE, MODO_LORA_SLEEP);
  escrever(p, REG_OP_MODE, MODO_LORA_STANDBY);
  escrever(p, REG_DIO_MAPPING1, DIO0_CAD_DONE);
  escrever(p, REG_IRQ_FLAGS, 0xFF);
  delay(5);
  bool antes[sizeof(CANDIDATOS_DIO) / sizeof(int)];
  for (size_t i = 0; i < sizeof(CANDIDATOS_DIO) / sizeof(int); i++) antes[i] = digitalRead(CANDIDATOS_DIO[i]);
  escrever(p, REG_OP_MODE, MODO_LORA_CAD);
  delay(20);
  uint8_t flags = ler(p, REG_IRQ_FLAGS);
  Serial.printf("Fim da deteccao de canal (CadDone): %s\n", (flags & 0x04) ? "sim" : "nao");
  bool achou = false;
  for (size_t i = 0; i < sizeof(CANDIDATOS_DIO) / sizeof(int); i++) {
    bool depois = digitalRead(CANDIDATOS_DIO[i]);
    if (!antes[i] && depois) {
      Serial.printf("[OK] DIO0 subiu no GPIO%d\n", CANDIDATOS_DIO[i]);
      achou = true;
    }
  }
  if (!achou) Serial.println("[FALHOU] Nenhum GPIO candidato subiu com o DIO0");
  escrever(p, REG_IRQ_FLAGS, 0xFF);
  escrever(p, REG_OP_MODE, MODO_LORA_SLEEP);
  SPI.end();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
}

void loop() {
  Serial.println("\n=== Teste de pinagem do RFM95 ===");
  const Pinagem *encontrada = nullptr;
  for (const Pinagem &p : PINAGENS) {
    uint8_t versao = lerVersao(p);
    Serial.printf("%s  SCK=%d MISO=%d MOSI=%d SS=%d RST=%d -> versao 0x%02X  %s\n",
                  versao == VERSAO_RFM95 ? "[OK]    " : "[FALHOU]",
                  p.sck, p.miso, p.mosi, p.ss, p.rst, versao, p.origem);
    if (versao == VERSAO_RFM95 && encontrada == nullptr) encontrada = &p;
  }
  if (encontrada != nullptr) {
    Serial.println("--- RST e DIO0 ---");
    identificarRstEDio0(*encontrada);
  }
  delay(5000);
}
