#pragma once
// Zadanie audio (rdzen 1): I2S + detektor klasniec.
// Oparty na szkicu testowym mikrofonu: poziom A = srednia |probka| (po >>14),
// tlo adaptacyjne (ALPHA, MULT) i dominujaca czestotliwosc z FFT (arduinoFFT 2.x).
// Roznice wzgledem szkicu testowego:
//  - A liczone PO usunieciu skladowej stalej (SPH0645 ma duze DC),
//  - bloki 256 probek (16 ms) zamiast 1024 (64 ms) -> dokladniejszy czas klasniec,
//  - FFT liczone tylko gdy jest kandydat na klasniecie (okno ostatnich 1024 probek),
//  - tlo uczone przed porownaniem i z rozgrzewka (WARMUP_BLOCKS).
// Zmiany pod szybkie serie klasniec:
//  - histereza stanu "glosno" (wlaczenie > thr, wylaczenie < thr * LOUD_OFF_RATIO),
//  - kandydat na klasniecie = przekroczenie progu NA ZBOCZU albo gwaltowny wzrost A
//    wzgledem poprzedniego bloku (drugie klasniecie na "ogonie" pierwszego tez zadziala),
//  - tlo jest (prawie) zamrazane gdy jest glosno i przez BASELINE_FREEZE_MS po klasnieciu,
//    dzieki czemu seria klasniec nie podnosi progu w trybie auto.
#include "config.h"
#include "driver/i2s_std.h"
#include "esp_timer.h"
#include <math.h>
#include <arduinoFFT.h>

#ifndef LOUD_OFF_RATIO
#define LOUD_OFF_RATIO 0.6f  // stan "glosno" wylacza sie dopiero gdy A < thr * ta wartosc
#endif
#ifndef RISE_RATIO
#define RISE_RATIO 1.5f  // A musi byc > prevA * RISE_RATIO, by uznac gwaltowny wzrost
#endif
#ifndef RISE_MIN_FRAC
#define RISE_MIN_FRAC 0.25f  // oraz urosnac o co najmniej thr * ta wartosc (odporne na szum)
#endif
#ifndef BASELINE_FREEZE_MS
#define BASELINE_FREEZE_MS 300  // tlo zamrozone tyle ms po zaakceptowanym klasnieciu
#endif
#ifndef BASELINE_FROZEN_FACTOR
#define BASELINE_FROZEN_FACTOR 0.00f  // w zamrozeniu tlo uczy sie tyle razy wolniej (nie 0, zeby
                                      // trwale wzrosniety halas w koncu podniosl tlo)
#endif

QueueHandle_t clapQueue;

// Mapowanie progu 1-100 (UI / API) na wartosc surowa detektora (skala A)
inline uint32_t thrUiToRaw(uint8_t ui) {
  return (uint32_t)(THR_RAW_MIN * powf(THR_RAW_MAX / THR_RAW_MIN, (ui - 1) / 99.0f));
}
volatile uint8_t gThrUi = THR_UI_DEFAULT;
volatile uint32_t gThreshold = 0;  // surowy, ustawiany w configApplyThreshold()
volatile bool gAutoSens = false;   // true = prog = tlo * BASELINE_MULT
volatile uint32_t gEffThr = 0;
volatile uint16_t gLastPeak = 0;  // ostatni poziom A
volatile float gBaseline = 0;
volatile float gFreq = 0;

void configApplyThreshold(int ui) {
  if (ui < 1) ui = 1;
  if (ui > 100) ui = 100;
  gThrUi = ui;
  gThreshold = thrUiToRaw(ui);
}

// ---------- FFT ----------
static float vReal[FFT_N];
static float vImag[FFT_N];
static ArduinoFFT<float> fft(vReal, vImag, FFT_N, (float)AUDIO_FS);
static int32_t fftWin[FFT_N];   // okno kolowe ostatnich probek
static uint16_t fftWinIdx = 0;  // wskazuje najstarsza probke

float estimateFrequencyFFT() {
  for (int i = 0; i < FFT_N; i++) {
    vReal[i] = (float)fftWin[(fftWinIdx + i) % FFT_N];
    vImag[i] = 0.0f;
  }
  fft.dcRemoval();
  fft.windowing(FFTWindow::Hamming, FFTDirection::Forward);
  fft.compute(FFTDirection::Forward);
  fft.complexToMagnitude();
  return fft.majorPeak();
}

