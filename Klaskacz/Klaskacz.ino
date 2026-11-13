
#include <Wire.h>
#include <U8g2lib.h>
#include "config.h"
#include "audio.h"
#include "session.h"
#include "api.h"

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

uint32_t buzzerUntil = 0;
uint64_t armedAtUs = 0;
bool dbgDetector = false;
uint64_t ignoreUntilUs = 0;    // do tego czasu detekcje ignorujemy (zeby pisk buzzera nie byl klasnieciem)

// ================= KONFIG (NVS) =================
void configLoad() {
  configApplyThreshold(prefs.getUChar("thr", THR_UI_DEFAULT));
  gAutoSens  = prefs.getBool("auto", false);
  gStartMode = (StartMode)prefs.getUChar("smode", SM_FIRST_CLAP);
}
void configSave() {
  prefs.putUChar("thr", gThrUi);
  prefs.putBool("auto", gAutoSens);
  prefs.putUChar("smode", (uint8_t)gStartMode);
}

// ================= BUZZER (nieblokujacy) =================
void beep(uint32_t ms) {
  digitalWrite(PIN_BUZZER, LOW);
  buzzerUntil = millis() + ms;
  ignoreUntilUs = esp_timer_get_time() + (uint64_t)(ms + BUZZER_GUARD_MS) * 1000ULL;
}

// ================= AUTOMAT STANOW =================
void handleClap(const ClapEvent& ev) {
  if (ev.t_us < ignoreUntilUs) return;        // pisk buzzera / szum po nim
  if (S.state == S_ARMED) {
    if (ev.t_us < armedAtUs) return;          // stare zdarzenie sprzed uzbrojenia
    sessionBegin(ev.t_us);                    // AUTOSTART: t0 = pierwsze klasniecie
    sessionAddClap(ev);                       // offset 0, interwal 0
  } else if (S.state == S_RUNNING) {
    sessionAddClap(ev);
  }
  // IDLE / FINISHED: ignorujemy
}

void startMeasurement() {                     // z IDLE
  xQueueReset(clapQueue);
  if (gStartMode == SM_SIGNAL) {              // start na sygnal: pisk i od razu liczymy czas
    beep(300);
    sessionBegin(esp_timer_get_time());
  } else {                                    // first_clap: uzbrajamy i czekamy na klasniecie
    beep(150);
    armedAtUs = esp_timer_get_time();
    S.state = S_ARMED;
  }
}

void handleCommand(Cmd c) {
  bool toggle = (c == CMD_START_STOP);
  if (c == CMD_RESET) {
    if (S.state == S_RUNNING) sessionFinish();   // nie gubimy trwajacej sesji - zapis przed czyszczeniem
    sessionClear();
    beep(60);
    return;
  }
  switch (S.state) {
    case S_IDLE:
      if (toggle || c == CMD_START) startMeasurement();
      break;
    case S_ARMED:
      if (toggle || c == CMD_STOP) { S.state = S_IDLE; beep(60); }   // anulowanie
      break;
    case S_RUNNING:
      if (toggle || c == CMD_STOP) { sessionFinish(); beep(300); }   // STOP zawsze zapisuje sesje
      break;
    case S_FINISHED:
      if (toggle || c == CMD_START) { sessionClear(); startMeasurement(); }   // nowa sesja
      break;
  }
}

void setWifi(bool on) {
  if (on) wifiStart(); else wifiStop();
  prefs.putBool("wifi", on);
}

// ================= PRZYCISKI =================
struct Btn {
  uint8_t pin; bool stable = true, lastRead = true, longDone = false;
  uint32_t tChange = 0, tDown = 0;
};
Btn btns[4] = {{PIN_BTN_UP}, {PIN_BTN_DOWN}, {PIN_BTN_START}, {PIN_BTN_RESET}};
enum { B_UP, B_DOWN, B_START, B_RESET };

void onShort(int id) {
  switch (id) {
    case B_UP:    configApplyThreshold(gThrUi + THR_UI_STEP); configSave(); break;
    case B_DOWN:  configApplyThreshold((int)gThrUi - THR_UI_STEP); configSave(); break;
    case B_START: handleCommand(CMD_START_STOP); break;
    case B_RESET: handleCommand(CMD_RESET); break;
  }
}
void onLong(int id) {
  if (id == B_RESET && S.state != S_RUNNING) { setWifi(!wifiOn); beep(100); }   // Wi-Fi z "menu"
  if (id == B_UP)   { gAutoSens = !gAutoSens; configSave(); beep(100); }        // auto / reczna czulosc
  if (id == B_DOWN && S.state != S_RUNNING) {                                   // tryb startu
    gStartMode = (gStartMode == SM_FIRST_CLAP) ? SM_SIGNAL : SM_FIRST_CLAP;
    configSave(); beep(100);
  }
}

void pollButtons() {
  uint32_t now = millis();
  for (int i = 0; i < 4; i++) {
    Btn& b = btns[i];
    bool r = digitalRead(b.pin);
    if (r != b.lastRead) { b.lastRead = r; b.tChange = now; }
    if (now - b.tChange > 25 && b.stable != b.lastRead) {   // debounce 25 ms
      b.stable = b.lastRead;
      if (!b.stable) { b.tDown = now; b.longDone = false; }  // wcisniety
      else if (!b.longDone) onShort(i);                       // puszczony, krotkie
    }
    if (!b.stable && !b.longDone && now - b.tDown > LONG_PRESS_MS) { b.longDone = true; onLong(i); }
  }
}

