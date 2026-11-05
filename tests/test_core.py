"""
Test suite for AegisCloud.

    pytest -q

Covers the parts that are easy to get silently wrong: authenticated encryption
and tamper detection, Shamir secret sharing over GF(2^8), password policy,
RFC 6238 TOTP, the tamper-evident audit chain, token verification and the risk
policy decision boundaries.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import crypto_vault as cv          # noqa: E402
from app import db, risk, security          # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fresh_db(tmp_path_factory):
    """Keep tests from touching the running app's DB, master key or vault blobs."""
    root = tmp_path_factory.mktemp("aegis-test")
    old_db, old_key, old_vault = db.DB_PATH, cv.MASTER_KEY_FILE, cv.VAULT_DIR
    db.DB_PATH = str(root / "test.db")
    cv.MASTER_KEY_FILE = str(root / "master.key")
    cv.VAULT_DIR = str(root / "vault")
    os.makedirs(cv.VAULT_DIR, exist_ok=True)
    old_env = os.environ.pop("AEGIS_MASTER_KEY", None)
    try:
        db.init_db()
        yield
    finally:
        db.DB_PATH, cv.MASTER_KEY_FILE, cv.VAULT_DIR = old_db, old_key, old_vault
        if old_env is not None:
            os.environ["AEGIS_MASTER_KEY"] = old_env


# --------------------------------------------------------------------------- #
# GF(2^8) arithmetic + Shamir
# --------------------------------------------------------------------------- #
def test_gf_tables_match_aes_reference():
    assert cv.gf_mul(0x53, 0xCA) == 0x01          # classic AES inverse pair
    assert cv.gf_mul(2, 3) == 6
    assert cv.gf_mul(3, 3) == 5
    assert cv.gf_div(6, 3) == 2
    assert cv.gf_mul(0, 99) == 0
    with pytest.raises(ZeroDivisionError):
        cv.gf_div(5, 0)


def test_shamir_roundtrip_threshold():
    secret = b"the master key is 32 bytes long!!"
    shares = cv.split_secret(secret, threshold=3, shares=5)
    assert len(shares) == 5
    assert cv.combine_shares(shares[:3]) == secret
    assert cv.combine_shares([shares[0], shares[2], shares[4]]) == secret
    assert cv.combine_shares(shares) == secret          # more than k also works


def test_shamir_below_threshold_reveals_garbage():
    secret = b"top-secret-value"
    shares = cv.split_secret(secret, threshold=4, shares=6)
    partial = cv.combine_shares(shares[:3])
    assert partial != secret


def test_shamir_text_helpers():
    r = cv.split_text("AegisCloud", 2, 3)
    assert cv.combine_text(r["share_list"][:2])["text"] == "AegisCloud"


# --------------------------------------------------------------------------- #
# Vault: authenticated encryption
# --------------------------------------------------------------------------- #
def test_vault_roundtrip_and_hash():
    db.init_db()
    uid = db.execute("INSERT INTO users(username,email,pw_hash,pw_salt,role,status,created_at)"
                     " VALUES(?,?,?,?,?,?,?)",
                     ("t_user", "t@local", "x", "y", "user", "active", time.time()))
    meta = cv.store_file(uid, "note.txt", b"hello aegis", "test")
    plain, row = cv.read_file(meta["id"])
    assert plain == b"hello aegis"
    assert row["sha256"] == meta["sha256"]
    assert row["wrapped_dek"] != ""                     # DEK is wrapped, never stored raw


def test_tamper_is_detected():
    db.init_db()
    uid = db.query("SELECT id FROM users WHERE username='t_user'", one=True)["id"]
    meta = cv.store_file(uid, "note2.txt", b"integrity matters", "")
    res = cv.tamper_test(meta["id"])
    assert res["detected"] is True
    # file must still be readable afterwards (test restores the original bytes)
    plain, _ = cv.read_file(meta["id"])
    assert plain == b"integrity matters"


