#include <Arduino.h>
#include <HardwareSerial.h>
#include <Preferences.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <driver/uart.h>

namespace Pins {
constexpr int I2C_SDA = 4;
constexpr int I2C_SCL = 5;

constexpr int RADIO_RX = 16;
constexpr int RADIO_TX = 17;
constexpr int CIV_TX = 13;
constexpr int CIV_RX = 14;

constexpr int MTR_IN1 = 25;
constexpr int MTR_IN2 = 26;
constexpr int MTR_ISENSE = 27;

constexpr int SWR_FWD = 34;
constexpr int SWR_REV = 35;
constexpr int ANT_SENSE_A = 36;
constexpr int ANT_SENSE_B = 39;

constexpr int BTN_TUNE = 32;
constexpr int BTN_PARK = 33;
constexpr int TUNE_UP = 22;
constexpr int TUNE_DOWN = 23;
}  // namespace Pins

namespace Cfg {
constexpr uint32_t UI_MS = 33;
constexpr uint32_t MEAS_MS = 15;
constexpr uint32_t CTRL_MS = 8;
constexpr uint32_t RADIO_POLL_MS = 220;
constexpr uint32_t FLASH_MSG_MS = 220;
constexpr uint16_t POST_STEP_MS = 450;
constexpr uint32_t UI_CHORD_HOLD_MS = 900;

constexpr uint8_t ADC_SAMPLES = 40;
constexpr float NO_RF_FWD_V = 0.05f;

constexpr uint8_t PWM_BITS = 10;
constexpr uint16_t PWM_MAX = (1u << PWM_BITS) - 1u;
constexpr uint32_t PWM_FREQ_HZ = 20000;
constexpr uint32_t SOFTSTART_MS = 140;

constexpr uint16_t DUTY_JOG = 560;
constexpr uint16_t DUTY_COARSE = 680;
constexpr uint16_t DUTY_FINE = 300;
constexpr uint16_t DUTY_PARK = 520;

constexpr float SWR_TARGET_DEFAULT = 1.30f;
constexpr float STALL_A_DEFAULT = 1.8f;
constexpr uint32_t STALL_DEBOUNCE_MS = 150;

constexpr uint32_t BTN_DEBOUNCE_MS = 20;
constexpr uint32_t TUNE_TIMEOUT_MS = 30000;
constexpr uint32_t RF_WAIT_TIMEOUT_MS = 8000;
constexpr uint32_t SAMPLE_STEP_MS = 120;
}  // namespace Cfg

enum class MotorDir : uint8_t { COAST, UP, DOWN, BRAKE };
enum class RadioBrand : uint8_t { NONE, ICOM, KENWOOD, YAESU };
enum class RadioProto : uint8_t { NONE, CIV, CAT_ASCII, YAESU_OLD_BIN };
enum class AppState : uint8_t { IDLE, TUNING, PARKING };
enum class TunePhase : uint8_t { PREP, WAIT_RF, COARSE, RETURN_BEST, CLEANUP, DONE, FAIL };
enum class DisplayPage : uint8_t { MAIN, DIAG1, DIAG2 };

struct PostResult {
  const char* title = "";
  String detail;
  bool ok = false;
};

struct FeedbackData {
  bool aLevel = true;
  bool bLevel = false;
  bool pulseSeen = false;
  bool homed = false;
  int32_t positionCounts = 0;
  uint32_t lastPulseMs = 0;
};

struct RadioConfig {
  RadioBrand brand = RadioBrand::NONE;
  RadioProto proto = RadioProto::NONE;
  uint32_t baud = 0;
  uint8_t civAddr = 0;
  bool detected = false;
};

struct CalData {
  float fwdOffsetV = 0.01f;
  float revOffsetV = 0.01f;
  float linearGain = 1.0f;
  float squareGain = 1.0f;
  float kneeV = 0.18f;
  float swrTarget = Cfg::SWR_TARGET_DEFAULT;
  float stallA = Cfg::STALL_A_DEFAULT;
};

struct MeasureData {
  float vfwd = 0.0f;
  float vrev = 0.0f;
  float pfwd = 0.0f;
  float prev = 0.0f;
  float swr = 99.0f;
  float motorCurrentA = 0.0f;
  bool carrierPresent = false;
};

class DebouncedInput {
 public:
  void begin(uint8_t pin, bool activeLow, bool usePullup) {
    pin_ = pin;
    activeLow_ = activeLow;
    pinMode(pin_, usePullup ? INPUT_PULLUP : INPUT);
    stable_ = readRaw();
    lastRaw_ = stable_;
  }

  void update(uint32_t nowMs) {
    bool raw = readRaw();
    if (raw != lastRaw_) {
      lastRaw_ = raw;
      changedMs_ = nowMs;
    }
    if ((nowMs - changedMs_) >= Cfg::BTN_DEBOUNCE_MS && stable_ != raw) {
      stable_ = raw;
      if (stable_) {
        pressedEdge_ = true;
      }
    }
  }

  bool isPressed() const { return stable_; }

  bool takePressedEdge() {
    bool e = pressedEdge_;
    pressedEdge_ = false;
    return e;
  }

 private:
  bool readRaw() const {
    bool level = digitalRead(pin_);
    return activeLow_ ? !level : level;
  }

  uint8_t pin_ = 0;
  bool activeLow_ = true;
  bool stable_ = false;
  bool lastRaw_ = false;
  bool pressedEdge_ = false;
  uint32_t changedMs_ = 0;
};

class MotorController {
 public:
  void begin() {
    pinMode(Pins::MTR_IN1, OUTPUT);
    pinMode(Pins::MTR_IN2, OUTPUT);
    ledcSetup(kChan1, Cfg::PWM_FREQ_HZ, Cfg::PWM_BITS);
    ledcSetup(kChan2, Cfg::PWM_FREQ_HZ, Cfg::PWM_BITS);
    ledcAttachPin(Pins::MTR_IN1, kChan1);
    ledcAttachPin(Pins::MTR_IN2, kChan2);
    stopCoast();
  }

