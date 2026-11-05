#!/usr/bin/env python3
"""Generate the AegisCloud review deck (python-pptx, 16:9, dark SOC theme).

    python scripts/make_deck.py   ->  docs/AegisCloud_Presentation.pptx
"""
import json
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(BASE, "screenshots")
OUT = os.path.join(BASE, "docs", "AegisCloud_Presentation.pptx")

# ---------------------------------------------------------------- palette ---
BG = RGBColor(0x06, 0x0A, 0x13)
PANEL = RGBColor(0x0D, 0x16, 0x28)
PANEL2 = RGBColor(0x11, 0x1C, 0x33)
LINE = RGBColor(0x22, 0x31, 0x4D)
INK = RGBColor(0xE8, 0xEE, 0xFC)
MUT = RGBColor(0x9D, 0xB0, 0xCF)
DIM = RGBColor(0x64, 0x78, 0x9B)
CYAN = RGBColor(0x22, 0xD3, 0xEE)
VIOLET = RGBColor(0x8B, 0x5C, 0xF6)
INDIGO = RGBColor(0x63, 0x66, 0xF1)
OK = RGBColor(0x34, 0xD3, 0x99)
WARN = RGBColor(0xFB, 0xBF, 0x24)
BAD = RGBColor(0xFB, 0x71, 0x85)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD = "Segoe UI Semibold"
BODY = "Segoe UI"

W, H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
prs.core_properties.author = "Praveen Sudireddy"
prs.core_properties.last_modified_by = "Praveen Sudireddy"
prs.core_properties.title = "AegisCloud — Adaptive Security for Cloud Sessions"
prs.core_properties.subject = "Educational security prototype and synthetic ML evaluation"
prs.core_properties.comments = "Prototype: simulated decisions; not cloud access enforcement."
BLANK = prs.slide_layouts[6]

_metrics = None
def metrics():
    global _metrics
    if _metrics is None:
        import joblib
        _metrics = joblib.load(os.path.join(BASE, "artifacts", "champion.joblib"))
    return _metrics


# ---------------------------------------------------------------- helpers ---
def slide(title=None, kicker=None, page=None):
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG; bg.line.fill.background()
    bg.shadow.inherit = False
    # top accent line
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Pt(4))
    bar.fill.solid(); bar.fill.fore_color.rgb = CYAN; bar.line.fill.background()
    bar.shadow.inherit = False
    if kicker:
        t = text(s, Inches(0.62), Inches(0.34), Inches(9), Inches(0.3), kicker.upper(),
                 11, CYAN, bold=True, spacing=True)
    if title:
        text(s, Inches(0.6), Inches(0.62), Inches(12.1), Inches(0.8), title, 30, INK, bold=True)
    if page is not None:
        text(s, Inches(12.25), Inches(6.95), Inches(0.8), Inches(0.3), str(page), 10, DIM,
             align=PP_ALIGN.RIGHT)
        text(s, Inches(0.62), Inches(6.95), Inches(8), Inches(0.3),
             "AEGISCLOUD  ·  SECURITY DEMONSTRATION", 9, DIM)
    return s


def text(s, x, y, w, h, body, size=14, color=INK, bold=False, font=BODY,
         align=PP_ALIGN.LEFT, spacing=False, line=1.15, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    lines = body.split("\n") if isinstance(body, str) else body
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        r = p.add_run(); r.text = ln
        r.font.size = Pt(size); r.font.bold = bold; r.font.name = font
        r.font.color.rgb = color
        if spacing:
            r.font.name = HEAD
    return tb


def bullets(s, x, y, w, h, items, size=14, gap=0.14, color=INK):
    """items: list of (level, text) or plain strings."""
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0; tf.margin_top = tf.margin_bottom = 0
    first = True
    for it in items:
        lvl, txt = it if isinstance(it, tuple) else (0, it)
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.line_spacing = 1.18
        p.space_after = Pt(gap * 72)
        dot = "▸  " if lvl == 0 else "–  "
        r0 = p.add_run(); r0.text = ("    " * lvl) + dot
        r0.font.size = Pt(size); r0.font.name = BODY
        r0.font.color.rgb = CYAN if lvl == 0 else DIM
        # bold lead-in before ':' if present
        if ":" in txt:
            lead, rest = txt.split(":", 1)
            r1 = p.add_run(); r1.text = lead + ":"
            r1.font.size = Pt(size); r1.font.bold = True; r1.font.name = BODY
            r1.font.color.rgb = WHITE
            r2 = p.add_run(); r2.text = rest
            r2.font.size = Pt(size); r2.font.name = BODY; r2.font.color.rgb = color
        else:
            r1 = p.add_run(); r1.text = txt
            r1.font.size = Pt(size); r1.font.name = BODY; r1.font.color.rgb = color
    return tb


def panel(s, x, y, w, h, fill=PANEL, line=LINE, radius=None):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.adjustments[0] = 0.06
    shp.fill.solid(); shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = line; shp.line.width = Pt(0.9)
    shp.shadow.inherit = False
    return shp


def kpi(s, x, y, w, h, label, value, sub="", accent=CYAN):
    panel(s, x, y, w, h)
    tag = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y + Inches(0.16), Pt(3), h - Inches(0.32))
    tag.fill.solid(); tag.fill.fore_color.rgb = accent; tag.line.fill.background()
    tag.shadow.inherit = False
    text(s, x + Inches(0.22), y + Inches(0.18), w - Inches(0.3), Inches(0.24), label.upper(),
         9.5, DIM, bold=True, spacing=True)
    text(s, x + Inches(0.22), y + Inches(0.46), w - Inches(0.3), Inches(0.45), value,
         25, accent, bold=True, font=HEAD)
    if sub:
        text(s, x + Inches(0.22), y + h - Inches(0.42), w - Inches(0.3), Inches(0.3), sub, 9.5, MUT)