def test_share_link_is_one_time():
    db.init_db()
    uid = db.query("SELECT id FROM users WHERE username='t_user'", one=True)["id"]
    meta = cv.store_file(uid, "share.txt", b"shared bytes", "")
    link = cv.create_share_link(meta["id"], uid, ttl_minutes=5, max_downloads=1)
    plain, _ = cv.consume_share_link(link["id"], link["token"])
    assert plain == b"shared bytes"
    with pytest.raises(PermissionError):
        cv.consume_share_link(link["id"], link["token"])      # limit reached
    link2 = cv.create_share_link(meta["id"], uid, ttl_minutes=5, max_downloads=1)
    with pytest.raises(PermissionError):
        cv.consume_share_link(link2["id"], "wrong-token")      # token check


# --------------------------------------------------------------------------- #
# Identity primitives
# --------------------------------------------------------------------------- #
def test_password_policy():
    weak = security.password_report("password")
    strong = security.password_report("Tr0ub4dor&3-shadow")
    assert not weak["ok"] and not weak["checks"]["not_common"]
    assert strong["ok"]
    assert strong["entropy_bits"] > weak["entropy_bits"]


def test_password_hash_is_salted():
    h1, s1 = security.hash_password("SamePassword1!")
    h2, s2 = security.hash_password("SamePassword1!")
    assert h1 != h2 and s1 != s2
    assert security.verify_password("SamePassword1!", h1, s1)
    assert not security.verify_password("WrongPassword1!", h1, s1)


def test_totp_rfc6238_vectors():
    # RFC 6238 test vectors use the ASCII secret "12345678901234567890"
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert security.totp_now(secret, at=59) == "287082"
    assert security.totp_now(secret, at=1111111109) == "081804"
    assert security.verify_totp(secret, security.totp_now(secret))


def test_token_lifecycle_and_revocation():
    db.init_db()
    uid = db.execute("INSERT OR IGNORE INTO users(id,username,email,pw_hash,pw_salt,role,status,"
                     "created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (999, "tok_user", "tok@local", "x", "y", "user", "active", time.time()))
    tok = security.issue_token(999, "tok_user", True)
    payload = security.verify_token(tok["token"])
    assert payload and payload["u"] == "tok_user"
    security.revoke_session(tok["sid"])
    assert security.verify_token(tok["token"]) is None


def test_token_signature_cannot_be_forged():
    db.init_db()
    tok = security.issue_token(999, "tok_user", True)
    raw, sig = tok["token"].rsplit(".", 1)
    forged = raw[:-2] + ("AA" if not raw.endswith("AA") else "BB") + "." + sig
    assert security.verify_token(forged) is None


def test_audit_chain_detects_tampering():
    db.init_db()
    security.audit("test.event", "tester", "target", {"a": 1})
    security.audit("test.event2", "tester", "target", {"a": 2})
    assert security.verify_audit_chain()["ok"] is True
    row = db.query("SELECT id FROM audit ORDER BY id DESC LIMIT 1", one=True)
    db.execute("UPDATE audit SET action='tampered' WHERE id=?", (row["id"],))
    res = security.verify_audit_chain()
    assert res["ok"] is False and res["broken_at"] == row["id"]
    db.execute("UPDATE audit SET action='test.event2' WHERE id=?", (row["id"],))
    assert security.verify_audit_chain()["ok"] is True


# --------------------------------------------------------------------------- #
# Risk policy
# --------------------------------------------------------------------------- #
def test_risk_monotonic_in_attack_signals():
    benign = {"auth_method": "biometric", "failed_attempts": 0, "is_new_device": 0,
              "geo_mismatch": 0, "hour_of_day": 11, "request_rate_per_min": 4,
              "resource_sensitivity": 2, "session_duration_sec": 1500,
              "anomaly_flag": 0, "session_type": "web", "cloud_provider": "aws",
              "resource_accessed": "analytics"}
    hostile = dict(benign, auth_method="password", failed_attempts=5, is_new_device=1,
                   geo_mismatch=1, hour_of_day=3, request_rate_per_min=60,
                   resource_sensitivity=5, anomaly_flag=3)
    r_benign = risk.score_session(benign)
    r_hostile = risk.score_session(hostile)
    assert r_benign["risk_score"] < r_hostile["risk_score"]
    assert r_benign["decision"] == "allow"
    assert r_hostile["decision"] == "block"


def test_contributions_sum_to_score():
    payload = {"auth_method": "mfa", "failed_attempts": 2, "is_new_device": 1,
               "geo_mismatch": 0, "hour_of_day": 2, "request_rate_per_min": 20,
               "resource_sensitivity": 4, "session_duration_sec": 900,
               "anomaly_flag": 1, "session_type": "api", "cloud_provider": "gcp",
               "resource_accessed": "k8s_prod"}
    r = risk.score_session(payload)
    total = sum(f["points"] for f in r["factors"])
    assert abs(total - r["risk_score"]) < 0.11        # additive by construction


def test_policy_thresholds_are_ordered():
    assert risk.POLICY["allow_below"] < risk.POLICY["stepup_below"] < risk.POLICY["review_below"]


def test_clamped_risk_contributions_still_sum():
    r = risk.score_session(risk.PRESETS["credential_stuffing"]["payload"])
    assert r["risk_score"] == 100.0
    assert abs(sum(f["points"] for f in r["factors"]) - r["risk_score"]) < 0.01
    assert any(f["kind"] == "adjustment" for f in r["factors"])


def test_user_baseline_is_fitted_on_training_only():
    import pandas as pd
    from app.ml import engineer
    def row(uid, duration):
        return {"user_id": uid, "session_duration_sec": duration,
                "cloud_provider": "aws", "auth_method": "mfa",
                "session_type": "web", "resource_accessed": "object_store"}
    train = pd.DataFrame([row("alice", 100), row("alice", 300), row("bob", 700)])
    _, baseline = engineer(train)
    validation = pd.DataFrame([row("alice", 10000), row("unseen", 10000)])
    X, same_baseline = engineer(validation, baseline)
    assert same_baseline["alice"]["mean"] == 200
    assert same_baseline["__global__"]["mean"] == 1100 / 3
    assert X["duration_z"].notna().all()
    assert X["duration_absdev"].notna().all()


def test_concurrent_audit_writes_keep_a_single_chain():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: security.audit("concurrent", "tester", str(i)), range(24)))
    assert len(set(results)) == 24
    assert security.verify_audit_chain()["ok"] is True


