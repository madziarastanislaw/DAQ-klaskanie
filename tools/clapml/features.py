"""Kandydaci na klasniecie (onsety) i cechy liczone wokol kazdego z nich.

Dwa etapy, tak jak docelowo na ESP32:
 1. `find_candidates` - czuly detektor onsetow (ma lapac prawie wszystko, takze fałszywki).
    Obwiednia energii po filtrze gornoprzepustowym w ramkach 2 ms, tlo = percentyl
    z ostatnich ~1 s, kandydat = szybki wzrost energii wyraznie ponad tlo.
 2. `extract_features` - cechy okna 32 ms zaczynajacego sie 5 ms przed onsetem;
    o tym, czy kandydat jest klasnieciem, decyduje model (model.py).

Wszystkie cechy da sie policzyc na ESP32 (jeden biquad, jedno FFT 512, kilka sum).
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import percentile_filter
from scipy.signal import butter, sosfilt

FS = 16000
HOP = 32                 # 2 ms - rozdzielczosc obwiedni
PRE = 80                 # 5 ms przed onsetem w oknie analizy
WIN = 512                # 32 ms okno analizy (FFT)
HPF_HZ = 300.0
FLOOR_WIN_S = 1.0        # okno do szacowania tla
FLOOR_PCT = 20           # percentyl energii jako tlo
CAND_SNR_DB = 8.0        # kandydat: energia ramki > tlo + tyle dB
CAND_RISE_DB = 6.0       # ... i wzrost wzgledem ramki sprzed 4 ms o tyle dB
REFRACTORY_S = 0.025     # minimalny odstep kandydatow (jak REFRACTORY_MS w firmware)

BANDS = [(0, 300), (300, 1000), (1000, 2500), (2500, 5000), (5000, 8000)]

FEATURES = [
    "snr_db",          # szczyt energii (pierwsze 10 ms) ponad tlo
    "attack_ms",       # onset -> szczyt amplitudy
    "decay_ms",        # szczyt -> spadek o 20 dB (max 100 ms)
    "sustain_db",      # energia 30-80 ms po onsecie minus energia 0-30 ms
    "crest_db",        # szczyt / RMS w oknie
    "centroid_hz",     # srodek ciezkosci widma
    "flatness",        # plaskosc widma 200-7000 Hz (1 = szum, 0 = ton)
    "rolloff_hz",      # czestotliwosc ponizej ktorej jest 85 % energii
    "zcr",             # przejscia przez zero na probke (po HPF)
    *[f"band_{lo}_{hi}" for lo, hi in BANDS],  # udzial energii pasma [dB wzgl. calosci]
]


def highpass(x: np.ndarray, fs: int = FS) -> np.ndarray:
    sos = butter(2, HPF_HZ, btype="highpass", fs=fs, output="sos")
    return sosfilt(sos, x - np.mean(x[: fs // 10]) if len(x) else x)


def envelope_db(xh: np.ndarray) -> np.ndarray:
    n = len(xh) // HOP
    fr = xh[: n * HOP].reshape(n, HOP)
    return 10 * np.log10(np.mean(fr * fr, axis=1) + 1e-3)


def noise_floor_db(env: np.ndarray) -> np.ndarray:
    size = max(3, int(FLOOR_WIN_S * FS / HOP))
    # filtr "przyczynowy": tlo z przeszlosci, tak jak na urzadzeniu
    padded = np.concatenate([np.full(size - 1, env[: size].min() if len(env) else 0.0), env])
    pf = percentile_filter(padded, FLOOR_PCT, size=size)  # okno wysrodkowane
    # wynik dla env[j] = okno env[j-size+1 .. j] = srodek okna w padded[j + size//2]
    return pf[size // 2 : size // 2 + len(env)]


def find_candidates(x: np.ndarray, fs: int = FS):
    """Zwraca (onsety w probkach, xh, env_db, floor_db)."""
    xh = highpass(x, fs)
    env = envelope_db(xh)
    floor = noise_floor_db(env)
    onsets = []
    last = -10**9
    refr = int(REFRACTORY_S * fs / HOP)
    for f in range(2, len(env)):
        if env[f] - floor[f] < CAND_SNR_DB:
            continue
        if env[f] - env[f - 2] < CAND_RISE_DB:
            continue
        if f - last < refr:
            continue
        # doprecyzowanie onsetu do probki: pierwsza probka > 25 % szczytu
        a = max(0, (f - 1) * HOP)
        b = min(len(xh), (f + 2) * HOP)
        seg = np.abs(xh[a:b])
        if len(seg) == 0:
            continue
        pk = int(np.argmax(seg))
        above = np.nonzero(seg[: pk + 1] > 0.25 * seg[pk])[0]
        onset = a + int(above[0])
        onsets.append(onset)
        last = f
    return np.array(onsets, dtype=int), xh, env, floor


def extract_features(x, xh, env, floor, onset: int, fs: int = FS) -> dict:
    f0 = onset // HOP
    fl = floor[min(f0, len(floor) - 1)]
    # energia
    pk_f = f0 + int(np.argmax(env[f0 : f0 + 5])) if f0 < len(env) else f0
    pk_db = env[min(pk_f, len(env) - 1)]
    snr = pk_db - fl
    # attack
    seg = np.abs(xh[onset : onset + int(0.010 * fs)])
    attack_ms = 1000 * int(np.argmax(seg)) / fs if len(seg) else 0.0
    # decay do -20 dB (albo do tla, jesli jest wyzej)
    lim = max(pk_db - 20, fl + 3)
    dec = env[pk_f : pk_f + int(0.100 * fs / HOP)]
    below = np.nonzero(dec < lim)[0]
    decay_ms = (below[0] if len(below) else len(dec)) * HOP * 1000 / fs
    # sustain
    def e(a_ms, b_ms):
        a, b = onset + int(a_ms * fs / 1000), onset + int(b_ms * fs / 1000)
        s = xh[a:b]
        return 10 * np.log10(np.mean(s * s) + 1e-3) if len(s) else -30.0
    sustain_db = e(30, 80) - e(0, 30)
    # okno analizy
    a = max(0, onset - PRE)
    w = x[a : a + WIN].astype(np.float64)
    if len(w) < WIN:
        w = np.pad(w, (0, WIN - len(w)))
    w = w - w.mean()
    wh = xh[a : a + WIN]
    rms = np.sqrt(np.mean(wh * wh)) + 1e-9
    crest_db = 20 * np.log10(np.max(np.abs(wh)) / rms + 1e-9) if len(wh) else 0.0
    zcr = float(np.mean(np.abs(np.diff(np.signbit(wh))))) if len(wh) > 1 else 0.0
    spec = np.abs(np.fft.rfft(w * np.hanning(WIN))) ** 2
    freqs = np.fft.rfftfreq(WIN, 1 / fs)
    tot = spec.sum() + 1e-9
    centroid = float((freqs * spec).sum() / tot)
    cum = np.cumsum(spec)
    rolloff = float(freqs[np.searchsorted(cum, 0.85 * cum[-1])])
    m = (freqs >= 200) & (freqs <= 7000)
    ps = spec[m] + 1e-9
    flatness = float(np.exp(np.mean(np.log(ps))) / np.mean(ps))
    out = dict(snr_db=snr, attack_ms=attack_ms, decay_ms=decay_ms, sustain_db=sustain_db,
               crest_db=crest_db, centroid_hz=centroid, flatness=flatness, rolloff_hz=rolloff, zcr=zcr)
    for lo, hi in BANDS:
        bm = (freqs >= lo) & (freqs < hi)
        out[f"band_{lo}_{hi}"] = 10 * np.log10(spec[bm].sum() / tot + 1e-9)
    return out


def candidates_with_features(x: np.ndarray, fs: int = FS):
    """Lista (onset_sample, dict cech) dla calego nagrania."""
    onsets, xh, env, floor = find_candidates(x, fs)
    return [(int(o), extract_features(x, xh, env, floor, int(o), fs)) for o in onsets]