  void command(MotorDir dir, uint16_t duty, uint32_t nowMs) {
    if (dir != dir_) {
      dir_ = dir;
      dirChangeMs_ = nowMs;
    }
    targetDuty_ = constrain(duty, 0u, Cfg::PWM_MAX);
    apply(nowMs);
  }

  void update(uint32_t nowMs, float motorA, float stallA) {
    apply(nowMs);
    if ((dir_ == MotorDir::UP || dir_ == MotorDir::DOWN) && targetDuty_ > 0) {
      if (motorA > stallA) {
        if (!stallArmed_) {
          stallArmed_ = true;
          stallStartMs_ = nowMs;
        } else if ((nowMs - stallStartMs_) >= Cfg::STALL_DEBOUNCE_MS) {
          stopBrake();
          stallLatched_ = true;
        }
      } else {
        stallArmed_ = false;
      }
    } else {
      stallArmed_ = false;
    }
  }

  bool takeStallLatched() {
    bool v = stallLatched_;
    stallLatched_ = false;
    return v;
  }

  MotorDir dir() const { return dir_; }

  void stopBrake() {
    dir_ = MotorDir::BRAKE;
    targetDuty_ = 0;
    currentDuty_ = 0;
    digitalWrite(Pins::MTR_IN1, HIGH);
    digitalWrite(Pins::MTR_IN2, HIGH);
  }

  void stopCoast() {
    dir_ = MotorDir::COAST;
    targetDuty_ = 0;
    currentDuty_ = 0;
    ledcWrite(kChan1, 0);
    ledcWrite(kChan2, 0);
    digitalWrite(Pins::MTR_IN1, LOW);
    digitalWrite(Pins::MTR_IN2, LOW);
  }

 private:
  void apply(uint32_t nowMs) {
    if (dir_ == MotorDir::BRAKE) {
      ledcWrite(kChan1, 0);
      ledcWrite(kChan2, 0);
      digitalWrite(Pins::MTR_IN1, HIGH);
      digitalWrite(Pins::MTR_IN2, HIGH);
      return;
    }
    if (dir_ == MotorDir::COAST) {
      ledcWrite(kChan1, 0);
      ledcWrite(kChan2, 0);
      digitalWrite(Pins::MTR_IN1, LOW);
      digitalWrite(Pins::MTR_IN2, LOW);
      return;
    }

    float ramp = min(1.0f, static_cast<float>(nowMs - dirChangeMs_) / static_cast<float>(Cfg::SOFTSTART_MS));
    currentDuty_ = static_cast<uint16_t>(targetDuty_ * ramp);
    if (dir_ == MotorDir::UP) {
      ledcWrite(kChan1, currentDuty_);
      ledcWrite(kChan2, 0);
    } else {
      ledcWrite(kChan1, 0);
      ledcWrite(kChan2, currentDuty_);
    }
  }

  static constexpr uint8_t kChan1 = 0;
  static constexpr uint8_t kChan2 = 1;

  MotorDir dir_ = MotorDir::COAST;
  uint16_t targetDuty_ = 0;
  uint16_t currentDuty_ = 0;
  uint32_t dirChangeMs_ = 0;

  bool stallArmed_ = false;
  uint32_t stallStartMs_ = 0;
  bool stallLatched_ = false;
};

class AntennaFeedback {
 public:
  void begin() {
    pinMode(Pins::ANT_SENSE_A, INPUT);
    pinMode(Pins::ANT_SENSE_B, INPUT);
    aStable_ = digitalRead(Pins::ANT_SENSE_A);
    bStable_ = digitalRead(Pins::ANT_SENSE_B);
    lastRawA_ = aStable_;
    lastRawB_ = bStable_;
  }

  void update(uint32_t nowMs, MotorDir dir) {
    bool rawA = digitalRead(Pins::ANT_SENSE_A);
    bool rawB = digitalRead(Pins::ANT_SENSE_B);

    if (rawA != lastRawA_) {
      lastRawA_ = rawA;
      lastChangeA_ = nowMs;
    }
    if (rawB != lastRawB_) {
      lastRawB_ = rawB;
      lastChangeB_ = nowMs;
    }

    if ((nowMs - lastChangeA_) >= kDebounceMs && aStable_ != rawA) {
      bool prev = aStable_;
      aStable_ = rawA;
      if (prev && !aStable_ && (dir == MotorDir::UP || dir == MotorDir::DOWN) &&
          (nowMs - lastPulseMs_) >= kMinPulseGapMs) {
        data_.pulseSeen = true;
        data_.lastPulseMs = nowMs;
        lastPulseMs_ = nowMs;
        data_.positionCounts += (dir == MotorDir::UP) ? 1 : -1;
      }
    }

    if ((nowMs - lastChangeB_) >= kDebounceMs && bStable_ != rawB) {
      bStable_ = rawB;
    }

    data_.aLevel = aStable_;
    data_.bLevel = bStable_;
  }

  void markParkedHome() {
    data_.positionCounts = 0;
    data_.homed = true;
  }

  void clearHome() { data_.homed = false; }

  const FeedbackData& data() const { return data_; }

 private:
  static constexpr uint32_t kDebounceMs = 3;
  static constexpr uint32_t kMinPulseGapMs = 5;

  FeedbackData data_{};
  bool aStable_ = true;
  bool bStable_ = false;
  bool lastRawA_ = true;
  bool lastRawB_ = false;
  uint32_t lastChangeA_ = 0;
  uint32_t lastChangeB_ = 0;
  uint32_t lastPulseMs_ = 0;
};

class RadioManager {
 public:
  void begin() {
    Serial1.begin(19200, SERIAL_8N1, Pins::CIV_RX, Pins::CIV_TX);
    uart_set_line_inverse(UART_NUM_1, UART_SIGNAL_RXD_INV | UART_SIGNAL_TXD_INV);
    Serial2.begin(9600, SERIAL_8N1, Pins::RADIO_RX, Pins::RADIO_TX);
  }

