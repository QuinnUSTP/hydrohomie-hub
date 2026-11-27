#include <SPI.h>
#include <RadioLib.h>
#include <U8g2lib.h>
#include "mbedtls/md.h"

#define USE_OLED 1

// ---- Settings: must match the node sketch ----
const float    LORA_FREQ_MHZ = 928.0;   // SET THIS after confirming your band
const float    LORA_BW_KHZ   = 125.0;
const uint8_t  LORA_SF       = 9;
const uint8_t  LORA_CR       = 5;
const uint8_t  LORA_SYNC     = 0x12;
const uint16_t LORA_PREAMBLE = 8;
const char*    SHARED_SECRET = "gwapokaykoomgdilimagg";
const unsigned long HEARTBEAT_MS = 5000;
// -----------------------------------------------

const int PIN_SCK = 9, PIN_MISO = 11, PIN_MOSI = 10;
const int PIN_NSS = 8, PIN_DIO1 = 14, PIN_RST = 12, PIN_BUSY = 13;
const int PIN_FEM_EN = 2;
const int PIN_VEXT = 36;
const int VEXT_ON_LEVEL = LOW;   // flip to HIGH if the OLED stays dark

SX1262 radio = new Module(PIN_NSS, PIN_DIO1, PIN_RST, PIN_BUSY);
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, 21, 18, 17);

volatile bool rxFlag = false;
bool radioOk = false;
int radioErr = 0;
unsigned long lastBeat = 0, lastDraw = 0, pktCount = 0;

struct Seen { char node[21]; long seq; bool used; };
Seen seen[8];

struct NodeInfo { char id[21]; float cm; bool noEcho; bool fl; int rssi; unsigned long last; bool used; };
NodeInfo nodes[4];

void IRAM_ATTR onRx() { rxFlag = true; }

String macOf(const String& msg) {
  unsigned char out[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)SHARED_SECRET, strlen(SHARED_SECRET));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)msg.c_str(), msg.length());
  mbedtls_md_hmac_finish(&ctx, out);
  mbedtls_md_free(&ctx);
  char hex[9];
  snprintf(hex, sizeof(hex), "%02x%02x%02x%02x", out[0], out[1], out[2], out[3]);
  return String(hex);
}

bool isNumber(const String& s) {
  bool digit = false;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c >= '0' && c <= '9') digit = true;
    else if (c != '.') return false;
  }
  return digit;
}

bool validNode(const String& s) {
  if (s.length() < 1 || s.length() > 20) return false;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (!isalnum(c) && c != '-' && c != '_') return false;
  }
  return true;
}

bool isDuplicate(const String& node, long seq) {
  for (int i = 0; i < 8; i++) {
    if (seen[i].used && node == seen[i].node) {
      if (seen[i].seq == seq) return true;
      seen[i].seq = seq;
      return false;
    }
  }
  for (int i = 0; i < 8; i++) {
    if (!seen[i].used) {
      node.toCharArray(seen[i].node, 21);
      seen[i].seq = seq;
      seen[i].used = true;
      return false;
    }
  }
  node.toCharArray(seen[0].node, 21);
  seen[0].seq = seq;
  return false;
}

void noteNode(const String& id, float cm, bool noEcho, bool fl, int rssi) {
  int slot = -1;
  for (int i = 0; i < 4; i++) if (nodes[i].used && id == nodes[i].id) { slot = i; break; }
  if (slot < 0) {
    for (int i = 0; i < 4; i++) if (!nodes[i].used) { slot = i; break; }
  }
  if (slot < 0) {
    slot = 0;
    for (int i = 1; i < 4; i++) if (nodes[i].last < nodes[slot].last) slot = i;
  }
  id.toCharArray(nodes[slot].id, 21);
  nodes[slot].cm = cm; nodes[slot].noEcho = noEcho; nodes[slot].fl = fl;
  nodes[slot].rssi = rssi; nodes[slot].last = millis(); nodes[slot].used = true;
}

void reject(const char* why) { Serial.printf("# rejected: %s\n", why); }

void processPacket(String raw, float rssi, float snr) {
  raw.trim();
  int p = raw.lastIndexOf(',');
  if (p < 0) return reject("format");
  String body = raw.substring(0, p);
  String mac = raw.substring(p + 1);
  if (!mac.equalsIgnoreCase(macOf(body))) return reject("bad mac");

  int a = body.indexOf(',');
  int b = body.indexOf(',', a + 1);
  int c = body.indexOf(',', b + 1);
  if (a < 1 || b < 0 || c < 0 || body.indexOf(',', c + 1) >= 0) return reject("fields");

  String node = body.substring(0, a);
  String cm = body.substring(a + 1, b);
  String fl = body.substring(b + 1, c);
  String sq = body.substring(c + 1);

  if (!validNode(node)) return reject("node id");
  if (fl != "0" && fl != "1") return reject("float");
  if (cm != "-" && (!isNumber(cm) || cm.toFloat() > 500.0)) return reject("cm");
  if (!isNumber(sq)) return reject("seq");
  long seq = sq.toInt();
  if (isDuplicate(node, seq)) return reject("duplicate");

  pktCount++;
  noteNode(node, cm == "-" ? 0 : cm.toFloat(), cm == "-", fl == "1", (int)rssi);
  Serial.printf("{\"node\":\"%s\",\"cm\":%s,\"float\":%s,\"seq\":%ld,\"rssi\":%.0f,\"snr\":%.1f}\n",
                node.c_str(), cm == "-" ? "null" : cm.c_str(), fl.c_str(), seq, rssi, snr);
}