def chip(s, x, y, w, h, label, color=CYAN, size=10):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.adjustments[0] = 0.5
    shp.fill.solid(); shp.fill.fore_color.rgb = PANEL2
    shp.line.color.rgb = color; shp.line.width = Pt(0.9)
    shp.shadow.inherit = False
    tf = shp.text_frame; tf.word_wrap = False
    tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.size = Pt(size); r.font.bold = True; r.font.name = BODY
    r.font.color.rgb = color
    return shp


def table(s, x, y, w, rows, col_ratios=None, header=True, size=10.5, row_h=0.32,
          accent_col=None):
    nrow, ncol = len(rows), len(rows[0])
    shp = s.shapes.add_table(nrow, ncol, x, y, w, Inches(row_h * nrow))
    tbl = shp.table
    tbl.first_row = header
    if col_ratios:
        total = sum(col_ratios)
        for i, r in enumerate(col_ratios):
            tbl.columns[i].width = Emu(int(w * r / total))
    for ri, row in enumerate(rows):
        tbl.rows[ri].height = Inches(row_h)
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.margin_left = Inches(0.08); cell.margin_right = Inches(0.05)
            cell.margin_top = Inches(0.02); cell.margin_bottom = Inches(0.02)
            cell.fill.solid()
            if header and ri == 0:
                cell.fill.fore_color.rgb = PANEL2
            else:
                cell.fill.fore_color.rgb = PANEL if ri % 2 else RGBColor(0x0A, 0x12, 0x22)
            tf = cell.text_frame; tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run(); r.text = str(val)
            r.font.size = Pt(size); r.font.name = BODY
            if header and ri == 0:
                r.font.bold = True; r.font.color.rgb = MUT
            else:
                r.font.color.rgb = INK
                if accent_col is not None and ci == accent_col:
                    r.font.bold = True; r.font.color.rgb = CYAN
    return tbl


def pic(s, path, x, y, w, h, border=True):
    from PIL import Image
    if not os.path.exists(path):
        return None
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    px = x + int((w - nw) / 2); py = y + int((h - nh) / 2)
    if border:
        frame = panel(s, px - Inches(0.05), py - Inches(0.05),
                      Emu(nw) + Inches(0.1), Emu(nh) + Inches(0.1), fill=RGBColor(0x08, 0x0F, 0x1C))
    return s.shapes.add_picture(path, Emu(px), Emu(py), Emu(nw), Emu(nh))


def arrow(s, x1, y1, x2, y2, color=LINE):
    ln = s.shapes.add_connector(1, x1, y1, x2, y2)
    ln.line.color.rgb = color; ln.line.width = Pt(1.4)
    return ln


def flow_box(s, x, y, w, h, title, sub="", accent=CYAN, fill=PANEL):
    if not isinstance(accent, RGBColor):
        accent = CYAN
    panel(s, x, y, w, h, fill=fill, line=accent)
    text(s, x + Inches(0.14), y + Inches(0.1), w - Inches(0.28), Inches(0.28), title,
         11.5, INK, bold=True, align=PP_ALIGN.CENTER)
    if sub:
        text(s, x + Inches(0.1), y + Inches(0.4), w - Inches(0.2), h - Inches(0.45), sub,
             8.8, MUT, align=PP_ALIGN.CENTER)


M = metrics()
TEST = M["test_metrics"]
CANDS = M["candidates"]
THR = M["threshold"]

# =========================================================== 1 title slide ===
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
bg.fill.solid(); bg.fill.fore_color.rgb = BG; bg.line.fill.background(); bg.shadow.inherit = False
art = os.path.join(BASE, "media", "design", "cyber_background.png")
if os.path.exists(art):
    s.shapes.add_picture(art, Inches(7.22), Inches(0), height=H)
mark = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.72), Inches(0.55), Inches(0.55))
mark.adjustments[0] = 0.25
mark.fill.solid(); mark.fill.fore_color.rgb = CYAN; mark.line.fill.background(); mark.shadow.inherit = False
text(s, Inches(0.8), Inches(0.81), Inches(0.55), Inches(0.35), "A", 20, BG, bold=True, font=HEAD, align=PP_ALIGN.CENTER)
text(s, Inches(1.5), Inches(0.86), Inches(5.0), Inches(0.4), "SECURITY  /  MACHINE LEARNING  /  CRYPTOGRAPHY", 10.5, CYAN, bold=True, spacing=True)
text(s, Inches(0.8), Inches(1.66), Inches(7.6), Inches(0.95), "AegisCloud", 48, WHITE, bold=True, font=HEAD)
text(s, Inches(0.82), Inches(2.76), Inches(7.2), Inches(1.28), "Adaptive security for\ncloud sessions.", 31, INK, bold=True, font=HEAD, line=1.08)
text(s, Inches(0.84), Inches(4.21), Inches(6.85), Inches(0.62), "An educational prototype combining MFA, authenticated\nencryption and explainable synthetic risk scoring.", 13.5, MUT, line=1.2)
for i, (lbl, val, sub, col) in enumerate([
    ("synthetic holdout", f"{TEST['accuracy']*100:.1f}%", "accuracy", OK),
    ("success-class F1", f"{TEST['f1']:.3f}", "synthetic test", CYAN),
    ("isolated tests", "26", "passed", VIOLET),
]):
    kpi(s, Inches(0.82) + Inches(2.16) * i, Inches(5.04), Inches(2.02), Inches(1.35), lbl, val, sub, col)
