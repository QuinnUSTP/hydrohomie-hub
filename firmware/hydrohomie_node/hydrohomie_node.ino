// HydroHomie node firmware
// Board: Heltec WiFi LoRa 32 V4 (ESP32-S3R2)
// Output: one JSON line per cycle at 115200 baud, for example
// {"node":"Z1","cm":42.5,"float":0}

// ---------- Settings you may change ----------
const char* NODE_ID = "Z1";

const int TRIG_PIN = 4;    // HC-SR04 TRIG
const int ECHO_PIN = 6;    // HC-SR04 ECHO (through a 1k + 2k voltage divider)
const int FLOAT_PIN = 33;  // float switch, other wire to GND
const int LED_PIN = 35;    // onboard LED on the V4 (S3R2). Polarity not verified.

// Float switch reads LOW when closed to GND. Set to HIGH if your switch
// opens when the water rises.
const int FLOAT_ACTIVE_LEVEL = LOW;

// Local indicator only. Django (A6) makes the real alert decision.
// Keep this value equal to your threshold in the admin.
const float ALERT_CM = 30.0;

const unsigned long CYCLE_MS = 2000;
const int SAMPLES = 5;
const unsigned long ECHO_TIMEOUT_US = 30000;  // about 5 m
const float MIN_VALID_CM = 2.0;
const float MAX_VALID_CM = 400.0;
// ---------------------------------------------

// Returns distance in cm, or -1 if there was no valid echo.
float readOnce() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (duration == 0) {
    return -1;
  }
  float cm = duration * 0.0343f / 2.0f;
  if (cm < MIN_VALID_CM || cm > MAX_VALID_CM) {
    return -1;
  }
  return cm;
}

// Median of several readings to reduce noise. Returns -1 if none are valid.
float readDistanceCm() {
  float valid[SAMPLES];
  int count = 0;

  for (int i = 0; i < SAMPLES; i++) {
    float cm = readOnce();
    if (cm > 0) {
      valid[count++] = cm;
    }
    delay(60);
  }

  if (count == 0) {
    return -1;
  }

  // Insertion sort, then take the middle value.
  for (int i = 1; i < count; i++) {
    float key = valid[i];
    int j = i - 1;
    while (j >= 0 && valid[j] > key) {
      valid[j + 1] = valid[j];
      j--;
    }
    valid[j + 1] = key;
  }
  return valid[count / 2];
}

// Majority vote of 5 reads, so wave splashes do not flip the result.
bool readFloatTriggered() {
  int active = 0;
  for (int i = 0; i < 5; i++) {
    if (digitalRead(FLOAT_PIN) == FLOAT_ACTIVE_LEVEL) {
      active++;
    }
    delay(10);
  }
  return active >= 3;
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(FLOAT_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  unsigned long start = millis();

  float cm = readDistanceCm();
  bool floatHigh = readFloatTriggered();

  bool ultrasonicHigh = (cm > 0) && (cm <= ALERT_CM);
  bool bothAgree = ultrasonicHigh && floatHigh;
  digitalWrite(LED_PIN, bothAgree ? HIGH : LOW);

  if (cm > 0) {
    Serial.printf("{\"node\":\"%s\",\"cm\":%.1f,\"float\":%d}\n",
                  NODE_ID, cm, floatHigh ? 1 : 0);
  } else {
    Serial.printf("{\"node\":\"%s\",\"cm\":null,\"float\":%d}\n",
                  NODE_ID, floatHigh ? 1 : 0);
  }

  unsigned long elapsed = millis() - start;
  if (elapsed < CYCLE_MS) {
    delay(CYCLE_MS - elapsed);
  }
}