def test_share_link_only_one_concurrent_download():
    from concurrent.futures import ThreadPoolExecutor
    uid = db.query("SELECT id FROM users WHERE username='t_user'", one=True)["id"]
    meta = cv.store_file(uid, "race.txt", b"once", "")
    link = cv.create_share_link(meta["id"], uid, max_downloads=1)
    def consume(_):
        try:
            return cv.consume_share_link(link["id"], link["token"])[0]
        except PermissionError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, range(2)))
    assert sorted(x is not None for x in results) == [False, True]


def test_recovery_code_is_single_use():
    uid = db.query("SELECT id FROM users WHERE username='t_user'", one=True)["id"]
    code = security.generate_recovery_codes(uid, count=1)[0]
    assert security.use_recovery_code(uid, code)
    assert not security.use_recovery_code(uid, code)


def test_users_cannot_revoke_other_users_sessions():
    from app import create_app
    for i in (201, 202):
        db.execute("INSERT OR IGNORE INTO users(id,username,email,pw_hash,pw_salt,role,status,created_at) "
                   "VALUES(?,?,?,?,?,?,?,?)", (i, f"iso{i}", f"iso{i}@local", "x", "y", "user", "active", time.time()))
    a = security.issue_token(201, "iso201", True)
    b = security.issue_token(202, "iso202", True)
    client = create_app().test_client()
    res = client.delete('/api/auth/sessions/' + b["sid"], headers={'Authorization': 'Bearer ' + a["token"]})
    assert res.status_code == 404
    assert security.verify_token(b["token"]) is not None
    res = client.delete('/api/auth/sessions/' + b["sid"], headers={'Authorization': 'Bearer ' + b["token"]})
    assert res.status_code == 200
    assert security.verify_token(b["token"]) is None


def test_psi_counts_out_of_range_traffic_and_constant_shift():
    import numpy as np
    import pandas as pd
    from app.drift import _psi_numeric
    reference = pd.Series(np.linspace(0, 1, 1000))
    extreme = pd.Series(np.full(1000, 10.0))
    assert _psi_numeric(reference, extreme) > 1.0
    assert _psi_numeric(pd.Series([5.0] * 100), pd.Series([8.0] * 100)) > 1.0
    assert _psi_numeric(reference, reference) == pytest.approx(0.0)
