#pragma once
// Zrzut surowego audio przez UART -> komputer (tools/recorder/record.py).
// Sluzy WYLACZNIE do zbierania nagran do analizy / uczenia modelu.
//
// Przeplyw danych:
//   audioTask (rdzen 1, prio 5) --rawdumpAudio()/rawdumpEvent()--> StreamBuffer
//   rawdumpTask (rdzen 0, prio 2) --Serial.write()--> UART --> komputer
// audioTask nigdy nie czeka na UART: jesli bufor jest pelny, ramka jest
// pomijana, a licznik "dropped" rosnie (komputer widzi tez dziure w seq).
//
// Wlaczanie / wylaczanie: znak 'R' na porcie szeregowym (patrz serialCommands()).
// Podczas zrzutu inne wypisywanie tekstu na Serial jest wstrzymane.
//
// Format ramki (little-endian):
//   off len
//   0   4   magic "KLSK"
//   4   1   typ: 1 = blok audio, 2 = zdarzenie detektora
//   5   1   wersja formatu = 1
//   6   2   L = dlugosc payloadu
//   8   L   payload
//   8+L 2   CRC-16/CCITT-FALSE liczone z bajtow 0 .. 8+L-1
//
// Payload audio (typ 1):
//   u32 seq       numer bloku (rosnie o 1 na kazdy blok odczytany z I2S)
//   u64 t_us      esp_timer_get_time() tuz po odczycie bloku (= ClapEvent.t_us)
//   u32 dropped   ile ramek pominieto od wlaczenia zrzutu (pelny bufor)
//   u16 n         liczba probek
//   n * 3 bajty   probki int24 = dokladnie wartosc "s = buf[i] >> 14" z detektora
//
// Payload zdarzenia (typ 2) - kandydat na klasniecie z obecnego detektora:
//   u32 seq       numer bloku, w ktorym wystapil (ten sam co w ramce audio)
//   u64 t_us
//   f32 A, f32 thr, f32 baseline, f32 freq
//   u8  flags     bit0 = zaakceptowany (wyslany do clapQueue), 0 = odrzucony bramka FFT
#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/stream_buffer.h"
#include "config.h"

#ifndef RAWDUMP_SB_BYTES
#define RAWDUMP_SB_BYTES 16384  // ~0.3 s audio; przetrzymuje chwilowe zatory UART
#endif

#define RAWDUMP_TYPE_AUDIO 1
#define RAWDUMP_TYPE_EVENT 2
#define RAWDUMP_VERSION    1
#define RAWDUMP_HDR        8
#define RAWDUMP_AUDIO_FIXED (4 + 8 + 4 + 2)
#define RAWDUMP_EVENT_LEN   (4 + 8 + 4 * 4 + 1)
#define RAWDUMP_MAX_FRAME   (RAWDUMP_HDR + RAWDUMP_AUDIO_FIXED + AUDIO_BLOCK * 3 + 2)

static StreamBufferHandle_t rdSb = nullptr;
static volatile bool rdActive = false;
static volatile uint32_t rdDropped = 0;
static uint32_t rdSeq = 0;      // numer biezacego bloku (zapisywany tylko w audioTask)

inline bool rawdumpActive() { return rdActive; }

static uint16_t rdCrc16(const uint8_t* p, size_t n) {
  uint16_t crc = 0xFFFF;
  while (n--) {
    crc ^= (uint16_t)(*p++) << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

static inline uint8_t* rdPut(uint8_t* p, const void* v, size_t n) { memcpy(p, v, n); return p + n; }

// Dokleja naglowek i CRC, wrzuca cala ramke do bufora albo ja pomija (nigdy czesciowo).
// Wolane tylko z audioTask (jedyny pisarz StreamBuffer - wymog FreeRTOS).
static void rdSend(uint8_t* frame, uint8_t type, uint16_t payloadLen) {
  frame[0] = 'K'; frame[1] = 'L'; frame[2] = 'S'; frame[3] = 'K';
  frame[4] = type;
  frame[5] = RAWDUMP_VERSION;
  memcpy(frame + 6, &payloadLen, 2);
  size_t len = RAWDUMP_HDR + payloadLen;
  uint16_t crc = rdCrc16(frame, len);
  memcpy(frame + len, &crc, 2);
  len += 2;
  if (xStreamBufferSpacesAvailable(rdSb) < len) { rdDropped++; return; }
  xStreamBufferSend(rdSb, frame, len, 0);
}

// Wolane z audioTask raz na blok, PRZED logika detekcji.
void rawdumpAudio(const int32_t* buf, int n, uint64_t t_us) {
  rdSeq++;
  if (!rdActive || !rdSb) return;
  if (n > AUDIO_BLOCK) n = AUDIO_BLOCK;
  static uint8_t frame[RAWDUMP_MAX_FRAME];
  uint8_t* p = frame + RAWDUMP_HDR;
  uint32_t seq = rdSeq, dropped = rdDropped;
  uint16_t nn = (uint16_t)n;
  p = rdPut(p, &seq, 4);
  p = rdPut(p, &t_us, 8);
  p = rdPut(p, &dropped, 4);
  p = rdPut(p, &nn, 2);
  for (int i = 0; i < n; i++) {
    int32_t s = buf[i] >> 14;  // identycznie jak w detektorze
    *p++ = (uint8_t)(s);
    *p++ = (uint8_t)(s >> 8);
    *p++ = (uint8_t)(s >> 16);
  }
  rdSend(frame, RAWDUMP_TYPE_AUDIO, (uint16_t)(p - frame - RAWDUMP_HDR));
}

// Wolane z audioTask dla kazdego kandydata na klasniecie (zaakceptowanego lub nie).
void rawdumpEvent(uint64_t t_us, float A, float thr, float baseline, float freq, bool accepted) {
  if (!rdActive || !rdSb) return;
  static uint8_t frame[RAWDUMP_HDR + RAWDUMP_EVENT_LEN + 2];
  uint8_t* p = frame + RAWDUMP_HDR;
  uint32_t seq = rdSeq;
  uint8_t flags = accepted ? 1 : 0;
  p = rdPut(p, &seq, 4);
  p = rdPut(p, &t_us, 8);
  p = rdPut(p, &A, 4);
  p = rdPut(p, &thr, 4);
  p = rdPut(p, &baseline, 4);
  p = rdPut(p, &freq, 4);
  p = rdPut(p, &flags, 1);
  rdSend(frame, RAWDUMP_TYPE_EVENT, RAWDUMP_EVENT_LEN);
}

static void rawdumpTask(void*) {
  static uint8_t tmp[1024];
  for (;;) {
    size_t n = xStreamBufferReceive(rdSb, tmp, sizeof(tmp), pdMS_TO_TICKS(50));
    if (n) Serial.write(tmp, n);
  }
}

// Wywolac w setup() PO Serial.begin().
void rawdumpInit() {
  rdSb = xStreamBufferCreate(RAWDUMP_SB_BYTES, 1);
  xTaskCreatePinnedToCore(rawdumpTask, "rawdump", 3072, NULL, 2, NULL, 0);
}

void rawdumpSetActive(bool on) {
  if (on == rdActive) return;
  if (on) {
    Serial.println("RAWDUMP ON");  // tekst przed pierwsza ramka; komputer go pomija
    Serial.flush();
    rdDropped = 0;
  }
  rdActive = on;
}