  void applyConfig(const RadioConfig& cfg) {
    cfg_ = cfg;
    if (cfg_.proto == RadioProto::CIV && cfg_.baud > 0) {
      Serial1.begin(cfg_.baud, SERIAL_8N1, Pins::CIV_RX, Pins::CIV_TX);
      uart_set_line_inverse(UART_NUM_1, UART_SIGNAL_RXD_INV | UART_SIGNAL_TXD_INV);
    }
    if ((cfg_.proto == RadioProto::CAT_ASCII || cfg_.proto == RadioProto::YAESU_OLD_BIN) && cfg_.baud > 0) {
      Serial2.begin(cfg_.baud, SERIAL_8N1, Pins::RADIO_RX, Pins::RADIO_TX);
    }
  }

  RadioConfig detect() {
    RadioConfig out{};

    const uint32_t civBauds[] = {19200, 9600, 4800};
    for (uint32_t b : civBauds) {
      Serial1.begin(b, SERIAL_8N1, Pins::CIV_RX, Pins::CIV_TX);
      uart_set_line_inverse(UART_NUM_1, UART_SIGNAL_RXD_INV | UART_SIGNAL_TXD_INV);
      if (probeCiv(out)) {
        out.detected = true;
        out.brand = RadioBrand::ICOM;
        out.proto = RadioProto::CIV;
        out.baud = b;
        cfg_ = out;
        return out;
      }
    }

    const uint32_t catBauds[] = {9600, 4800, 38400, 57600, 115200};
    for (uint32_t b : catBauds) {
      Serial2.begin(b, SERIAL_8N1, Pins::RADIO_RX, Pins::RADIO_TX);
      if (probeKenwood()) {
        out.detected = true;
        out.brand = RadioBrand::KENWOOD;
        out.proto = RadioProto::CAT_ASCII;
        out.baud = b;
        cfg_ = out;
        return out;
      }
      if (probeYaesuAscii()) {
        out.detected = true;
        out.brand = RadioBrand::YAESU;
        out.proto = RadioProto::CAT_ASCII;
        out.baud = b;
        cfg_ = out;
        return out;
      }
    }

    out.detected = false;
    out.brand = RadioBrand::NONE;
    out.proto = RadioProto::NONE;
    out.baud = 0;
    cfg_ = out;
    return out;
  }

  bool readFrequencyHz(uint64_t& outHz) {
    if (!cfg_.detected) return false;
    if (cfg_.proto == RadioProto::CIV) return readCivFrequency(outHz);
    if (cfg_.proto == RadioProto::CAT_ASCII) return readAsciiFrequency(outHz);
    return false;
  }

  bool enterLowPowerTune() {
    if (!cfg_.detected) return false;
    if (cfg_.proto == RadioProto::CAT_ASCII) {
      Serial2.print("PC005;");
      String rsp = readAsciiReply(Serial2, 120);
      (void)rsp;
      return true;
    }
    if (cfg_.proto == RadioProto::CIV) {
      uint8_t addr = (cfg_.civAddr == 0) ? 0x00 : cfg_.civAddr;
      // CI-V power set command (scaled) and PTT handled separately.
      uint8_t cmd[] = {0xFE, 0xFE, addr, 0xE0, 0x14, 0x0A, 0x01, 0x00, 0xFD};
      Serial1.write(cmd, sizeof(cmd));
      return true;
    }
    return false;
  }

  bool keyCarrier(bool on) {
    if (!cfg_.detected) return false;
    if (cfg_.proto == RadioProto::CAT_ASCII) {
      Serial2.print(on ? "TX;" : "RX;");
      return true;
    }
    if (cfg_.proto == RadioProto::CIV) {
      uint8_t addr = (cfg_.civAddr == 0) ? 0x00 : cfg_.civAddr;
      uint8_t cmd[] = {0xFE, 0xFE, addr, 0xE0, 0x1C, 0x00, static_cast<uint8_t>(on ? 0x01 : 0x00), 0xFD};
      Serial1.write(cmd, sizeof(cmd));
      return true;
    }
    return false;
  }

  bool restorePower() {
    if (!cfg_.detected) return false;
    // Placeholder: in this first pass we force low-power tune and rely on manual restoration if needed.
    // Keeping function for later model-specific restoration commands.
    return true;
  }

  const RadioConfig& config() const { return cfg_; }

 private:
  static void flush(HardwareSerial& s) {
    while (s.available()) s.read();
  }

  static String readAsciiReply(HardwareSerial& s, uint32_t timeoutMs) {
    String out;
    uint32_t start = millis();
    while ((millis() - start) < timeoutMs) {
      while (s.available()) {
        char c = static_cast<char>(s.read());
        out += c;
        if (c == ';') return out;
      }
      delay(1);
    }
    return out;
  }

  static size_t readUntilFd(HardwareSerial& s, uint8_t* out, size_t maxLen, uint32_t timeoutMs) {
    size_t n = 0;
    uint32_t start = millis();
    while ((millis() - start) < timeoutMs && n < maxLen) {
      while (s.available() && n < maxLen) {
        out[n++] = static_cast<uint8_t>(s.read());
        if (out[n - 1] == 0xFD) return n;
      }
      delay(1);
    }
    return n;
  }

  bool probeCiv(RadioConfig& out) {
    flush(Serial1);
    uint8_t cmd[] = {0xFE, 0xFE, 0x00, 0xE0, 0x03, 0xFD};
    Serial1.write(cmd, sizeof(cmd));
    uint8_t frame[32] = {0};
    size_t n = readUntilFd(Serial1, frame, sizeof(frame), 160);
    if (n < 6 || frame[0] != 0xFE || frame[1] != 0xFE || frame[n - 1] != 0xFD) return false;
    if (frame[2] != 0xE0) return false;
    out.civAddr = frame[3];
    return true;
  }

  bool probeKenwood() {
    flush(Serial2);
    Serial2.print("ID;");
    String rsp = readAsciiReply(Serial2, 160);
    return rsp.startsWith("ID") && rsp.endsWith(";");
  }

