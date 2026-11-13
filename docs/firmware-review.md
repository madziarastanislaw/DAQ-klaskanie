# Klaskacz firmware review: findings and proposed fixes

Reviewed state: branch `esp-ap`, commit `8e2b968` ("audio works").
Scope: `Klaskacz/*.ino`, `*.h`, and how `Klaskacz/data/app.js` uses the API.

Severity:
- **High**: wrong data or a feature that doesn't work.
- **Medium**: lower accuracy, data loss in edge cases, or poor robustness.
- **Low**: cleanup and small UX issues.

---

## Overview of the architecture

| Task | Core / prio | Role |
|---|---|---|
| `audioTask` (`audio.h`) | core 1, prio 5 | I2S read (256 samples = 16 ms), DC removal, level `A`, threshold/edge/FFT detection, sends `ClapEvent` to `clapQueue` |
| `logicTask` (`Klaskacz.ino`) | core 0, prio 1 | buttons, serial commands, `handleClap` (state machine), HTTP server, buzzer, AUTO_STOP, OLED, LittleFS/NVS writes |
| Arduino `loopTask` | core 1, prio 1 | runs `setup()`, then sleeps forever |

The two tasks share only `clapQueue` (32 events) and a few `volatile` globals. All session state and HTTP handlers run in `logicTask`, so no locks are needed. This design is sound.

---

## High

### H1. Web app never syncs the clock, so `started_at` is always `null`
`app.js` never calls `POST /api/time`. As a result:
- `timeValid()` is always false and every session has `started_at: null`;
- the history table shows "—";
- the ISO column in the CSV export is empty.

**Fix** (`app.js`, in `applySource()` ESP32 branch, and again whenever the status reports `time_synced === false`):
```js
async function syncTime() {
  try { await api('/api/time', 'POST', { epoch_ms: Date.now() }); } catch { /* ignore */ }
}
// in applySource(), ESP32 branch:
syncTime(); pollStatus(); fetchConfig();
// in pollStatus(), after a successful read:
if (result.time_synced === false) syncTime();
```

### H2. I2S setup errors are ignored, so the audio task can spin silently
`i2s_new_channel`, `i2s_channel_init_std_mode` and `i2s_channel_enable` don't check their return values. If any of them fails:
- `i2s_channel_read` returns immediately with `bytes = 0`;
- the loop hits `continue` with no delay, so a priority-5 task spins on core 1;
- nothing explains the failure.

**Fix** (`audio.h`):
```cpp
ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));
ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx_handle, &std_cfg));
// audioTask:
ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));
...
esp_err_t err = i2s_channel_read(rx_handle, buf, sizeof(buf), &bytes, portMAX_DELAY);
int n = bytes / 4;
if (err != ESP_OK || n <= 0) { vTaskDelay(1); continue; }
```

### H3. Battery measurement is turned off and the API reports 0 V
In `8e2b968` the battery read was commented out, which avoids the ADC2/Wi-Fi conflict on GPIO4. Effects:
- `gBattery` stays at `0`;
- the OLED shows `0.00V`;
- `/api/status` returns `"battery_v": 0`, which reads as an empty battery.

**Fix (software, for now):**
- send `"battery_v": null` until a working pin is chosen;
- drop the voltage from the OLED status line;
- remove the now-unused `lastBat` variable.

```cpp
// api.h
d["battery_v"] = nullptr;   // not measured (no ADC1 pin free)
```

**Fix (hardware, proper):** GPIO4 is on ADC2, and ADC2 can't be read while Wi-Fi is running. The divider must go on an ADC1 pin (GPIO 32–39). All of those are in use now: 32/33 by I2S and 34–39 by buttons. Suggested change:
- move I2S BCLK from GPIO33 to a free GPIO (for example 26);
- put the battery divider on GPIO33;
- restore `updateBattery()`.

---

## Medium

### M1. DMA buffer settings don't line up with the read size
`I2S_CHANNEL_DEFAULT_CONFIG` gives 6 buffers × 240 frames, but each read is 256 samples. A read often waits across two DMA buffers, which adds jitter to the block timestamp. There is also only about 90 ms of headroom, which flash writes can exceed (see M2).

