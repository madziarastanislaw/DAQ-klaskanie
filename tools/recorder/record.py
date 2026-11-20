"""Nagrywanie surowego audio z Klaskacza przez UART (protokol z Klaskacz/rawdump.h).

Przyklad:
    python tools/recorder/record.py --port COM5 --expected-claps 10 \
        --scenario klaski --person A --distance 1 --room sala1 --seconds 30

Wynik (katalog recordings/<data>_<scenariusz>/):
    audio.wav    24-bit PCM, 16 kHz, mono. Wartosc probki = "buf >> 14" z detektora
                 (18 bitow, wiec w Audacity nagranie jest ciche - to normalne).
    events.csv   kandydaci na klasniecie z obecnego detektora (accepted=1 -> policzony).
    meta.json    opis nagrania; pole expected_claps mozna poprawic recznie.
"""
from __future__ import annotations

import argparse
import binascii
import csv
import json
import re
import struct
import sys
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

MAGIC = b"KLSK"
HDR = 8
TYPE_AUDIO = 1
TYPE_EVENT = 2
FS = 16000
MAX_PAYLOAD = 4096


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) - to samo co rdCrc16() w firmware."""
    return binascii.crc_hqx(data, 0xFFFF)


class FrameParser:
    """Wyszukuje ramki w strumieniu bajtow; odporny na smieci i tekst miedzy ramkami."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.crc_errors = 0
        self.skipped_bytes = 0

    def feed(self, data: bytes):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(MAGIC)
            if i < 0:
                keep = len(MAGIC) - 1  # koncowka moze byc poczatkiem magic
                if len(self.buf) > keep:
                    self.skipped_bytes += len(self.buf) - keep
                    del self.buf[: len(self.buf) - keep]
                break
            if i > 0:
                self.skipped_bytes += i
                del self.buf[:i]
            if len(self.buf) < HDR:
                break
            ftype, _ver, plen = struct.unpack_from("<BBH", self.buf, 4)
            if plen > MAX_PAYLOAD:
                self.crc_errors += 1
                del self.buf[:1]
                continue
            total = HDR + plen + 2
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            (crc,) = struct.unpack_from("<H", frame, HDR + plen)
            if crc != crc16_ccitt(frame[: HDR + plen]):
                self.crc_errors += 1
                del self.buf[:1]  # szukaj kolejnego magic
                continue
            del self.buf[:total]
            out.append((ftype, frame[HDR : HDR + plen]))
        return out


def decode_audio(payload: bytes):
    seq, t_us, dropped, n = struct.unpack_from("<IQIH", payload, 0)
    raw = np.frombuffer(payload, dtype=np.uint8, count=3 * n, offset=18).reshape(n, 3).astype(np.int32)
    v = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
    v = np.where(v & 0x800000, v - (1 << 24), v)  # rozszerzenie znaku int24
    return seq, t_us, dropped, v.astype(np.int32)


def decode_event(payload: bytes):
    seq, t_us, A, thr, base, freq, flags = struct.unpack_from("<IQffffB", payload, 0)
    return dict(seq=seq, t_us=t_us, A=A, thr=thr, baseline=base, freq=freq, accepted=flags & 1)


@dataclass
class Recording:
    chunks: list = field(default_factory=list)  # bloki probek (np.int32)
    n_samples: int = 0
    events: list = field(default_factory=list)
    first_seq: int | None = None
    next_seq: int | None = None
    first_t_us: int | None = None
    block_start: dict = field(default_factory=dict)  # seq -> indeks pierwszej probki bloku
    lost_blocks: int = 0
    device_dropped: int = 0
    block_len: int = 256

    def add_frame(self, ftype: int, payload: bytes) -> None:
        if ftype == TYPE_AUDIO:
            seq, t_us, dropped, s = decode_audio(payload)
            self.device_dropped = dropped
            if self.first_seq is None:
                self.first_seq, self.next_seq, self.first_t_us = seq, seq, t_us
                self.block_len = len(s)
            gap = seq - self.next_seq
            if gap < 0:
                return  # duplikat / stara ramka
            if gap > 0:  # zgubione bloki -> cisza, zeby os czasu sie zgadzala
                self.lost_blocks += gap
                self.chunks.append(np.zeros(gap * self.block_len, dtype=np.int32))
                self.n_samples += gap * self.block_len
            self.block_start[seq] = self.n_samples
            self.chunks.append(s)
            self.n_samples += len(s)
            self.next_seq = seq + 1
        elif ftype == TYPE_EVENT and self.first_seq is not None:
            ev = decode_event(payload)
            start = self.block_start.get(ev["seq"])
            if start is None:
                return
            # t_us odpowiada koncowi bloku (znacznik zaraz po odczycie I2S)
            ev["block_start_sample"] = start
            ev["block_end_sample"] = start + self.block_len
            ev["t_s"] = round(ev["block_end_sample"] / FS, 4)
            self.events.append(ev)


    def samples(self) -> np.ndarray:
        return np.concatenate(self.chunks) if self.chunks else np.zeros(0, dtype=np.int32)


