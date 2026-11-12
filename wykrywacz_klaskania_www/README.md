# Frontend wykrywacza klaskania

Prototyp interfejsu WWW dla projektu **Wykrywacz klaskania** (ESP32 DevKit V1, mikrofon I2S, OLED, Wi-Fi). Strona napisana w HTML/CSS/JavaScript **bez zewnętrznych bibliotek**.

## Uruchamianie bez ESP32

1. Otwórz `index.html` w przeglądarce.
2. Domyślnie aktywny jest tryb **DEMO** – nie wymaga żadnego sprzętu ani serwera.
3. Kliknij **Rozpocznij**. W trybie autostartu symulacja poczeka na pierwsze klaśnięcie, po czym uruchomi timer.
4. Kliknij **Zatrzymaj**, a następnie przejdź do **Historii sesji** i wybierz **Szczegóły / Eksport CSV**.
5. W **Konfiguracji** możesz zmienić próg i sposób startu – dotyczy to tylko symulacji do czasu podłączenia ESP32.

Przykładowe sesje historyczne są fikcyjne. Nowe sesje DEMO zapisywane są w `localStorage` przeglądarki (nie w pamięci urządzenia). Zmiana progu w DEMO służy prezentacji formularza – symulator generuje klaśnięcia niezależnie od ustawionego progu.

## Uruchamianie przez serwer lokalny (zalecane)

W katalogu z plikami:

```bash
python -m http.server 8000
```

Otwórz `http://localhost:8000`.

## Podłączenie do ESP32

1. Uzgodnić format API.
2. Umieść trzy pliki frontendowe (`index.html`, `styles.css`, `app.js`) w systemie plików ESP32, np. LittleFS, i udostępnij przez serwer HTTP.
3. Połącz telefon z siecią Wi-Fi ESP32; wejdź na adres serwera, np. `http://192.168.4.1`.
4. W **Konfiguracja → Źródło danych** wybierz ESP32 i kliknij **Zastosuj źródło danych**. Jeśli frontend i API są na tym samym serwerze, pole adresu API pozostaw puste.
5. Jeśli strona działa lokalnie na komputerze, a API na innym adresie, ustaw pełny adres `http://...`; ESP32 musi wtedy dopuścić żądania CORS, a przy otwieraniu strony przez HTTPS może działać blokada mixed content. **Najprostsze rozwiązanie: strona i API na ESP32, pod jednym adresem**.

**Ważne:** samo przełączenie na ESP32 nie uruchomi pomiarów – backend HTTP, akwizycja I2S i logika sesji muszą zostać zaimplementowane w firmware. W razie braku połączenia aplikacja sygnalizuje błąd i nie udaje prawdziwych danych.

## Zakres obecnej wersji

- Responsywny interfejs na telefon/komputer.
- Licznik i timer, CPS, średni/ostatni odstęp, wykres 12 ostatnich odstępów.
- Start/stop/reset, wybór trybu startu oraz automatycznego/manualnego progu.
- Historia, szczegóły i lokalny eksport CSV (z zapisanego szczegółowego logu).
- Dwa źródła danych: DEMO i ESP32 (`fetch`, odświeżanie statusu co 500 ms).

## Czego jeszcze nie ma

- Fizycznego połączenia i weryfikacji z ESP32 (wymaga modułu firmware od zespołu).
- Zapisu historii w LittleFS i synchronizacji po okresie offline – to funkcje ESP32; frontend będzie je pobierał przez API.
- Ustalonych na poziomie zespołu jednostek progu detekcji i zegara sesji.
- Produkcyjnej obsługi bezpieczeństwa dla dostępu z obcych sieci; projekt zakłada lokalną, bliskozasięgową komunikację z urządzeniem.

## Pliki

```text
index.html        struktura strony
styles.css        styl i układ responsywny
app.js            logika, symulacja i komunikacja API
API_CONTRACT.md   propozycja interfejsów dla firmware
README.md         instrukcja uruchomienia
```