**Fix:**
```cpp
i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
chan_cfg.dma_frame_num = AUDIO_BLOCK;  // 1 DMA buffer == 1 analysis block
chan_cfg.dma_desc_num  = 8;            // ~128 ms headroom
...
.clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_FS),   // was hardcoded 16000
```

### M2. Timestamps are rounded to 16 ms and drift during flash writes
`t_us = esp_timer_get_time()` is taken once per block, after `i2s_channel_read` returns. This causes two problems:
1. Every clap time and interval is rounded to about 16 ms steps. For a measurement device, that limits accuracy.
2. LittleFS writes (every 50 claps, and at STOP) pause code running from flash on both cores. When the audio task catches up, the queued blocks all get late timestamps, and if the DMA overflowed, samples are lost.

**Fix:** compute time from a running sample counter, and find the exact sample where the clap starts inside the block:
```cpp
static uint64_t samplesTotal = 0;
static uint64_t t0Us = 0;                 // set once, right after i2s_channel_enable
...
int onset = -1;
for (int i = 0; i < n; i++) {
  ...
  int32_t v = abs(s - dc);
  if (onset < 0 && v > thr * ONSET_K) onset = i;   // ONSET_K: tune vs. block-average scale
}
uint64_t t_us = t0Us + (samplesTotal + (onset < 0 ? n : onset)) * 1000000ULL / AUDIO_FS;
samplesTotal += n;
```
This gives about 62.5 µs resolution and doesn't depend on scheduling or flash stalls. Optionally, also detect DMA overflow by registering `on_recv_q_ovf` with `i2s_channel_register_event_callback` and logging or counting it.

### M3. Level saturates at 65535
`A` can reach about 131072 (18-bit samples), but `gLastPeak`, `ClapEvent.peak` and `Clap.peak` are `uint16_t` and are capped at 65535. Loud claps record a clipped level, which makes calibration with `level` harder.

**Fix:** change these three fields to `uint32_t` (CSV and API need no change), or store `A >> 1` and document the scale.

### M4. Flash write failures are silent and storage is never cleaned up
- If `LittleFS.open` fails in `storageFlush()` (for example, flash full), it returns without updating `flushed`. It then tries again on every clap and reports nothing.
- Sessions are never deleted, so the flash will eventually fill up.

**Fix:**
- add `"storage_free"` (`LittleFS.totalBytes() - LittleFS.usedBytes()`) and a `"storage_error"` flag to `/api/status`;
- add `DELETE /api/sessions/{id}`, which removes `/s<id>.csv` and `/m<id>.json`;
- in `sessionBegin()`, delete the oldest session when free space is below a limit (for example 64 KB).

### M5. A session interrupted by power loss disappears
`/m<id>.json` is written only in `sessionFinish()`. After a power cut the CSV exists, but `/api/sessions` never lists the session.

**Fix:**
- call `sessionSaveMeta()` in `sessionBegin()`, which writes `duration_ms = 0` and `"complete": false`;
- write it again in `sessionFinish()`;
- optionally, at boot, find CSVs without a meta file and rebuild the meta from the last CSV row.

### M6. `/api/sessions` returns the first 50 files, not the newest 50
`sendSessionList()` stops collecting IDs once `n == 50`, in directory order (`api.h:142`). Once there are more than 50 sessions, recent ones can be missing.

**Fix:** keep the 50 *largest* IDs while scanning, by replacing the smallest when full:
```cpp
if (sscanf(name.c_str(), "m%lu.json", &id) == 1) {
  if (n < 50) ids[n++] = id;
  else {
    int mi = 0; for (int k = 1; k < 50; k++) if (ids[k] < ids[mi]) mi = k;
    if (id > ids[mi]) ids[mi] = id;
  }
}
```

### M7. Buttons on GPIO 34–39 need external pull-ups
These pins have no internal pull-ups and are set as plain `INPUT`. Without resistors on the board, the inputs float and produce random presses. A random long RESET press turns Wi-Fi off, which is easy to mistake for a network problem.

