# Weryfikacja frontendu

Testy używają prawdziwego Chrome headless i lokalnego mock API. Nie wymagają instalowania pakietów npm. Mock odwzorowuje metody, JSON i przejścia stanów z `Klaskacz/api.h`, `session.h`, `config.h` i `Klaskacz.ino`; nie testuje wykonania firmware.

Uruchomienie z katalogu repozytorium (Node.js 22+ i Chrome):

```powershell
node tests/frontend.mjs
```

Domyślna ścieżka przeglądarki to `C:\Program Files\Google\Chrome\Application\chrome.exe`. Inny Chrome lub Edge można wskazać zmienną `CHROME_PATH`. Serwer nasłuchuje wyłącznie na `127.0.0.1`, na wolnym porcie. Profil przeglądarki i zrzut ekranu powstają w nowym katalogu tymczasowym; ścieżka jest wypisywana w wynikach. Test zamyka przeglądarkę i serwer.

## Wykonane testy z mockiem

Weryfikacja w Chrome headless obejmuje:

- DEMO z `file://` oraz z serwera HTTP bez API; przełączanie zakładek, Start/Stop/Reset, oba tryby startu, historię symulowanych sesji.
- Automatyczne wykrywanie API tego samego serwera mimo wcześniej zapisanego innego adresu. Odrzucanie odpowiedzi bez wymaganych pól statusu.
- Ręczny wybór źródła danych, czyszczenie szczegółów i zastępowanie historii podczas zmiany źródła.
- Wszystkie stany `idle`, `armed`, `running`, `finished`; anulowanie `armed` przez Stop wraca do `idle`, zgodnie z firmware.
- Statystyki statusu, wykres oraz `null` w średnim/ostatnim odstępie.
- `GET /api/config`, `PUT /api/config`, auto/manual, próg, oba tryby startu. Ochronę niezapisanych pól przed odświeżaniem co 500 ms.
- `POST /api/session/start`, `/stop`, `/reset`, pobranie historii jako `{sessions: [...]}` i szczegółów jako obiektu z `claps[].offset_ms`.
- Wyświetlanie „Data nieznana” dla brakującej/niepoprawnej daty, poprawne przesunięcia ISO i ochronę przed przekroczeniem zakresu dat.
- Zawartość CSV z datą oraz bez daty. Bez daty kolumna ISO jest pusta, a offsety i odstępy nadal są eksportowane. Test przechwytuje Blob i nazwę pobieranego pliku, bez zapisywania pobrania na dysku.
- Utratę połączenia bez przejścia na dane DEMO, powrót połączenia i odblokowanie po timeout 4 s.
- `POST /api/time` z aktualnym `Date.now()` tylko przy braku synchronizacji. Po błędzie maksymalnie dwie dodatkowe próby, po 5 i 15 s od poprzedniego błędu (łącznie 3 próby na połączenie). Test sprawdza odstępy między żądaniami, wyczerpanie limitu oraz udane ponowienie przy stale dostępnym statusie. Potwierdzenie zegara pochodzi z `time_synced` w następnym statusie.
- Zatrzymanie ponowień po `time_synced: true`, pomijanie synchronizacji po ponownym połączeniu z urządzeniem z ustawionym zegarem, blokadę równoczesnych żądań i anulowanie trwającej synchronizacji przy zmianie źródła na DEMO. Limit prób resetuje się po utracie połączenia lub zastosowaniu źródła danych.
- Dłuższe timeouty: status i pozostałe operacje 4 s, lista sesji 15 s, szczegóły sesji 30 s. Timer obejmuje również odczyt całego ciała odpowiedzi. Mock wysyła porcjami listę 50 sesji przez 6 s i szczegóły zawierające 10 000 klaśnięć przez 7 s; test potwierdza pobranie całości, działanie statusu i możliwość przełączania zakładek podczas oczekiwania.
- Odrzucanie opóźnionego statusu starego połączenia i ochronę ręcznego wyboru przed opóźnionym automatycznym wykrywaniem.
- Brak nieobsłużonych wyjątków JavaScript, zgodność statycznych identyfikatorów DOM oraz identyczność bajtową HTML/CSS/JS w obu katalogach.
- Emulację rozmiaru telefonu 320 i 390 px: wszystkie zakładki bez poziomego przewijania całej strony. To test przeglądarkowy, nie test fizycznego telefonu.

Dodatkowo wykonano `node --check` dla aplikacji i testów oraz `git diff --check`.

## Do wykonania na prawdziwym ESP32 i telefonie

1. Wgrać trzy pliki z `Klaskacz/data/` do LittleFS odpowiednim narzędziem projektu. Uwaga: wgrywanie obrazu LittleFS może usunąć zapisane sesje; przed nim zabezpieczyć potrzebne pomiary.
2. Połączyć komputer/telefon z Wi-Fi ESP32; otworzyć `http://192.168.4.1` i sprawdzić automatyczny wybór ESP32. W ustawieniach można ręcznie wybrać DEMO lub ESP32; pusty adres oznacza serwer strony. Zwykły serwer lokalny bez API pozostaje w DEMO z komunikatem o niewykryciu urządzenia.
3. Przy nieustawionym zegarze potwierdzić `POST /api/time` i `time_synced: true` po kolejnym odczycie statusu. Przy ustawionym zegarze żądanie ma być pomijane. Sprawdzić datę nowej sesji oraz sesji sprzed synchronizacji z tego samego uruchomienia. Starsza sesja bez daty z innego uruchomienia ma pozostać bez daty.
4. W obu trybach startu wykonać pomiar prawdziwych klaśnięć. Sprawdzić buzzer, OLED, statystyki, Stop i Reset, zapis historii w LittleFS oraz trwałość konfiguracji po restarcie.
5. Sprawdzić historię, szczegóły i rzeczywiste pobranie CSV na komputerze oraz Androidzie/iOS; dla sesji bez daty zachować puste pole ISO.
6. Rozłączyć Wi-Fi podczas pracy strony i połączyć ponownie. Sprawdzić komunikat, zachowanie ostatnich danych oraz ponowną synchronizację bez danych DEMO.
7. Sprawdzić dotyk, czytelność, tabelę przewijaną poziomo wewnątrz karty i pobieranie plików na fizycznym telefonie, w pionie i poziomie.
8. Przy korzystaniu z frontendu na innym serwerze ustawić pełny adres API i sprawdzić CORS (w tym preflight PUT/POST), ograniczenia HTTPS/HTTP oraz uprawnienia przeglądarki do sieci lokalnej. Najprostsza konfiguracja to strona i API na ESP32 pod jednym adresem.

Testy sprzętowe i testy na fizycznym telefonie nie zostały wykonane. Nie zmieniono firmware, pinów, detektora ani kontraktu API. W wyniku przeglądu nie potwierdzono osobnego błędu firmware wymagającego zmiany dla tej integracji.
