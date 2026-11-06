#pragma once
// Zadanie audio (rdzen 1): I2S + detektor klasniec.
// Oparty na szkicu testowym mikrofonu: poziom A = srednia |probka| (po >>14),
// tlo adaptacyjne (ALPHA, MULT) i dominujaca czestotliwosc z FFT (arduinoFFT 2.x).
// Roznice wzgledem szkicu testowego:
//  - A liczone PO usunieciu skladowej stalej (SPH0645 ma duze DC),
//  - bloki 256 probek (16 ms) zamiast 1024 (64 ms) -> dokladniejszy czas klasniec,
//  - FFT liczone tylko gdy jest kandydat na klasniecie (okno ostatnich 1024 probek),
//  - detekcja na zboczu narastajacym (jedno klasniecie = jedno zdarzenie, bez podwojnych),
//  - tlo uczone przed porownaniem i z rozgrzewka (WARMUP_BLOCKS).
#include "config.h"
#include "driver/i2s.h"
#include "esp_timer.h"
#include <math.h>
#include <arduinoFFT.h>

QueueHandle_t clapQueue;

// Mapowanie progu 1-100 (UI / API) na wartosc surowa detektora (skala A)
inline uint32_t thrUiToRaw(uint8_t ui) {
  return (uint32_t)(THR_RAW_MIN * powf(THR_RAW_MAX / THR_RAW_MIN, (ui - 1) / 99.0f));
}
volatile uint8_t  gThrUi     = THR_UI_DEFAULT;
volatile uint32_t gThreshold = 0;            // surowy, ustawiany w configApplyThreshold()
volatile bool     gAutoSens  = false;        // true = prog = tlo * BASELINE_MULT
volatile uint32_t gEffThr    = 0;
volatile uint16_t gLastPeak  = 0;            // ostatni poziom A
volatile float    gBaseline  = 0;
volatile float    gFreq      = 0;

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
static int32_t fftWin[FFT_N];                // okno kolowe ostatnich probek
static uint16_t fftWinIdx = 0;               // wskazuje najstarsza probke

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
void audioInit() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = AUDIO_FS;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;     // SEL -> GND = lewy kanal
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_I2S_BCLK;
  pins.ws_io_num = PIN_I2S_LRCL;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_I2S_DOUT;
  i2s_set_pin(I2S_NUM_0, &pins);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

// ---------- detektor ----------
void audioTask(void*) {
  static int32_t buf[AUDIO_BLOCK];
  int32_t dc = 0;
  float baseline = 0;
  uint32_t blocks = 0;
  bool prevLoud = false;
  uint32_t lastClapMs = 0;

  for (;;) {
    size_t bytes = 0;
    i2s_read(I2S_NUM_0, buf, sizeof(buf), &bytes, portMAX_DELAY);
    uint64_t t_us = esp_timer_get_time();     // znacznik czasu OD RAZU po odczycie bloku
    int n = bytes / 4;
    if (n <= 0) continue;

    int64_t sumAbs = 0;
    for (int i = 0; i < n; i++) {
      int32_t s = buf[i] >> 14;               // 18-bit
      fftWin[fftWinIdx] = s;
      fftWinIdx = (fftWinIdx + 1) % FFT_N;
      dc += (s - dc) >> 8;                    // usuwanie skladowej stalej
      sumAbs += abs(s - dc);
    }
    float A = (float)sumAbs / n;
    gLastPeak = A > 65535 ? 65535 : (uint16_t)A;
    if (blocks == 0) baseline = A;

    // prog: reczny (z API/przyciskow) albo automatyczny (tlo * MULT)
    uint32_t thr = gThreshold;
    if (gAutoSens) {
      float t = baseline * BASELINE_MULT;
      if (t < AUTO_MIN_THR) t = AUTO_MIN_THR;
      thr = (uint32_t)t;
    }
    gEffThr = thr;

    bool loud = (blocks > WARMUP_BLOCKS) && (A > thr);
    uint32_t nowMs = (uint32_t)(t_us / 1000ULL);
    if (loud && !prevLoud && (nowMs - lastClapMs) > REFRACTORY_MS) {
      float f = estimateFrequencyFFT();       // FFT tylko dla kandydata
      gFreq = f;
      if (f >= CLAP_FREQ_MIN_HZ && f <= CLAP_FREQ_MAX_HZ) {
        lastClapMs = nowMs;
        ClapEvent ev = { t_us, gLastPeak };
        xQueueSend(clapQueue, &ev, 0);
      }
    }
    prevLoud = loud;

    // tlo uczymy PO porownaniu (klasniecie nie podnosi progu w tym samym bloku)
    float alpha = (blocks < WARMUP_BLOCKS) ? 0.05f : BASELINE_ALPHA;
    baseline = baseline * (1 - alpha) + A * alpha;
    gBaseline = baseline;
    blocks++;
  }
}