"""Bootstrap demo data: users, vault files, a slice of scored session history."""
import csv
import json
import os
import random
import time

from . import crypto_vault, db, risk, security

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(BASE_DIR, "artifacts")

USERS = [
    # username,   email (LOCAL PART),            password,             role
    ("admin",     "admin",    "Admin@Aegis2026",   "admin"),
    ("analyst",   "analyst",  "Analyst@Aegis2026", "analyst"),
    ("demo_user", "demo_user", "User@Aegis2026", "user"),
]
EMAIL_DOMAIN = os.environ.get("AEGIS_EMAIL_DOMAIN", "aegiscloud.local")


def create_user(username, email, password, role, totp_enabled=False, totp_secret=None):
    if db.query("SELECT id FROM users WHERE username=?", (username,), one=True):
        return db.query("SELECT id FROM users WHERE username=?", (username,), one=True)["id"]
    pw_hash, salt = security.hash_password(password)
    uid = db.execute(
        "INSERT INTO users(username,email,pw_hash,pw_salt,role,status,totp_secret,totp_enabled,"
        "created_at,mfa_required) VALUES(?,?,?,?,?,?,?,?,?,1)",
        (username, f"{email}@{EMAIL_DOMAIN}", pw_hash, salt, role, "active",
         totp_secret, int(totp_enabled), time.time()))
    if totp_enabled:
        security.generate_recovery_codes(uid)
    security.audit("seed.user", "system", username, {"role": role})
    return uid


def seed_vault(admin_id):
    if db.query("SELECT COUNT(*) c FROM vault_files", one=True)["c"]:
        return
    samples = {
        "cloud_audit_q3.csv": "session_id,user,provider,outcome\nsess_1,user_001,aws,success\n"
                              "sess_2,user_002,gcp,failure\n",
        "incident_playbook.md": "# Zero-Trust Incident Playbook\n\n1. Detect\n2. Contain\n"
                                "3. Eradicate\n4. Recover\n5. Lessons learned\n",
        "sample_access_events.json": json.dumps({"note": "Synthetic demo records",
                                           "events": [{"user": "user_001", "result": "success"},
                                                      {"user": "user_002", "result": "failure"}]}, indent=2),
        "board_financials.txt": "Quarterly cloud spend: 4.2M INR\nRisk-adjusted saving: 11%\n",
    }
    for name, content in samples.items():
        crypto_vault.store_file(admin_id, name, content.encode(), tags="demo,seed")


def seed_history(limit=180):
    if db.query("SELECT COUNT(*) c FROM decisions", one=True)["c"] > 0:
        return
    path = os.path.join(ARTIFACTS, "sessions_train.csv")
    if not os.path.exists(path):
        return
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))[:limit]
    random.seed(7)
    for raw in rows:
        payload = {
            "user_id": raw["user_id"], "cloud_provider": raw["cloud_provider"],
            "auth_method": raw["auth_method"], "session_type": raw["session_type"],
            "resource_accessed": raw["resource_accessed"],
            "resource_sensitivity": int(raw["resource_sensitivity"]),
            "session_duration_sec": int(raw["session_duration_sec"]),
            "bytes_transferred_mb": float(raw["bytes_transferred_mb"]),
            "failed_attempts": int(raw["failed_attempts"]),
            "request_rate_per_min": float(raw["request_rate_per_min"]),
            "is_new_device": int(raw["is_new_device"]),
            "geo_mismatch": int(raw["geo_mismatch"]),
            "hour_of_day": int(raw["hour_of_day"]),
            "anomaly_flag": int(raw["anomaly_flag"]),
        }
        res = risk.score_session(payload, actor=raw["user_id"], persist=True, source="stream")
        pred_success = res["ml_probability"] >= 0.5
        actual = raw["outcome"]
        label = "correct" if ((actual == "success") == pred_success) else "incorrect"
        db.execute("UPDATE decisions SET label=?, actual_outcome=? WHERE id=?",
                   (label, actual, res["decision_id"]))
    # spread timestamps backwards so the dashboard has a 6h curve
    db.execute("UPDATE decisions SET ts = ts - (id * 95)")
    # keep the alert inbox meaningful rather than flooded
    db.execute("DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT 6)")


def seed_alerts():
    if db.query("SELECT COUNT(*) c FROM alerts", one=True)["c"] > 3:
        return
    security.alert("warning", "Synthetic replay ready",
                   "Compare replay and reference distributions in the model lab.")
    security.alert("info", "Model champion registered",
                   "Inspect synthetic holdout metrics and model details in the model lab.")


def run():
    db.init_db()
    ids = {}
    for username, email, pw, role in USERS:
        totp = username == "analyst"
        existing = db.query("SELECT totp_secret FROM users WHERE username=?", (username,), one=True)
        secret = (existing["totp_secret"] if existing else security.generate_totp_secret()) if totp else None
        ids[username] = create_user(username, email, pw, role, totp, secret)
        if totp and not existing:
            print(f"[seed] analyst TOTP secret = {secret}")
            print(f"[seed] analyst current code = {security.totp_now(secret)}")
    seed_vault(ids["admin"])
    seed_history()
    seed_alerts()
    print(f"[seed] users={db.query('SELECT COUNT(*) c FROM users', one=True)['c']} "
          f"decisions={db.query('SELECT COUNT(*) c FROM decisions', one=True)['c']} "
          f"files={db.query('SELECT COUNT(*) c FROM vault_files', one=True)['c']}")
    print("[seed] login: admin / Admin@Aegis2026  (email-OTP demo code is shown in the UI)")
    print("[seed] login: analyst / Analyst@Aegis2026  (real TOTP, secret above)")


if __name__ == "__main__":
    run()