// ================= BATERIA =================
// void updateBattery() {
//   uint32_t mv = 0;
//   for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_BAT);
//   gBattery = (mv / 8.0f) * 2.0f / 1000.0f;   // dzielnik 2x100k
// }

// ================= OLED =================
void drawDisplay() {
  char l[32];
  uint32_t t = sessionElapsedMs();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  snprintf(l, sizeof l, "%s %s %.2fV", stateName(S.state), wifiOn ? "WiFi" : "    ", gBattery);
  u8g2.drawStr(0, 9, l);
  snprintf(l, sizeof l, "Czas %lu:%02lu.%lu", (unsigned long)(t / 60000), (unsigned long)((t / 1000) % 60), (unsigned long)((t / 100) % 10));
  u8g2.drawStr(0, 22, l);
  snprintf(l, sizeof l, "Klasniec: %lu", (unsigned long)S.count);
  u8g2.drawStr(0, 34, l);
  snprintf(l, sizeof l, "Sred: %lu ms", (unsigned long)sessionAvgMs());
  u8g2.drawStr(0, 46, l);
  snprintf(l, sizeof l, "CPS: %.2f", sessionCps());
  u8g2.drawStr(0, 58, l);
  snprintf(l, sizeof l, "P:%u%s %s", (unsigned)gThrUi, gAutoSens ? "A" : "", gStartMode == SM_SIGNAL ? "SYG" : "KLP");
  u8g2.drawStr(66, 58, l);
  u8g2.sendBuffer();
}

// ================= SERIAL (testy bez mikrofonu) =================
void serialCommands() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == 'c') { ClapEvent ev = { (uint64_t)esp_timer_get_time(), 0 }; handleClap(ev); }
    else if (ch == 's') handleCommand(CMD_START_STOP);
    else if (ch == 'x') handleCommand(CMD_STOP);
    else if (ch == 'r') handleCommand(CMD_RESET);
    else if (ch == 'w') setWifi(!wifiOn);
    else if (ch == 'd') dbgDetector = !dbgDetector;
    else if (ch == 'p') {
      Serial.printf("%s count=%lu t=%lums avg=%lums min=%lu max=%lu cps=%.2f\n",
        stateName(S.state), (unsigned long)S.count, (unsigned long)sessionElapsedMs(),
        (unsigned long)sessionAvgMs(), (unsigned long)S.interval_min_ms, (unsigned long)S.interval_max_ms,
        sessionCps());
    }
  }
}

// ================= ZADANIE LOGIKI (rdzen 0) =================
void logicTask(void*) {
  uint32_t lastDraw = 0, lastBat = 0;
  for (;;) {
    pollButtons();
    serialCommands();

    ClapEvent ev;
    while (xQueueReceive(clapQueue, &ev, 0) == pdTRUE) handleClap(ev);

    if (wifiOn) server.handleClient();

    static uint32_t lastDbg = 0;
    if (dbgDetector && millis() - lastDbg > 200) {
      lastDbg = millis();
      Serial.printf("A=%u base=%d thr=%u f=%d\n", (unsigned)gLastPeak, (int)gBaseline, (unsigned)gEffThr, (int)gFreq);
    }

    uint32_t now = millis();
    if (buzzerUntil && (int32_t)(now - buzzerUntil) >= 0) { digitalWrite(PIN_BUZZER, HIGH); buzzerUntil = 0; }

    if (AUTO_STOP_MS && S.state == S_RUNNING && sessionElapsedMs() - S.last_clap_ms > AUTO_STOP_MS)
      handleCommand(CMD_STOP);

    // if (now - lastBat > 2000) { lastBat = now; updateBattery(); }
    if (now - lastDraw > 100) { lastDraw = now; drawDisplay(); }   // ~10 Hz
    vTaskDelay(1);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT); digitalWrite(PIN_BUZZER, HIGH);
  for (int i = 0; i < 4; i++) pinMode(btns[i].pin, btns[i].pin >= 34 ? INPUT : INPUT_PULLUP);  // 34-39: tylko zewnetrzny pull-up

  prefs.begin("klask", false);
  gBoot = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", gBoot);
  configLoad();
  if (!LittleFS.begin(true)) Serial.println("LittleFS FAIL");

  Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
  u8g2.begin();

  clapQueue = xQueueCreate(32, sizeof(ClapEvent));
  audioInit();
  xTaskCreatePinnedToCore(audioTask, "audio", 6144, NULL, 5, NULL, 1);

  wifiInitRoutes();
  if (prefs.getBool("wifi", true)) wifiStart();
  xTaskCreatePinnedToCore(logicTask, "logic", 10240, NULL, 1, NULL, 0);
  Serial.println("Gotowe. Komendy: c s x r w p");
}

void loop() { vTaskDelay(portMAX_DELAY); }   // cala praca w zadaniach