  bool probeYaesuAscii() {
    flush(Serial2);
    Serial2.print("FA;");
    String rsp = readAsciiReply(Serial2, 160);
    return rsp.startsWith("FA") && rsp.endsWith(";") && rsp.length() >= 5;
  }

  bool readCivFrequency(uint64_t& outHz) {
    flush(Serial1);
    uint8_t addr = (cfg_.civAddr == 0) ? 0x00 : cfg_.civAddr;
    uint8_t cmd[] = {0xFE, 0xFE, addr, 0xE0, 0x03, 0xFD};
    Serial1.write(cmd, sizeof(cmd));

    uint8_t frame[40] = {0};
    size_t n = readUntilFd(Serial1, frame, sizeof(frame), 160);
    if (n < 8 || frame[0] != 0xFE || frame[1] != 0xFE || frame[n - 1] != 0xFD || frame[4] != 0x03) return false;

    uint64_t f = 0;
    uint64_t place = 1;
    for (size_t i = 5; i < n - 1; ++i) {
      uint8_t b = frame[i];
      uint8_t lo = b & 0x0F;
      uint8_t hi = (b >> 4) & 0x0F;
      if (lo > 9 || hi > 9) return false;
      f += static_cast<uint64_t>(lo) * place;
      place *= 10;
      f += static_cast<uint64_t>(hi) * place;
      place *= 10;
    }
    outHz = f;
    return true;
  }

  bool readAsciiFrequency(uint64_t& outHz) {
    flush(Serial2);
    Serial2.print("FA;");
    String rsp = readAsciiReply(Serial2, 160);
    if (!rsp.startsWith("FA") || !rsp.endsWith(";")) return false;
    String digits = rsp.substring(2, rsp.length() - 1);
    uint64_t f = 0;
    for (size_t i = 0; i < digits.length(); ++i) {
      char c = digits[i];
      if (c < '0' || c > '9') return false;
      f = f * 10 + static_cast<uint64_t>(c - '0');
    }
    outHz = f;
    return true;
  }

  RadioConfig cfg_{};
};

U8G2_SSD1306_128X64_NONAME_F_HW_I2C g_oled(U8G2_R0, U8X8_PIN_NONE);
Preferences g_pref;
MotorController g_motor;
RadioManager g_radio;
AntennaFeedback g_feedback;

DebouncedInput g_btnTune;
DebouncedInput g_btnPark;
DebouncedInput g_btnUp;
DebouncedInput g_btnDown;

CalData g_cal{};
MeasureData g_meas{};
RadioConfig g_radioCfg{};

AppState g_state = AppState::IDLE;
TunePhase g_tunePhase = TunePhase::DONE;
String g_status = "READY";
uint64_t g_freqHz = 0;
String g_flashMessage;
uint8_t g_flashTogglesRemaining = 0;
bool g_flashVisible = false;
uint32_t g_flashNextMs = 0;
DisplayPage g_displayPage = DisplayPage::MAIN;
uint32_t g_uiChordStartMs = 0;
bool g_uiChordLatched = false;
uint8_t g_postFailCount = 0;
PostResult g_postResults[8];
uint8_t g_postResultCount = 0;

uint32_t g_lastUiMs = 0;
uint32_t g_lastMeasMs = 0;
uint32_t g_lastCtrlMs = 0;
uint32_t g_lastRadioMs = 0;
uint32_t g_tuneStartMs = 0;
uint32_t g_lastStepMs = 0;

int32_t g_sweepIdx = 0;
int32_t g_bestIdx = 0;
float g_bestSwr = 99.0f;
uint8_t g_reversals = 0;
uint8_t g_worseCount = 0;
MotorDir g_sweepDir = MotorDir::UP;
bool g_keyed = false;
int32_t g_tuneOriginCounts = 0;
int32_t g_bestPositionCounts = 0;

bool feedbackTrackingReady() {
  const FeedbackData& fb = g_feedback.data();
  return fb.homed && fb.pulseSeen;
}

void startFlashMessage(const char* msg, uint8_t flashes) {
  if (flashes == 0) return;
  g_flashMessage = msg;
  g_flashTogglesRemaining = flashes * 2;
  g_flashVisible = true;
  g_flashNextMs = millis() + Cfg::FLASH_MSG_MS;
}

void serviceFlashMessage(uint32_t now) {
  if (g_flashTogglesRemaining == 0) return;
  if (now < g_flashNextMs) return;

  g_flashVisible = !g_flashVisible;
  if (g_flashTogglesRemaining > 0) {
    g_flashTogglesRemaining--;
  }
  g_flashNextMs = now + Cfg::FLASH_MSG_MS;
  if (g_flashTogglesRemaining == 0) {
    g_flashVisible = false;
    g_flashMessage = "";
  }
}

void postScreen(const char* title, const char* detail, bool ok) {
  if (!ok && g_postFailCount < 255) g_postFailCount++;
  if (g_postResultCount < (sizeof(g_postResults) / sizeof(g_postResults[0]))) {
    g_postResults[g_postResultCount].title = title;
    g_postResults[g_postResultCount].detail = detail;
    g_postResults[g_postResultCount].ok = ok;
    g_postResultCount++;
  }
  Serial.printf("POST %-12s : %s\n", title, detail);
  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_6x12_tr);
  g_oled.drawStr(0, 12, "POWER-ON SELF TEST");
  g_oled.drawStr(0, 28, title);
  g_oled.drawStr(0, 42, detail);
  g_oled.drawStr(0, 58, ok ? "RESULT: OK" : "RESULT: CHECK");
  g_oled.sendBuffer();
  delay(Cfg::POST_STEP_MS);
}

void printPostSummary() {
  Serial.println("POST summary table");
  Serial.println("-------------------------------");
  for (uint8_t i = 0; i < g_postResultCount; ++i) {
    Serial.printf("%-12s | %-5s | %s\n",
                  g_postResults[i].title,
                  g_postResults[i].ok ? "OK" : "CHECK",
                  g_postResults[i].detail.c_str());
  }
  Serial.println("-------------------------------");
}