text(s, Inches(0.84), Inches(6.55), Inches(6.8), Inches(0.35), "PRESENTED BY  ·  PRAVEEN SUDIREDDY", 11, CYAN, bold=True)
text(s, Inches(8.95), Inches(6.84), Inches(3.9), Inches(0.3), "SIMULATED RECOMMENDATIONS ONLY", 9, MUT, align=PP_ALIGN.RIGHT)


# =========================================================== 2 agenda ======
s = slide("Agenda", "walkthrough", 2)
items = [("01", "Problem & motivation", "why perimeter security fails in the cloud"),
         ("02", "Project scope & boundaries", "what the prototype does and does not do"),
         ("03", "Proposed architecture", "four pillars, one decision point"),
         ("04", "Identity & hybrid cryptography", "TOTP, AES-256-GCM, Shamir sharing"),
         ("05", "Risk engine & ML pipeline", "features, model selection, explainability"),
         ("06", "Results, testing & future work", "synthetic holdout, tests and roadmap")]
for i, (n, t, sub) in enumerate(items):
    col, row = i % 2, i // 2
    x = Inches(0.62) + Inches(6.15) * col
    y = Inches(1.72) + Inches(1.55) * row
    panel(s, x, y, Inches(5.85), Inches(1.3))
    text(s, x + Inches(0.24), y + Inches(0.24), Inches(0.8), Inches(0.5), n, 22, CYAN, bold=True,
         font=HEAD)
    text(s, x + Inches(1.12), y + Inches(0.26), Inches(4.5), Inches(0.35), t, 14.5, INK, bold=True)
    text(s, x + Inches(1.12), y + Inches(0.66), Inches(4.5), Inches(0.4), sub, 11, MUT)

# ===================================================== 3 problem statement ==
s = slide("Cloud access needs context beyond the network",
          "01 · problem & motivation", 3)
bullets(s, Inches(0.62), Inches(1.75), Inches(6.3), Inches(4.6), [
    "Stolen credentials: passwords can be phished or replayed, potentially exposing protected resources.",
    "Unauthenticated encryption: without an integrity tag, modified ciphertext may not be detected.",
    "Limited context: unfamiliar devices, unusual times or geographic changes may merit further review.",
    "Alert fatigue: coarse static thresholds can create too many alerts or miss unusual activity.",
    "Audit gaps: mutable logs can make investigation and integrity verification harder.",
], size=13.5)
panel(s, Inches(7.25), Inches(1.75), Inches(5.4), Inches(4.55))
text(s, Inches(7.55), Inches(1.98), Inches(4.8), Inches(0.4), "Design objectives", 14,
     VIOLET, bold=True)
bullets(s, Inches(7.55), Inches(2.45), Inches(4.8), Inches(3.6), [
    "Explore session-level recommendations informed by identity and context.",
    "ML probability + deterministic policy can be fused so the verdict is still explainable.",
    "Cryptography can combine authenticated envelopes with a separate threshold-sharing demo.",
    "Adaptation should be measured: PSI monitoring, manual retraining and model versions.",
], size=12.5)

# =================================================== 4 scope & boundaries ===
s = slide("A practical scope, clearly bounded", "02 · prototype scope", 4)
cards = [
    ("01", "IDENTITY", "Password hashing, demo MFA, TOTP endpoints and revocable sessions.", OK),
    ("02", "RISK", "Synthetic sessions scored with model output and explainable rule points.", CYAN),
    ("03", "CRYPTOGRAPHY", "Authenticated file encryption and an independent k-of-n sharing demo.", VIOLET),
    ("04", "OPERATIONS", "Synthetic replay, model evaluation, PSI and hash-linked audit records.", WARN),
]
for i, (num, title, desc, col) in enumerate(cards):
    x = Inches(0.62) + Inches(3.11) * i
    panel(s, x, Inches(1.78), Inches(2.86), Inches(3.55), line=col)
    text(s, x+Inches(.22), Inches(2.0), Inches(2.35), Inches(.35), num, 15, col, bold=True, font=HEAD)
    text(s, x+Inches(.22), Inches(2.52), Inches(2.4), Inches(.4), title, 14, INK, bold=True)
    text(s, x+Inches(.22), Inches(3.12), Inches(2.38), Inches(1.65), desc, 12, MUT, line=1.22)
