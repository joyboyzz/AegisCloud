"""Synthetic risk scoring and a simulated policy decision point.

The score combines a synthetic success-probability estimate with explicit
behavioural rule points. The signals may use overlapping features. Displayed
point contributions sum to the bounded score. Per-user threshold shifts are
demo heuristics, not a validated fairness guarantee or cloud enforcement.
"""
from typing import Dict, List

from . import db
from .ml import service

ALLOW, STEPUP, REVIEW, BLOCK = "allow", "stepup", "review", "block"

# Demo thresholds were manually selected for the synthetic generator. They
# are heuristic, may shift per user, and do not enforce real cloud access.
POLICY = {
    "allow_below": 38.0,
    "stepup_below": 64.0,
    "review_below": 82.0,
}

AUTH_POINTS = {"password": 14.0, "certificate": 5.0, "mfa": 1.0,
               "biometric": -3.0, "hardware_key": -7.0}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def user_policy_offset(username: str) -> float:
    """Adaptive shift of the decision window based on the user's own history."""
    row = db.query(
        "SELECT AVG(risk_score) m, COUNT(*) c FROM decisions WHERE actor=?", (username,), one=True)
    if not row or not row["c"] or row["c"] < 5:
        return 0.0
    mean = float(row["m"] or 0)
    # Higher historical scores can shift cutoffs up by at most 4 points;
    # lower historical scores can shift them down by at most 8 points.
    return round(float(max(-8.0, min(4.0, (mean - 45.0) * 0.25))), 2)


def score_session(payload: dict, actor: str = None, persist: bool = False,
                  source: str = "manual") -> dict:
    mdl = service()
    p_success = mdl.predict_proba(payload)
    ml_points = (1.0 - p_success) * 100.0 * 0.42          # ML signal weight

    factors: List[Dict] = [
        {"factor": "Baseline exposure", "points": 6.0,
         "detail": "Every internet-facing session starts from a non-zero baseline",
         "kind": "base"},
        {
        "factor": "Model failure probability",
        "points": round(ml_points, 1),
        "detail": f"P(success) = {p_success:.3f} from the registered synthetic outcome model",
        "kind": "ml",
    }]

    auth = str(payload.get("auth_method", "password"))
    factors.append({
        "factor": "Authentication strength",
        "points": AUTH_POINTS.get(auth, 15.0),
        "detail": f"'{auth}' is "
                  + ("a weak single factor" if auth == "password" else "a strong factor"),
        "kind": "rule",
    })

    fa = int(payload.get("failed_attempts", 0) or 0)
    if fa:
        factors.append({"factor": "Recent failed attempts", "points": min(26.0, 6.5 * fa),
                        "detail": f"{fa} failed attempt(s) before this session", "kind": "rule"})

    if int(payload.get("is_new_device", 0) or 0):
        factors.append({"factor": "Unrecognised device", "points": 10.0,
                        "detail": "Supplied session is marked as a new device",
                        "kind": "rule"})

    if int(payload.get("geo_mismatch", 0) or 0):
        country = payload.get("country") or payload.get("ip_country") or "foreign"
        factors.append({"factor": "Geographic anomaly flag", "points": 14.0,
                        "detail": f"Geo mismatch flag set for reported country {country}",
                        "kind": "rule"})

    hour = int(payload.get("hour_of_day", 12) or 0)
    if hour < 7 or hour > 21:
        factors.append({"factor": "Off-hours access", "points": 5.0,
                        "detail": f"Session at {hour:02d}:00 is outside the configured hours",
                        "kind": "rule"})

    rate = float(payload.get("request_rate_per_min", 0) or 0)
    if rate > 15:
        excess = min(13.0, (rate - 15) * 0.55)
        factors.append({"factor": "Abnormal request velocity", "points": excess,
                        "detail": f"{rate:.1f} requests/min vs. baseline ~4", "kind": "rule"})

    sens = int(payload.get("resource_sensitivity", 3) or 3)
    if sens >= 4:
        factors.append({"factor": "High-value resource",
                        "points": (sens - 3) * 4.0,
                        "detail": f"{payload.get('resource_accessed', 'resource')} "
                                  f"has sensitivity {sens}/5", "kind": "rule"})

    anom = int(payload.get("anomaly_flag", 0) or 0)
    if anom:
        factors.append({"factor": "Anomaly detector flags", "points": min(18.0, 6.0 * anom),
                        "detail": f"Supplied anomaly flag count: {anom}",
                        "kind": "rule"})

    # Round before summing so the displayed point values reproduce the score.
    # An explicit adjustment explains the 0/100 cap instead of hiding excess.
    for f in factors:
        f["points"] = round(float(f["points"]), 1)
    raw = round(sum(f["points"] for f in factors), 1)
    offset = user_policy_offset(actor) if actor else 0.0
    risk = round(_clamp(raw), 1)
    adjustment = round(risk - raw, 1)
    if adjustment:
        factors.append({"factor": "Score bound adjustment", "points": adjustment,
                        "detail": "Keeps the final score in the 0–100 range",
                        "kind": "adjustment"})

    thresholds = {
        "allow": round(POLICY["allow_below"] + offset, 1),
        "stepup": round(POLICY["stepup_below"] + offset, 1),
        "review": round(POLICY["review_below"] + offset, 1),
    }
    if risk < thresholds["allow"]:
        decision = ALLOW
    elif risk < thresholds["stepup"]:
        decision = STEPUP
    elif risk < thresholds["review"]:
        decision = REVIEW
    else:
        decision = BLOCK

    explain = sorted([f for f in factors if f["points"] != 0],
                     key=lambda f: -abs(f["points"]))

    result = {
        "risk_score": round(risk, 1),
        "decision": decision,
        "ml_probability": round(p_success, 4),
        "ml_confidence": round(abs(p_success - 0.5) * 2, 3),
        "factors": explain,
        "thresholds": thresholds,
        "policy_offset": offset,
        "model_contributions": mdl.explain(payload),
        "narrative": _narrative(decision, explain, risk),
    }

    if persist:
        decision_id = db.execute(
            "INSERT INTO decisions(ts,source,actor,payload,ml_probability,risk_score,decision,reasons)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (db.now(), source, actor or payload.get("user_id", "-"),
             _json(payload), p_success, risk, decision, _json(explain)))
        result["decision_id"] = decision_id
        if decision in (REVIEW, BLOCK):
            db.execute("INSERT INTO approvals(decision_id,requested_by,status,created_at)"
                       " VALUES(?,?,?,?)", (decision_id, actor or "-", "pending", db.now()))
            from .security import alert
            alert("critical" if decision == BLOCK else "warning",
                  f"{decision.upper()} — risk {risk:.0f}/100",
                  f"{actor or payload.get('user_id','-')} · {payload.get('auth_method','?')} · "
                  f"{payload.get('resource_accessed','?')}")
    return result


