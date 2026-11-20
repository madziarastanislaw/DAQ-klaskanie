"""Symulacja OBECNEGO detektora z Klaskacz/audio.h na nagraniu (punkt odniesienia).

Odtwarza: bloki 256 probek, usuwanie DC (int, >>8), poziom A, tlo uczone tylko w
rozgrzewce, prog reczny lub auto (tlo * MULT), wyzwolenie gdy A > prog, okres
refrakcji i bramke czestotliwosci dominujacej z FFT 1024 (Hamming).
Wartosci domyslne = config.h / audio.h z repozytorium; zmien je tutaj, jesli zmienisz firmware.
FFT nie jest bit-w-bit takie jak arduinoFFT, wiec pojedyncze decyzje na granicy
bramki czestotliwosci moga sie roznic.
"""
from __future__ import annotations

import numpy as np

FS = 16000
AUDIO_BLOCK = 256
FFT_N = 1024
BASELINE_ADAPTATION = 0.05
BASELINE_MULT = 4.0
AUTO_MIN_THR = 100.0
WARMUP_BLOCKS = 60
CLAP_FREQ_MIN_HZ = 100
CLAP_FREQ_MAX_HZ = 3000
REFRACTORY_MS = 25
THR_RAW_MIN = 50.0
THR_RAW_MAX = 20000.0


def thr_ui_to_raw(ui: int) -> int:
    return int(THR_RAW_MIN * (THR_RAW_MAX / THR_RAW_MIN) ** ((ui - 1) / 99.0))


def _major_peak(win: np.ndarray) -> float:
    v = win.astype(np.float64)
    v = v - v.mean()
    v = v * np.hamming(FFT_N)
    mag = np.abs(np.fft.rfft(v))[: FFT_N // 2]
    k = int(np.argmax(mag[1:])) + 1
    if 1 <= k < len(mag) - 1:  # interpolacja paraboliczna jak w arduinoFFT
        a, b, c = mag[k - 1], mag[k], mag[k + 1]
        den = a - 2 * b + c
        d = 0.5 * (a - c) / den if den != 0 else 0.0
        return (k + d) * FS / FFT_N
    return k * FS / FFT_N


def run_baseline(x: np.ndarray, thr_ui: int = 60, auto: bool = False):
    """Zwraca liste slownikow: t_s (koniec bloku), accepted, A, thr, freq."""
    s_all = np.round(x).astype(np.int64)
    n_blocks = len(s_all) // AUDIO_BLOCK
    fft_win = np.zeros(FFT_N, dtype=np.int64)
    widx = 0
    dc = 0
    baseline = 0.0
    last_clap_ms = 0
    thr_manual = thr_ui_to_raw(thr_ui)
    out = []
    for blk in range(n_blocks):
        s = s_all[blk * AUDIO_BLOCK : (blk + 1) * AUDIO_BLOCK]
        sum_abs = 0
        for v in s:  # petla jak w C (DC zalezy od poprzedniej probki)
            fft_win[widx] = v
            widx = (widx + 1) % FFT_N
            dc += (int(v) - dc) >> 8
            sum_abs += abs(int(v) - dc)
        A = sum_abs / AUDIO_BLOCK
        if blk == 0:
            baseline = A
        thr = thr_manual
        if auto:
            thr = int(max(baseline * BASELINE_MULT, AUTO_MIN_THR))
        end_sample = (blk + 1) * AUDIO_BLOCK
        now_ms = int(1000 * end_sample / FS)
        warm = blk > WARMUP_BLOCKS
        trigger = warm and A > thr
        if trigger and (now_ms - last_clap_ms) > REFRACTORY_MS:
            f = _major_peak(np.roll(fft_win, -widx))
            acc = CLAP_FREQ_MIN_HZ <= f <= CLAP_FREQ_MAX_HZ
            if acc:
                last_clap_ms = now_ms
            out.append(dict(t_s=end_sample / FS, accepted=acc, A=A, thr=thr, freq=f))
        if not warm:
            baseline = baseline * (1 - BASELINE_ADAPTATION) + A * BASELINE_ADAPTATION
    return out
