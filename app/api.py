"""JSON REST API consumed by the single-page console."""
import csv
import hashlib
import io
import json
import os
import threading
import time
from datetime import datetime
from functools import wraps

from flask import Blueprint, Response, jsonify, request, send_file

from . import crypto_vault, db, risk, security
from .ml import service as model_service, train

api = Blueprint("api", __name__, url_prefix="/api")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS = os.path.join(BASE_DIR, "artifacts")
DEMO = os.environ.get("AEGIS_DEMO", "1") == "1"

# in-memory MFA challenges (short lived, server side)
_challenges = {}
_challenge_lock = threading.Lock()
OTP_TTL = 240


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _json_body():
    return request.get_json(silent=True) or {}


def _token_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("aegis_token") or request.args.get("token")


def current_user():
    payload = security.verify_token(_token_from_request())
    if not payload:
        return None
    row = db.query("SELECT * FROM users WHERE id=?", (payload["uid"],), one=True)
    if not row or row["status"] != "active":
        return None
    security.touch_session(payload["sid"])
    payload["role"] = row["role"]
    payload["email"] = row["email"]
    return payload


def require_auth(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                return jsonify({"success": False, "error": "authentication required"}), 401
            if roles and user["role"] not in roles:
                return jsonify({"success": False, "error": "insufficient role"}), 403
            return fn(user, *a, **kw)
        return wrapper
    return deco


def _session_cookie_options():
    # A preview embedded on a different top-level site needs a partitioned,
    # cross-site cookie. The live preview is served over HTTPS by the proxy;
    # this relaxation is explicitly limited to the opt-in demo environment.
    if os.environ.get("AEGIS_ALLOW_EMBED", "0") == "1":
        return {"secure": True, "samesite": "None", "partitioned": True}
    return {"secure": False, "samesite": "Lax", "partitioned": False}


def _with_cookie(payload, max_age=8 * 3600):
    resp = jsonify(payload)
    if payload.get("token"):
        resp.set_cookie("aegis_token", payload["token"], max_age=max_age, httponly=True,
                        path="/", **_session_cookie_options())
    return resp


def _purge_challenges():
    now = time.time()
    with _challenge_lock:
        for k in [k for k, v in _challenges.items() if v["expires_at"] < now]:
            _challenges.pop(k, None)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@api.post("/auth/register")
def register():
    d = _json_body()
    username = (d.get("username") or "").strip()
    email = (d.get("email") or "").strip()
    password = d.get("password") or ""
    if not username or not email or not password:
        return jsonify({"success": False, "error": "username, email and password are required"}), 400
    report = security.password_report(password)
    if not report["ok"]:
        return jsonify({"success": False, "error": "Password does not meet the policy",
                        "password_report": report}), 400
    if db.query("SELECT id FROM users WHERE username=?", (username,), one=True):
        return jsonify({"success": False, "error": "Username already exists"}), 409
    if db.query("SELECT id FROM users WHERE email=?", (email,), one=True):
        return jsonify({"success": False, "error": "Email already registered"}), 409
    pw_hash, salt = security.hash_password(password)
    uid = db.execute(
        "INSERT INTO users(username,email,pw_hash,pw_salt,role,status,created_at,mfa_required)"
        " VALUES(?,?,?,?,?,?,?,1)", (username, email, pw_hash, salt, "user", "active", time.time()))
    security.audit("user.register", username, username, {"email": email})
    security.alert("info", "New account registered", f"{username} <{email}>")
    return jsonify({"success": True, "user_id": uid, "password_report": report})


@api.post("/auth/password-check")
def password_check():
    return jsonify(security.password_report(_json_body().get("password", "")))


@api.post("/auth/login")
def login():
    _purge_challenges()
    d = _json_body()
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    ip = request.remote_addr or "-"
    device_fp = d.get("device_fp") or hashlib.sha256(
        (ip + (request.headers.get("User-Agent") or "")).encode()).hexdigest()[:16]

    row = db.query("SELECT * FROM users WHERE username=?", (username,), one=True)
    if not row:
        security.audit("auth.login", username or "-", "-", {"result": "unknown user", "ip": ip})
        return jsonify({"success": False, "error": "Invalid credentials"}), 401
    if row["status"] != "active":
        return jsonify({"success": False, "error": "Account suspended"}), 403
    if row["locked_until"] and row["locked_until"] > time.time():
        wait = int(row["locked_until"] - time.time())
        return jsonify({"success": False, "error": f"Account locked, retry in {wait}s",
                        "locked_for": wait}), 429
    if not security.verify_password(password, row["pw_hash"], row["pw_salt"]):
        fails = security.register_failure(row["id"])
        security.audit("auth.login.failed", username, "-", {"attempts": fails, "ip": ip})
        return jsonify({"success": False, "error": "Invalid credentials", "attempts": fails}), 401

    security.reset_failures(row["id"])

    # device bookkeeping
    dev = db.query("SELECT * FROM devices WHERE user_id=? AND fingerprint=?",
                   (row["id"], device_fp), one=True)
    device_new = dev is None
    if dev:
        db.execute("UPDATE devices SET last_seen=? WHERE id=?", (time.time(), dev["id"]))
    else:
        db.execute("INSERT INTO devices(user_id,fingerprint,label,trusted,first_seen,last_seen)"
                   " VALUES(?,?,?,?,?,?)", (row["id"], device_fp,
                                            (request.headers.get("User-Agent") or "browser")[:60],
                                            0, time.time(), time.time()))

    hour = int(d.get("hour", datetime.now().hour))
    pre_risk = risk.login_risk(username, device_new, ip, row["failed_attempts"], hour)

    if row["mfa_required"] == 0:
        tok = security.issue_token(row["id"], username, True, device_fp, ip)
        db.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), row["id"]))
        security.audit("auth.login", username, "-", {"ip": ip, "mfa": False})
        return _with_cookie({"success": True, **tok, "username": username, "role": row["role"],
                             "pre_risk": pre_risk})

    mode = "totp" if row["totp_enabled"] else "email"
    if mode == "email" and not DEMO:
        return jsonify({"success": False, "error": "Email OTP delivery is not configured; use demo mode or TOTP"}), 503
    challenge = security.secrets.token_hex(16)
    oto = security.secrets.randbelow(900000) + 100000 if mode == "email" else None
    with _challenge_lock:
        _challenges[challenge] = {
            "user_id": row["id"], "username": username, "mode": mode,
            "device_fp": device_fp, "ip": ip, "expires_at": time.time() + OTP_TTL,
            "otp": str(oto) if oto else None, "attempts": 0,
        }
    security.audit("auth.challenge", username, mode, {"ip": ip, "device_new": device_new})
    body = {"success": True, "mfa_required": mode, "challenge": challenge,
            "expires_in": OTP_TTL, "pre_risk": pre_risk, "device_new": device_new,
            "username": username}
    if DEMO and oto:
        body["demo_otp"] = str(oto)          # demo only: no mail server in the sandbox
    return jsonify(body)