panel(s, Inches(.62), Inches(5.55), Inches(12.1), Inches(1.1), fill=PANEL2)
text(s, Inches(.9), Inches(5.77), Inches(1.45), Inches(.3), "BOUNDARY", 11, WARN, bold=True)
text(s, Inches(2.4), Inches(5.74), Inches(9.95), Inches(.55),
     "No real cloud access enforcement. Training data and replay are synthetic. Demo OTP and local keys are not production controls.",
     12, INK, line=1.15)


# ================================================= 5 proposed system pillars ==
s = slide("Four pillars, one decision point", "03 · proposed system", 5)
pillars = [
    ("Identity", "MFA", "scrypt passwords, RFC-6238 TOTP, recovery codes,\ntrusted devices, revocable sessions, RBAC", OK),
    ("Risk engine", "Adaptive", "ML P(success) + behavioural rules →\n0-100 risk score with additive explanation", CYAN),
    ("Cryptography", "Hybrid", "AES-256-GCM envelope encryption,\ntamper detection, Shamir secret-sharing demo", VIOLET),
    ("Intelligence", "Continuous", "PSI comparison, manual retraining,\nversioned champion promotion", WARN),
]
for i, (t, tag, body, col) in enumerate(pillars):
    x = Inches(0.62) + Inches(3.11) * i
    panel(s, x, Inches(1.72), Inches(2.86), Inches(3.6), line=col)
    text(s, x + Inches(0.22), Inches(1.94), Inches(2.4), Inches(0.35), tag.upper(), 10, col,
         bold=True, spacing=True)
    text(s, x + Inches(0.22), Inches(2.24), Inches(2.4), Inches(0.4), t, 17, INK, bold=True, font=HEAD)
    text(s, x + Inches(0.22), Inches(2.86), Inches(2.45), Inches(2.2), body, 11, MUT, line=1.25)
panel(s, Inches(0.62), Inches(5.5), Inches(12.1), Inches(1.15), fill=PANEL2)
text(s, Inches(0.9), Inches(5.72), Inches(11.6), Inches(0.8),
     "Simulated sessions → suggested ALLOW · STEP-UP · REVIEW · BLOCK — not enforced on cloud resources",
     14, INK, bold=True, align=PP_ALIGN.CENTER)

# ==================================================== 6 architecture slide ==
s = slide("System architecture", "03 · proposed system", 6)
# browser layer
flow_box(s, Inches(0.62), Inches(1.72), Inches(2.5), Inches(1.0), "SOC console (SPA)",
         "vanilla JS · SVG charts", CYAN)
flow_box(s, Inches(0.62), Inches(2.95), Inches(2.5), Inches(1.0), "Flask API",
         "auth · risk · vault · model", INDIGO)
flow_box(s, Inches(0.62), Inches(4.18), Inches(2.5), Inches(1.0), "SQLite (WAL)",
         "users · decisions · audit", VIOLET)
flow_box(s, Inches(0.62), Inches(5.41), Inches(2.5), Inches(1.0), "Instance store",
         "AES-GCM blobs · master key", OK)
arrow(s, Inches(3.16), Inches(2.22), Inches(3.62), Inches(2.22))
arrow(s, Inches(1.87), Inches(2.98), Inches(1.87), Inches(3.95))
arrow(s, Inches(3.16), Inches(3.45), Inches(3.62), Inches(3.45), VIOLET)

# middle: services
svc = [("Identity service", "security.py", OK), ("Risk engine", "risk.py", CYAN),
       ("Crypto vault", "crypto_vault.py", VIOLET), ("ML service", "ml.py", WARN),
       ("Drift monitor", "drift.py", BAD)]
for i, (t, f, col) in enumerate(svc):
    y = Inches(1.72) + Inches(0.86) * i
    flow_box(s, Inches(3.75), y, Inches(3.1), Inches(0.74), t, f, col)
# pillars
flow_box(s, Inches(7.2), Inches(1.72), Inches(2.35), Inches(1.8), "Policy decision point",
         "demo thresholds\nper-user adaptation\nfour recommendations", CYAN)
flow_box(s, Inches(7.2), Inches(3.72), Inches(2.35), Inches(1.8), "Evidence store",
         "decisions · feedback\nlabels · alerts\naudit hash chain", VIOLET)
flow_box(s, Inches(7.2), Inches(5.72), Inches(2.35), Inches(0.7), "Approval queue", "demo only", WARN)
arrow(s, Inches(6.9), Inches(2.45), Inches(7.16), Inches(2.45), CYAN)
arrow(s, Inches(6.9), Inches(3.3), Inches(7.16), Inches(4.2), LINE)
# right column: models + external
flow_box(s, Inches(9.85), Inches(1.72), Inches(2.85), Inches(1.15), "Champion model",
         f"{M['champion']} · synthetic model", OK)
flow_box(s, Inches(9.85), Inches(3.05), Inches(2.85), Inches(1.15), "Model registry",
         "versions · metrics · promote", WARN)
flow_box(s, Inches(9.85), Inches(4.38), Inches(2.85), Inches(1.15), "Training pipeline",
         "time-ordered split · 4 candidates", INDIGO)
flow_box(s, Inches(9.85), Inches(5.71), Inches(2.85), Inches(0.7), "TOTP / demo OTP", "no SMTP provider", MUT)
text(s, Inches(0.62), Inches(6.65), Inches(6), Inches(0.3),
     "Conceptual architecture · local single-node demonstration", 9, DIM)

