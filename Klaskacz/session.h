#pragma once
// Struktura sesji, statystyki, zapis CSV + metadanych do LittleFS.
// Pliki na sesje: /s<id>.csv (klasniecia), /m<id>.json (podsumowanie, zapisywane przy STOP).
#include "config.h"
#include <LittleFS.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>
#include <sys/time.h>
#include "esp_timer.h"

Preferences prefs;
float gBattery = 0;
uint32_t gBoot = 0;                       // numer uruchomienia urzadzenia (do wyliczania daty sesji)
StartMode gStartMode = SM_FIRST_CLAP;

struct Clap {
  uint32_t t_ms;         // offset od startu sesji (pierwsze klasniecie = 0 w trybie first_clap)
  uint32_t interval_ms;  // odstep od poprzedniego (0 dla pierwszego)
  uint16_t peak;
};

struct Session {
  uint32_t id = 0;
  SessionState state = S_IDLE;
  uint64_t t0_us = 0, stop_us = 0;
  uint32_t count = 0, flushed = 0;
  uint32_t intervals_sum_ms = 0;
  uint32_t interval_min_ms = 0, interval_max_ms = 0, last_clap_ms = 0;
  int64_t  epoch_s = 0;      // data startu, jesli zegar byl zsynchronizowany (0 = nieznana)
  uint32_t uptime_ms = 0;    // uptime w chwili startu
  uint32_t boot = 0;         // numer uruchomienia w chwili startu
  Clap claps[MAX_CLAPS_RAM]; // bufor kolowy
};
Session S;

const char* stateName(SessionState s) {   // zgodne z kontraktem API
  static const char* n[] = {"idle", "armed", "running", "finished"};
  return n[s];
}
const char* startModeName(StartMode m) { return m == SM_SIGNAL ? "signal" : "first_clap"; }

// ---------- czas ----------
bool timeValid() { return time(nullptr) > 1700000000; }   // ustawiany przez POST /api/time
void isoFromEpoch(int64_t e, char* buf, size_t n) {
  time_t t = (time_t)e; struct tm tmv; gmtime_r(&t, &tmv);
  strftime(buf, n, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}
// Data startu sesji: znana od razu albo wyliczona z uptime (jesli ten sam boot i zegar juz zsynchronizowany)
int64_t resolveStartEpoch(int64_t epoch_s, uint32_t uptime_ms, uint32_t boot) {
  if (epoch_s > 0) return epoch_s;
  if (boot == gBoot && timeValid()) {
    uint32_t upNow = (uint32_t)(esp_timer_get_time() / 1000ULL);
    return (int64_t)time(nullptr) - (int64_t)(upNow - uptime_ms) / 1000;
  }
  return 0;
}

// ---------- sciezki / id ----------
void sessionPath(char* buf, size_t n, uint32_t id) { snprintf(buf, n, "/s%lu.csv", (unsigned long)id); }
void metaPath(char* buf, size_t n, uint32_t id)    { snprintf(buf, n, "/m%lu.json", (unsigned long)id); }

uint32_t sessionNextId() {
  uint32_t id = prefs.getUInt("sid", 0) + 1;
  prefs.putUInt("sid", id);
  return id;
}

void sessionClear() {   // id zostaje (dane ostatniej sesji sa w pamieci flash)
  S.state = S_IDLE;
  S.t0_us = S.stop_us = 0;
  S.count = S.flushed = 0;
  S.intervals_sum_ms = 0;
  S.interval_min_ms = S.interval_max_ms = S.last_clap_ms = 0;
}

// ---------- statystyki ----------
uint32_t sessionElapsedMs() {
  if (S.state == S_RUNNING)  return (uint32_t)((esp_timer_get_time() - S.t0_us) / 1000ULL);
  if (S.state == S_FINISHED) return (uint32_t)((S.stop_us - S.t0_us) / 1000ULL);
  return 0;
}
uint32_t sessionAvgMs() { return S.count > 1 ? S.intervals_sum_ms / (S.count - 1) : 0; }
// CPS wg kontraktu (przyklad: 8 klasniec / 6.55 s = 1.22): liczba klasniec / czas sesji
float sessionCps() {
  uint32_t e = sessionElapsedMs();
  return e > 0 ? S.count * 1000.0f / e : 0;
}

// ---------- zapis ----------
void storageOpen() {
  char p[24]; sessionPath(p, sizeof p, S.id);
  File f = LittleFS.open(p, "w");
  if (f) { f.println("index,t_ms,interval_ms,peak"); f.close(); }
}

void storageFlush() {
  if (S.flushed >= S.count) return;
  uint32_t from = S.flushed;
  if (S.count - from > MAX_CLAPS_RAM) from = S.count - MAX_CLAPS_RAM;
  char p[24]; sessionPath(p, sizeof p, S.id);
  File f = LittleFS.open(p, "a");
  if (!f) return;
  char line[64];
  for (uint32_t i = from; i < S.count; i++) {
    const Clap& c = S.claps[i % MAX_CLAPS_RAM];
    int n = snprintf(line, sizeof line, "%lu,%lu,%lu,%u\n", (unsigned long)i,
                     (unsigned long)c.t_ms, (unsigned long)c.interval_ms, c.peak);
    f.write((const uint8_t*)line, n);
  }
  f.close();
  S.flushed = S.count;
}

// Wypelnia podsumowanie biezacej sesji (te same klucze trafiaja do /m<id>.json)
void sessionFillMeta(JsonDocument& d) {
  d["clap_count"] = S.count;
  d["duration_ms"] = sessionElapsedMs();
  if (S.count > 1) d["avg_interval_ms"] = sessionAvgMs();
  d["cps"] = roundf(sessionCps() * 100) / 100;
  d["epoch_s"] = S.epoch_s;
  d["uptime_ms"] = S.uptime_ms;
  d["boot"] = S.boot;
}

void sessionSaveMeta() {
  JsonDocument d; sessionFillMeta(d);
  char p[24]; metaPath(p, sizeof p, S.id);
  File f = LittleFS.open(p, "w");
  if (f) { serializeJson(d, f); f.close(); }
}

// ---------- cykl zycia sesji ----------
void sessionBegin(uint64_t t0_us) {       // IDLE/ARMED -> RUNNING
  sessionClear();
  S.id = sessionNextId();
  S.t0_us = t0_us;
  S.state = S_RUNNING;
  S.epoch_s = timeValid() ? (int64_t)time(nullptr) : 0;
  S.uptime_ms = (uint32_t)(t0_us / 1000ULL);
  S.boot = gBoot;
  storageOpen();
}

void sessionFinish() {                    // RUNNING -> FINISHED + zapis do pamieci
  S.stop_us = esp_timer_get_time();
  S.state = S_FINISHED;
  storageFlush();
  sessionSaveMeta();
}

void sessionAddClap(const ClapEvent& ev) {
  uint32_t t = (uint32_t)((ev.t_us - S.t0_us) / 1000ULL);
  Clap& c = S.claps[S.count % MAX_CLAPS_RAM];
  c.t_ms = t; c.peak = ev.peak; c.interval_ms = 0;
  if (S.count > 0) {
    uint32_t iv = t - S.last_clap_ms;
    c.interval_ms = iv;
    S.intervals_sum_ms += iv;
    if (S.count == 1 || iv < S.interval_min_ms) S.interval_min_ms = iv;
    if (iv > S.interval_max_ms) S.interval_max_ms = iv;
  }
  S.last_clap_ms = t;
  S.count++;
  if (S.count - S.flushed >= FLASH_BATCH) storageFlush();
}