// ---------- I2S ----------
i2s_chan_handle_t rx_handle;
void audioInit() {
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  i2s_new_channel(&chan_cfg, NULL, &rx_handle);

  i2s_std_config_t std_cfg = {
    .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000),
    .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = PIN_I2S_BCLK,
      .ws = PIN_I2S_LRCL,
      .dout = I2S_GPIO_UNUSED,
      .din = PIN_I2S_DOUT,
      .invert_flags = {
        .mclk_inv = false,
        .bclk_inv = false,
        .ws_inv = false,
      },
    },
  };
  /* Initialize the channel */
  i2s_channel_init_std_mode(rx_handle, &std_cfg);
}

// ---------- detektor ----------
void audioTask(void*) {
  static int32_t buf[AUDIO_BLOCK];
  int32_t dc = 0;
  float baseline = 0;
  float prevA = 0;
  uint32_t blocks = 0;
  bool loudState = false;  // stan "glosno" z histereza
  uint32_t lastClapMs = 0;

  /* Before reading data, start the RX channel first */
  i2s_channel_enable(rx_handle);

  for (;;) {
    size_t bytes = 0;
    i2s_channel_read(rx_handle, buf, sizeof(buf), &bytes, portMAX_DELAY);
    uint64_t t_us = esp_timer_get_time();  // znacznik czasu OD RAZU po odczycie bloku
    int n = bytes / 4;
    if (n <= 0) continue;

    int64_t sumAbs = 0;
    for (int i = 0; i < n; i++) {
      int32_t s = buf[i] >> 14;  // 18-bit
      fftWin[fftWinIdx] = s;
      fftWinIdx = (fftWinIdx + 1) % FFT_N;
      dc += (s - dc) >> 8;  // usuwanie skladowej stalej
      sumAbs += abs(s - dc);
    }
    float A = (float)sumAbs / n;
    gLastPeak = A > 65535 ? 65535 : (uint16_t)A;
    if (blocks == 0) {
      baseline = A;
      prevA = A;
    }

    // prog: reczny (z API/przyciskow) albo automatyczny (tlo * MULT)
    uint32_t thr = gThreshold;
    if (gAutoSens) {
      float t = baseline * BASELINE_MULT;
      if (t < AUTO_MIN_THR) t = AUTO_MIN_THR;
      thr = (uint32_t)t;
    }
    gEffThr = thr;

    uint32_t nowMs = (uint32_t)(t_us / 1000ULL);
    bool warm = (blocks > WARMUP_BLOCKS);

    // --- stan "glosno" z histereza ---
    bool wasLoud = loudState;
    bool aboveThr = (A > thr);
    if (aboveThr) {
      loudState = true;
    } else if (A < thr * LOUD_OFF_RATIO) {
      loudState = false;
    }  // pomiedzy progami stan sie utrzymuje

    // --- kandydat: zbocze narastajace LUB gwaltowny wzrost poziomu ---
    bool rising = (A > prevA * RISE_RATIO) && ((A - prevA) > thr * RISE_MIN_FRAC);
    bool trigger = warm && aboveThr && (!wasLoud || rising);

    if (trigger && (nowMs - lastClapMs) > REFRACTORY_MS) {
      float f = estimateFrequencyFFT();  // FFT tylko dla kandydata
      gFreq = f;
      if (f >= CLAP_FREQ_MIN_HZ && f <= CLAP_FREQ_MAX_HZ) {
        lastClapMs = nowMs;
        ClapEvent ev = { t_us, gLastPeak };
        xQueueSend(clapQueue, &ev, 0);
      }
    }
    prevA = A;

    // tlo uczymy PO porownaniu. Podczas glosnego stanu i tuz po klasnieciu tlo jest
    // zamrozone (uczy sie tylko BASELINE_FROZEN_FACTOR razy wolniej), zeby seria
    // klasniec nie podnosila progu w trybie auto. W rozgrzewce uczymy normalnie.
    float alpha;
    if (!warm) {
      alpha = 0.05f;
    } else {
      bool frozen = loudState || ((nowMs - lastClapMs) < BASELINE_FREEZE_MS);
      alpha = frozen ? BASELINE_ALPHA * BASELINE_FROZEN_FACTOR : BASELINE_ALPHA;
    }
    baseline = baseline * (1 - alpha) + A * alpha;
    gBaseline = baseline;
    blocks++;
  }
}