# ================================================= 7 decision pipeline ======
s = slide("Risk recommendations for simulated sessions", "03 · proposed system", 7)
steps = [("Session\ningested", "cloud · auth ·\nresource · device", CYAN),
         ("Feature\nengineering", "17 numeric + derived\nfeatures", INDIGO),
         ("P(success)\nML", f"{M['champion']}\nROC-AUC {TEST['roc_auc']}", OK),
         ("Rule\nevidence", "8 deterministic\nsignals", VIOLET),
         ("Fusion\n0-100", "additive in risk\npoints", CYAN)]
for i, (t, sub, col) in enumerate(steps):
    x = Inches(0.62) + Inches(2.5) * i
    flow_box(s, x, Inches(1.85), Inches(2.05), Inches(1.3), t, sub, col)
    if i < 4:
        arrow(s, x + Inches(2.08), Inches(2.5), x + Inches(2.42), Inches(2.5), col)
dec = [("ALLOW", "< 38", "suggested outcome", OK), ("STEP-UP", "38-64", "suggest challenge", WARN),
       ("REVIEW", "64-82", "queue for review", RGBColor(0xFB, 0x92, 0x3C)),
       ("BLOCK", "≥ 82", "suggest denial", BAD)]
for i, (t, rng, sub, col) in enumerate(dec):
    x = Inches(0.62) + Inches(3.11) * i
    panel(s, x, Inches(3.55), Inches(2.86), Inches(1.5), line=col)
    text(s, x + Inches(0.2), Inches(3.72), Inches(2.4), Inches(0.4), t, 18, col, bold=True, font=HEAD)
    text(s, x + Inches(0.2), Inches(4.14), Inches(2.4), Inches(0.3), f"risk {rng}", 11, INK)
    text(s, x + Inches(0.2), Inches(4.44), Inches(2.4), Inches(0.3), sub, 10, MUT)
text(s, Inches(0.62), Inches(5.35), Inches(6.2), Inches(0.35),
     "How to interpret the score:", 13, VIOLET, bold=True)
bullets(s, Inches(0.62), Inches(5.72), Inches(6.1), Inches(1.2), [
    "demo thresholds may shift based on the scored subject’s past scores",
    "the explanation is exact — contributions sum to the score",
], size=11.5)
bullets(s, Inches(7.1), Inches(5.72), Inches(5.6), Inches(1.2), [
    "every decision stores features, probability, verdict and reasons",
    "feedback is recorded, but retraining does not yet ingest it",
], size=11.5)

# ==================================================== 8 identity layer ======
s = slide("Pillar 1 — identity & session security", "04 · identity", 8)
bullets(s, Inches(0.62), Inches(1.75), Inches(6.1), Inches(4.5), [
    "Password storage: scrypt (N=2¹⁴, r=8, p=1) with a per-user 16-byte salt; constant-time verify.",
    "Policy engine: length, character classes, block-list, sequence detection, entropy estimate — scored live in the UI.",
    "Second factor: RFC 6238 TOTP with enrollment API, plus 10 single-use recovery codes (scrypt-hashed).",
    "Session tokens: HMAC-SHA256 signed payload + server-side row; revocation and 8 h TTL.",
    "Brute force: per-account failure counter with exponential lockout, per-attempt risk scoring, audit of every failure.",
    "Device memory: a first-seen device adds +16 to the informational login-risk score; trust can be recorded.",
    "RBAC: role checks protect administrative routes; demo OTP is not production MFA.",
], size=12.5, gap=0.1)
panel(s, Inches(7.0), Inches(1.75), Inches(5.7), Inches(4.4))
text(s, Inches(7.3), Inches(1.98), Inches(5), Inches(0.3), "Login is itself a scored event", 14, CYAN,
     bold=True)
pic(s, os.path.join(SHOTS, "02_mfa.png"), Inches(7.25), Inches(2.45), Inches(5.2), Inches(3.5),
    border=False)
text(s, Inches(7.3), Inches(6.05), Inches(5.2), Inches(0.4),
     "new device and failures change displayed risk; MFA is required in the demo", 10, MUT)

# ================================================= 9 cryptography ==========
s = slide("Pillar 2 — authenticated cryptography", "04 · cryptography", 9)
panel(s, Inches(0.62), Inches(1.72), Inches(6.3), Inches(2.55))
text(s, Inches(0.9), Inches(1.92), Inches(5.8), Inches(0.3), "Envelope encryption (per file)", 13.5, CYAN,
     bold=True)
flow_box(s, Inches(0.9), Inches(2.4), Inches(1.55), Inches(0.8), "file bytes", "", MUT)
flow_box(s, Inches(2.75), Inches(2.4), Inches(1.55), Inches(0.8), "AES-256-GCM", "DEK random", CYAN)
flow_box(s, Inches(4.6), Inches(2.4), Inches(1.55), Inches(0.8), "ciphertext", "+ tag", OK)
arrow(s, Inches(2.47), Inches(2.8), Inches(2.72), Inches(2.8))
arrow(s, Inches(4.32), Inches(2.8), Inches(4.57), Inches(2.8))
text(s, Inches(0.9), Inches(3.35), Inches(5.7), Inches(0.8),
     "DEK is wrapped by the master key (AES-GCM key wrap). AAD binds ciphertext to owner:filename,\n"
     "so a blob moved to another record fails authentication.", 10.5, MUT)
