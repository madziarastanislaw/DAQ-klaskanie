#pragma once

#include "config.h"
#include "audio.h"
#include "session.h"
#include <WiFi.h>
#include <WebServer.h>
#include <uri/UriBraces.h>
#include <ESPmDNS.h>

void handleCommand(Cmd c);   // z .ino
void configSave();           // z .ino

WebServer server(80);
bool wifiOn = false;

void sendCors() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}
void sendJson(JsonDocument& d, int code = 200) {
  String o; serializeJson(d, o);
  sendCors();
  server.send(code, "application/json", o);
}
void sendError(int code, const char* msg) {
  JsonDocument d; d["ok"] = false; d["error"] = msg;
  sendJson(d, code);
}
void sendOk() { JsonDocument d; d["ok"] = true; sendJson(d); }
float round2(float x) { return roundf(x * 100) / 100; }

// /api/config
void fillConfig(JsonObject o) {
  o["sensitivity"] = gAutoSens ? "auto" : "manual";
  o["threshold"] = (int)gThrUi;
  o["start_mode"] = startModeName(gStartMode);
}
void sendConfig() {
  JsonDocument d; fillConfig(d.to<JsonObject>()); sendJson(d);
}
void handleConfigWrite() {   // PUT i POST
  JsonDocument d;
  if (deserializeJson(d, server.arg("plain"))) { sendError(400, "bad json"); return; }

  bool autoS = gAutoSens; int thr = gThrUi; StartMode sm = gStartMode;
  if (!d["sensitivity"].isNull()) {
    String s = d["sensitivity"].as<String>();
    if (s == "auto") autoS = true; else if (s == "manual") autoS = false;
    else { sendError(400, "sensitivity must be auto|manual"); return; }
  }
  if (!d["threshold"].isNull()) {
    if (!d["threshold"].is<int>()) { sendError(400, "threshold must be 1-100"); return; }
    thr = d["threshold"].as<int>();
    if (thr < 1 || thr > 100) { sendError(400, "threshold must be 1-100"); return; }
  }
  if (!d["start_mode"].isNull()) {
    String s = d["start_mode"].as<String>();
    if (s == "first_clap") sm = SM_FIRST_CLAP; else if (s == "signal") sm = SM_SIGNAL;
    else { sendError(400, "start_mode must be first_clap|signal"); return; }
  }
  gAutoSens = autoS; gStartMode = sm; configApplyThreshold(thr);
  configSave();
  sendConfig();
}

// /api/status
void sendStatus() {
  JsonDocument d;
  d["state"] = stateName(S.state);
  d["elapsed_ms"] = sessionElapsedMs();
  d["clap_count"] = S.count;
  d["cps"] = round2(sessionCps());
  if (S.count > 1) {
    d["avg_interval_ms"] = sessionAvgMs();
    d["last_interval_ms"] = S.claps[(S.count - 1) % MAX_CLAPS_RAM].interval_ms;
  } else {
    d["avg_interval_ms"] = nullptr;
    d["last_interval_ms"] = nullptr;
  }

  JsonArray arr = d["intervals_ms"].to<JsonArray>();
  uint32_t n = S.count > 1 ? S.count - 1 : 0;
  uint32_t k = n < STATUS_INTERVALS ? n : STATUS_INTERVALS;
  for (uint32_t i = S.count - k; i < S.count && k > 0; i++) arr.add(S.claps[i % MAX_CLAPS_RAM].interval_ms);
  d["wifi_enabled"] = wifiOn;
  fillConfig(d["config"].to<JsonObject>());

  d["battery_v"] = round2(gBattery);
  d["time_synced"] = timeValid();
  d["level"] = (int)gLastPeak;          // biezacy poziom (A) - do kalibracji progu
  d["baseline"] = (int)gBaseline;
  d["freq_hz"] = (int)gFreq;            // dominujaca czestotliwosc ostatniego kandydata
  d["eff_threshold"] = (uint32_t)gEffThr;
  sendJson(d);
}

// /api/session/* 
void sessionCmd(Cmd c) { handleCommand(c); sendOk(); }

// /api/time
void handleTimeSync() {
  JsonDocument d;
  if (deserializeJson(d, server.arg("plain"))) { sendError(400, "bad json"); return; }
  uint64_t ms = d["epoch_ms"].as<uint64_t>();
  if (ms < 1700000000000ULL) { sendError(400, "epoch_ms invalid"); return; }
  struct timeval tv = { (time_t)(ms / 1000), (suseconds_t)((ms % 1000) * 1000) };
  settimeofday(&tv, nullptr);
  sendOk();
}

// /api/sessions
bool loadMeta(uint32_t id, JsonDocument& m) {
  char p[24]; metaPath(p, sizeof p, id);
  File f = LittleFS.open(p, "r");
  if (!f) return false;
  DeserializationError e = deserializeJson(m, f);
  f.close();
  return !e;
}

