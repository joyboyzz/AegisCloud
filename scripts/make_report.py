#!/usr/bin/env python3
"""Generate a truthful, metric-backed DOCX report-additions pack."""
from pathlib import Path
import joblib
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / 'docs' / 'AegisCloud_Report_Additions.docx'
M = joblib.load(BASE / 'artifacts' / 'champion.joblib')
T, V, C = M['test_metrics'], M['val_metrics'], M['candidates']
cm = T['confusion']
failure_recall = cm['tn'] / (cm['tn'] + cm['fp'])
D = Document()
D.core_properties.author = 'Praveen Sudireddy'
D.core_properties.last_modified_by = 'Praveen Sudireddy'
D.core_properties.title = 'AegisCloud — Technical Project Overview'
sec = D.sections[0]
sec.top_margin = sec.bottom_margin = Inches(.8)
sec.left_margin = sec.right_margin = Inches(.9)
normal = D.styles['Normal']
normal.font.name = 'Calibri'; normal.font.size = Pt(10.5)
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.13
for i, size in [(1, 16), (2, 12.5), (3, 11)]:
    style = D.styles[f'Heading {i}']
    style.font.name = 'Calibri'; style.font.size = Pt(size)
    style.font.bold = True; style.font.color.rgb = RGBColor(31, 78, 121)
header = sec.header.paragraphs[0]
header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = header.add_run('AEGISCLOUD  /  TECHNICAL OVERVIEW')
run.italic = True; run.font.size = Pt(8); run.font.color.rgb = RGBColor(100, 110, 125)


def p(text='', style=None, bold=False, italic=False, align=None):
    q = D.add_paragraph(style=style)
    r = q.add_run(str(text)); r.bold = bold; r.italic = italic
    if align is not None: q.alignment = align
    return q


def table(head, rows):
    t = D.add_table(rows=1, cols=len(head))
    t.style = 'Light Grid Accent 1'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, x in enumerate(head):
        t.rows[0].cells[i].text = str(x)
        for r in t.rows[0].cells[i].paragraphs[0].runs: r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for i, x in enumerate(row): cells[i].text = str(x)
    for row in t.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.space_after = Pt(1)
                for r in para.runs: r.font.size = Pt(9)
    D.add_paragraph()
    return t


