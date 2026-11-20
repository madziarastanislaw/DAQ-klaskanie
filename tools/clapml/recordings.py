"""Wczytywanie nagran i etykiet.

Katalog nagrania (tworzy go tools/recorder/record.py):
    audio.wav          probki detektora (int24, 16 kHz)
    meta.json          m.in. expected_claps = ile klasniec POWINNO byc w nagraniu
    labels.txt         (opcjonalnie) etykiety Audacity: momenty klasniec - "prawda"
    labels_draft.txt   (opcjonalnie) szkic etykiet z `clapml draft` do poprawienia w Audacity

Etykiety (labels.txt, format "Eksportuj etykiety" z Audacity: start<TAB>koniec<TAB>tekst):
    - kazda etykieta = jedno klasniecie, liczy sie jej poczatek (start),
    - tekst zaczynajacy sie od "?" = niepewne; kandydaci przy nim nie trafiaja do uczenia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile

FS = 16000


@dataclass
class Recording:
    name: str
    path: Path
    x: np.ndarray            # float64, skala detektora (s = buf>>14)
    fs: int
    meta: dict
    labels: np.ndarray | None      # czasy klasniec [s] albo None (brak labels.txt)
    uncertain: np.ndarray          # czasy etykiet "?" [s]

    @property
    def expected(self) -> int | None:
        return self.meta.get("expected_claps")

    @property
    def duration_s(self) -> float:
        return len(self.x) / self.fs

    @property
    def group(self) -> str:
        """Grupa do walidacji krzyzowej: nagrania tej samej osoby nie trafia jednoczesnie do train i test."""
        return self.meta.get("person") or self.meta.get("session") or self.name

    @property
    def truth(self) -> np.ndarray | None:
        """Czasy klasniec, jesli sa znane: z etykiet albo pewne zero (expected_claps == 0)."""
        if self.labels is not None:
            return self.labels
        if self.expected == 0:
            return np.zeros(0)
        return None


def read_audacity_labels(path: Path) -> tuple[np.ndarray, np.ndarray]:
    sure, unsure = [], []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split("\t")
        if not parts or not parts[0] or parts[0].startswith("\\"):  # "\" = linia z zakresem czestotliwosci
            continue
        t = float(parts[0].replace(",", "."))
        text = parts[2].strip() if len(parts) > 2 else ""
        (unsure if text.startswith("?") else sure).append(t)
    return np.sort(np.array(sure)), np.sort(np.array(unsure))


def write_audacity_labels(path: Path, times, texts=None) -> None:
    lines = []
    for i, t in enumerate(times):
        txt = texts[i] if texts is not None else str(i + 1)
        lines.append(f"{t:.6f}\t{t:.6f}\t{txt}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_recording(path: Path) -> Recording:
    path = Path(path)
    fs, data = wavfile.read(path / "audio.wav")
    x = data.astype(np.float64)
    if x.ndim > 1:
        x = x[:, 0]
    meta_p = path / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    if meta.get("sample_format", "").startswith("int24") or data.dtype == np.int32:
        # scipy zwraca 24-bit jako int32 przesuniete w lewo o 8 bitow
        x = x / 256.0
    lab_p = path / "labels.txt"
    labels, unsure = (read_audacity_labels(lab_p) if lab_p.exists() else (None, np.zeros(0)))
    return Recording(path.name, path, x, fs, meta, labels, unsure)


def find_recordings(root: Path) -> list[Path]:
    root = Path(root)
    if (root / "audio.wav").exists():
        return [root]
    return sorted(p.parent for p in root.rglob("audio.wav"))


def load_all(root: Path) -> list[Recording]:
    return [load_recording(p) for p in find_recordings(root)]
