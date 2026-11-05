"""Authenticated envelope encryption and independent secret-sharing demo.

A random per-file key encrypts bytes with AES-256-GCM. That key is wrapped
with a local master key using a separate AES-GCM operation. Owner and filename
are authenticated as associated data. The standalone Shamir GF(2^8) example
splits a user-provided secret; it is NOT integrated with vault-key recovery.
Local key storage and rotation are for demonstration, not a managed KMS.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import List, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = db.INSTANCE_DIR
VAULT_DIR = os.path.join(INSTANCE_DIR, "vault")
MASTER_KEY_FILE = os.path.join(INSTANCE_DIR, "master.key")
os.makedirs(VAULT_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# Master key handling
# --------------------------------------------------------------------------- #
def load_master_key() -> bytes:
    env = os.environ.get("AEGIS_MASTER_KEY")
    if env:
        return bytes.fromhex(env)
    if os.path.exists(MASTER_KEY_FILE):
        with open(MASTER_KEY_FILE, "r") as f:
            return bytes.fromhex(f.read().strip())
    key = secrets.token_bytes(32)
    with open(MASTER_KEY_FILE, "w") as f:
        f.write(key.hex())
    os.chmod(MASTER_KEY_FILE, 0o600)
    return key


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Envelope encryption
# --------------------------------------------------------------------------- #
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s)


def wrap_dek(dek: bytes, master: bytes) -> str:
    kid = key_id(master).encode()
    nonce = secrets.token_bytes(12)
    return _b64(nonce + AESGCM(master).encrypt(nonce, dek, kid))


def unwrap_dek(wrapped: str, master: bytes) -> bytes:
    raw = _unb64(wrapped)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(master).decrypt(nonce, ct, key_id(master).encode())


def store_file(owner_id: int, filename: str, data: bytes, tags: str = "") -> dict:
    master = load_master_key()
    dek = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = f"{owner_id}:{filename}".encode()
    ct = AESGCM(dek).encrypt(nonce, data, aad)

    digest = hashlib.sha256(data).hexdigest()
    file_id = db.execute(
        "INSERT INTO vault_files(owner_id,filename,size_bytes,sha256,nonce,wrapped_dek,key_id,created_at,tags)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (owner_id, filename, len(data), digest, _b64(nonce), wrap_dek(dek, master),
         key_id(master), time.time(), tags))
    with open(os.path.join(VAULT_DIR, f"{file_id}.enc"), "wb") as f:
        f.write(ct)
    return {"id": file_id, "filename": filename, "size_bytes": len(data), "sha256": digest}


def read_file(file_id: int) -> Tuple[bytes, dict]:
    row = db.query("SELECT * FROM vault_files WHERE id=?", (file_id,), one=True)
    if not row:
        raise ValueError("File not found")
    master = load_master_key()
    dek = unwrap_dek(row["wrapped_dek"], master)
    path = os.path.join(VAULT_DIR, f"{file_id}.enc")
    with open(path, "rb") as f:
        ct = f.read()
    aad = f"{row['owner_id']}:{row['filename']}".encode()
    plain = AESGCM(dek).decrypt(_unb64(row["nonce"]), ct, aad)   # raises InvalidTag on tamper
    if hashlib.sha256(plain).hexdigest() != row["sha256"]:
        raise InvalidTag("Integrity check failed (SHA-256 mismatch)")
    return plain, row


def tamper_test(file_id: int) -> dict:
    """Flip one byte of the ciphertext and prove GCM rejects it."""
    path = os.path.join(VAULT_DIR, f"{file_id}.enc")
    with open(path, "rb") as f:
        ct = bytearray(f.read())
    if not ct:
        raise ValueError("Empty ciphertext")
    original = bytes(ct)
    ct[len(ct) // 2] ^= 0x01
    with open(path, "wb") as f:
        f.write(ct)
    try:
        read_file(file_id)
        detected = False
        detail = "Tampering NOT detected"
    except InvalidTag:
        detected = True
        detail = "AES-GCM authentication tag rejected the modified ciphertext"
    except Exception as e:                                    # pragma: no cover
        detected = True
        detail = f"Rejected: {type(e).__name__}"
    finally:
        with open(path, "wb") as f:
            f.write(original)                                 # restore
    return {"detected": detected, "detail": detail}


def rotate_master_key() -> dict:
    if os.environ.get("AEGIS_MASTER_KEY"):
        raise ValueError("Key rotation through the UI is unavailable when AEGIS_MASTER_KEY is set")
    old = load_master_key()
    new = secrets.token_bytes(32)
    rows = db.query("SELECT id, wrapped_dek FROM vault_files")
    conn = db.connect()
    try:
        for r in rows:
            dek = unwrap_dek(r["wrapped_dek"], old)
            conn.execute("UPDATE vault_files SET wrapped_dek=?, key_id=? WHERE id=?",
                         (wrap_dek(dek, new), key_id(new), r["id"]))
        conn.commit()
    finally:
        conn.close()
    with open(MASTER_KEY_FILE, "w") as f:
        f.write(new.hex())
    os.chmod(MASTER_KEY_FILE, 0o600)
    return {"files_rewrapped": len(rows), "new_key_id": key_id(new), "old_key_id": key_id(old)}


# --------------------------------------------------------------------------- #
# Shamir's Secret Sharing over GF(2^8)
# --------------------------------------------------------------------------- #
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables():
    """Build log/antilog tables.  0x02 is *not* primitive in GF(2^8) with the
    AES polynomial (it has order 51), so we step with the generator 0x03:
    x <- x*3 = x ^ xtime(x)."""
    def xtime(a):
        a <<= 1
        if a & 0x100:
            a ^= 0x11B                      # AES irreducible polynomial
        return a & 0xFF

    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x = (x ^ xtime(x)) & 0xFF           # multiply by the generator 3
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def split_secret(secret: bytes, threshold: int, shares: int) -> List[dict]:
    if not (2 <= threshold <= shares <= 255):
        raise ValueError("Require 2 <= threshold <= shares <= 255")
    polys = []
    for _ in secret:
        polys.append([secrets.randbelow(256)] + [secrets.randbelow(256) for _ in range(threshold - 1)])
    # coefficient[0] = secret byte
    for i, byte in enumerate(secret):
        polys[i][0] = byte

    out = []
    for x in range(1, shares + 1):
        y = bytearray()
        for poly in polys:
            acc = 0
            for coeff in reversed(poly):
                acc = gf_mul(acc, x) ^ coeff
            y.append(acc)
        out.append({"x": x, "y": _b64(bytes(y))})
    return out


def combine_shares(share_list: List[dict]) -> bytes:
    if len(share_list) < 2:
        raise ValueError("At least two shares are required")
    xs = [s["x"] for s in share_list]
    if len(set(xs)) != len(xs):
        raise ValueError("Duplicate share indices")
    ys = [_unb64(s["y"]) for s in share_list]
    length = len(ys[0])
    secret = bytearray()
    for byte_i in range(length):
        acc = 0
        for i, xi in enumerate(xs):
            num, den = 1, 1
            for j, xj in enumerate(xs):
                if i == j:
                    continue
                num = gf_mul(num, xj)
                den = gf_mul(den, xi ^ xj)
            term = gf_mul(ys[i][byte_i], gf_div(num, den))
            acc ^= term
        secret.append(acc)
    return bytes(secret)


def split_text(text: str, threshold: int, shares: int) -> dict:
    raw = text.encode()
    parts = split_secret(raw, threshold, shares)
    return {
        "threshold": threshold,
        "shares": shares,
        "share_list": parts,
        "length": len(raw),
        "hint": f"Any {threshold} of the {shares} shares reconstruct the secret; fewer cannot.",
    }


def combine_text(share_list: List[dict], as_text: bool = True):
    raw = combine_shares(share_list)
    if not as_text:
        return {"hex": raw.hex(), "length": len(raw)}
    return {"text": raw.decode("utf-8", errors="replace"), "length": len(raw)}


# --------------------------------------------------------------------------- #
# Time-limited, one-time share links
# --------------------------------------------------------------------------- #
def create_share_link(file_id: int, user_id: int, ttl_minutes: int = 60,
                      max_downloads: int = 1) -> dict:
    token = secrets.token_urlsafe(24)
    link_id = secrets.token_hex(8)
    expires = time.time() + max(1, ttl_minutes) * 60
    db.execute(
        "INSERT INTO share_links(id,file_id,token_hash,created_by,created_at,expires_at,max_downloads)"
        " VALUES(?,?,?,?,?,?,?)",
        (link_id, file_id, hashlib.sha256(token.encode()).hexdigest(), user_id,
         time.time(), expires, max(1, max_downloads)))
    return {"id": link_id, "token": token, "expires_at": expires,
            "max_downloads": max_downloads,
            "url": f"/s/{link_id}/{token}"}


def consume_share_link(link_id: str, token: str) -> Tuple[bytes, dict]:
    # Hold a write transaction until the link is validated, the file is read,
    # and the download counter is advanced. This makes max-downloads atomic.
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM share_links WHERE id=?", (link_id,)).fetchone()
        if not row:
            raise PermissionError("Link not found")
        if row["revoked"]:
            raise PermissionError("Link revoked")
        candidate = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(candidate, row["token_hash"]):
            raise PermissionError("Invalid token")
        if row["expires_at"] < time.time():
            raise PermissionError("Link expired")
        if row["downloads"] >= row["max_downloads"]:
            raise PermissionError("Download limit reached")
        plain, meta = read_file(row["file_id"])
        conn.execute("UPDATE share_links SET downloads=downloads+1 WHERE id=?", (link_id,))
        conn.commit()
        return plain, meta
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
