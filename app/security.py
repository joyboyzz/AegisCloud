"""Identity, credential and audit-integrity primitives.

Password hashing, signed revocable sessions, TOTP, recovery codes and the
local hash-linked audit log use the Python standard library. The separate
vault requires the cryptography package. This is demonstration code, not a
production identity service or an externally anchored audit system.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import struct
import time
from typing import Optional, Tuple

from . import db

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SECRET_KEY = os.environ.get("AEGIS_SECRET", "aegis-dev-secret-change-me-in-prod")
SESSION_TTL = int(os.environ.get("AEGIS_SESSION_TTL", 60 * 60 * 8))       # 8 h
TOKEN_MAX_AGE = SESSION_TTL
LOCKOUT_BASE = 30                                    # seconds * 2^(attempts-1)
MAX_FAILED = 5

_COMMON_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "admin", "letmein", "welcome",
    "password1", "abc123", "iloveyou", "monkey", "dragon", "vijay", "india",
    "123456789", "qwerty123", "administrator", "root", "passw0rd", "test1234",
}


# --------------------------------------------------------------------------- #
# Password hashing & policy
# --------------------------------------------------------------------------- #
def _scrypt(password: str, salt: bytes, n: int = 2 ** 14) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=8, p=1, dklen=32)


def hash_password(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    return _scrypt(password, salt).hex(), salt.hex()


def verify_password(password: str, pw_hash: str, salt_hex: str) -> bool:
    try:
        return hmac.compare_digest(_scrypt(password, bytes.fromhex(salt_hex)).hex(), pw_hash)
    except Exception:
        return False


def password_report(password: str) -> dict:
    """Strength assessment + policy checks returned to the UI."""
    checks = {
        "length": len(password) >= 10,
        "upper": bool(re.search(r"[A-Z]", password)),
        "lower": bool(re.search(r"[a-z]", password)),
        "digit": bool(re.search(r"\d", password)),
        "symbol": bool(re.search(r"[^A-Za-z0-9]", password)),
        "not_common": password.lower() not in _COMMON_PASSWORDS,
        "no_sequence": not re.search(r"(0123|1234|2345|abcd|qwer|pass|admin)", password.lower()),
    }
    score = sum(checks.values())
    entropy = len(set(password)) * 0.0  # placeholder for readability
    if password:
        pool = 0
        pool += 26 if checks["upper"] else 0
        pool += 26 if checks["lower"] else 0
        pool += 10 if checks["digit"] else 0
        pool += 33 if checks["symbol"] else 0
        import math
        entropy = len(password) * math.log2(pool) if pool else 0
    strength = "very weak" if score <= 2 else "weak" if score <= 4 else "medium" if score <= 5 else "strong"
    return {
        "checks": checks,
        "score": score,
        "max_score": len(checks),
        "strength": strength,
        "entropy_bits": round(entropy, 1),
        "ok": all([checks["length"], checks["not_common"], checks["no_sequence"]])
        and score >= 5,
    }


# --------------------------------------------------------------------------- #
# TOTP (RFC 6238) - no external dependency
# --------------------------------------------------------------------------- #
_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def generate_totp_secret(length: int = 20) -> str:
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32decode(secret: str) -> bytes:
    pad = "=" * ((8 - len(secret) % 8) % 8)
    return base64.b32decode(secret.upper() + pad)


def totp_now(secret: str, step: int = 30, digits: int = 6, at: Optional[float] = None) -> str:
    counter = int((at if at is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(_b32decode(secret), msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    now = time.time()
    for drift in range(-window, window + 1):
        if hmac.compare_digest(totp_now(secret, at=now + drift * 30), code):
            return True
    return False


def totp_uri(secret: str, account: str, issuer: str = "AegisCloud") -> str:
    return (
        f"otpauth://totp/{issuer}:{account}?secret={secret}"
        f"&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )


def qr_svg(data: str, scale: int = 4) -> str:
    """Render a QR code as inline SVG (uses `segno`; falls back to text)."""
    try:
        import segno
        buf = io.StringIO()
        segno.make(data, error="m").save(buf, kind="svg", scale=scale, border=2,
                                         dark="#0b1220", light="#ffffff")
        return buf.getvalue()
    except Exception:
        return ("<div class='qr-fallback'>TOTP secret:<br><code>%s</code></div>" % data)


# --------------------------------------------------------------------------- #
# Recovery codes
# --------------------------------------------------------------------------- #
def generate_recovery_codes(user_id: int, count: int = 10) -> list:
    codes = ["-".join(secrets.token_hex(2).upper() for _ in range(2)) for _ in range(count)]
    rows = []
    for c in codes:
        h, _ = hash_password(c, salt_hex=secrets.token_hex(16))
        rows.append((user_id, h, None))
        # store with per-code salt embedded
    conn = db.connect()
    try:
        conn.execute("DELETE FROM recovery_codes WHERE user_id=?", (user_id,))
        for c in codes:
            salt = secrets.token_hex(16)
            h, _ = hash_password(c, salt_hex=salt)
            conn.execute("INSERT INTO recovery_codes(user_id, code_hash) VALUES(?,?)",
                         (user_id, f"{salt}:{h}"))
        conn.commit()
    finally:
        conn.close()
    return codes


def use_recovery_code(user_id: int, code: str) -> bool:
    code = code.strip().upper()
    rows = db.query("SELECT id, code_hash FROM recovery_codes WHERE user_id=? AND used_at IS NULL",
                    (user_id,))
    for r in rows:
        salt, h = r["code_hash"].split(":", 1)
        if verify_password(code, h, salt):
            conn = db.connect()
            try:
                # A conditional update prevents two simultaneous requests from
                # spending the same recovery code twice.
                cur = conn.execute("UPDATE recovery_codes SET used_at=? WHERE id=? AND used_at IS NULL",
                                   (db.now(), r["id"]))
                conn.commit()
                return cur.rowcount == 1
            finally:
                conn.close()
    return False


# --------------------------------------------------------------------------- #
# Signed session tokens
# --------------------------------------------------------------------------- #
def _sign(raw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]


def issue_token(user_id: int, username: str, mfa_verified: bool,
                device_fp: str = "", ip: str = "") -> dict:
    sid = secrets.token_hex(16)
    exp = int(time.time()) + TOKEN_MAX_AGE
    payload = {"uid": user_id, "u": username, "sid": sid, "exp": exp, "mfa": bool(mfa_verified)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    token = f"{raw}.{_sign(raw)}"
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO sessions(id,user_id,token_hash,device_fp,ip,mfa_verified,created_at,last_seen,expires_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, user_id, hashlib.sha256(token.encode()).hexdigest(), device_fp, ip,
             int(mfa_verified), time.time(), time.time(), exp))
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "sid": sid, "expires_at": exp, "mfa_verified": mfa_verified}


def verify_token(token: str) -> Optional[dict]:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(raw)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    row = db.query("SELECT * FROM sessions WHERE id=?", (payload["sid"],), one=True)
    if not row or row["revoked"] or row["expires_at"] < time.time():
        return None
    return payload


def touch_session(sid: str):
    db.execute("UPDATE sessions SET last_seen=? WHERE id=?", (time.time(), sid))


def revoke_session(sid: str):
    db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (sid,))


# --------------------------------------------------------------------------- #
# Brute-force protection
# --------------------------------------------------------------------------- #
def register_failure(user_id: int) -> int:
    db.execute("UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id=?", (user_id,))
    row = db.query("SELECT failed_attempts FROM users WHERE id=?", (user_id,), one=True)
    fails = row["failed_attempts"] if row else 0
    if fails >= MAX_FAILED:
        lock = time.time() + LOCKOUT_BASE * (2 ** min(fails - MAX_FAILED, 6))
        db.execute("UPDATE users SET locked_until=? WHERE id=?", (lock, user_id))
    return fails


def reset_failures(user_id: int):
    db.execute("UPDATE users SET failed_attempts=0, locked_until=0 WHERE id=?", (user_id,))


# --------------------------------------------------------------------------- #
# Tamper-evident audit log
# --------------------------------------------------------------------------- #
def _last_hash() -> str:
    row = db.query("SELECT hash FROM audit ORDER BY id DESC LIMIT 1", one=True)
    return row["hash"] if row else "GENESIS"


def audit(action: str, actor: str = "-", target: str = "-", meta: Optional[dict] = None) -> str:
    # Serialize reading the chain head and appending the next entry. Separate
    # connections race and can otherwise create two entries with the same head.
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "GENESIS"
        ts = time.time()
        body = f"{prev}|{ts}|{actor}|{action}|{target}|{json.dumps(meta or {}, sort_keys=True)}"
        h = hashlib.sha256(body.encode()).hexdigest()
        conn.execute("INSERT INTO audit(ts,actor,action,target,meta,prev_hash,hash) VALUES(?,?,?,?,?,?,?)",
                     (ts, actor, action, target, json.dumps(meta or {}), prev, h))
        conn.commit()
        return h
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_audit_chain() -> dict:
    rows = db.query("SELECT * FROM audit ORDER BY id ASC")
    prev = "GENESIS"
    for r in rows:
        body = (f"{prev}|{r['ts']}|{r['actor']}|{r['action']}|{r['target']}|"
                f"{json.dumps(json.loads(r['meta'] or '{}'), sort_keys=True)}")
        expect = hashlib.sha256(body.encode()).hexdigest()
        if expect != r["hash"] or r["prev_hash"] != prev:
            return {"ok": False, "broken_at": r["id"], "checked": len(rows)}
        prev = r["hash"]
    return {"ok": True, "checked": len(rows), "head": prev}


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
def alert(severity: str, title: str, detail: str = ""):
    db.execute("INSERT INTO alerts(ts,severity,title,detail) VALUES(?,?,?,?)",
               (time.time(), severity, title, detail))