bool anyControlPressedRaw() {
  return !digitalRead(Pins::BTN_TUNE) || !digitalRead(Pins::BTN_PARK) ||
         !digitalRead(Pins::TUNE_UP) || !digitalRead(Pins::TUNE_DOWN);
}

void waitForPostAcknowledge() {
  if (g_postFailCount == 0) return;

  Serial.printf("POST summary: %u check(s) need attention\n", g_postFailCount);
  while (anyControlPressedRaw()) delay(5);

  while (true) {
    g_oled.clearBuffer();
    g_oled.setFont(u8g2_font_6x12_tr);
    g_oled.drawStr(0, 12, "POST NEEDS REVIEW");
    g_oled.drawStr(0, 28, "Check serial log");
    g_oled.drawStr(0, 42, "Press any button");
    char line[24];
    snprintf(line, sizeof(line), "Failures: %u", g_postFailCount);
    g_oled.drawStr(0, 58, line);
    g_oled.sendBuffer();
    if (anyControlPressedRaw()) break;
    delay(20);
  }

  while (anyControlPressedRaw()) delay(5);
}

int readAveragedAdc(int pin, uint8_t samples) {
  uint32_t sum = 0;
  for (uint8_t i = 0; i < samples; ++i) sum += analogRead(pin);
  return static_cast<int>(sum / samples);
}

float adcToVolts(int adcRaw) {
  return (static_cast<float>(adcRaw) / 4095.0f) * 3.3f;
}

float detectorToPower(const CalData& cal, float v) {
  float vv = max(0.0f, v);
  if (vv < cal.kneeV) return vv * cal.linearGain;
  return (vv - cal.kneeV) * (vv - cal.kneeV) * cal.squareGain + cal.kneeV * cal.linearGain;
}

void loadCal() {
  g_pref.begin("cal", true);
  g_cal.fwdOffsetV = g_pref.getFloat("fo", g_cal.fwdOffsetV);
  g_cal.revOffsetV = g_pref.getFloat("ro", g_cal.revOffsetV);
  g_cal.linearGain = g_pref.getFloat("lg", g_cal.linearGain);
  g_cal.squareGain = g_pref.getFloat("sg", g_cal.squareGain);
  g_cal.kneeV = g_pref.getFloat("kv", g_cal.kneeV);
  g_cal.swrTarget = g_pref.getFloat("swrT", g_cal.swrTarget);
  g_cal.stallA = g_pref.getFloat("stallA", g_cal.stallA);
  g_pref.end();
}

void loadRadioCfg() {
  g_pref.begin("radio", true);
  g_radioCfg.brand = static_cast<RadioBrand>(g_pref.getUChar("brand", static_cast<uint8_t>(RadioBrand::NONE)));
  g_radioCfg.proto = static_cast<RadioProto>(g_pref.getUChar("proto", static_cast<uint8_t>(RadioProto::NONE)));
  g_radioCfg.baud = g_pref.getUInt("baud", 0);
  g_radioCfg.civAddr = g_pref.getUChar("addr", 0);
  g_radioCfg.detected = g_pref.getBool("det", false);
  g_pref.end();
}

void saveRadioCfg() {
  g_pref.begin("radio", false);
  g_pref.putUChar("brand", static_cast<uint8_t>(g_radioCfg.brand));
  g_pref.putUChar("proto", static_cast<uint8_t>(g_radioCfg.proto));
  g_pref.putUInt("baud", g_radioCfg.baud);
  g_pref.putUChar("addr", g_radioCfg.civAddr);
  g_pref.putBool("det", g_radioCfg.detected);
  g_pref.end();
}

void updateMeasurements() {
  int fwd = readAveragedAdc(Pins::SWR_FWD, Cfg::ADC_SAMPLES);
  int rev = readAveragedAdc(Pins::SWR_REV, Cfg::ADC_SAMPLES);
  int isense = readAveragedAdc(Pins::MTR_ISENSE, 8);

  g_meas.vfwd = max(0.0f, adcToVolts(fwd) - g_cal.fwdOffsetV);
  g_meas.vrev = max(0.0f, adcToVolts(rev) - g_cal.revOffsetV);
  g_meas.pfwd = detectorToPower(g_cal, g_meas.vfwd);
  g_meas.prev = detectorToPower(g_cal, g_meas.vrev);
  // INA180A1 + 0.05 ohm shunt => 1.0 A/V.
  g_meas.motorCurrentA = adcToVolts(isense);

  g_meas.carrierPresent = (g_meas.vfwd > Cfg::NO_RF_FWD_V) && (g_meas.pfwd > 0.005f);
  if (!g_meas.carrierPresent || g_meas.pfwd < 0.001f) {
    g_meas.swr = 99.0f;
    return;
  }

  float ratio = constrain(g_meas.prev / max(0.0001f, g_meas.pfwd), 0.0f, 0.98f);
  float gamma = constrain(sqrtf(ratio), 0.0f, 0.99f);
  g_meas.swr = (1.0f + gamma) / max(0.01f, 1.0f - gamma);
}

const char* brandName(RadioBrand b) {
  if (b == RadioBrand::ICOM) return "ICOM";
  if (b == RadioBrand::KENWOOD) return "KEN";
  if (b == RadioBrand::YAESU) return "YAESU";
  return "NONE";
}