void fillSummary(JsonObject o, uint32_t id, JsonDocument& m) {
  o["id"] = String("session-") + id;
  int64_t e = resolveStartEpoch(m["epoch_s"].as<int64_t>(), m["uptime_ms"].as<uint32_t>(), m["boot"].as<uint32_t>());
  if (e > 0) { char ts[24]; isoFromEpoch(e, ts, sizeof ts); o["started_at"] = String(ts); }
  else o["started_at"] = nullptr;
  o["duration_ms"] = m["duration_ms"].as<uint32_t>();
  o["clap_count"] = m["clap_count"].as<uint32_t>();
  o["cps"] = m["cps"].as<float>();
  o["avg_interval_ms"] = m["avg_interval_ms"];   // null, jesli brak
}

void sendSessionList() {
  uint32_t ids[50]; int n = 0;
  File root = LittleFS.open("/");
  File f = root.openNextFile();
  while (f) {
    String name = f.name();
    int sl = name.lastIndexOf('/'); if (sl >= 0) name = name.substring(sl + 1);
    unsigned long id;
    if (sscanf(name.c_str(), "m%lu.json", &id) == 1 && n < 50) ids[n++] = id;
    f = root.openNextFile();
  }
  for (int i = 0; i < n; i++)               // malejaco (najnowsze pierwsze)
    for (int j = i + 1; j < n; j++) if (ids[j] > ids[i]) { uint32_t t = ids[i]; ids[i] = ids[j]; ids[j] = t; }

  JsonDocument out;
  JsonArray arr = out["sessions"].to<JsonArray>();
  for (int i = 0; i < n; i++) {
    JsonDocument m;
    if (loadMeta(ids[i], m)) fillSummary(arr.add<JsonObject>(), ids[i], m);
  }
  sendJson(out);
}

void sendSessionDetail() {
  unsigned long id;
  if (sscanf(server.pathArg(0).c_str(), "session-%lu", &id) != 1) { sendError(404, "bad id"); return; }

  JsonDocument m;
  bool live = (id == S.id && S.state == S_RUNNING);   // trwajaca sesja nie ma jeszcze metadanych
  if (live) sessionFillMeta(m);
  else if (!loadMeta(id, m)) { sendError(404, "no such session"); return; }
  if (id == S.id) storageFlush();

  char p[24]; sessionPath(p, sizeof p, id);
  File f = LittleFS.open(p, "r");
  if (!f) { sendError(404, "no data"); return; }

  JsonDocument o; fillSummary(o.to<JsonObject>(), id, m);
  String head; serializeJson(o, head);
  head.remove(head.length() - 1);           // zdejmij koncowe '}'
  head += ",\"claps\":[";

  sendCors();
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "application/json", "");
  server.sendContent(head);

  f.readStringUntil('\n');                  // naglowek CSV
  String chunk; chunk.reserve(600);
  bool first = true;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    unsigned long t;
    if (sscanf(line.c_str(), "%*lu,%lu", &t) != 1) continue;
    if (!first) chunk += ',';
    first = false;
    chunk += "{\"offset_ms\":"; chunk += t; chunk += '}';
    if (chunk.length() > 500) { server.sendContent(chunk); chunk = ""; }
  }
  f.close();
  chunk += "]}";
  server.sendContent(chunk);
  server.sendContent("");                   // koniec chunked
}

String mimeFor(const String& p) {
  if (p.endsWith(".html")) return "text/html";
  if (p.endsWith(".css"))  return "text/css";
  if (p.endsWith(".js"))   return "application/javascript";
  if (p.endsWith(".json")) return "application/json";
  if (p.endsWith(".svg"))  return "image/svg+xml";
  if (p.endsWith(".png"))  return "image/png";
  if (p.endsWith(".ico"))  return "image/x-icon";
  return "application/octet-stream";
}
bool serveFile(String path) {
  if (path == "/") path = "/index.html";
  if (!LittleFS.exists(path)) return false;
  File f = LittleFS.open(path, "r");
  server.streamFile(f, mimeFor(path));
  f.close();
  return true;
}

void wifiInitRoutes() {
  server.on("/api/status",  HTTP_GET, sendStatus);
  server.on("/api/config",  HTTP_GET, sendConfig);
  server.on("/api/config",  HTTP_PUT, handleConfigWrite);
  server.on("/api/config",  HTTP_POST, handleConfigWrite);
  server.on("/api/session/start", HTTP_POST, []() { sessionCmd(CMD_START); });
  server.on("/api/session/stop",  HTTP_POST, []() { sessionCmd(CMD_STOP); });
  server.on("/api/session/reset", HTTP_POST, []() { sessionCmd(CMD_RESET); });
  server.on("/api/sessions", HTTP_GET, sendSessionList);
  server.on(UriBraces("/api/sessions/{}"), HTTP_GET, sendSessionDetail);
  server.on("/api/time", HTTP_POST, handleTimeSync);
  server.onNotFound([]() {
    Serial.println(server.uri());
    if (server.method() == HTTP_OPTIONS) { sendCors(); server.send(204); return; }
    if (server.method() == HTTP_GET && !server.uri().startsWith("/api") && serveFile(server.uri())) return;
    sendError(404, "not found");
  });
}

void wifiStart() {
  if (wifiOn) return;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_SSID, WIFI_PASS);     // IP: 192.168.4.1
  MDNS.begin("klaskacz");                // http://klaskacz.local
  server.begin();
  wifiOn = true;
}
void wifiStop() {
  if (!wifiOn) return;
  server.stop();
  MDNS.end();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_OFF);
  wifiOn = false;
}