@api.post("/auth/mfa")
def mfa_verify():
    d = _json_body()
    ch = d.get("challenge") or ""
    code = (d.get("code") or "").strip()
    with _challenge_lock:
        state = _challenges.get(ch)
    if not state or state["expires_at"] < time.time():
        return jsonify({"success": False, "error": "Challenge expired, please login again"}), 400
    row = db.query("SELECT * FROM users WHERE id=?", (state["user_id"],), one=True)
    ok = False
    if d.get("recovery"):
        ok = security.use_recovery_code(row["id"], code)
    elif state["mode"] == "totp":
        ok = security.verify_totp(row["totp_secret"], code)
    else:
        ok = code == state["otp"]

    if not ok:
        state["attempts"] += 1
        if state["attempts"] >= 5:
            with _challenge_lock:
                _challenges.pop(ch, None)
        security.audit("auth.mfa.failed", state["username"], state["mode"], {"ip": state["ip"]})
        return jsonify({"success": False, "error": "Invalid code"}), 401

    with _challenge_lock:
        _challenges.pop(ch, None)
    if d.get("trust_device"):
        db.execute("UPDATE devices SET trusted=1 WHERE user_id=? AND fingerprint=?",
                   (row["id"], state["device_fp"]))
    tok = security.issue_token(row["id"], row["username"], True, state["device_fp"], state["ip"])
    db.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), row["id"]))
    security.audit("auth.login", row["username"], "-",
                   {"ip": state["ip"], "mfa": state["mode"], "trusted_device": bool(d.get("trust_device"))})
    return _with_cookie({"success": True, **tok, "username": row["username"],
                         "role": row["role"]})


