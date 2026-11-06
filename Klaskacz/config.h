#pragma once
#include <Arduino.h>

// I2S (mikrofon SPH0645)
#define PIN_I2S_BCLK   33
#define PIN_I2S_LRCL   25
#define PIN_I2S_DOUT   32
// I2C OLED
#define PIN_OLED_SDA   21
#define PIN_OLED_SCL   22
// Przyciski 
#define PIN_BTN_UP     36
#define PIN_BTN_DOWN   39
#define PIN_BTN_START  34
#define PIN_BTN_RESET  35
// Buzzer aktywny
#define PIN_BUZZER     27
// Bateria
#define PIN_BAT        4

// PARAMETRY
#define WIFI_SSID         "Klaskacz"
#define WIFI_PASS         "haslo1234"   // min. 8 znakow
#define MAX_CLAPS_RAM     2000          // ile ostatnich klasniec trzymamy w RAM
#define FLASH_BATCH       50            // zapis do LittleFS co N klasniec
#define REFRACTORY_MS     50            // minimalny odstep miedzy klasnieciami
#define STATUS_INTERVALS  50            // ile ostatnich odstepow w /api/status
#define AUTO_STOP_MS      0             // 0 = wylaczone; np. 10000 = stop po 10 s ciszy
#define LONG_PRESS_MS     1500
// Detektor (audio.h)
#define AUDIO_FS          16000
#define AUDIO_BLOCK       256           // 16 ms - rozdzielczosc detekcji i czasu
#define FFT_N             1024          // okno FFT (potega 2) - liczone tylko przy kandydacie na klasniecie
#define BASELINE_ALPHA    0.00025f      // adaptacja tla na blok 256 (odpowiada 0.001 dla bloku 1024)
#define BASELINE_MULT     4.0f          // tryb auto: prog = tlo * MULT
#define AUTO_MIN_THR      100.0f        // dolne ograniczenie progu auto
#define WARMUP_BLOCKS     60            // ~1 s po starcie: uczenie tla, bez detekcji
#define CLAP_FREQ_MIN_HZ  0             // bramka czestotliwosci dominujacej (0..8000 = wylaczona)
#define CLAP_FREQ_MAX_HZ  8000
#define BUZZER_GUARD_MS   150           // tyle ms po pisku ignorujemy detekcje (buzzer != klasniecie)

// Prog 1-100 (skala z kontraktu API) -> wartosc surowa 18-bit (skala logarytmiczna).
// Wyzszy prog = trzeba glosniej klasnac (mniejsza czulosc).
#define THR_UI_DEFAULT    60
#define THR_UI_STEP       2
#define THR_RAW_MIN       50.0f         // prog = 1   (skala: srednia |probka| bloku, 18-bit)
#define THR_RAW_MAX       20000.0f      // prog = 100

// TYPY WSPOLNE
enum SessionState { S_IDLE = 0, S_ARMED, S_RUNNING, S_FINISHED };
enum StartMode    { SM_FIRST_CLAP = 0, SM_SIGNAL };
enum Cmd          { CMD_START_STOP, CMD_START, CMD_STOP, CMD_RESET };

struct ClapEvent {
  uint64_t t_us;   // esp_timer_get_time() w chwili detekcji
  uint16_t peak;
};