panel(s, Inches(7.15), Inches(1.72), Inches(5.55), Inches(2.55))
text(s, Inches(7.42), Inches(1.92), Inches(5), Inches(0.3), "Shamir's Secret Sharing over GF(2⁸)", 13.5,
     VIOLET, bold=True)
bullets(s, Inches(7.42), Inches(2.38), Inches(5.0), Inches(1.8), [
    "one random polynomial per secret byte, evaluated at x = 1…n",
    "any k shares reconstruct via Lagrange interpolation",
    "fewer than k shares do not determine the secret",
    "generic secret-sharing demo; not integrated with vault recovery",
], size=11)
rows = [["Control", "Implementation", "Scope"],
        ["File encryption", "AES-256-GCM per-file data key", "authenticated ciphertext and metadata"],
        ["Key wrapping", "local master key wraps each data key", "local demonstration; not managed KMS"],
        ["Tamper test", "GCM authentication tag rejects changes", "test temporarily alters and restores a byte"],
        ["Secret sharing", "GF(2⁸) k-of-n on a user-supplied string", "standalone; not connected to vault recovery"],
        ]
table(s, Inches(0.62), Inches(4.5), Inches(12.1), rows, col_ratios=[2.3, 4.5, 4.3], size=11, row_h=0.4)
text(s, Inches(0.62), Inches(6.65), Inches(12), Inches(0.25),
     "Local key storage and rotation are demonstration features, not a production key-management workflow.", 9.5, MUT)

# ==================================================== 10 ML pipeline ========
s = slide("Pillar 3 — features & training pipeline", "05 · ML pipeline", 10)
rows = [["Engineered feature", "Why it helps"],
        ["duration_z, duration_absdev", "deviation from *this user's* own session length"],
        ["velocity_score, velocity_excess", "request rate vs. baseline of 8 req/min"],
        ["off_hours", "access outside configured hours"],
        ["auth_strength", "ordinal encoding: password .15 → hardware key 1.0"],
        ["novelty_score, interaction_risk", "new device + geo mismatch, weighted by auth strength"],
        ["failed_attempts, anomaly_flag", "synthetic anomaly indicators"],
        ["resource_sensitivity", "blast radius of the resource being touched"],
        ]
table(s, Inches(0.62), Inches(1.72), Inches(6.45), rows, col_ratios=[2.4, 4.0], size=10.5,
      row_h=0.4)
text(s, Inches(0.62), Inches(5.1), Inches(6.4), Inches(0.4), "37 features: 9 numeric + 8 derived + one-hot", 11, CYAN,
     bold=True)
bullets(s, Inches(0.62), Inches(5.5), Inches(6.4), Inches(1.4), [
    "time-ordered split: first 70% train / 15% validation / 15% holdout",
    "some baselines use class weights; validation is not resampled",
    "threshold tuned for success-class recall ≥ 0.80",
], size=11)
panel(s, Inches(7.3), Inches(1.72), Inches(5.4), Inches(4.9))
text(s, Inches(7.58), Inches(1.95), Inches(4.9), Inches(0.35), "Pipeline", 13.5, WARN, bold=True)
steps = ["generate / load session corpus (9 000 rows)",
         "fit feature baselines on training only",
         "train 4 candidate families",
         "select champion on validation (F1)",
         "tune threshold (success recall ≥ .80)",
         "score the untouched holdout once",
         "register version + hot-swap in API",
         "monitor PSI → manually retrain if needed"]
for i, t in enumerate(steps):
    y = Inches(2.4) + Inches(0.5) * i
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(7.6), y + Inches(0.08), Inches(0.17), Inches(0.17))
    dot.fill.solid(); dot.fill.fore_color.rgb = CYAN; dot.line.fill.background(); dot.shadow.inherit = False
    text(s, Inches(7.92), y, Inches(4.6), Inches(0.35), t, 10.5, MUT)
text(s, Inches(7.58), Inches(6.28), Inches(4.9), Inches(0.4),
     "bootstrap reuses an existing model; delete it only to retrain", 9.5, DIM)

# ================================================ 11 model selection =======
s = slide("Model selection: validation, then holdout", "05 · results", 11)
order = sorted(CANDS.items(), key=lambda kv: -kv[1]["f1"])
rows = [["Candidate", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "Train"]]
for name, m in order:
    mark = "  ★" if name == M["champion"] else ""
    rows.append([name + mark, f"{m['accuracy']:.3f}", f"{m['precision']:.3f}",
                 f"{m['recall']:.3f}", f"{m['f1']:.3f}", f"{m['roc_auc']:.3f}",
                 f"{m['train_seconds']}s"])
table(s, Inches(0.62), Inches(1.75), Inches(7.5), rows, col_ratios=[2.6, 1.3, 1.4, 1.2, 1.1, 1.3, 1.0],
      size=11, row_h=0.46, accent_col=4)
text(s, Inches(0.62), Inches(4.5), Inches(7.4), Inches(0.3),
     "★ registered champion · table: validation at 0.50; holdout: 1,350 synthetic sessions", 10.5, MUT)