void drawDiagnosticsPage() {
  char line[32];
  const FeedbackData& fb = g_feedback.data();

  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_5x8_tr);
  g_oled.drawStr(0, 7, "DIAG LIVE  HOLD TUNE+PARK");

  snprintf(line, sizeof(line), "ST:%s RG:%s %lu", g_status.c_str(), brandName(g_radioCfg.brand),
           static_cast<unsigned long>(g_radioCfg.baud));
  g_oled.drawStr(0, 16, line);

  snprintf(line, sizeof(line), "FWD:%.2f REV:%.2f", g_meas.vfwd, g_meas.vrev);
  g_oled.drawStr(0, 25, line);

  snprintf(line, sizeof(line), "SWR:%s", g_meas.carrierPresent ? String(g_meas.swr, 2).c_str() : "NO RF");
  g_oled.drawStr(0, 34, line);

  snprintf(line, sizeof(line), "IM:%.2fA RF:%d", g_meas.motorCurrentA, g_meas.carrierPresent ? 1 : 0);
  g_oled.drawStr(0, 43, line);

  snprintf(line, sizeof(line), "BTN T%d P%d U%d D%d", g_btnTune.isPressed(), g_btnPark.isPressed(),
           g_btnUp.isPressed(), g_btnDown.isPressed());
  g_oled.drawStr(0, 52, line);

  snprintf(line, sizeof(line), "SNS A%d B%d H%d P%ld", fb.aLevel, fb.bLevel, fb.homed,
           static_cast<long>(fb.positionCounts));
  g_oled.drawStr(0, 61, line);
  g_oled.sendBuffer();
}

void drawDiagnosticsPage2() {
  char line[32];

  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_5x8_tr);
  g_oled.drawStr(0, 7, "DIAG TUNE  HOLD TUNE+PARK");

  snprintf(line, sizeof(line), "STATE:%d PH:%d PG:%d", static_cast<int>(g_state),
           static_cast<int>(g_tunePhase), static_cast<int>(g_displayPage));
  g_oled.drawStr(0, 16, line);

  snprintf(line, sizeof(line), "SWP:%ld BST:%ld", static_cast<long>(g_sweepIdx),
           static_cast<long>(g_bestIdx));
  g_oled.drawStr(0, 25, line);

  snprintf(line, sizeof(line), "BEST SWR:%.2f", g_bestSwr);
  g_oled.drawStr(0, 34, line);

  snprintf(line, sizeof(line), "REV:%u WORSE:%u", g_reversals, g_worseCount);
  g_oled.drawStr(0, 43, line);

  snprintf(line, sizeof(line), "ORIG:%ld CUR:%ld", static_cast<long>(g_tuneOriginCounts),
           static_cast<long>(g_feedback.data().positionCounts));
  g_oled.drawStr(0, 52, line);

  snprintf(line, sizeof(line), "POSTFAIL:%u FLASH:%u", g_postFailCount, g_flashTogglesRemaining);
  g_oled.drawStr(0, 61, line);
  g_oled.sendBuffer();
}

bool serviceDisplayChord(uint32_t now) {
  bool bothPressed = g_btnTune.isPressed() && g_btnPark.isPressed() &&
                     !g_btnUp.isPressed() && !g_btnDown.isPressed();
  if (!bothPressed) {
    g_uiChordStartMs = 0;
    g_uiChordLatched = false;
    return false;
  }

  if (g_uiChordStartMs == 0) {
    g_uiChordStartMs = now;
  }
  if (!g_uiChordLatched && (now - g_uiChordStartMs) >= Cfg::UI_CHORD_HOLD_MS) {
    if (g_displayPage == DisplayPage::MAIN) {
      g_displayPage = DisplayPage::DIAG1;
    } else if (g_displayPage == DisplayPage::DIAG1) {
      g_displayPage = DisplayPage::DIAG2;
    } else {
      g_displayPage = DisplayPage::MAIN;
    }
    g_uiChordLatched = true;
    const char* page = (g_displayPage == DisplayPage::MAIN) ? "MAIN" :
                       (g_displayPage == DisplayPage::DIAG1) ? "DIAG1" : "DIAG2";
    Serial.printf("OLED page -> %s\n", page);
  }
  return true;
}

void drawUi() {
  if (g_displayPage == DisplayPage::DIAG1) {
    drawDiagnosticsPage();
    return;
  }
  if (g_displayPage == DisplayPage::DIAG2) {
    drawDiagnosticsPage2();
    return;
  }

  char line[32];
  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_6x12_tr);

  const char* headline = g_status.c_str();
  if (g_flashVisible && g_flashMessage.length() > 0) {
    headline = g_flashMessage.c_str();
  }
  snprintf(line, sizeof(line), "State:%s", headline);
  g_oled.drawStr(0, 10, line);

  const FeedbackData& fb = g_feedback.data();
  if (feedbackTrackingReady()) {
    snprintf(line, sizeof(line), "Radio:%s P:%ld", brandName(g_radioCfg.brand), static_cast<long>(fb.positionCounts));
  } else if (fb.pulseSeen) {
    snprintf(line, sizeof(line), "Radio:%s P:UNH", brandName(g_radioCfg.brand));
  } else {
    snprintf(line, sizeof(line), "Radio:%s P:---", brandName(g_radioCfg.brand));
  }
  g_oled.drawStr(0, 22, line);

  if (g_freqHz > 0) {
    snprintf(line, sizeof(line), "F:%.3f MHz", static_cast<float>(g_freqHz) / 1000000.0f);
  } else {
    snprintf(line, sizeof(line), "F: ---");
  }
  g_oled.drawStr(0, 34, line);

  if (g_meas.carrierPresent) {
    snprintf(line, sizeof(line), "SWR: %.2f:1", g_meas.swr);
  } else {
    snprintf(line, sizeof(line), "SWR: NO RF");
  }
  g_oled.drawStr(0, 46, line);

  uint8_t barW = 100;
  float swrClamped = constrain(g_meas.swr, 1.0f, 3.0f);
  uint8_t fill = static_cast<uint8_t>(((swrClamped - 1.0f) / 2.0f) * barW);
  g_oled.drawFrame(0, 52, barW, 10);
  g_oled.drawBox(1, 53, fill, 8);

  g_oled.sendBuffer();
}

void endTune(bool ok, const char* msg) {
  if (g_keyed) {
    g_radio.keyCarrier(false);
    g_keyed = false;
  }
  g_radio.restorePower();
  g_motor.stopBrake();
  g_state = AppState::IDLE;
  g_tunePhase = ok ? TunePhase::DONE : TunePhase::FAIL;
  if (ok) {
    g_status = "READY";
    startFlashMessage("TUNED", 3);
  } else {
    g_status = msg;
  }
}