**Fix (hardware):** check that every button has a 10 kΩ pull-up resistor to 3.3 V.

### M8. Buzzer may chirp at boot
The buzzer is now active-low. `pinMode(PIN_BUZZER, OUTPUT)` drives the pin LOW, so the buzzer is briefly on until `digitalWrite(HIGH)` on the next line. The raw `HIGH`/`LOW` in three places also reads the opposite of what it means.

**Fix:**
```cpp
// config.h
#define BUZZER_ON   LOW
#define BUZZER_OFF  HIGH
// setup()
digitalWrite(PIN_BUZZER, BUZZER_OFF);   // set level before enabling output
pinMode(PIN_BUZZER, OUTPUT);
// beep(): digitalWrite(PIN_BUZZER, BUZZER_ON);
// logicTask: digitalWrite(PIN_BUZZER, BUZZER_OFF);
```
If it still chirps during reset (GPIO27 floats before code runs), add a pull-up resistor on the buzzer driver input.

---

## Low

### L1. Phones may drop the AP and `.local` doesn't resolve on Android
The AP has no internet and no captive portal. Android and iOS may mark it "no internet" and send requests over mobile data. `klaskacz.local` doesn't resolve on many Android phones.

**Fix:** document `http://192.168.4.1`, and optionally add a `DNSServer` captive portal that answers all DNS queries with `192.168.4.1`.

### L2. Session detail download blocks `logicTask`
`sendSessionDetail()` parses the CSV line by line with `readStringUntil`. For about 2000 claps this takes long enough that buttons, the OLED and status polling all stall. Claps are still timestamped in the audio task, and the queue holds 32.

**Fix:** read the file in larger chunks (for example 512 B), or store the offsets in a compact binary file and format the JSON directly from it.

### L3. A clap rejected by the FFT filter hides the next one
After a candidate is rejected by the frequency filter, `prevLoud` stays `true`. A real clap in the next block then isn't seen as a new rising edge. This doesn't matter now because the filter is effectively off (0–8000 Hz).

**Fix:** set `prevLoud = false` when the FFT filter rejects a candidate, or only set `prevLoud` from blocks that were accepted.

### L4. Auto threshold rises during long clapping
In auto mode the background level also learns from loud blocks, so continuous clapping slowly raises the threshold.

**Fix:** update `baseline` only when `!loud`, keeping the faster rate during warm-up.

### L5. Check the I2S sample format once
Audio works with `I2S_STD_MSB_SLOT_DEFAULT_CONFIG`. This is probably the known ESP32 + SPH0645 timing quirk, where MSB mode lines up the data correctly. Sanity check: print a few raw `buf[i] >> 14` values in silence. They should sit around a steady offset with small swings in both directions, not stick to one sign. If they look wrong, try `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` and/or set `std_cfg.slot_cfg.slot_mask` explicitly to `I2S_STD_SLOT_LEFT` or `I2S_STD_SLOT_RIGHT`.

### L6. Cleanup
- `api.h:230`: remove the debug `Serial.println(server.uri())`.
- `audio.h`: remove the commented-out old-driver block and the commented `Serial.println` lines. If you turn debug printing back on, don't print every block (62/s); use the existing `d` command (5/s).
- `audio.h:58`: fix the indentation of `rx_handle`, and consider making it `static`.
- `Klaskacz.ino`: `lastBat` is unused while battery measurement is off.
- `session.h`: revert the uncommitted blank line before `#pragma once`.
- The web app's default threshold is 50 and the firmware's is 60. This is harmless because the app reads the device config, but it's worth aligning.

---

## Suggested order of work
1. **H1** (time sync in web app) and **H2** (I2S error checks): small, high value.
2. **M1** (DMA config), then **M2** (sample-accurate timestamps): the main accuracy gain.
3. **H3/M8/L6**: battery null, buzzer macros, cleanup.
4. **M4/M5/M6**: storage robustness.
5. Hardware: **H3** (battery on ADC1), **M7** (button pull-ups).
