"""
Data / concept drift monitoring.

Population Stability Index (PSI) compares the distribution of a feature in the
reference window (training corpus) with the live window.  PSI < 0.10 is
considered stable, 0.10-0.25 warrants watching, above 0.25 means the input
distribution the model was trained on no longer matches reality and the model
should be retrained.  This is what turns "online retraining" from a buzzword
into a measurable trigger.
"""
import numpy as np
import pandas as pd

NUMERIC = ["session_duration_sec", "failed_attempts", "request_rate_per_min",
           "resource_sensitivity", "hour_of_day", "bytes_transferred_mb", "anomaly_flag"]
CATEGORICAL = ["auth_method", "cloud_provider", "session_type", "resource_accessed"]


def _psi_numeric(ref, cur, bins=10):
    ref = pd.to_numeric(ref, errors="coerce").dropna()
    cur = pd.to_numeric(cur, errors="coerce").dropna()
    if len(ref) < 10 or len(cur) < 10:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) == 1:
        # A constant reference is a valid distribution; a changed value is drift.
        return _psi_categorical(ref, cur)
    if len(edges) == 2:
        edges = np.array([-np.inf, (edges[0] + edges[1]) / 2.0, np.inf])
    else:
        # Count live values outside the reference range rather than silently
        # dropping the very extremes we want to detect.
        edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, bins=edges)[0] / len(ref)
    c = np.histogram(cur, bins=edges)[0] / len(cur)
    r = np.clip(r, 1e-4, None)
    c = np.clip(c, 1e-4, None)
    return float(np.sum((c - r) * np.log(c / r)))


def _psi_categorical(ref, cur):
    r = ref.astype(str).value_counts(normalize=True)
    c = cur.astype(str).value_counts(normalize=True)
    idx = sorted(set(r.index) | set(c.index))
    rv = np.clip(np.array([r.get(i, 0.0) for i in idx]), 1e-4, None)
    cv = np.clip(np.array([c.get(i, 0.0) for i in idx]), 1e-4, None)
    return float(np.sum((cv - rv) * np.log(cv / rv)))


def psi_report(ref: pd.DataFrame, cur: pd.DataFrame) -> dict:
    rows = []
    for col in NUMERIC:
        if col in ref and col in cur:
            s = _psi_numeric(ref[col], cur[col])
            rows.append({"feature": col, "psi": round(s, 4), "kind": "numeric"})
    for col in CATEGORICAL:
        if col in ref and col in cur:
            s = _psi_categorical(ref[col], cur[col])
            rows.append({"feature": col, "psi": round(s, 4), "kind": "categorical"})

    for r in rows:
        r["status"] = ("drift" if r["psi"] >= 0.25 else
                       "watch" if r["psi"] >= 0.10 else "stable")
    drifters = [r for r in rows if r["status"] == "drift"]
    watchers = [r for r in rows if r["status"] == "watch"]
    return {
        "features": sorted(rows, key=lambda r: -r["psi"]),
        "max_psi": max([r["psi"] for r in rows], default=0.0),
        "mean_psi": round(float(np.mean([r["psi"] for r in rows]) if rows else 0.0), 4),
        "drifted": len(drifters), "watching": len(watchers),
        "recommendation": ("retrain now" if drifters else
                           "monitor" if watchers else "no action"),
        "reference_rows": int(len(ref)), "current_rows": int(len(cur)),
    }