panel(s, Inches(0.62), Inches(4.95), Inches(7.5), Inches(1.85))
text(s, Inches(0.88), Inches(5.12), Inches(7), Inches(0.3), "What the numbers say", 12.5, CYAN, bold=True)
bullets(s, Inches(0.88), Inches(5.5), Inches(7.0), Inches(1.2), [
    f"holdout {M['champion']}: accuracy {TEST['accuracy']*100:.1f}%, success F1 {TEST['f1']}",
    f"Brier score {TEST['brier']}; calibration requires a reliability check",
    "failure recall is 0.6085; these are synthetic outcome metrics",
], size=10.5, gap=0.06)
for i, (lbl, val, col) in enumerate([("accuracy", f"{TEST['accuracy']*100:.1f}%", OK),
                                    ("success F1", str(TEST["f1"]), CYAN),
                                    ("ROC-AUC", str(TEST["roc_auc"]), VIOLET),
                                    ("success recall", str(TEST["recall"]), WARN)]):
    kpi(s, Inches(8.4), Inches(1.75) + Inches(1.22) * i, Inches(4.3), Inches(1.05), lbl, val, "", col)

# ================================================ 12 explainability ========
s = slide("Explainable, adaptive recommendations", "05 · explainability", 12)
pic(s, os.path.join(SHOTS, "04_risk_console.png"), Inches(0.62), Inches(1.7), Inches(8.2), Inches(4.9))
panel(s, Inches(9.05), Inches(1.7), Inches(3.65), Inches(4.9))
text(s, Inches(9.3), Inches(1.92), Inches(3.2), Inches(0.3), "Additive by construction", 13, CYAN,
     bold=True)
bullets(s, Inches(9.3), Inches(2.4), Inches(3.2), Inches(3.9), [
    "rules and model contribute points; a cap adjustment makes the sum exact",
    "fusion points are explicit; the ML probability remains a model output",
    "policy window can shift based on prior scored subject history",
    "attack presets let the examiner test credential stuffing, a geo flag, and insider download",
    "one click records a simulated decision; no cloud access is changed",
], size=10.5, gap=0.1)

# ================================================ 13 monitoring & drift ====
s = slide("Synthetic replay and drift comparison", "05 · adaptation", 13)
pic(s, os.path.join(SHOTS, "05_live_monitor.png"), Inches(0.62), Inches(1.7), Inches(6.6), Inches(4.85))
pic(s, os.path.join(SHOTS, "09_model_drift.png"), Inches(7.4), Inches(1.7), Inches(5.3), Inches(2.35))
panel(s, Inches(7.4), Inches(4.2), Inches(5.3), Inches(2.35))
text(s, Inches(7.65), Inches(4.4), Inches(4.9), Inches(0.3), "PSI → action", 12.5, WARN, bold=True)
bullets(s, Inches(7.65), Inches(4.78), Inches(4.85), Inches(1.6), [
    "< 0.10 stable · 0.10-0.25 watch · ≥ 0.25 review",
    "request rate and failed attempts are in the watch band in this stream",
    "manual retraining reuses the reference corpus; it does not ingest feedback",
], size=10)

# =================================================== 14 audit + vault ======
s = slide("Tamper-evident audit and the encrypted vault", "04 · evidence", 14)
pic(s, os.path.join(SHOTS, "10_audit.png"), Inches(0.62), Inches(1.7), Inches(6.4), Inches(4.85))
pic(s, os.path.join(SHOTS, "06_vault.png"), Inches(7.2), Inches(1.7), Inches(5.5), Inches(4.85))

# ===================================================== 15 testing slide =====
s = slide("Testing & security validation", "06 · testing", 15)
tests = [("GF(2⁸) tables vs AES reference", "0x53 · 0xCA = 0x01"),
         ("Shamir roundtrip (k-of-n)", "k reconstructs; fewer do not reveal the secret"),
         ("Vault roundtrip + SHA-256", "plaintext and digest match"),
         ("Tamper detection", "one flipped byte ⇒ AES-GCM InvalidTag"),
         ("Share link is one-time", "2nd download / wrong token refused"),
         ("Password policy & salting", "same password ⇒ different hashes"),
         ("TOTP RFC 6238 vectors", "287082 & 081804 reproduced"),
         ("Token forgery & revocation", "modified signature rejected"),
         ("Audit chain tampering", "edited row localised by verifier"),
         ("Risk monotonicity", "hostile session scores higher, blocks"),
         ("Additive explanation", "Σ contributions == score")]
left = tests[:6]; right = tests[6:]
for i, (t, d) in enumerate(left):
    y = Inches(1.78) + Inches(0.78) * i
    panel(s, Inches(0.62), y, Inches(5.9), Inches(0.66))
    chip(s, Inches(0.78), y + Inches(0.17), Inches(0.5), Inches(0.32), "PASS", OK, size=8.5)
    text(s, Inches(1.42), y + Inches(0.11), Inches(4.9), Inches(0.24), t, 10.5, INK, bold=True)
    text(s, Inches(1.42), y + Inches(0.35), Inches(4.9), Inches(0.24), d, 9, MUT)