void debugRx(const String& raw, float rssi) {
  Serial.printf("# rx %u bytes, rssi %.0f: ", (unsigned)raw.length(), rssi);
  for (size_t i = 0; i < raw.length() && i < 40; i++) {
    char c = raw[i];
    Serial.print((c >= 32 && c <= 126) ? c : '.');
  }
  Serial.println();
}

#if USE_OLED
void drawBars(int x, int yBottom, int rssi) {
  int lvl = rssi > -70 ? 4 : rssi > -85 ? 3 : rssi > -100 ? 2 : rssi > -115 ? 1 : 0;
  for (int i = 0; i < 4; i++) {
    int h = 2 + i * 2;
    if (i < lvl) u8g2.drawBox(x + i * 4, yBottom - h, 3, h);
    else u8g2.drawHLine(x + i * 4, yBottom - 1, 3);
  }
}

void drawScreen() {
  char buf[32];
  u8g2.clearBuffer();
  u8g2.setDrawColor(1);
  u8g2.drawBox(0, 0, 128, 12);
  u8g2.setDrawColor(0);
  u8g2.setFont(u8g2_font_helvB08_tr);
  u8g2.drawStr(3, 10, "HYDROHOMIE HUB");
  u8g2.setFont(u8g2_font_5x7_tf);
  u8g2.drawStr(radioOk ? 104 : 100, 9, radioOk ? "LIVE" : "ERROR");
  u8g2.setDrawColor(1);

  if (!radioOk) {
    u8g2.setFont(u8g2_font_6x10_tf);
    if (LORA_FREQ_MHZ <= 0.0) {
      u8g2.drawStr(4, 32, "Set LORA_FREQ_MHZ");
      u8g2.drawStr(4, 46, "then re-flash");
    } else {
      snprintf(buf, sizeof(buf), "Radio error: %d", radioErr);
      u8g2.drawStr(4, 36, buf);
    }
  } else {
    int shown = 0;
    u8g2.setFont(u8g2_font_6x10_tf);
    for (int i = 0; i < 4 && shown < 3; i++) {
      if (!nodes[i].used) continue;
      int y = 24 + shown * 12;
      unsigned long age = (millis() - nodes[i].last) / 1000;
      u8g2.drawStr(0, y, nodes[i].id);
      if (nodes[i].noEcho) snprintf(buf, sizeof(buf), "--");
      else snprintf(buf, sizeof(buf), "%.0fcm", nodes[i].cm);
      u8g2.drawStr(28, y, buf);
      if (nodes[i].fl) {
        u8g2.drawBox(60, y - 9, 31, 11);
        u8g2.setDrawColor(0);
        u8g2.drawStr(61, y, "FLOAT");
        u8g2.setDrawColor(1);
      }
      if (age < 60) snprintf(buf, sizeof(buf), "%lus", age);
      else snprintf(buf, sizeof(buf), "OFF");
      u8g2.drawStr(93, y, buf);
      drawBars(112, y, age < 60 ? nodes[i].rssi : -200);
      shown++;
    }
    if (shown == 0) {
      u8g2.drawStr(10, 38, "Waiting for nodes...");
    }
  }

  u8g2.setFont(u8g2_font_5x7_tf);
  unsigned long up = millis() / 1000;
  snprintf(buf, sizeof(buf), "RX %lu   UP %luh%02lum", pktCount, up / 3600, (up / 60) % 60);
  u8g2.drawStr(0, 63, buf);
  u8g2.sendBuffer();
}
#endif

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_FEM_EN, OUTPUT);
  digitalWrite(PIN_FEM_EN, HIGH);

#if USE_OLED
  pinMode(PIN_VEXT, OUTPUT);
  digitalWrite(PIN_VEXT, VEXT_ON_LEVEL);
  delay(100);
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_helvB14_tr);
  u8g2.drawStr(8, 30, "HYDROHOMIE");
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(34, 48, "LoRa Hub");
  u8g2.sendBuffer();
#endif
  delay(1200);

  if (LORA_FREQ_MHZ > 0.0) {
    SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_NSS);
    radioErr = radio.begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR,
                           LORA_SYNC, 10, LORA_PREAMBLE, 1.8);
    if (radioErr == RADIOLIB_ERR_NONE) {
      radio.setDio2AsRfSwitch(true);
      radio.setCRC(2);
      radio.setDio1Action(onRx);
      radioErr = radio.startReceive();
      if (radioErr == RADIOLIB_ERR_NONE) {
        radioOk = true;
        Serial.println("# hub ready");
      }
    }
    if (!radioOk) Serial.printf("# radio error: %d\n", radioErr);
  }
}

void loop() {
  if (millis() - lastBeat >= HEARTBEAT_MS) {
    lastBeat = millis();
    if (!radioOk) Serial.println("# hub not ready: set LORA_FREQ_MHZ or check radio errors");
    Serial.printf("{\"node\":\"HUB\",\"cm\":null,\"float\":0,\"uptime\":%lu}\n", millis() / 1000);
  }
  if (radioOk && rxFlag) {
    rxFlag = false;
    String s;
    int st = radio.readData(s);
    if (st == RADIOLIB_ERR_NONE) processPacket(s, radio.getRSSI(), radio.getSNR());
    else if (st == RADIOLIB_ERR_CRC_MISMATCH) Serial.println("# crc error");
    radio.startReceive();
  }
#if USE_OLED
  if (millis() - lastDraw >= 500) { lastDraw = millis(); drawScreen(); }
#endif
}