@api.get("/auth/me")
@require_auth()
def me(user):
    return jsonify({"success": True, "username": user["u"], "role": user["role"],
                    "email": user["email"], "mfa_verified": user["mfa"],
                    "session_id": user["sid"]})


@api.post("/auth/logout")
@require_auth()
def logout(user):
    security.revoke_session(user["sid"])
    security.audit("auth.logout", user["u"], "-", {})
    resp = jsonify({"success": True})
    resp.delete_cookie("aegis_token", path="/", httponly=True, **_session_cookie_options())
    return resp


@api.get("/auth/totp/enroll")
@require_auth()
def totp_enroll(user):
    row = db.query("SELECT * FROM users WHERE id=?", (user["uid"],), one=True)
    secret = row["totp_secret"] or security.generate_totp_secret()
    if not row["totp_secret"]:
        db.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, user["uid"]))
    uri = security.totp_uri(secret, row["email"], "AegisCloud")
    return jsonify({"success": True, "secret": secret, "uri": uri,
                    "qr_svg": security.qr_svg(uri), "enabled": bool(row["totp_enabled"])})


@api.post("/auth/totp/activate")
@require_auth()
def totp_activate(user):
    code = (_json_body().get("code") or "").strip()
    row = db.query("SELECT * FROM users WHERE id=?", (user["uid"],), one=True)
    if not row["totp_secret"] or not security.verify_totp(row["totp_secret"], code):
        return jsonify({"success": False, "error": "Invalid authenticator code"}), 400
    db.execute("UPDATE users SET totp_enabled=1 WHERE id=?", (user["uid"],))
    codes = security.generate_recovery_codes(user["uid"])
    security.audit("auth.totp.enabled", user["u"], "-", {})
    return jsonify({"success": True, "recovery_codes": codes})


@api.get("/auth/sessions")
@require_auth()
def my_sessions(user):
    rows = db.query("SELECT id,ip,device_fp,created_at,last_seen,expires_at,revoked FROM sessions"
                    " WHERE user_id=? ORDER BY last_seen DESC LIMIT 20", (user["uid"],))
    return jsonify({"success": True, "sessions": rows, "current": user["sid"]})


@api.delete("/auth/sessions/<sid>")
@require_auth()
def kill_session(user, sid):
    owner = db.query("SELECT user_id FROM sessions WHERE id=?", (sid,), one=True)
    if not owner or (owner["user_id"] != user["uid"] and user["role"] != "admin"):
        return jsonify({"success": False, "error": "session not found"}), 404
    security.revoke_session(sid)
    security.audit("auth.session.revoked", user["u"], sid, {})
    return jsonify({"success": True})


# --------------------------------------------------------------------------- #
# Risk engine
# --------------------------------------------------------------------------- #
@api.get("/risk/presets")
@require_auth()
def risk_presets(user):
    return jsonify({"success": True, "presets": risk.PRESETS,
                    "policy": risk.POLICY})