void startTune() {
  g_displayPage = DisplayPage::MAIN;
  g_state = AppState::TUNING;
  g_tunePhase = TunePhase::PREP;
  g_tuneStartMs = millis();
  g_lastStepMs = g_tuneStartMs;
  g_sweepIdx = 0;
  g_bestIdx = 0;
  g_bestSwr = 99.0f;
  g_reversals = 0;
  g_worseCount = 0;
  g_sweepDir = MotorDir::UP;
  g_tuneOriginCounts = g_feedback.data().positionCounts;
  g_bestPositionCounts = g_tuneOriginCounts;
  g_status = "TUNING";
}

void startPark() {
  g_displayPage = DisplayPage::MAIN;
  g_state = AppState::PARKING;
  g_status = "PARKING";
}

void serviceTune() {
  uint32_t now = millis();

  if (g_btnPark.isPressed() || g_btnUp.isPressed() || g_btnDown.isPressed()) {
    endTune(false, "ABORT");
    return;
  }
  if ((now - g_tuneStartMs) > Cfg::TUNE_TIMEOUT_MS) {
    endTune(false, "TIMEOUT");
    return;
  }

  bool stalled = g_motor.takeStallLatched();

  if (g_tunePhase == TunePhase::PREP) {
    if (g_radioCfg.detected) {
      g_radio.enterLowPowerTune();
      g_radio.keyCarrier(true);
      g_keyed = true;
    }
    g_tunePhase = TunePhase::WAIT_RF;
    g_lastStepMs = now;
    return;
  }

  if (g_tunePhase == TunePhase::WAIT_RF) {
    if (g_meas.carrierPresent) {
      g_bestSwr = g_meas.swr;
      g_bestIdx = 0;
      g_sweepIdx = 0;
      g_tuneOriginCounts = g_feedback.data().positionCounts;
      g_bestPositionCounts = g_tuneOriginCounts;
      g_tunePhase = TunePhase::COARSE;
      g_lastStepMs = now;
      return;
    }
    if ((now - g_lastStepMs) > Cfg::RF_WAIT_TIMEOUT_MS) {
      endTune(false, "NO CARRIER");
    }
    return;
  }

  if (g_tunePhase == TunePhase::COARSE) {
    g_motor.command(g_sweepDir, Cfg::DUTY_COARSE, now);

    bool advanced = false;
    if (feedbackTrackingReady()) {
      int32_t idx = g_feedback.data().positionCounts - g_tuneOriginCounts;
      if (idx != g_sweepIdx) {
        g_sweepIdx = idx;
        g_lastStepMs = now;
        advanced = true;
      }
    } else if ((now - g_lastStepMs) >= Cfg::SAMPLE_STEP_MS) {
      g_lastStepMs = now;
      g_sweepIdx += (g_sweepDir == MotorDir::UP) ? 1 : -1;
      advanced = true;
    }

    if (advanced) {
      if (g_meas.swr < g_bestSwr) {
        g_bestSwr = g_meas.swr;
        g_bestIdx = g_sweepIdx;
        g_bestPositionCounts = g_feedback.data().positionCounts;
        g_worseCount = 0;
      } else if (g_meas.swr > (g_bestSwr + 0.08f)) {
        g_worseCount++;
      }

      if (stalled || g_worseCount >= 5) {
        if (g_reversals == 0) {
          g_reversals = 1;
          g_worseCount = 0;
          g_sweepDir = (g_sweepDir == MotorDir::UP) ? MotorDir::DOWN : MotorDir::UP;
        } else {
          g_tunePhase = TunePhase::RETURN_BEST;
        }
      }
    }
    return;
  }

  if (g_tunePhase == TunePhase::RETURN_BEST) {
    if (feedbackTrackingReady()) {
      int32_t errCounts = g_bestPositionCounts - g_feedback.data().positionCounts;
      if (abs(errCounts) <= 0) {
        endTune(true, (g_bestSwr <= g_cal.swrTarget) ? "TUNE OK" : "TUNE DONE");
        return;
      }

      MotorDir d = (errCounts > 0) ? MotorDir::UP : MotorDir::DOWN;
      g_motor.command(d, Cfg::DUTY_FINE, now);
      if (stalled) {
        endTune(false, "NO DIP");
      }
      return;
    }

    int32_t err = g_bestIdx - g_sweepIdx;
    if (abs(err) <= 1) {
      endTune(true, (g_bestSwr <= g_cal.swrTarget) ? "TUNE OK" : "TUNE DONE");
      return;
    }

    MotorDir d = (err > 0) ? MotorDir::UP : MotorDir::DOWN;
    g_motor.command(d, Cfg::DUTY_FINE, now);
    if ((now - g_lastStepMs) >= Cfg::SAMPLE_STEP_MS) {
      g_lastStepMs = now;
      g_sweepIdx += (d == MotorDir::UP) ? 1 : -1;
      if (stalled) {
        endTune(false, "NO DIP");
      }
    }
    return;
  }
}

void servicePark() {
  uint32_t now = millis();
  g_motor.command(MotorDir::DOWN, Cfg::DUTY_PARK, now);
  if (g_motor.takeStallLatched()) {
    g_motor.stopBrake();
    g_feedback.markParkedHome();
    g_state = AppState::IDLE;
    g_status = "PARK";
  }
}

void serviceIdleControls() {
  uint32_t now = millis();

  if (serviceDisplayChord(now)) {
    g_motor.stopBrake();
    return;
  }

  if (g_btnTune.takePressedEdge()) {
    startTune();
    return;
  }
  if (g_btnPark.takePressedEdge()) {
    startPark();
    return;
  }

  if (g_btnUp.isPressed() && !g_btnDown.isPressed()) {
    g_status = "JOG UP";
    g_motor.command(MotorDir::UP, Cfg::DUTY_JOG, now);
  } else if (g_btnDown.isPressed() && !g_btnUp.isPressed()) {
    g_status = "JOG DOWN";
    g_motor.command(MotorDir::DOWN, Cfg::DUTY_JOG, now);
  } else {
    if (g_status == "JOG UP" || g_status == "JOG DOWN") g_status = "READY";
    g_motor.stopBrake();
  }
}

