"""Generate synthetic multi-cloud session logs for educational experiments.

Outcome labels are sampled from a synthetic session-health model dependent on
authentication strength, anomaly indicators and context, plus random noise.
Because the data-generating process is artificial, reported metrics do not
establish real-world security or attack-detection performance.
"""
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(BASE_DIR, "artifacts")
os.makedirs(ARTIFACTS, exist_ok=True)

PROVIDERS = ["aws", "azure", "gcp", "oci"]
AUTH_METHODS = ["password", "certificate", "mfa", "hardware_key", "biometric"]
SESSION_TYPES = ["web", "api", "cli", "mobile"]
COUNTRIES = ["IN", "US", "SG", "DE", "BR", "NG", "RU", "CN"]

AUTH_COEF = {
    "password": -1.30,
    "certificate": 0.10,
    "mfa": 0.75,
    "hardware_key": 1.55,
    "biometric": 1.05,
}
SENSITIVE_RESOURCES = {"finance_db": 5, "hr_records": 4, "k8s_prod": 5,
                       "ci_pipeline": 3, "object_store": 2, "analytics": 2,
                       "log_archive": 1}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def generate(n_sessions: int = 9000, seed: int = 42, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    random.seed(seed)

    # ---- population of users -------------------------------------------- #
    n_users = 120
    users = []
    for i in range(n_users):
        users.append({
            "user_id": f"user_{i:03d}",
            "home_country": rng.choice(COUNTRIES, p=[0.55, 0.15, 0.10, 0.08, 0.04, 0.03, 0.03, 0.02]),
            "usual_hour": int(rng.normal(13, 3)) % 24,
            "usual_duration": float(rng.normal(1800, 600)),
            "device": f"dev_{rng.integers(100, 999)}",
            "pref_auth": AUTH_METHODS[int(rng.integers(0, len(AUTH_METHODS)))],
        })

    start = datetime(2026, 1, 1)
    rows = []
    for i in range(n_sessions):
        u = users[int(rng.integers(0, n_users))]

        # authentication & session shape
        if rng.random() < 0.45:
            auth = u["pref_auth"]
        else:
            auth = AUTH_METHODS[int(rng.integers(0, len(AUTH_METHODS)))]
        provider = PROVIDERS[int(rng.integers(0, len(PROVIDERS)))]
        stype = SESSION_TYPES[int(rng.integers(0, len(SESSION_TYPES)))]

        # time of day
        hour = int((u["usual_hour"] + rng.normal(0, 2)) % 24) if rng.random() < 0.75 \
            else int(rng.integers(0, 24))
        ts = start + timedelta(days=float(rng.uniform(0, 300)),
                               hours=float(hour), minutes=float(rng.integers(0, 60)))

        # geo / device novelty
        geo_mismatch = int(rng.random() < (0.10 + drift * 0.10))
        country = COUNTRIES[int(rng.integers(0, len(COUNTRIES)))] if geo_mismatch else u["home_country"]
        is_new_device = int(rng.random() < (0.12 + drift * 0.08))
        device = (f"dev_{rng.integers(1000, 9999)}" if is_new_device else u["device"])

        # behavioural counters
        failed_attempts = int(rng.poisson(0.5 + drift * 0.6))
        request_rate = float(np.round(rng.lognormal(1.2 + drift * 0.45, 0.55), 2))
        resource = random.choice(list(SENSITIVE_RESOURCES.keys()))
        sensitivity = SENSITIVE_RESOURCES[resource]

        duration = float(max(20, rng.normal(u["usual_duration"] * (1.6 if stype == "web" else 1.0), 500)))
        if auth in ("hardware_key", "biometric"):
            duration *= 0.9

        bytes_mb = float(np.round(rng.lognormal(2.0, 0.8), 2))
        anomaly = int(rng.choice([0, 0, 0, 0, 0, 1, 1, 2, 3], p=None))

        # ---- latent outcome process ------------------------------------- #
        # A synthetic logit combines signal with noise. No real-world accuracy
        # or theoretical performance ceiling is established by this generator.
        z = 2.55
        z += 1.5 * AUTH_COEF[auth]
        z -= 0.95 * failed_attempts
        z -= 1.30 * is_new_device
        z -= 1.50 * geo_mismatch
        z -= 0.65 * int(not (8 <= hour <= 20))
        z -= 0.55 * max(0.0, np.log1p(request_rate) - np.log1p(8))
        z -= 0.45 * max(0.0, sensitivity - 3)
        z -= 1.00 * anomaly
        z -= 0.35 * float(np.clip(abs(duration - u["usual_duration"]) / 2000.0, 0, 2))
        z += 0.15 * {"web": 0.0, "api": -0.4, "cli": -0.2, "mobile": 0.1}[stype]
        z += rng.normal(0, 0.52)                      # irreducible noise

        p_success = float(_sigmoid(z))
        outcome = "success" if rng.random() < p_success else "failure"

        rows.append({
            "session_id": f"sess_{i:06d}",
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": u["user_id"],
            "ip_address": f"{rng.choice(['10','172','192','203'])}."
                          f"{rng.integers(0,255)}.{rng.integers(0,255)}.{rng.integers(1,254)}",
            "country": country,
            "device_id": device,
            "cloud_provider": provider,
            "auth_method": auth,
            "session_type": stype,
            "resource_accessed": resource,
            "resource_sensitivity": sensitivity,
            "session_duration_sec": int(duration),
            "bytes_transferred_mb": bytes_mb,
            "failed_attempts": failed_attempts,
            "request_rate_per_min": request_rate,
            "is_new_device": is_new_device,
            "geo_mismatch": geo_mismatch,
            "hour_of_day": hour,
            "anomaly_flag": anomaly,
            "risk_probability_true": round(p_success, 4),
            "outcome": outcome,
        })

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


def write_datasets():
    train = generate(9000, seed=42, drift=0.0)
    stream = generate(2500, seed=777, drift=0.55)        # drifted "live" traffic
    p1 = os.path.join(ARTIFACTS, "sessions_train.csv")
    p2 = os.path.join(ARTIFACTS, "sessions_stream.csv")
    train.to_csv(p1, index=False)
    stream.to_csv(p2, index=False)
    return p1, p2, len(train), len(stream)


if __name__ == "__main__":
    p1, p2, n1, n2 = write_datasets()
    print(f"wrote {p1} ({n1} rows)\nwrote {p2} ({n2} rows)")
