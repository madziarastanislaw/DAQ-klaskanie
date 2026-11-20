#pragma once
#include "config.h"
#include "rawdump.h"
#include "driver/i2s_std.h"
#include "esp_timer.h"
#include <math.h>
#include <arduinoFFT.h>

#ifndef LOUD_OFF_RATIO
#define LOUD_OFF_RATIO 0.6f
#endif
#ifndef RISE_RATIO
#define RISE_RATIO 1.5f
#endif
#ifndef RISE_MIN_FRAC
#define RISE_MIN_FRAC 0.25f
#endif
#ifndef BASELINE_FREEZE_MS
#define BASELINE_FREEZE_MS 300
#endif

QueueHandle_t clapQueue;

inline uint32_t thrUiToRaw(uint8_t ui) {
  return (uint32_t)(THR_RAW_MIN * powf(THR_RAW_MAX / THR_RAW_MIN, (ui - 1) / 99.0f));
}
volatile uint8_t gThrUi = THR_UI_DEFAULT;
volatile uint32_t gThreshold = 0;
volatile bool gAutoSens = false;
volatile uint32_t gEffThr = 0;
volatile uint16_t gLastPeak = 0;
volatile float gBaseline = 0;
volatile float gFreq = 0;

void configApplyThreshold(int ui) {
  if (ui < 1) ui = 1;
  if (ui > 100) ui = 100;
  gThrUi = ui;
  gThreshold = thrUiToRaw(ui);
}

static float vReal[FFT_N];
static float vImag[FFT_N];
static ArduinoFFT<float> fft(vReal, vImag, FFT_N, (float)AUDIO_FS);
static int32_t fftWin[FFT_N];
static uint16_t fftWinIdx = 0;

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
  i2s_channel_init_std_mode(rx_handle, &std_cfg);
}

// ---------- detektor ----------
void audioTask(void*) {
  static int32_t buf[AUDIO_BLOCK];
  int32_t dc = 0;
  float baseline = 0;
  float prevA = 0;
  uint32_t blocks = 0;
  uint32_t lastClapMs = 0;

  i2s_channel_enable(rx_handle);

  for (;;) {
    size_t bytes = 0;
    i2s_channel_read(rx_handle, buf, sizeof(buf), &bytes, portMAX_DELAY);
    uint64_t t_us = esp_timer_get_time();
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
    rawdumpAudio(buf, n, t_us);  // zrzut surowych probek przez UART (tylko gdy wlaczony 'R')
    gLastPeak = A > 65535 ? 65535 : (uint16_t)A;
    if (blocks == 0) {
      baseline = A;
      prevA = A;
    }

    //próg

    uint32_t thr = gThreshold;
    if (gAutoSens) {
      float t = baseline * BASELINE_MULT;
      if (t < AUTO_MIN_THR) {
        t = AUTO_MIN_THR;
      }
      thr = (uint32_t)t;
    }
    gEffThr = thr;


    ////////////////////////////

    uint32_t nowMs = (uint32_t)(t_us / 1000ULL);
    bool warm = (blocks > WARMUP_BLOCKS);


    //główna logika wykrywania 
    bool aboveThr = (A > thr);

    bool trigger = warm && aboveThr;

    if (trigger && (nowMs - lastClapMs) > REFRACTORY_MS) {
      float f = estimateFrequencyFFT();
      gFreq = f;
      bool accepted = (f >= CLAP_FREQ_MIN_HZ && f <= CLAP_FREQ_MAX_HZ);
      rawdumpEvent(t_us, A, (float)thr, baseline, f, accepted);
      if (accepted) {
        lastClapMs = nowMs;
        ClapEvent ev = { t_us, gLastPeak };
        xQueueSend(clapQueue, &ev, 0);
      }
    }

    ///////////////////////////
    prevA = A;

    if (!warm) {
      baseline = baseline * (1 - BASELINE_ADAPTATION) + A * BASELINE_ADAPTATION;
    }
    
    gBaseline = baseline;
    blocks++;
  }
}