"""
SQLite persistence layer for AegisCloud.
Thin, dependency-free wrapper (sqlite3 + row factory) with schema bootstrap.
"""
import os
import sqlite3
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.abspath(os.environ.get("AEGIS_INSTANCE_DIR", os.path.join(BASE_DIR, "instance")))
DB_PATH = os.environ.get("AEGIS_DB", os.path.join(INSTANCE_DIR, "aegis.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    pw_salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst',          -- admin | analyst | user
    status TEXT NOT NULL DEFAULT 'active',         -- active | suspended
    totp_secret TEXT,
    totp_enabled INTEGER NOT NULL DEFAULT 0,
    mfa_required INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    last_login REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL,
    used_at REAL
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    label TEXT,
    trusted INTEGER NOT NULL DEFAULT 0,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    UNIQUE(user_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    device_fp TEXT,
    ip TEXT,
    mfa_verified INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,
    target TEXT,
    meta TEXT,
    prev_hash TEXT,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    source TEXT NOT NULL,                 -- manual | stream | auth
    actor TEXT,
    payload TEXT NOT NULL,                -- raw session features
    ml_probability REAL,
    risk_score REAL NOT NULL,
    decision TEXT NOT NULL,               -- allow | stepup | review | block
    reasons TEXT,
    label TEXT,                           -- NULL | success | failure | tp | fp | tn | fn
    actual_outcome TEXT
);

CREATE TABLE IF NOT EXISTS vault_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    nonce TEXT NOT NULL,
    wrapped_dek TEXT NOT NULL,
    key_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    tags TEXT
);

CREATE TABLE IF NOT EXISTS share_links (
    id TEXT PRIMARY KEY,
    file_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    max_downloads INTEGER NOT NULL DEFAULT 1,
    downloads INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    engine TEXT NOT NULL,
    metrics TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    requested_by TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    created_at REAL NOT NULL,
    resolved_at REAL,
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    severity TEXT NOT NULL,      -- info | warning | critical
    title TEXT NOT NULL,
    detail TEXT,
    acked INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def query(sql, args=(), one=False):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def executemany(sql, seq):
    conn = connect()
    try:
        conn.executemany(sql, seq)
        conn.commit()
    finally:
        conn.close()


def jload(raw, default=None):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def now():
    return time.time()