def write_wav24(path: Path, samples: np.ndarray) -> None:
    data = samples.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(FS)
        w.writeframes(data)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-") or "nagranie"


def open_port(port: str, baud: int):
    import serial  # pip install pyserial

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, baud, 0.05
    ser.dtr = False  # nie resetuj ESP32 przy otwarciu portu (na wiekszosci plytek)
    ser.rts = False
    ser.open()
    return ser


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="np. COM5")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--out", default="recordings", help="katalog na nagrania")
    ap.add_argument("--seconds", type=float, default=0, help="czas nagrania; 0 = do Ctrl+C")
    ap.add_argument("--expected-claps", type=int, default=None,
                    help="ile klasniec bylo w nagraniu (0 = nagranie bez klasniec)")
    ap.add_argument("--scenario", default="", help="np. klaski, mowa, klawiatura, stukanie")
    ap.add_argument("--person", default="", help="kto klaskal (do podzialu train/test)")
    ap.add_argument("--distance", type=float, default=None, help="odleglosc od mikrofonu [m]")
    ap.add_argument("--room", default="")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    ser = open_port(args.port, args.baud)
    time.sleep(0.3)
    ser.reset_input_buffer()

    parser = FrameParser()
    rec = Recording()

    # Jesli zrzut juz trwa (np. po przerwanym nagraniu), nie wysylaj 'R' - to by go wylaczylo.
    probe_end = time.time() + 0.5
    already = False
    while time.time() < probe_end:
        if any(t == TYPE_AUDIO for t, _ in parser.feed(ser.read(4096))):
            already = True
            break
    if not already:
        ser.write(b"R")
    parser = FrameParser()
    ser.reset_input_buffer()

    print("Nagrywanie... (Ctrl+C konczy)" if not args.seconds else f"Nagrywanie {args.seconds:g} s...")
    t0 = time.time()
    last_print = 0.0
    try:
        while True:
            for ftype, payload in parser.feed(ser.read(8192)):
                rec.add_frame(ftype, payload)
            now = time.time()
            if now - last_print > 1.0:
                last_print = now
                dur = rec.n_samples / FS
                acc = sum(e["accepted"] for e in rec.events)
                print(f"\r  {dur:6.1f} s  zgubione bloki: {rec.lost_blocks}  bledy CRC: {parser.crc_errors}"
                      f"  detektor: {acc} klasn. ({len(rec.events)} kandyd.)   ", end="", flush=True)
                if rec.first_seq is None and now - t0 > 3:
                    print("\nBrak danych z urzadzenia. Sprawdz port, baud (SERIAL_BAUD) i czy firmware ma rawdump.h.")
                    return 1
            if args.seconds and rec.n_samples / FS >= args.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        ser.write(b"R")  # wylacz zrzut
        time.sleep(0.2)
        ser.close()
    print()

    if rec.n_samples == 0:
        print("Nic nie nagrano.")
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = stamp + ("_" + slug(args.scenario) if args.scenario else "")
    out = Path(args.out) / name
    out.mkdir(parents=True, exist_ok=False)

    write_wav24(out / "audio.wav", rec.samples())
    with open(out / "events.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["t_s", "block_start_sample", "block_end_sample", "seq", "t_us", "A", "thr", "baseline", "freq", "accepted"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for e in rec.events:
            w.writerow({k: e[k] for k in cols})

    accepted = sum(e["accepted"] for e in rec.events)
    meta = {
        "format": 1,
        "created": datetime.now().isoformat(timespec="seconds"),
        "sample_rate": FS,
        "sample_format": "int24 w pliku = s = buf>>14 z detektora (18 bit)",
        "expected_claps": args.expected_claps,
        "scenario": args.scenario,
        "person": args.person,
        "distance_m": args.distance,
        "room": args.room,
        "notes": args.notes,
        "duration_s": round(rec.n_samples / FS, 3),
        "first_t_us": rec.first_t_us,
        "lost_blocks": rec.lost_blocks,
        "device_dropped_frames": rec.device_dropped,
        "crc_errors": parser.crc_errors,
        "detector_candidates": len(rec.events),
        "detector_accepted": accepted,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Zapisano: {out}")
    print(f"  czas {meta['duration_s']} s, zgubione bloki {rec.lost_blocks}, bledy CRC {parser.crc_errors}")
    if args.expected_claps is not None:
        print(f"  obecny detektor: {accepted} klasniec, oczekiwano {args.expected_claps}")
    if rec.lost_blocks or parser.crc_errors:
        print("  UWAGA: dane niekompletne - luki wypelniono cisza. Rozwaz powtorzenie nagrania.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
