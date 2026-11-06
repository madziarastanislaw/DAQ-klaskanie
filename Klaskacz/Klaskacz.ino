#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <driver/i2s.h>
#include <arduinoFFT.h>

// ===== PINY (sprawdź z połączeniami na płytce) =====
#define BUZZER_PIN  27
#define I2S_BCLK    33
#define I2S_LRCL    25
#define I2S_DOUT    32
// OLED SH1106 (I2C): SDA = GPIO21, SCL = GPIO22 domyślnie na ESP32
// UWAGA: jeśli OLED jest na GPIO22/21, nie kolidują z I2S tylko gdy I2S_DOUT != 21/22

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

unsigned long lastBeep = 0;
bool buzzerOn = false;

void setupI2S() {
  i2s_config_t cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,   // SEL do GND = lewy kanał
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pins = {
    .bck_io_num = I2S_BCLK,
    .ws_io_num = I2S_LRCL,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_DOUT
  };

  i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pins);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  u8g2.begin();
  u8g2.setFont(u8g2_font_ncenB10_tr);

  setupI2S();
}

void loop() {
  // --- Buzzer: piknięcie co 3 s ---
  unsigned long now = millis();
  if (!buzzerOn && now - lastBeep >= 3000) {
    digitalWrite(BUZZER_PIN, HIGH);
    buzzerOn = true;
    lastBeep = now;
  } else if (buzzerOn && now - lastBeep >= 150) {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerOn = false;
  }

  // --- Odczyt z mikrofonu ---
 static int32_t buf[1024];
size_t bytesRead = 0;
i2s_read(I2S_NUM_0, buf, sizeof(buf), &bytesRead, portMAX_DELAY);
int n = bytesRead / sizeof(int32_t);

float f = estimateFrequencyFFT(buf, n);
  long long sum = 0;
  for (int i = 0; i < n; i++) {
    sum += labs(buf[i] >> 14);   // SPH0645 daje 24 bity wyrównane do 32
  }
  long avg = (n > 0) ? (long)(sum / n) : 0;

  // --- Wyświetlanie ---
  char txt[32];
  snprintf(txt, sizeof(txt), "Hz: %.0f", f);
  Serial.println(avg);

  int barWidth = constrain(avg / 20, 0, 126);   // skala do kalibracji

  u8g2.clearBuffer();
  u8g2.drawStr(0, 20, txt);
  u8g2.drawFrame(0, 35, 128, 14);
  u8g2.drawBox(1, 36, barWidth, 12);
  u8g2.sendBuffer();
}



const uint16_t FFT_N = 1024;      // musi być potęgą dwójki
const float FFT_FS = 16000.0f;    // częstotliwość próbkowania

float vReal[FFT_N];
float vImag[FFT_N];
ArduinoFFT<float> fft(vReal, vImag, FFT_N, FFT_FS);

// Zwraca dominującą częstotliwość w Hz z bufora I2S
float estimateFrequencyFFT(int32_t *buf, int n) {
  if (n < 2) return 0;

  // 1. Przepisz próbki do bufora FFT i usuń składową stałą (DC)
  long long sum = 0;
  for (int i = 0; i < FFT_N; i++) {
    int32_t s = (i < n) ? (buf[i] >> 14) : 0;
    vReal[i] = s;
    sum += s;
  }
  float mean = (float)sum / FFT_N;
  for (int i = 0; i < FFT_N; i++) {
    vReal[i] -= mean;
    vImag[i] = 0.0f;               // część urojona zawsze zerowa dla sygnału rzeczywistego
  }
  fft.dcRemoval();

  // 2. Okno Hamminga ogranicza przecieki widma
  fft.windowing(FFTWindow::Hamming, FFTDirection::Forward);

  // 3. FFT, a potem moduł każdego prążka
  fft.compute(FFTDirection::Forward);
  fft.complexToMagnitude();

  // 4. Szukaj prążka o największej amplitudzie
  return fft.majorPeak();
}