@api.post("/risk/score")
@require_auth()
def risk_score(user):
    d = _json_body()
    payload = d.get("session") or d
    result = risk.score_session(payload, actor=payload.get("user_id") or user["u"],
                                persist=bool(d.get("persist", False)),
                                source=d.get("source", "manual"))
    if d.get("persist"):
        security.audit("risk.decision", user["u"], str(result.get("decision_id")),
                       {"risk": result["risk_score"], "decision": result["decision"]})
    return jsonify({"success": True, **result})


@api.post("/risk/feedback")
@require_auth()
def risk_feedback(user):
    d = _json_body()
    did = d.get("decision_id")
    label = (d.get("label") or "").lower()
    actual = d.get("actual_outcome")
    if not did or label not in ("correct", "incorrect"):
        return jsonify({"success": False, "error": "decision_id and label required"}), 400
    row = db.query("SELECT * FROM decisions WHERE id=?", (did,), one=True)
    if not row:
        return jsonify({"success": False, "error": "decision not found"}), 404
    threshold = (model_service().bundle or {}).get("threshold", 0.5)
    pred_success = row["ml_probability"] >= threshold
    if label == "correct":
        actual = "success" if pred_success else "failure"
    else:
        actual = "failure" if pred_success else "success"
    db.execute("UPDATE decisions SET label=?, actual_outcome=? WHERE id=?",
               (label, actual, did))
    security.audit("risk.feedback", user["u"], str(did), {"label": label, "actual": actual})
    return jsonify({"success": True, "recorded": {"label": label, "actual_outcome": actual}})