def caption(text):
    q = p(text, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    for r in q.runs: r.font.size = Pt(9); r.font.color.rgb = RGBColor(90, 90, 90)


def picture(name, note):
    path = BASE / 'screenshots' / name
    if path.exists():
        q = D.add_paragraph(); q.alignment = WD_ALIGN_PARAGRAPH.CENTER
        q.add_run().add_picture(str(path), width=Inches(6.35))
        caption(note)


p('AegisCloud', bold=True, align=WD_ALIGN_PARAGRAPH.CENTER).runs[0].font.size = Pt(24)
p('Technical project overview', bold=True,
  align=WD_ALIGN_PARAGRAPH.CENTER).runs[0].font.size = Pt(15)
p('Adaptive security for simulated cloud sessions', align=WD_ALIGN_PARAGRAPH.CENTER)
p('Prepared by Praveen Sudireddy', align=WD_ALIGN_PARAGRAPH.CENTER)
D.add_heading('About this document', 1)
p('This technical overview describes the delivered educational prototype, its architecture, '
  'synthetic experiment, test coverage and limitations. It can be adapted to an institution’s '
  'required report template. The sequence-model notebook is prepared but not trained.')
p('Risk recommendations do not enforce access to any cloud provider, and the metrics '
  'below are not real-world attack-detection results.', bold=True)

D.add_heading('Abstract', 1)
p(f'AegisCloud is a demonstration prototype combining password and second-factor '
  f'authentication, authenticated encryption and machine-learning-assisted session scoring. '
  f'An AES-256-GCM vault encrypts files with individual data keys protected by a local master '
  f'key. An independent Shamir secret-sharing demonstration operates over GF(2⁸). '
  f'A synthetic dataset of 9,000 sessions is split chronologically into 70% training, 15% '
  f'validation and 15% test. User baselines and the feature vocabulary are fitted using only '
  f'training rows. Four scikit-learn classifiers are compared on validation data; the selected '
  f'{M["champion"]} model achieves test accuracy {T["accuracy"]:.4f}, success-class F1 '
  f'{T["f1"]:.4f} and ROC-AUC {T["roc_auc"]:.4f} on 1,350 synthetic test sessions. '
  f'The model output and deterministic rules produce an interpretable 0–100 score and suggested '
  f'allow, step-up, review or block outcomes. A dashboard displays simulated traffic, a PSI '
  f'distribution comparison, a model registry and an audit hash chain. These are prototype '
  f'recommendations, not enforced decisions for an actual cloud provider. The current evidence '
  f'does not establish real-world attack-detection performance or a deep-learning advantage.')
p('Keywords: multi-factor authentication, AES-GCM, secret sharing, risk scoring, '
  'synthetic data, model evaluation, distribution drift.', italic=True)

D.add_heading('1. Objectives and scope', 1)
for x in [
    'Demonstrate password hashing, revocable sessions, TOTP and recovery-code primitives.',
    'Protect demonstration files with AES-256-GCM envelope encryption and show tag-based tamper detection.',
    'Compare several classifiers using a chronological evaluation of synthetic session data.',
    'Explain a risk recommendation using explicit model and rule-point contributions.',
    'Present drift indicators, manually triggered retraining, a model registry and an audit trail.',
]: p(x, 'List Bullet')
p('Scope boundary: the console does not intercept actual AWS, Azure or GCP access requests; '
  'step-up, review and block are recommendations for simulated events. A separately generated '
  'Shamir share set is not connected to the vault master-key recovery process.')

D.add_heading('2. Capabilities and boundaries', 1)
table(['Area', 'Prototype capability', 'Boundary'], [
    ['Identity', 'Password hashing, TOTP API, recovery codes and revocable sessions.',
     'Demo OTP is shown on screen; secure delivery is not integrated.'],
    ['Risk', 'Model output and rule points combine into an explainable recommendation.',
     'No provider-side access enforcement or validated attack-detection claim.'],
    ['Cryptography', 'AES-GCM envelope encryption and tamper detection.',
     'Local master key and rotation are for demonstration only.'],
    ['Secret sharing', 'GF(2⁸) k-of-n splitting of a supplied secret.',
     'The demo is independent of the vault recovery workflow.'],
    ['Monitoring', 'Synthetic replay, PSI, model registry and hash-linked audit.',
     'Replay is not live telemetry; retraining is manual.'],
])

D.add_heading('3. Architecture and components', 1)
table(['Component', 'Implementation', 'Scope'], [
    ['Identity', 'scrypt, TOTP, signed revocable sessions, lockout', 'Demo email OTP appears in the UI; no email provider is integrated.'],
    ['Vault', 'Per-file AES-256-GCM DEK; master-key wrapping', 'Local single-node key and file store.'],
    ['Risk model', f'{M["champion"]}; {len(M["features"])} model features', 'Predicts a synthetic success label.'],
    ['Policy', 'Additive rule points + model contribution; four recommendations', 'No live cloud-enforcement integration.'],
    ['Drift', 'PSI on reference and replay CSV files', 'Monitoring aid; retraining is manual.'],
    ['Audit', 'Hash-linked SQLite events with an integrity checker', 'Tamper evidence, not cryptographic non-repudiation.'],
])

D.add_heading('4. Design details', 1)
D.add_heading('4.1 Authentication and sessions', 2)
p('Passwords are stored with per-user salts using scrypt. The seeded analyst uses RFC 6238 '
  'TOTP; other seeded demo accounts use a generated code shown on screen. Signed session '
  'tokens are backed by server-side records so that they can be revoked. TOTP enrollment '
  'and recovery-code endpoints are present, but enrollment has no dedicated console page. '
  'The demo lacks an SMTP delivery provider, phishing-resistant authentication, HTTPS '
  'termination and production-grade session controls.')
D.add_heading('4.2 Authenticated file encryption', 2)
p('Each uploaded file is encrypted using a random 256-bit data-encryption key and a fresh '
  '96-bit GCM nonce. Its owner ID and file name are authenticated as associated data. The '
  'data key is wrapped with another AES-GCM operation under a local master key. Decryption '
  'checks the authentication tag and a stored SHA-256 digest. The tamper-test action '
  'modifies and restores a ciphertext byte to demonstrate detection. Key rotation and local '
  'key storage are intended only for a single-node demonstration, not production key management.')
D.add_heading('4.3 Threshold secret-sharing demonstration', 2)
p('Each secret byte is used as the constant of a random polynomial over GF(2⁸). Any k '
  'proper shares allow interpolation; fewer do not reveal the secret. The interface splits '
  'a user-supplied demo secret rather than the actual vault key. The share format does not '
  'carry authenticated threshold metadata: providing too few shares can produce incorrect '
  'bytes rather than a reliable explicit error.')
D.add_heading('4.4 Risk scoring and limitations', 2)
p('The model contributes 0.42 × 100 × (1 − P(success)). Additional rules contribute points '
  'for the chosen authentication method, failed attempts, new device, geographic anomaly, '
  'off-hours access, request rate, resource sensitivity and anomaly flags. A baseline '
  'contribution and any score-bound adjustment are included, so displayed contributions '
  'sum to the score in the range 0–100. Base demo thresholds are 38, 64 and 82; they may '
  'shift using the scored subject’s prior recorded risk. These are prototype heuristics, '
  'not validated safety guarantees or actual enforcement policies.')
picture('04_risk_console.png', 'Figure 1. Example simulated session and additive score explanation.')

D.add_heading('5. Data and experimental method', 1)
p('The supplied generator creates 9,000 synthetic multi-cloud sessions and an additional '
  '2,500-row replay corpus with a different distribution. Features and synthetic outcomes '
  'are generated together; therefore these results evaluate that generator, not real cloud '
  'telemetry or attacker behavior. The outcome is success = 1 and failure = 0.')
p('The training pipeline orders rows by timestamp and partitions them into 6,300 training, '
  '1,350 validation and 1,350 test sessions. User-duration statistics and category columns '
  'are learned on the training split; unseen users use training-wide statistics. Four '
  'candidates are compared at threshold 0.50 on validation. The highest validation '
  'success-class F1 is selected, then its probability threshold is tuned on validation '
  'to maximize that F1 subject to success-class recall at least 0.80. Finally the selected '
  'model is assessed on the chronologically later test block.')
D.add_heading('5.1 Validation candidate comparison', 2)
rows = []
for name, m in sorted(C.items(), key=lambda kv: -kv[1]['f1']):
    rows.append([name + (' *' if name == M['champion'] else ''),
                 f'{m["accuracy"]:.4f}', f'{m["precision"]:.4f}', f'{m["recall"]:.4f}',
                 f'{m["f1"]:.4f}', f'{m["roc_auc"]:.4f}'])
table(['Candidate', 'Accuracy', 'Precision¹', 'Recall¹', 'F1¹', 'ROC-AUC'], rows)
caption('Table 1. Validation results at threshold 0.50; * selected before threshold tuning. ¹ Success class.')
D.add_heading('5.2 Selected model: final synthetic test block', 2)
table(['Measure', 'Value'], [
    ['Model / version', f'{M["champion"]} / {M["version"]}'],
    ['Test rows / selected threshold', f'{M["test_rows"]:,} / {M["threshold"]:.2f}'],
    ['Accuracy', f'{T["accuracy"]:.4f}'],
    ['Success precision / recall / F1', f'{T["precision"]:.4f} / {T["recall"]:.4f} / {T["f1"]:.4f}'],
    ['Failure recall (specificity)', f'{failure_recall:.4f}'],
    ['ROC-AUC / Brier score', f'{T["roc_auc"]:.4f} / {T["brier"]:.4f}'],
    ['Confusion matrix [TN, FP; FN, TP]', f'[{cm["tn"]}, {cm["fp"]}; {cm["fn"]}, {cm["tp"]}]'],
])
p('Failure recall is TN/(TN+FP) because failure is encoded as class 0. Success recall is '
  'TP/(TP+FN). Neither quantity is a validated real-world attack-detection rate. Brier '
  'score measures mean squared probability error; by itself it does not prove calibration. '
  'A reliability plot and independent real-world data are needed for stronger claims.')
picture('08_model_lab.png', 'Figure 2. Model lab: test metrics and validation-based model comparison.')

D.add_heading('6. Drift and retraining', 1)
p('The PSI screen compares the synthetic training CSV with the supplied synthetic replay '
  'CSV, not live provider telemetry. PSI values from 0.10 to below 0.25 are labelled watch, '
  'and values at or above 0.25 are labelled drift. In this snapshot request rate and failed '
  'attempts are in the watch band. An operator can manually retrain and promote a model. '
  'The current retraining job reuses the reference CSV; recorded analyst feedback is not '
  'yet incorporated into model training.')

D.add_heading('7. Testing and demonstration', 1)
p('At the time of this report, the isolated pytest suite reports 26 passing tests. '
  'The tests cover GF arithmetic, threshold reconstruction, vault integrity, share-link '
  'limits and concurrency, password hashing, TOTP vectors, session authorization and '
  'revocation, audit-chain consistency under concurrent writes, drift bins, training-only '
  'baseline handling and risk-score contributions. The test suite uses a temporary DB '
  'and vault rather than the running demo’s storage.')
picture('06_vault.png', 'Figure 3. Local demo vault and a separate secret-sharing demonstration.')
D.add_heading('Suggested demonstration sequence', 2)
for x in [
    'Sign in with the seeded demo account and enter the on-screen demo OTP.',
    'Compare the normal and credential-stuffing presets; point out that outcomes are recommendations.',
    'Replay synthetic traffic and show the PSI comparison and validation/test metrics.',
    'Upload and download a test file, then run the vault tamper test.',
    'Split a demo string 3-of-5: three shares reconstruct; two may produce invalid text rather than an explicit error.',
    'Verify the audit chain and show the manual model-retraining control.',
]: p(x, 'List Number')

D.add_heading('8. Conclusion and future work', 1)
p('AegisCloud demonstrates how authentication, authenticated encryption, synthetic '
  'session scoring and an auditable interface can be combined in one educational prototype. '
  'The experiment supports the reported synthetic-data metrics but does not show a '
  'real-world security benefit or production readiness. The '
  'companion Colab notebook provides a sequence-model experiment to run, not precomputed '
  'LSTM or CNN findings.')
for x in [
    'Evaluate on independently sourced, properly consented real telemetry with threat-labelled data.',
    'Integrate provider-side policy enforcement and design an actual approval separation-of-duties control.',
    'Implement secure OTP delivery, phishing-resistant MFA, HTTPS, rate limiting and managed secrets.',
    'Connect protected key recovery to a KMS/HSM with an authenticated, tested recovery protocol.',
    'Validate calibration and define false-positive/false-negative costs before selecting operating thresholds.',
    'Implement a reviewed, versioned feedback-ingestion pipeline and reevaluate drift on live windows.',
]: p(x, 'List Bullet')
D.add_heading('Selected references', 1)
for x in [
    'NIST SP 800-207, Zero Trust Architecture, 2020. https://csrc.nist.gov/pubs/sp/800/207/final',
    'NIST SP 800-38D, Galois/Counter Mode (GCM), 2007. https://csrc.nist.gov/pubs/sp/800/38/d/final',
    'D. M’Raihi et al., RFC 6238: TOTP, 2011. https://www.rfc-editor.org/rfc/rfc6238',
    'A. Shamir, “How to Share a Secret,” Communications of the ACM, 1979. https://doi.org/10.1145/359168.359176',
]: p(x, 'List Number')
OUT.parent.mkdir(parents=True, exist_ok=True)
D.save(OUT)
print('saved', OUT, OUT.stat().st_size, 'bytes')
