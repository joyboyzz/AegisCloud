"""Train and evaluate the synthetic session-outcome model.

Features include user baselines, time and behavioural context. A chronological
split and training-only preprocessing separate fitting from validation and
holdout evaluation. Candidate selection and threshold tuning use validation;
the selected model is then evaluated on the later synthetic test block.
Results do not establish performance on actual security events.
"""
import json
import os
import time
import uuid

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, brier_score_loss, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score,
                             roc_curve, precision_recall_curve, average_precision_score)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(BASE_DIR, "artifacts")
MODEL_DIR = os.path.join(ARTIFACTS, "models")
os.makedirs(MODEL_DIR, exist_ok=True)

NUMERIC = ["resource_sensitivity", "session_duration_sec", "bytes_transferred_mb",
           "failed_attempts", "request_rate_per_min", "is_new_device",
           "geo_mismatch", "hour_of_day", "anomaly_flag"]
CATEGORICAL = ["cloud_provider", "auth_method", "session_type", "resource_accessed"]
DERIVED = ["duration_z", "duration_absdev", "off_hours", "velocity_score",
           "velocity_excess", "auth_strength", "novelty_score", "interaction_risk"]

AUTH_STRENGTH = {"password": 0.15, "certificate": 0.55, "mfa": 0.75,
                 "hardware_key": 1.0, "biometric": 0.9}


def engineer(df: pd.DataFrame, user_baseline: dict | None = None) -> tuple:
    """Build model features; when fitting, learn baselines from this input only.

    For evaluation or serving, pass the training baseline. The global training
    mean/std are used for previously unseen users; no statistic is estimated
    from the validation/test block or the single request being scored.
    """
    d = df.copy()
    for c in NUMERIC:
        if c not in d:
            d[c] = 0
    durations = pd.to_numeric(d["session_duration_sec"], errors="coerce").fillna(0.0)
    d["session_duration_sec"] = durations
    if user_baseline is None:
        global_mean = float(durations.mean()) if len(durations) else 1800.0
        global_std = float(durations.std()) if len(durations) > 1 else 1.0
        if not np.isfinite(global_mean):
            global_mean = 1800.0
        if not np.isfinite(global_std) or global_std <= 0:
            global_std = 1.0
        grouped = d.groupby("user_id")["session_duration_sec"].agg(["mean", "std"])
        user_baseline = {"__global__": {"mean": global_mean, "std": global_std}}
        for user_id, row in grouped.iterrows():
            mean, std = float(row["mean"]), float(row["std"])
            user_baseline[str(user_id)] = {
                "mean": mean if np.isfinite(mean) else global_mean,
                "std": std if np.isfinite(std) and std > 0 else global_std,
            }
    global_stats = user_baseline.get("__global__", {"mean": 1800.0, "std": 600.0})
    global_mean = float(global_stats.get("mean", 1800.0))
    global_std = float(global_stats.get("std", 600.0))
    if not np.isfinite(global_std) or global_std <= 0:
        global_std = 1.0
    means = d["user_id"].map(lambda u: user_baseline.get(str(u), global_stats).get("mean", global_mean)).astype(float)
    stds = d["user_id"].map(lambda u: user_baseline.get(str(u), global_stats).get("std", global_std)).astype(float)
    stds = stds.replace([np.inf, -np.inf, 0], np.nan).fillna(global_std)
    d["duration_z"] = ((durations - means) / stds).clip(-4, 4)
    d["off_hours"] = ((d["hour_of_day"] < 8) | (d["hour_of_day"] > 20)).astype(int)
    d["duration_absdev"] = (means - durations).abs() / 2000.0
    d["velocity_score"] = np.log1p(d["request_rate_per_min"].clip(lower=0))
    d["velocity_excess"] = (d["velocity_score"] - np.log1p(8)).clip(lower=0)
    d["auth_strength"] = d["auth_method"].map(AUTH_STRENGTH).fillna(0.15)
    d["novelty_score"] = d["is_new_device"] * 1.0 + d["geo_mismatch"] * 1.0
    d["interaction_risk"] = (d["novelty_score"] * (1.0 - d["auth_strength"])
                             + 0.5 * d["failed_attempts"] * d["off_hours"])
    feats = d[NUMERIC + DERIVED]
    cat = pd.get_dummies(d[CATEGORICAL], columns=CATEGORICAL, prefix_sep="=")
    X = pd.concat([feats, cat], axis=1).astype("float32")
    return X, user_baseline


def _split_time(X, y, blocks=(0.70, 0.15, 0.15)):
    n = len(X)
    a = int(n * blocks[0])
    b = int(n * (blocks[0] + blocks[1]))
    return (X.iloc[:a], y.iloc[:a]), (X.iloc[a:b], y.iloc[a:b]), (X.iloc[b:], y.iloc[b:])


