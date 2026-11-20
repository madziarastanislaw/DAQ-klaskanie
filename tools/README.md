# Nagrania i uczenie detektora klaśnięć

Trzy części:

| Część | Gdzie | Rola |
|---|---|---|
| Zrzut audio w firmware | `Klaskacz/rawdump.h` | wysyła przez UART dokładnie te próbki, które widzi detektor, oraz decyzje obecnego detektora |
| Nagrywarka | `tools/recorder/record.py` | odbiera strumień, zapisuje `audio.wav`, `events.csv`, `meta.json` |
| Uczenie i ocena | `tools/clapml/` | kandydaci → cechy → model → ocena → `clap_model.h` |

Instalacja (Python 3.10+):

```powershell
pip install -r tools/requirements.txt
```

## 1. Nagrywanie

Firmware: `Serial` działa teraz z prędkością `SERIAL_BAUD` = 921600 (`config.h`). W monitorze portu szeregowego ustaw tę samą prędkość. Znak `R` włącza i wyłącza zrzut. Nagrywarka wysyła go sama. Podczas zrzutu firmware nie wypisuje innego tekstu na port. Zamknij monitor portu w Arduino IDE, bo port może mieć otwarty tylko jeden program.

```powershell
python tools/recorder/record.py --port COM5 --seconds 30 --expected-claps 10 --scenario klaski --person A --distance 1 --room sala1
```

Bez `--seconds` nagrywanie trwa do Ctrl+C. Wynik trafia do `recordings/<data>_<scenariusz>/`:

- `audio.wav`: 24 bit, 16 kHz. Wartość próbki to `buf >> 14`, czyli 18 bitów, więc w Audacity nagranie jest ciche.
- `events.csv`: kandydaci obecnego detektora; `accepted=1` oznacza klaśnięcie policzone przez urządzenie.
- `meta.json`: opis nagrania i statystyka transmisji. `lost_blocks` i `crc_errors` powinny wynosić 0.

Nagrania bez klaśnięć (mowa, muzyka, klawiatura, stukanie, drzwi) nagrywaj z `--expected-claps 0`. Nie trzeba ich oznaczać, a to z nich model uczy się, czego nie zgłaszać.

## 2. Etykiety: ile i kiedy

Są dwa poziomy etykiet:

1. **`expected_claps` w `meta.json`**: ile klaśnięć było w nagraniu. Wystarcza dla nagrań bez klaśnięć (0). Daje też metrykę „czy policzono dokładnie tyle, ile trzeba”. Liczbę można poprawić ręcznie w pliku.
2. **`labels.txt`**: kiedy dokładnie było każde klaśnięcie. To jest prawda do uczenia i do pomiaru błędu czasu.

Żeby nie stawiać każdej etykiety od zera:

```powershell
cd tools
python -m clapml draft ../recordings
```

Polecenie w każdym nagraniu z `expected_claps > 0` bez `labels.txt` wybiera N najsilniejszych impulsów i zapisuje je w `labels_draft.txt`. Potem w Audacity:

1. Otwórz `audio.wav`; Plik → Importuj → Etykiety → `labels_draft.txt`.
2. Popraw etykiety: przesuń na początek impulsu, usuń błędne, dodaj brakujące. Przyda się widok spektrogramu i powiększenie w pionie.
3. Plik → Eksportuj → Eksportuj etykiety → `labels.txt` w katalogu nagrania.

Każda etykieta to jedno klaśnięcie, liczy się jej początek. Tekst zaczynający się od `?` oznacza przypadek niepewny i jest pomijany w uczeniu. Po pierwszym modelu szkice będą lepsze: `python -m clapml draft ../recordings --model ../models/model.joblib`.

## 3. Uczenie i ocena

```powershell
python -m clapml baseline ../recordings --thr 60
```

```powershell
python -m clapml train ../recordings -o ../models
```

```powershell
python -m clapml eval ../recordings --model ../models/model.joblib
```

- `baseline` odtwarza obecny detektor z `audio.h` na nagraniach. To punkt odniesienia. Przy `--auto` używa trybu automatycznej czułości.
- `train` robi kilka rzeczy:
  - wyszukuje kandydatów (szybkie wzrosty energii po filtrze 300 Hz) i liczy dla nich 14 cech (`features.py`);
  - dopasowuje kandydatów do etykiet w tolerancji ±20 ms;
  - uczy regresję logistyczną, albo drzewo przy `--kind tree`;
  - sprawdza model walidacją krzyżową **po osobach** (`--person`) i wybiera próg;
  - zapisuje `model.joblib`, `report.json`, `features.csv` oraz `clap_model.h` z funkcją `clapIsClap(const float* features)` gotową do ESP32.
- `--min-precision 0.98` wybiera próg, który daje mało fałszywych alarmów kosztem pominięć.
- `eval` liczy metryki na poziomie zdarzeń: precision, recall, F1, fałszywe alarmy na minutę w nagraniach bez klaśnięć, odsetek nagrań z dokładnie poprawną liczbą klaśnięć oraz błąd czasu w ms.

Uczciwe są tylko wyniki walidacji krzyżowej z `train` i `eval` na nagraniach, których model nie widział. Najprościej trzymać osobny katalog, np. `recordings_test/`, nagrany przez inne osoby albo w innej sali.

`python -m clapml dataset ../recordings -o cechy.csv` zapisuje tabelę cech, np. do wykresów rozkładów (klaśnięcia vs reszta).

## Co jeszcze nie jest zrobione

`clap_model.h` zawiera tylko klasyfikator. Żeby działał na ESP32, trzeba przenieść do C++ wyszukiwanie kandydatów i liczenie cech z `features.py` (biquad, obwiednia 2 ms, FFT 512). Potem warto sprawdzić, że dla tego samego WAV-a PC i urządzenie dają te same cechy.