def _json(obj):
    import json
    return json.dumps(obj, default=str)


def _narrative(decision, factors, risk) -> str:
    top = ", ".join(f["factor"].lower() for f in factors if f.get("kind") != "adjustment")
    top = ", ".join(top.split(", ")[:2]) or "no dominant factor"
    action = {ALLOW: "allow", STEPUP: "require step-up", REVIEW: "request review", BLOCK: "block"}[decision]
    return (f"Suggested action: {action} (risk {risk:.0f}). Main drivers: {top}. "
            "This prototype scores a simulated session; it does not enforce cloud access.")


PRESETS = {
    "credential_stuffing": {
        "label": "Credential stuffing burst",
        "payload": {"auth_method": "password", "failed_attempts": 5, "is_new_device": 1,
                    "geo_mismatch": 1, "hour_of_day": 3, "request_rate_per_min": 48,
                    "session_type": "api", "resource_accessed": "finance_db",
                    "resource_sensitivity": 5, "session_duration_sec": 90,
                    "cloud_provider": "aws", "anomaly_flag": 2},
    },
    "impossible_travel": {
        "label": "Geo mismatch (simulated)",
        "payload": {"auth_method": "mfa", "failed_attempts": 1, "is_new_device": 1,
                    "geo_mismatch": 1, "hour_of_day": 2, "request_rate_per_min": 9,
                    "session_type": "web", "resource_accessed": "k8s_prod",
                    "resource_sensitivity": 5, "session_duration_sec": 600,
                    "cloud_provider": "azure", "anomaly_flag": 1},
    },
    "insider_mass_download": {
        "label": "Insider mass download",
        "payload": {"auth_method": "mfa", "failed_attempts": 0, "is_new_device": 0,
                    "geo_mismatch": 0, "hour_of_day": 14, "request_rate_per_min": 22,
                    "session_type": "cli", "resource_accessed": "hr_records",
                    "resource_sensitivity": 4, "session_duration_sec": 5400,
                    "bytes_transferred_mb": 480, "cloud_provider": "gcp",
                    "anomaly_flag": 2},
    },
    "normal_user": {
        "label": "Normal user session",
        "payload": {"auth_method": "biometric", "failed_attempts": 0, "is_new_device": 0,
                    "geo_mismatch": 0, "hour_of_day": 11, "request_rate_per_min": 4,
                    "session_type": "web", "resource_accessed": "analytics",
                    "resource_sensitivity": 2, "session_duration_sec": 1500,
                    "cloud_provider": "aws", "anomaly_flag": 0},
    },
    "service_account_misuse": {
        "label": "Service-account misuse",
        "payload": {"auth_method": "certificate", "failed_attempts": 2, "is_new_device": 1,
                    "geo_mismatch": 0, "hour_of_day": 4, "request_rate_per_min": 60,
                    "session_type": "api", "resource_accessed": "object_store",
                    "resource_sensitivity": 2, "session_duration_sec": 120,
                    "bytes_transferred_mb": 220, "cloud_provider": "oci",
                    "anomaly_flag": 3},
    },
}


def login_risk(username: str, device_new: bool, ip: str, failed: int, hour: int) -> dict:
    """Risk of the *authentication event itself* (pre-session)."""
    factors = []
    if device_new:
        factors.append({"factor": "New device", "points": 16.0, "detail": "Device not trusted"})
    if failed:
        factors.append({"factor": "Failed logins", "points": min(35.0, 9.0 * failed),
                        "detail": f"{failed} failed attempt(s)"})
    if hour < 7 or hour > 21:
        factors.append({"factor": "Off-hours login", "points": 8.0,
                        "detail": f"Login at {hour:02d}:00"})
    risk = _clamp(sum(f["points"] for f in factors) + 8.0)
    decision = (ALLOW if risk < POLICY["allow_below"] else
                STEPUP if risk < POLICY["stepup_below"] else
                REVIEW if risk < POLICY["review_below"] else BLOCK)
    return {"risk_score": round(risk, 1), "decision": decision, "factors": factors}