def _candidates(seed=42):
    return {
        "LogisticRegression": Pipeline([
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]),
        "RandomForest": RandomForestClassifier(
            n_estimators=350, max_depth=14, min_samples_leaf=4,
            class_weight="balanced_subsample", n_jobs=-1, random_state=seed),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, max_depth=6, l2_regularization=1.0,
            random_state=seed),
        "MLPClassifier": Pipeline([
            ("sc", StandardScaler()),
            ("clf", MLPClassifier(hidden_layer_sizes=(64, 32), activation="relu",
                                  alpha=1e-4, learning_rate_init=3e-3, max_iter=400,
                                  early_stopping=True, random_state=seed)),
        ]),
    }


def _metrics(y_true, proba, threshold=0.5, y_pred=None):
    if y_pred is None:
        y_pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr, tpr, _ = roc_curve(y_true, proba)
    prec, rec, _ = precision_recall_curve(y_true, proba)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 4),
        "avg_precision": round(float(average_precision_score(y_true, proba)), 4),
        "brier": round(float(brier_score_loss(y_true, proba)), 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "roc_curve": [[round(float(a), 5), round(float(b), 5)] for a, b in zip(fpr, tpr)][::max(1, len(fpr) // 120)],
        "pr_curve": [[round(float(a), 5), round(float(b), 5)] for a, b in zip(rec, prec)][::max(1, len(prec) // 120)],
        "threshold": threshold,
    }


def train(train_csv: str | None = None, register: bool = True, notes: str = "") -> dict:
    train_csv = train_csv or os.path.join(ARTIFACTS, "sessions_train.csv")
    df = pd.read_csv(train_csv).sort_values("timestamp", kind="stable").reset_index(drop=True)
    n = len(df)
    if n < 20:
        raise ValueError("at least 20 dated sessions are required")
    train_end, val_end = int(n * 0.70), int(n * 0.85)
    raw_tr, raw_va, raw_te = df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]
    ytr = (raw_tr["outcome"].str.lower() == "success").astype(int)
    yva = (raw_va["outcome"].str.lower() == "success").astype(int)
    yte = (raw_te["outcome"].str.lower() == "success").astype(int)

    # Fit all user baselines and categorical vocabulary on the past only.
    Xtr, baseline = engineer(raw_tr)
    Xva, _ = engineer(raw_va, baseline)
    Xte, _ = engineer(raw_te, baseline)
    Xva = Xva.reindex(columns=Xtr.columns, fill_value=0)
    Xte = Xte.reindex(columns=Xtr.columns, fill_value=0)

    results, models = {}, {}
    for name, mdl in _candidates().items():
        t0 = time.time()
        mdl.fit(Xtr, ytr)
        p_va = mdl.predict_proba(Xva)[:, 1]
        results[name] = _metrics(yva, p_va)
        results[name]["train_seconds"] = round(time.time() - t0, 2)
        models[name] = mdl

    champion = max(results, key=lambda k: (results[k]["f1"], results[k]["roc_auc"]))
    best = models[champion]

    # threshold tuning on validation (maximise F1, keep recall >= 0.80)
    p_va = best.predict_proba(Xva)[:, 1]
    grid = np.linspace(0.2, 0.8, 61)
    best_thr, best_f1 = 0.5, -1
    for t in grid:
        pred = (p_va >= t).astype(int)
        f1 = f1_score(yva, pred, zero_division=0)
        rec = recall_score(yva, pred, zero_division=0)
        if rec >= 0.80 and f1 > best_f1:
            best_thr, best_f1 = round(float(t), 2), f1

    p_te = best.predict_proba(Xte)[:, 1]
    test_metrics = _metrics(yte, p_te, threshold=best_thr)
    val_metrics = _metrics(yva, p_va, threshold=best_thr)

    scan = []
    for t in np.round(np.arange(0.10, 0.96, 0.05), 2):
        m = _metrics(yva, p_va, threshold=float(t))
        scan.append({"threshold": round(float(t), 2), "accuracy": m["accuracy"],
                     "precision": m["precision"], "recall": m["recall"], "f1": m["f1"],
                     "fp": m["confusion"]["fp"], "fn": m["confusion"]["fn"]})

    version = time.strftime("v%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    path = os.path.join(MODEL_DIR, f"{version}.joblib")
    bundle = {
        "model": best, "champion": champion, "features": list(Xtr.columns),
        "threshold": best_thr, "baseline": baseline, "version": version,
        "trained_at": time.time(), "engine": "sklearn",
        "val_metrics": val_metrics, "test_metrics": test_metrics,
        "candidates": results,
        "feature_importance": _global_importance(best, list(Xtr.columns), Xva, yva),
        "train_rows": int(len(Xtr)), "test_rows": int(len(Xte)),
        "threshold_scan": scan,
    }
    joblib.dump(bundle, path)
    joblib.dump(bundle, os.path.join(ARTIFACTS, "champion.joblib"))

    if register:
        db.execute("INSERT INTO model_versions(version,engine,metrics,path,created_at,active,notes)"
                   " VALUES(?,?,?,?,?,?,?)",
                   (version, champion,
                    json.dumps({"candidates": results, "val": val_metrics, "test": test_metrics}),
                    path, time.time(), 0, notes))

    return {
        "version": version, "champion": champion, "path": path,
        "candidates": results, "val": val_metrics, "test": test_metrics,
        "threshold": best_thr,
    }


def _global_importance(model, feature_names, validation_X=None, validation_y=None):
    """Normalised native or validation-set permutation importance (AUC)."""
    try:
        imp = None
        inner = model.named_steps["clf"] if hasattr(model, "named_steps") else model
        if hasattr(inner, "feature_importances_"):
            imp = np.asarray(inner.feature_importances_, dtype=float)
        elif hasattr(inner, "coef_"):
            imp = np.abs(np.asarray(inner.coef_)).ravel()
        elif validation_X is not None and validation_y is not None:
            perm = permutation_importance(model, validation_X, validation_y,
                                          scoring="roc_auc", n_repeats=2,
                                          random_state=42, n_jobs=1)
            imp = np.clip(np.asarray(perm.importances_mean, dtype=float), 0, None)
        if imp is None:
            return []
        imp = imp / (imp.sum() or 1)
        pairs = sorted(zip(feature_names, imp), key=lambda t: -t[1])[:12]
        return [{"feature": f, "importance": round(float(v), 4)} for f, v in pairs]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Runtime model service
# --------------------------------------------------------------------------- #
class ModelService:
    def __init__(self):
        self.bundle = None
        self.loaded_at = None
        self.load()

    def load(self):
        path = os.path.join(ARTIFACTS, "champion.joblib")
        if os.path.exists(path):
            self.bundle = joblib.load(path)
            self.loaded_at = time.time()
        return self.bundle

    # ---------------------------------------------------------------- predict
    def _row_from_payload(self, p: dict) -> pd.DataFrame:
        row = {
            "user_id": p.get("user_id", "user_000"),
            "cloud_provider": p.get("cloud_provider", "aws"),
            "auth_method": p.get("auth_method", "password"),
            "session_type": p.get("session_type", "web"),
            "resource_accessed": p.get("resource_accessed", "object_store"),
            "resource_sensitivity": int(p.get("resource_sensitivity", 3)),
            "session_duration_sec": int(p.get("session_duration_sec", 1200)),
            "bytes_transferred_mb": float(p.get("bytes_transferred_mb", 2.0)),
            "failed_attempts": int(p.get("failed_attempts", 0)),
            "request_rate_per_min": float(p.get("request_rate_per_min", 4.0)),
            "is_new_device": int(p.get("is_new_device", 0)),
            "geo_mismatch": int(p.get("geo_mismatch", 0)),
            "hour_of_day": int(p.get("hour_of_day", 12)),
            "anomaly_flag": int(p.get("anomaly_flag", 0)),
        }
        return pd.DataFrame([row])

    def predict_proba(self, payload: dict) -> float:
        if not self.bundle:
            self.load()
        if not self.bundle:
            return 0.5
        df = self._row_from_payload(payload)
        X, _ = engineer(df, self.bundle["baseline"])
        X = X.reindex(columns=self.bundle["features"], fill_value=0)
        return float(self.bundle["model"].predict_proba(X)[:, 1][0])

    def explain(self, payload: dict, top_k: int = 8) -> list:
        """Leave-one-out contributions on the success probability."""
        base = self.predict_proba(payload)
        touched = ["auth_method", "failed_attempts", "is_new_device", "geo_mismatch",
                   "hour_of_day", "request_rate_per_min", "resource_sensitivity",
                   "session_duration_sec", "anomaly_flag", "session_type"]
        neutral = {"auth_method": "mfa", "failed_attempts": 0, "is_new_device": 0,
                   "geo_mismatch": 0, "hour_of_day": 12, "request_rate_per_min": 4.0,
                   "resource_sensitivity": 3, "session_duration_sec": 1800,
                   "anomaly_flag": 0, "session_type": "web"}
        out = []
        for k in touched:
            probe = dict(payload)
            probe[k] = neutral[k]
            delta = self.predict_proba(probe) - base
            # sign convention: negative delta => the actual value made it riskier
            out.append({"feature": k,
                        "value": payload.get(k),
                        "impact": round(-delta, 4)})
        out.sort(key=lambda r: -abs(r["impact"]))
        return out[:top_k]

    def top_features(self, k: int = 12):
        if not self.bundle:
            return []
        return self.bundle.get("feature_importance", [])[:k]

    def info(self) -> dict:
        b = self.bundle or {}
        return {
            "version": b.get("version"), "champion": b.get("champion"),
            "engine": b.get("engine"), "threshold": b.get("threshold"),
            "trained_at": b.get("trained_at"),
            "features": len(b.get("features", [])),
            "train_rows": b.get("train_rows"), "test_rows": b.get("test_rows"),
            "val_metrics": b.get("val_metrics"), "test_metrics": b.get("test_metrics"),
            "candidates": b.get("candidates", {}),
            "importance": b.get("feature_importance", []),
            "threshold_scan": b.get("threshold_scan", []),
        }


_service = None


def service() -> ModelService:
    global _service
    if _service is None:
        _service = ModelService()
    return _service
