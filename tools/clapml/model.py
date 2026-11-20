"""Zbior uczacy, uczenie, ocena i eksport modelu do naglowka C.

Etykietowanie kandydatow (build_dataset):
  - nagranie z labels.txt: kandydat w odleglosci <= tol od etykiety -> 1, pozostali -> 0,
    kandydat przy etykiecie "?" -> pomijany,
  - nagranie z expected_claps == 0 (np. sama mowa): wszyscy kandydaci -> 0,
  - nagranie z expected_claps > 0 bez labels.txt -> pomijane (najpierw `clapml draft`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .features import FEATURES, candidates_with_features
from .recordings import Recording

TOL_S = 0.020


def match_events(det: np.ndarray, truth: np.ndarray, tol: float = TOL_S):
    """Dopasowanie 1:1 (zachlanne po odleglosci). Zwraca pary (i_det, i_truth)."""
    pairs = []
    if len(det) == 0 or len(truth) == 0:
        return pairs
    d = np.abs(det[:, None] - truth[None, :])
    cand = np.argwhere(d <= tol)
    cand = cand[np.argsort(d[cand[:, 0], cand[:, 1]])]
    used_d, used_t = set(), set()
    for i, j in cand:
        if i not in used_d and j not in used_t:
            used_d.add(i); used_t.add(j); pairs.append((int(i), int(j)))
    return pairs


def build_dataset(recs: list[Recording], tol: float = TOL_S, verbose: bool = True) -> pd.DataFrame:
    rows = []
    for r in recs:
        truth = r.truth
        if truth is None:
            if verbose:
                print(f"  pomijam {r.name}: expected_claps={r.expected}, brak labels.txt")
            continue
        cands = candidates_with_features(r.x, r.fs)
        t = np.array([o / r.fs for o, _ in cands])
        y = np.zeros(len(cands))
        for i, _ in match_events(t, truth, tol):
            y[i] = 1
        if len(r.uncertain) and len(t):
            near_unsure = np.min(np.abs(t[:, None] - r.uncertain[None, :]), axis=1) <= tol
            y[near_unsure & (y == 0)] = np.nan
        missed = len(truth) - int(np.nansum(y))
        if verbose:
            print(f"  {r.name}: {len(cands)} kandydatow, {int(np.nansum(y))}/{len(truth)} klasniec"
                  + (f"  (UWAGA: {missed} etykiet bez kandydata - detektor onsetow je zgubil)" if missed else ""))
        for (o, feat), ti, yi in zip(cands, t, y):
            rows.append(dict(rec=r.name, group=r.group, t_s=ti, y=yi, **feat))
    df = pd.DataFrame(rows)
    return df.dropna(subset=["y"]) if len(df) else df


def make_model(kind: str):
    if kind == "logreg":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    if kind == "tree":
        return DecisionTreeClassifier(max_depth=4, min_samples_leaf=5, class_weight="balanced")
    raise ValueError(kind)


def _prf(y, p):
    tp = int(((p == 1) & (y == 1)).sum()); fp = int(((p == 1) & (y == 0)).sum()); fn = int(((p == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def train(df: pd.DataFrame, kind: str = "logreg", min_precision: float | None = None):
    """Walidacja krzyzowa po grupach (osobach), wybor progu, model koncowy na calosci."""
    X = df[FEATURES].to_numpy(float)
    y = df["y"].to_numpy(int)
    groups = df["group"].to_numpy()
    n_groups = len(np.unique(groups))
    if len(np.unique(y)) < 2:
        raise SystemExit("W zbiorze jest tylko jedna klasa - potrzebne sa i klasniecia, i inne dzwieki.")
    oof = np.full(len(y), np.nan)
    if n_groups >= 2:
        for tr, te in GroupKFold(n_splits=min(5, n_groups)).split(X, y, groups):
            if len(np.unique(y[tr])) < 2:
                continue
            m = make_model(kind).fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
    else:
        print("UWAGA: tylko jedna grupa (osoba) - wyniki walidacji beda zawyzone. Uzupelnij meta.person.")
    ok = ~np.isnan(oof)
    best_thr, best = 0.5, (0, 0, 0)
    if ok.sum():
        for thr in np.linspace(0.05, 0.95, 91):
            prf = _prf(y[ok], (oof[ok] >= thr).astype(int))
            if min_precision is not None:
                if prf[0] >= min_precision and prf[1] > best[1]:
                    best_thr, best = thr, prf
            elif prf[2] > best[2]:
                best_thr, best = thr, prf
    model = make_model(kind).fit(X, y)
    report = dict(kind=kind, n=len(y), n_pos=int(y.sum()), n_groups=n_groups, threshold=float(best_thr),
                  cv_precision=best[0], cv_recall=best[1], cv_f1=best[2])
    return model, float(best_thr), report


def detect(model, threshold: float, rec: Recording):
    cands = candidates_with_features(rec.x, rec.fs)
    if not cands:
        return np.zeros(0)
    X = np.array([[f[k] for k in FEATURES] for _, f in cands])
    p = model.predict_proba(X)[:, 1]
    return np.array([o / rec.fs for (o, _), pi in zip(cands, p) if pi >= threshold])


def event_metrics(results: list[tuple[Recording, np.ndarray]], tol: float = TOL_S) -> pd.DataFrame:
    """results: (nagranie, czasy wykrytych klasniec [s]). Metryki na poziomie zdarzen."""
    rows = []
    for r, det in results:
        truth = r.truth
        row = dict(rec=r.name, scenario=r.meta.get("scenario", ""), dur_s=round(r.duration_s, 1),
                   expected=r.expected, detected=len(det))
        if truth is not None:
            pairs = match_events(det, truth, tol)
            err = [1000 * (det[i] - truth[j]) for i, j in pairs]
            row.update(tp=len(pairs), fp=len(det) - len(pairs), fn=len(truth) - len(pairs),
                       err_mean_ms=round(float(np.mean(err)), 1) if err else None,
                       err_std_ms=round(float(np.std(err)), 1) if err else None)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> dict:
    lab = df.dropna(subset=["tp"]) if "tp" in df else df.iloc[0:0]
    tp, fp, fn = lab["tp"].sum(), lab["fp"].sum(), lab["fn"].sum()
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    neg = df[df["expected"] == 0]
    fa_min = neg["detected"].sum() / (neg["dur_s"].sum() / 60) if len(neg) and neg["dur_s"].sum() else float("nan")
    cnt = df.dropna(subset=["expected"])
    exact = float((cnt["detected"] == cnt["expected"]).mean()) if len(cnt) else float("nan")
    return dict(precision=round(prec, 3), recall=round(rec, 3),
                f1=round(2 * prec * rec / (prec + rec), 3) if prec + rec else float("nan"),
                false_alarms_per_min_on_negatives=round(fa_min, 2),
                count_exact_ratio=round(exact, 3))


# ---------------- eksport do C ----------------

def export_c_header(model, threshold: float, path: Path) -> None:
    lines = [
        "#pragma once",
        "// WYGENEROWANE przez tools/clapml (python -m clapml train). Nie edytowac recznie.",
        "// Cechy musza byc liczone dokladnie jak w tools/clapml/features.py, w tej kolejnosci:",
    ]
    lines += [f"//   [{i}] {n}" for i, n in enumerate(FEATURES)]
    lines.append(f"#define CLAP_N_FEATURES {len(FEATURES)}")
    lines.append(f"#define CLAP_THRESHOLD {threshold:.6f}f")
    if hasattr(model, "named_steps"):  # logreg
        sc = model.named_steps["standardscaler"]; lr = model.named_steps["logisticregression"]
        f = lambda a: ", ".join(f"{v:.7g}f" for v in a)
        lines += [
            f"static const float CLAP_MEAN[CLAP_N_FEATURES]  = {{{f(sc.mean_)}}};",
            f"static const float CLAP_SCALE[CLAP_N_FEATURES] = {{{f(sc.scale_)}}};",
            f"static const float CLAP_COEF[CLAP_N_FEATURES]  = {{{f(lr.coef_[0])}}};",
            f"static const float CLAP_BIAS = {lr.intercept_[0]:.7g}f;",
            "",
            "// Prawdopodobienstwo, ze kandydat jest klasnieciem (0..1).",
            "inline float clapProbability(const float* x) {",
            "  float z = CLAP_BIAS;",
            "  for (int i = 0; i < CLAP_N_FEATURES; i++) z += CLAP_COEF[i] * (x[i] - CLAP_MEAN[i]) / CLAP_SCALE[i];",
            "  return 1.0f / (1.0f + expf(-z));",
            "}",
        ]
    else:  # drzewo
        t = model.tree_
        def node(i, ind):
            pad = "  " * ind
            if t.children_left[i] == -1:
                v = t.value[i][0]
                return [f"{pad}return {v[1] / v.sum():.4f}f;"]
            return ([f"{pad}if (x[{t.feature[i]}] <= {t.threshold[i]:.6g}f) {{  // {FEATURES[t.feature[i]]}"]
                    + node(t.children_left[i], ind + 1) + [f"{pad}}} else {{"]
                    + node(t.children_right[i], ind + 1) + [f"{pad}}}"])
        lines += ["", "inline float clapProbability(const float* x) {"] + node(0, 1) + ["}"]
    lines += ["", "inline bool clapIsClap(const float* x) { return clapProbability(x) >= CLAP_THRESHOLD; }", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