void setup() {
  Serial.begin(115200);
  delay(50);

  pinMode(12, INPUT);

  g_btnTune.begin(Pins::BTN_TUNE, true, true);
  g_btnPark.begin(Pins::BTN_PARK, true, true);
  g_btnUp.begin(Pins::TUNE_UP, true, true);
  g_btnDown.begin(Pins::TUNE_DOWN, true, true);

  analogReadResolution(12);
  analogSetPinAttenuation(Pins::SWR_FWD, ADC_11db);
  analogSetPinAttenuation(Pins::SWR_REV, ADC_11db);
  analogSetPinAttenuation(Pins::MTR_ISENSE, ADC_11db);

  Wire.begin(Pins::I2C_SDA, Pins::I2C_SCL);
  g_oled.begin();
  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_6x12_tr);
  g_oled.drawStr(0, 14, "Screwdriver Tuner");
  g_oled.drawStr(0, 28, "Booting...");
  g_oled.sendBuffer();

  g_motor.begin();
  g_feedback.begin();
  g_radio.begin();

  Serial.println();
  Serial.println("POST begin");
  bool oledAck = false;
  Wire.beginTransmission(0x3C);
  oledAck = (Wire.endTransmission() == 0);
  postScreen("OLED/I2C", oledAck ? "SSD1306 @0x3C" : "No ACK @0x3C", oledAck);

  loadCal();
  loadRadioCfg();
  postScreen("NVS", "Calibration + radio cfg", true);

  updateMeasurements();
  char detail[32];
  snprintf(detail, sizeof(detail), "ADC F%.2f R%.2f I%.2f", g_meas.vfwd, g_meas.vrev, g_meas.motorCurrentA);
  bool adcOk = isfinite(g_meas.vfwd) && isfinite(g_meas.vrev) && isfinite(g_meas.motorCurrentA);
  postScreen("ADC", detail, adcOk);

  g_btnTune.update(millis());
  g_btnPark.update(millis());
  g_btnUp.update(millis());
  g_btnDown.update(millis());
  snprintf(detail, sizeof(detail), "T%d P%d U%d D%d", g_btnTune.isPressed(), g_btnPark.isPressed(), g_btnUp.isPressed(), g_btnDown.isPressed());
  bool buttonsIdle = !g_btnTune.isPressed() && !g_btnPark.isPressed() && !g_btnUp.isPressed() && !g_btnDown.isPressed();
  postScreen("BUTTONS", detail, buttonsIdle);

  const FeedbackData& fb = g_feedback.data();
  snprintf(detail, sizeof(detail), "A%d B%d P%ld", fb.aLevel, fb.bLevel, static_cast<long>(fb.positionCounts));
  postScreen("ANT SENSE", detail, true);

  // Chord at boot: force radio re-scan.
  uint32_t start = millis();
  bool forceRescan = false;
  g_oled.clearBuffer();
  g_oled.setFont(u8g2_font_6x12_tr);
  g_oled.drawStr(0, 14, "Hold TUNE+PARK");
  g_oled.drawStr(0, 28, "for radio rescan");
  g_oled.sendBuffer();
  while (millis() - start < 700) {
    g_btnTune.update(millis());
    g_btnPark.update(millis());
    if (g_btnTune.isPressed() && g_btnPark.isPressed()) {
      forceRescan = true;
      break;
    }
    delay(5);
  }

  if (g_radioCfg.detected && !forceRescan) {
    g_radio.applyConfig(g_radioCfg);
    snprintf(detail, sizeof(detail), "%s %lu", brandName(g_radioCfg.brand), static_cast<unsigned long>(g_radioCfg.baud));
    postScreen("RADIO CFG", detail, true);
  } else {
    g_oled.clearBuffer();
    g_oled.drawStr(0, 14, "Detecting radio...");
    g_oled.sendBuffer();
    g_radioCfg = g_radio.detect();
    saveRadioCfg();
    snprintf(detail, sizeof(detail), "%s %lu", brandName(g_radioCfg.brand), static_cast<unsigned long>(g_radioCfg.baud));
    postScreen("RADIO SCAN", g_radioCfg.detected ? detail : "No radio found", g_radioCfg.detected);
  }

  g_status = g_radioCfg.detected ? "READY" : "NO RADIO";
  postScreen("POST DONE", g_status.c_str(), g_radioCfg.detected || !forceRescan);
  printPostSummary();
  waitForPostAcknowledge();
}

void loop() {
  uint32_t now = millis();
  serviceFlashMessage(now);

  if ((now - g_lastCtrlMs) >= Cfg::CTRL_MS) {
    g_lastCtrlMs = now;
    g_btnTune.update(now);
    g_btnPark.update(now);
    g_btnUp.update(now);
    g_btnDown.update(now);
    g_feedback.update(now, g_motor.dir());
  }

  if ((now - g_lastMeasMs) >= Cfg::MEAS_MS) {
    g_lastMeasMs = now;
    updateMeasurements();
  }

  g_motor.update(now, g_meas.motorCurrentA, g_cal.stallA);

  if (g_state == AppState::IDLE) {
    serviceIdleControls();
  } else if (g_state == AppState::TUNING) {
    serviceTune();
  } else if (g_state == AppState::PARKING) {
    if (g_btnTune.takePressedEdge() || g_btnUp.isPressed() || g_btnDown.isPressed()) {
      g_motor.stopBrake();
      g_state = AppState::IDLE;
      g_status = "ABORT";
    } else {
      servicePark();
    }
  }

  if ((now - g_lastRadioMs) >= Cfg::RADIO_POLL_MS) {
    g_lastRadioMs = now;
    uint64_t f = 0;
    if (g_radio.readFrequencyHz(f)) g_freqHz = f;
  }

  if ((now - g_lastUiMs) >= Cfg::UI_MS) {
    g_lastUiMs = now;
    drawUi();
  }

  delay(1);
}