@api.get("/risk/history")
@require_auth()
def risk_history(user):
    limit = min(int(request.args.get("limit", 60)), 500)
    rows = db.query("SELECT id,ts,source,actor,risk_score,decision,ml_probability,label,payload"
                    " FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["factors"] = db.jload(r.pop("payload"), {})
    return jsonify({"success": True, "decisions": rows})


# --------------------------------------------------------------------------- #
# Live monitor (streams the drifted session feed through the engine)
# --------------------------------------------------------------------------- #
_stream = {"rows": None, "index": 0, "lock": threading.Lock()}


def _stream_rows():
    if _stream["rows"] is None:
        path = os.path.join(ARTIFACTS, "sessions_stream.csv")
        with open(path, newline="") as f:
            _stream["rows"] = list(csv.DictReader(f))
    return _stream["rows"]


@api.post("/stream/reset")
@require_auth()
def stream_reset(user):
    with _stream["lock"]:
        _stream["index"] = 0
    return jsonify({"success": True, "total": len(_stream_rows())})


@api.get("/stream/next")
@require_auth()
def stream_next(user):
    n = min(int(request.args.get("n", 1)), 10)
    rows = _stream_rows()
    out = []
    with _stream["lock"]:
        for _ in range(n):
            if _stream["index"] >= len(rows):
                _stream["index"] = 0
            raw = rows[_stream["index"]]
            _stream["index"] += 1
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
            res = risk.score_session(payload, actor=raw["user_id"], persist=True,
                                     source="stream")
            out.append({
                "session_id": raw["session_id"],
                # present the replayed row as "now" so the feed reads like live traffic
                "timestamp": datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S"),
                "source_timestamp": raw["timestamp"],
                "user_id": raw["user_id"], "ip": raw["ip_address"],
                "provider": raw["cloud_provider"], "auth": raw["auth_method"],
                "resource": raw["resource_accessed"], "country": raw["country"],
                "actual": raw["outcome"], "risk_score": res["risk_score"],
                "decision": res["decision"], "ml_probability": res["ml_probability"],
                "top_factor": (res["factors"][0]["factor"] if res["factors"] else "-"),
                "decision_id": res.get("decision_id"),
            })
    return jsonify({"success": True, "items": out,
                    "position": _stream["index"], "total": len(rows)})


# --------------------------------------------------------------------------- #
# Vault
# --------------------------------------------------------------------------- #
@api.post("/vault/upload")
@require_auth()
def vault_upload(user):
    if "file" not in request.files:
        return jsonify({"success": False, "error": "no file"}), 400
    f = request.files["file"]
    data = f.read()
    if len(data) > 25 * 1024 * 1024:
        return jsonify({"success": False, "error": "file larger than 25 MB"}), 413
    meta = crypto_vault.store_file(user["uid"], f.filename or "unnamed.bin", data,
                                   request.form.get("tags", ""))
    security.audit("vault.upload", user["u"], meta["filename"],
                   {"size": meta["size_bytes"], "sha256": meta["sha256"][:16]})
    return jsonify({"success": True, **meta})


@api.get("/vault/files")
@require_auth()
def vault_files(user):
    rows = db.query(
        "SELECT f.*, (SELECT COUNT(*) FROM share_links s WHERE s.file_id=f.id AND s.revoked=0"
        " AND s.expires_at>?) AS links FROM vault_files f WHERE f.owner_id=? ORDER BY f.id DESC",
        (time.time(), user["uid"]))
    for r in rows:
        r.pop("wrapped_dek", None)
    return jsonify({"success": True, "files": rows, "key_id": crypto_vault.key_id(
        crypto_vault.load_master_key())})


@api.get("/vault/download/<int:fid>")
@require_auth()
def vault_download(user, fid):
    meta = db.query("SELECT * FROM vault_files WHERE id=?", (fid,), one=True)
    if not meta or (meta["owner_id"] != user["uid"] and user["role"] != "admin"):
        return jsonify({"success": False, "error": "not found"}), 404
    try:
        plain, _ = crypto_vault.read_file(fid)
    except Exception as e:
        security.alert("critical", "Integrity failure on vault file", f"{meta['filename']}: {e}")
        return jsonify({"success": False, "error": f"Integrity check failed: {e}"}), 409
    security.audit("vault.download", user["u"], meta["filename"], {})
    return send_file(io.BytesIO(plain), as_attachment=True, download_name=meta["filename"],
                     mimetype="application/octet-stream")


@api.post("/vault/tamper/<int:fid>")
@require_auth()
def vault_tamper(user, fid):
    meta = db.query("SELECT * FROM vault_files WHERE id=?", (fid,), one=True)
    if not meta or meta["owner_id"] != user["uid"]:
        return jsonify({"success": False, "error": "not found"}), 404
    res = crypto_vault.tamper_test(fid)
    security.audit("vault.tamper_test", user["u"], meta["filename"], res)
    return jsonify({"success": True, **res})


@api.post("/vault/share/<int:fid>")
@require_auth()
def vault_share(user, fid):
    d = _json_body()
    meta = db.query("SELECT * FROM vault_files WHERE id=?", (fid,), one=True)
    if not meta or meta["owner_id"] != user["uid"]:
        return jsonify({"success": False, "error": "not found"}), 404
    link = crypto_vault.create_share_link(fid, user["uid"],
                                          int(d.get("ttl_minutes", 60)),
                                          int(d.get("max_downloads", 1)))
    security.audit("vault.share", user["u"], meta["filename"],
                   {"ttl": d.get("ttl_minutes", 60), "max": d.get("max_downloads", 1)})
    return jsonify({"success": True, **link})


@api.delete("/vault/files/<int:fid>")
@require_auth()
def vault_delete(user, fid):
    meta = db.query("SELECT * FROM vault_files WHERE id=?", (fid,), one=True)
    if not meta or meta["owner_id"] != user["uid"]:
        return jsonify({"success": False, "error": "not found"}), 404
    db.execute("DELETE FROM vault_files WHERE id=?", (fid,))
    path = os.path.join(crypto_vault.VAULT_DIR, f"{fid}.enc")
    if os.path.exists(path):
        os.remove(path)
    security.audit("vault.delete", user["u"], meta["filename"], {})
    return jsonify({"success": True})


@api.post("/vault/rotate")
@require_auth("admin")
def vault_rotate(user):
    try:
        res = crypto_vault.rotate_master_key()
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    security.audit("vault.rotate", user["u"], res["new_key_id"], res)
    security.alert("warning", "Master key rotated", f"{res['files_rewrapped']} file DEKs re-wrapped")
    return jsonify({"success": True, **res})


@api.post("/vault/split")
@require_auth()
def vault_split(user):
    d = _json_body()
    secret = d.get("secret") or ""
    if not secret:
        return jsonify({"success": False, "error": "secret required"}), 400
    k = int(d.get("threshold", 3))
    n = int(d.get("shares", 5))
    res = crypto_vault.split_text(secret, k, n)
    security.audit("crypto.split", user["u"], f"{k}-of-{n}", {})
    return jsonify({"success": True, **res})


@api.post("/vault/combine")
@require_auth()
def vault_combine(user):
    d = _json_body()
    share_list = d.get("share_list") or []
    try:
        res = crypto_vault.combine_text(share_list)
        return jsonify({"success": True, **res})
    except Exception as e:
        security.audit("crypto.combine.failed", user["u"], "-", {"error": str(e)})
        return jsonify({"success": False, "error": str(e)}), 400


# --------------------------------------------------------------------------- #
# Model lab
# --------------------------------------------------------------------------- #
_retrain = {"running": False, "log": [], "result": None, "lock": threading.Lock()}


@api.get("/model/info")
@require_auth()
def model_info(user):
    return jsonify({"success": True, "model": model_service().info()})


@api.get("/model/versions")
@require_auth()
def model_versions(user):
    rows = db.query("SELECT id,version,engine,metrics,created_at,active,notes"
                    " FROM model_versions ORDER BY id DESC LIMIT 20")
    for r in rows:
        r["metrics"] = db.jload(r["metrics"], {})
    return jsonify({"success": True, "versions": rows})


@api.get("/model/drift")
@require_auth()
def model_drift(user):
    import pandas as pd
    from .drift import psi_report
    ref = pd.read_csv(os.path.join(ARTIFACTS, "sessions_train.csv"))
    cur = pd.read_csv(os.path.join(ARTIFACTS, "sessions_stream.csv"))
    return jsonify({"success": True, **psi_report(ref, cur)})


@api.post("/model/retrain")
@require_auth("admin", "analyst")
def model_retrain(user):
    with _retrain["lock"]:
        if _retrain["running"]:
            return jsonify({"success": False, "error": "retraining already running"}), 409
        _retrain["running"] = True
        _retrain["log"] = ["[queued] retraining requested by " + user["u"]]
        _retrain["result"] = None

    def job():
        try:
            _retrain["log"].append("[1/4] regenerating feature block from session corpus…")
            _retrain["log"].append("[2/4] training candidates (logreg / RF / HGB / MLP)…")
            res = train(register=True, notes=f"triggered by {user['u']}")
            _retrain["log"].append(
                f"[3/4] champion = {res['champion']} · holdout accuracy "
                f"{res['test']['accuracy']:.3f} · F1 {res['test']['f1']:.3f} · "
                f"AUC {res['test']['roc_auc']:.3f}")
            model_service().load()
            _retrain["log"].append("[4/4] champion artifact hot-swapped into the API")
            rows = db.query("SELECT id FROM model_versions ORDER BY id DESC LIMIT 1", one=True)
            db.execute("UPDATE model_versions SET active=0")
            db.execute("UPDATE model_versions SET active=1 WHERE id=?", (rows["id"],))
            _retrain["result"] = res
            security.audit("model.retrain", user["u"], res["version"],
                           {"champion": res["champion"], "acc": res["test"]["accuracy"]})
            security.alert("info", "Model retrained",
                           f"{res['version']} · {res['champion']} · acc {res['test']['accuracy']:.3f}")
        except Exception as e:
            _retrain["log"].append(f"[error] {e}")
        finally:
            with _retrain["lock"]:
                _retrain["running"] = False

    threading.Thread(target=job, daemon=True).start()
    return jsonify({"success": True})


@api.get("/model/retrain/status")
@require_auth()
def retrain_status(user):
    return jsonify({"success": True, "running": _retrain["running"],
                    "log": _retrain["log"], "result": _retrain["result"]})


@api.post("/model/activate/<int:vid>")
@require_auth("admin")
def model_activate(user, vid):
    row = db.query("SELECT * FROM model_versions WHERE id=?", (vid,), one=True)
    if not row:
        return jsonify({"success": False, "error": "version not found"}), 404
    if "[Deprecated:" in (row.get("notes") or ""):
        return jsonify({"success": False, "error": "version deprecated due to evaluation leakage"}), 400
    import joblib
    import shutil
    dest = os.path.join(ARTIFACTS, "champion.joblib")
    if os.path.abspath(row["path"]) != os.path.abspath(dest):
        shutil.copy(row["path"], dest)
    model_service().load()
    db.execute("UPDATE model_versions SET active=0")
    db.execute("UPDATE model_versions SET active=1 WHERE id=?", (vid,))
    security.audit("model.activate", user["u"], row["version"], {})
    return jsonify({"success": True, "version": row["version"]})


# --------------------------------------------------------------------------- #
# Audit / alerts
# --------------------------------------------------------------------------- #
@api.get("/audit/events")
@require_auth()
def audit_events(user):
    limit = min(int(request.args.get("limit", 80)), 500)
    rows = db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["meta"] = db.jload(r["meta"], {})
    return jsonify({"success": True, "events": rows})


@api.get("/audit/verify")
@require_auth()
def audit_verify(user):
    res = security.verify_audit_chain()
    security.audit("audit.verify", user["u"], "chain", res)
    return jsonify({"success": True, **res})


@api.get("/alerts")
@require_auth()
def alerts(user):
    rows = db.query("SELECT * FROM alerts ORDER BY id DESC LIMIT 40")
    return jsonify({"success": True, "alerts": rows,
                    "unacked": sum(1 for r in rows if not r["acked"])})


@api.post("/alerts/<int:aid>/ack")
@require_auth()
def alert_ack(user, aid):
    db.execute("UPDATE alerts SET acked=1 WHERE id=?", (aid,))
    return jsonify({"success": True})


# --------------------------------------------------------------------------- #
# Overview / dashboard
# --------------------------------------------------------------------------- #
@api.get("/overview")
@require_auth()
def overview(user):
    total = db.query("SELECT COUNT(*) c FROM decisions", one=True)["c"]
    blocked = db.query("SELECT COUNT(*) c FROM decisions WHERE decision='block'", one=True)["c"]
    stepup = db.query("SELECT COUNT(*) c FROM decisions WHERE decision='stepup'", one=True)["c"]
    review = db.query("SELECT COUNT(*) c FROM decisions WHERE decision='review'", one=True)["c"]
    avg = db.query("SELECT AVG(risk_score) a FROM decisions", one=True)["a"] or 0
    since = time.time() - 3600
    last_hour = db.query("SELECT COUNT(*) c FROM decisions WHERE ts>?", (since,), one=True)["c"]

    buckets = db.query(
        "SELECT CASE WHEN risk_score<20 THEN '0-20' WHEN risk_score<40 THEN '20-40'"
        " WHEN risk_score<60 THEN '40-60' WHEN risk_score<80 THEN '60-80' ELSE '80-100' END b,"
        " COUNT(*) c FROM decisions GROUP BY b")
    series = db.query(
        "SELECT CAST(ts/900 AS INTEGER)*900 t, COUNT(*) c, AVG(risk_score) r"
        " FROM decisions WHERE ts > ? GROUP BY t ORDER BY t", (time.time() - 3600 * 6,))
    top_users = db.query(
        "SELECT actor, COUNT(*) n, AVG(risk_score) r FROM decisions"
        " GROUP BY actor ORDER BY r DESC LIMIT 6")
    recent = db.query("SELECT id,ts,actor,risk_score,decision,ml_probability,source"
                      " FROM decisions ORDER BY id DESC LIMIT 12")
    labels = db.query("SELECT label, COUNT(*) c FROM decisions WHERE label IS NOT NULL GROUP BY label")
    info = model_service().info()
    return jsonify({
        "success": True,
        "kpis": {"sessions": total, "blocked": blocked, "stepup": stepup, "review": review,
                 "avg_risk": round(float(avg), 1), "last_hour": last_hour,
                 "block_rate": round(blocked / total * 100, 1) if total else 0},
        "buckets": buckets, "series": series, "top_users": top_users,
        "recent": recent, "labels": labels,
        "model": {"version": info["version"], "champion": info["champion"],
                  "metrics": info["test_metrics"],
                  "accuracy": (info["test_metrics"] or {}).get("accuracy")},
        "alerts": db.query("SELECT * FROM alerts WHERE acked=0 ORDER BY id DESC LIMIT 5"),
    })


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@api.get("/admin/users")
@require_auth("admin")
def admin_users(user):
    rows = db.query("SELECT id,username,email,role,status,totp_enabled,failed_attempts,"
                    "last_login,created_at FROM users ORDER BY id")
    return jsonify({"success": True, "users": rows})


@api.post("/admin/users/<int:uid>")
@require_auth("admin")
def admin_update_user(user, uid):
    d = _json_body()
    if d.get("role") in ("admin", "analyst", "user"):
        db.execute("UPDATE users SET role=? WHERE id=?", (d["role"], uid))
    if d.get("status") in ("active", "suspended"):
        db.execute("UPDATE users SET status=? WHERE id=?", (d["status"], uid))
    if d.get("unlock"):
        db.execute("UPDATE users SET failed_attempts=0, locked_until=0 WHERE id=?", (uid,))
    security.audit("admin.user.update", user["u"], str(uid), d)
    return jsonify({"success": True})


@api.get("/admin/sessions")
@require_auth("admin")
def admin_sessions(user):
    rows = db.query("SELECT s.id,s.ip,s.created_at,s.last_seen,s.revoked,u.username"
                    " FROM sessions s JOIN users u ON u.id=s.user_id ORDER BY s.last_seen DESC LIMIT 40")
    return jsonify({"success": True, "sessions": rows})


@api.get("/admin/approvals")
@require_auth("admin", "analyst")
def admin_approvals(user):
    rows = db.query("SELECT a.*, d.risk_score, d.decision, d.actor, d.reasons"
                    " FROM approvals a JOIN decisions d ON d.id=a.decision_id"
                    " ORDER BY a.id DESC LIMIT 40")
    for r in rows:
        r["reasons"] = db.jload(r["reasons"], [])
    return jsonify({"success": True, "approvals": rows})


@api.post("/admin/approvals/<int:aid>")
@require_auth("admin")
def admin_resolve_approval(user, aid):
    d = _json_body()
    status = d.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"success": False, "error": "status must be approved|rejected"}), 400
    db.execute("UPDATE approvals SET status=?, resolved_at=?, resolved_by=? WHERE id=?",
               (status, time.time(), user["u"], aid))
    security.audit("admin.approval", user["u"], str(aid), {"status": status})
    return jsonify({"success": True})


# --------------------------------------------------------------------------- #
# Share link consumption (no auth: token *is* the capability)
# --------------------------------------------------------------------------- #
@api.get("/health")
def health():
    return jsonify({"status": "ok", "time": time.time(),
                    "model": (model_service().bundle or {}).get("version")})
