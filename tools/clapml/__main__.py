"""clapml - uczenie i ocena detektora klasniec na nagraniach z tools/recorder.

Uruchamiac z katalogu tools/:
    python -m clapml draft    ../recordings              # szkic etykiet z expected_claps
    python -m clapml train    ../recordings -o ../models # uczenie + clap_model.h
    python -m clapml eval     ../recordings --model ../models/model.joblib
    python -m clapml baseline ../recordings --thr 60     # obecny detektor z firmware
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .baseline import run_baseline
from .features import FEATURES, candidates_with_features
from .model import build_dataset, detect, event_metrics, export_c_header, summarize, train
from .recordings import load_all, write_audacity_labels


def cmd_draft(a):
    model = joblib.load(a.model) if a.model else None
    for r in load_all(a.root):
        if r.labels is not None and not a.force:
            continue
        if not r.expected:
            continue
        cands = candidates_with_features(r.x, r.fs)
        if not cands:
            print(f"  {r.name}: brak kandydatow"); continue
        if model is not None:
            score = model["model"].predict_proba(np.array([[f[k] for k in FEATURES] for _, f in cands]))[:, 1]
        else:
            score = np.array([f["snr_db"] for _, f in cands])  # najglosniejsze impulsy
        top = np.sort(np.argsort(-score)[: r.expected])
        times = [cands[i][0] / r.fs for i in top]
        write_audacity_labels(r.path / "labels_draft.txt", times)
        warn = "" if len(times) == r.expected else f"  (UWAGA: tylko {len(times)} kandydatow)"
        print(f"  {r.name}: {len(times)} etykiet -> labels_draft.txt{warn}")
    print("\nOtworz audio.wav w Audacity, Plik > Importuj > Etykiety (labels_draft.txt), popraw,\n"
          "potem Plik > Eksportuj > Eksportuj etykiety jako labels.txt w tym samym katalogu.")


def cmd_dataset(a):
    df = build_dataset(load_all(a.root), a.tol / 1000)
    df.to_csv(a.out, index=False)
    print(f"Zapisano {len(df)} kandydatow ({int(df['y'].sum()) if len(df) else 0} klasniec) -> {a.out}")


def cmd_train(a):
    recs = load_all(a.root)
    print("Zbior danych:")
    df = build_dataset(recs, a.tol / 1000)
    if df.empty:
        sys.exit("Brak danych z etykietami.")
    model, thr, rep = train(df, a.kind, a.min_precision)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "threshold": thr, "features": FEATURES, "kind": a.kind}, out / "model.joblib")
    export_c_header(model, thr, out / "clap_model.h")
    df.to_csv(out / "features.csv", index=False)
    # ocena na zdarzeniach (UWAGA: na danych uczacych - optymistyczna; uczciwe sa wyniki CV powyzej)
    res = event_metrics([(r, detect(model, thr, r)) for r in recs], a.tol / 1000)
    rep["train_events"] = summarize(res)
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nWalidacja krzyzowa po osobach (kandydaci):")
    print(f"  precision={rep['cv_precision']:.3f} recall={rep['cv_recall']:.3f} f1={rep['cv_f1']:.3f} prog={thr:.2f}")
    if a.kind == "logreg":
        lr = model.named_steps["logisticregression"]
        imp = sorted(zip(FEATURES, lr.coef_[0]), key=lambda p: -abs(p[1]))
        print("Najwazniejsze cechy (waga po standaryzacji):")
        for n, w in imp[:6]:
            print(f"  {n:16s} {w:+.2f}")
    else:
        from sklearn.tree import export_text
        print(export_text(model, feature_names=FEATURES))
    print(f"\nZapisano: {out / 'model.joblib'}, {out / 'clap_model.h'}, {out / 'report.json'}")


def _print_eval(res: pd.DataFrame, title: str, csv: str | None):
    pd.set_option("display.width", 160)
    print(f"\n== {title} ==")
    print(res.to_string(index=False))
    print("\nPodsumowanie:", json.dumps(summarize(res), ensure_ascii=False))
    if csv:
        res.to_csv(csv, index=False)


def cmd_eval(a):
    m = joblib.load(a.model)
    thr = a.threshold if a.threshold is not None else m["threshold"]
    recs = load_all(a.root)
    _print_eval(event_metrics([(r, detect(m["model"], thr, r)) for r in recs], a.tol / 1000),
                f"model {m['kind']} (prog {thr:.2f})", a.csv)


def cmd_baseline(a):
    recs = load_all(a.root)
    res = []
    for r in recs:
        ev = run_baseline(r.x, a.thr, a.auto)
        res.append((r, np.array([e["t_s"] for e in ev if e["accepted"]])))
    # obecny detektor podaje koniec bloku 16 ms, wiec tolerancja musi pokryc kwantyzacje
    _print_eval(event_metrics(res, a.tol / 1000), f"obecny detektor ({'auto' if a.auto else f'prog {a.thr}'})", a.csv)


def main():
    ap = argparse.ArgumentParser(prog="clapml", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("draft", help="szkic etykiet (N najsilniejszych impulsow, N = expected_claps)")
    p.add_argument("root"); p.add_argument("--model"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_draft)

    p = sub.add_parser("dataset", help="tabela cech kandydatow do wlasnej analizy (CSV)")
    p.add_argument("root"); p.add_argument("-o", "--out", default="features.csv"); p.add_argument("--tol", type=float, default=20)
    p.set_defaults(fn=cmd_dataset)

    p = sub.add_parser("train", help="uczenie modelu i eksport clap_model.h")
    p.add_argument("root"); p.add_argument("-o", "--out", default="models")
    p.add_argument("--kind", choices=["logreg", "tree"], default="logreg")
    p.add_argument("--min-precision", type=float, default=None, help="wybierz prog z precision >= tej wartosci")
    p.add_argument("--tol", type=float, default=20, help="tolerancja dopasowania do etykiety [ms]")
    p.set_defaults(fn=cmd_train)

    p = sub.add_parser("eval", help="ocena modelu na nagraniach")
    p.add_argument("root"); p.add_argument("--model", required=True); p.add_argument("--threshold", type=float)
    p.add_argument("--tol", type=float, default=20); p.add_argument("--csv")
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("baseline", help="ocena obecnego detektora z firmware")
    p.add_argument("root"); p.add_argument("--thr", type=int, default=60); p.add_argument("--auto", action="store_true")
    p.add_argument("--tol", type=float, default=30); p.add_argument("--csv")
    p.set_defaults(fn=cmd_baseline)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