for i, (t, d) in enumerate(right):
    y = Inches(1.78) + Inches(0.78) * i
    panel(s, Inches(6.7), y, Inches(6.0), Inches(0.66))
    chip(s, Inches(6.86), y + Inches(0.17), Inches(0.5), Inches(0.32), "PASS", OK, size=8.5)
    text(s, Inches(7.5), y + Inches(0.11), Inches(5.0), Inches(0.24), t, 10.5, INK, bold=True)
    text(s, Inches(7.5), y + Inches(0.35), Inches(5.0), Inches(0.24), d, 9, MUT)
text(s, Inches(0.62), Inches(6.55), Inches(12), Inches(0.3),
     "pytest -q  →  26 passed. Tests are isolated from the demo database and vault.",
     10.5, CYAN)

# ================================================== 16 project outcomes =====
s = slide("Results, without overclaiming", "06 · project outcomes", 16)
for i, (label, value, sub, accent) in enumerate([
    ("synthetic test accuracy", f"{TEST['accuracy']*100:.1f}%", "1,350 later sessions", OK),
    ("success-class F1", f"{TEST['f1']:.4f}", "success = class 1", CYAN),
    ("ROC-AUC", f"{TEST['roc_auc']:.4f}", "synthetic outcomes", VIOLET),
    ("isolated pytest suite", "26 passed", "DB and vault isolated", WARN),
]):
    kpi(s, Inches(.62)+Inches(3.1)*i, Inches(1.78), Inches(2.85), Inches(1.38), label, value, sub, accent)
panel(s, Inches(.62), Inches(3.48), Inches(5.88), Inches(2.63))
text(s, Inches(.9), Inches(3.7), Inches(5.25), Inches(.3), "What is demonstrated", 14, CYAN, bold=True)
bullets(s, Inches(.9), Inches(4.14), Inches(5.2), Inches(1.68), [
    "working identity, vault, scoring and audit flows",
    "validation-based model selection and holdout evaluation",
    "repeatable local tests and synthetic traffic replay",
], size=11.5, gap=.12)
panel(s, Inches(6.72), Inches(3.48), Inches(5.98), Inches(2.63))
text(s, Inches(7.0), Inches(3.7), Inches(5.25), Inches(.3), "What is not established", 14, WARN, bold=True)
bullets(s, Inches(7.0), Inches(4.14), Inches(5.2), Inches(1.68), [
    "real-world attack detection or cloud enforcement",
    "production-grade key management or MFA delivery",
    "LSTM / CNN results — notebook training has not run",
], size=11.5, gap=.12)
text(s, Inches(.62), Inches(6.45), Inches(12), Inches(.3),
     "Evaluation uses generated labels. Failure recall = 0.6085; results do not measure attack-detection recall.", 10.5, MUT)


# ==================================================== 17 future work ======
s = slide("Future work", "06 · roadmap", 17)
fut = [("Production hardening", "Postgres + Redis, HTTPS reverse proxy, secrets manager, rate limiting at the edge"),
       ("Deeper models", "run the supplied LSTM/1D-CNN notebook and report actual results"),
       ("Federation", "SAML/OIDC single sign-on, SCIM provisioning, WebAuthn/passkey as a factor"),
       ("Real telemetry", "CloudTrail / Azure Activity / GCP Audit Log ingestion instead of a synthetic replay"),
       ("Deeper explainability", "counterfactual “what would make this allow?” suggestions for analysts"),
       ("Evaluation", "adversarial testing, false-positive cost analysis, latency budget under load")]
for i, (t, d) in enumerate(fut):
    col, row = i % 2, i // 2
    x = Inches(0.62) + Inches(6.15) * col
    y = Inches(1.78) + Inches(1.62) * row
    panel(s, x, y, Inches(5.85), Inches(1.38))
    text(s, x + Inches(0.24), y + Inches(0.2), Inches(5.2), Inches(0.3), t, 13, CYAN, bold=True)
    text(s, x + Inches(0.24), y + Inches(0.58), Inches(5.3), Inches(0.7), d, 10.5, MUT, line=1.2)

# ================================================== 18 close / thank you ==
s = slide()
glow = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(3.6), Inches(-3.2), Inches(7), Inches(7))
glow.fill.solid(); glow.fill.fore_color.rgb = RGBColor(0x0A, 0x24, 0x33)
glow.line.fill.background(); glow.shadow.inherit = False
text(s, Inches(0.9), Inches(2.1), Inches(11.5), Inches(1.4), "Thank you", 46, INK, bold=True, font=HEAD,
     align=PP_ALIGN.CENTER)
text(s, Inches(1.4), Inches(3.35), Inches(10.5), Inches(0.5),
     "Demo: login → second factor → risk console → synthetic replay → vault → model lab", 14, CYAN,
     align=PP_ALIGN.CENTER)
text(s, Inches(1.4), Inches(4.15), Inches(10.5), Inches(1.6),
     "Questions we expect: why not a pure LSTM? · how are thresholds chosen? · what happens when the model\n"
     "is wrong? · how would key recovery be integrated? · what is still missing for production?",
     11.5, MUT, align=PP_ALIGN.CENTER, line=1.35)
text(s, Inches(1.4), Inches(6.2), Inches(10.5), Inches(0.9),
     "Presented by Praveen Sudireddy",
     11, DIM, align=PP_ALIGN.CENTER)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print("saved", OUT, os.path.getsize(OUT), "bytes,", len(prs.slides.__iter__.__self__._sldIdLst), "slides")
