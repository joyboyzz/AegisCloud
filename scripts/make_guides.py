#!/usr/bin/env python3
"""Refresh handoff guides from the current registered experiment."""
from pathlib import Path
import joblib

ROOT = Path(__file__).resolve().parent.parent
m = joblib.load(ROOT / 'artifacts' / 'champion.joblib')
t, c = m['test_metrics'], m['test_metrics']['confusion']
failure = c['tn']/(c['tn'] + c['fp'])
rows = '\n'.join(
    f"| {name}{' **(selected)**' if name == m['champion'] else ''} | {v['accuracy']:.4f} | {v['f1']:.4f} | {v['roc_auc']:.4f} |"
    for name, v in sorted(m['candidates'].items(), key=lambda kv: -kv[1]['f1']))

readme = f'''<div align="center">

![AegisCloud — Adaptive Security for Cloud Sessions](media/GitHub_Banner.png)

**A hands-on security prototype combining identity, encryption and explainable synthetic risk scoring.**

[Explore the presentation](docs/AegisCloud_Presentation.pptx) · [Project guide](docs/PROJECT_GUIDE.md) · [Demo questions](docs/VIVA_QA.md)

</div>

> **Educational prototype, not a production security system.** Risk actions are
> recommendations on synthetic sessions; they do not enforce AWS, Azure or GCP
> access. The model predicts synthetic success/failure, not real attack labels.

![AegisCloud dashboard](screenshots/03_overview.png)

## What you can explore

| Area | Implemented demonstration |
|---|---|
| Identity & access | Password registration, scrypt hashing, login lockout, TOTP and recovery-code APIs, trusted-device records, role checks and revocable sessions. |
| Session risk | ML success probability + rule points, bounded 0–100 risk, per-factor explanation, four suggested actions and synthetic scenario presets. |
| Encrypted vault | Per-file AES-256-GCM data keys wrapped by a local master key; tamper test, local key rotation and limited-use expiring share links. |
| Threshold sharing | Standalone Shamir k-of-n demo over GF(2⁸) for a supplied string—not a vault-key recovery system. |
| ML & monitoring | Four validation candidates, chronological holdout, threshold tuning, a model registry, manual retraining and PSI comparison of synthetic CSVs. |
| Operations | Synthetic replay, stored feedback, demo review queue, alerts, hash-linked audit records and an integrity checker. |
| Engineering | Flask/SQLite, responsive web console, Docker demo, 26 isolated tests, screenshots and an exploratory sequence-model notebook. |

## Quick start

Python 3.10–3.13 recommended. Run locally in a virtual environment:

```bash
git clone https://github.com/joyboyzz/AegisCloud.git
cd AegisCloud
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
python scripts/bootstrap.py     # register bundled synthetic model and seed demo
python run.py                   # http://127.0.0.1:5000
```

| Demo user | Demo password | Second factor |
|---|---|---|
| `admin` | `Admin@Aegis2026` | OTP displayed on screen in demo mode |
| `analyst` | `Analyst@Aegis2026` | TOTP; run `python scripts/show_demo_totp.py` locally |
| `demo_user` | `User@Aegis2026` | OTP displayed on screen in demo mode |

> The demo credentials and development secret are deliberately public, not
> secure defaults. `AEGIS_DEMO=0` has no SMTP provider, so email-OTP accounts
> cannot sign in until a delivery provider is implemented. Do not expose this
> development server to an untrusted network.

The generated SQLite database, vault blobs and master key live under `instance/`
and must be kept private and backed up together. To run a separate fresh demo
without altering another database or vault, set `AEGIS_INSTANCE_DIR` to a new
folder **for both bootstrap and run**:

```bash
export AEGIS_INSTANCE_DIR="$PWD/instance/fresh-demo"
python scripts/bootstrap.py
python run.py
```

The default response blocks cross-origin framing. For a trusted embedded demo
preview only, `AEGIS_ALLOW_EMBED=1` opts into cross-site framing and Secure,
partitioned cookies. An HTTPS proxy is required. Do not use this in production.

## Synthetic experiment

The included corpus contains **9,000 generated sessions**. The chronological
split is **6,300 train / 1,350 validation / 1,350 holdout**. User baselines,
category vocabulary and scaling are fitted only on training data. Class 1 is
**success** and class 0 is **failure**. A separate 2,500-row corpus is replayed.

Candidates compared on the **validation block** at a 0.50 threshold:

| Candidate | Accuracy | Success F1 | ROC-AUC |
|---|---:|---:|---:|
{rows}

The selected **{m['champion']}** has its threshold tuned on validation and is
then evaluated on the later **synthetic holdout**:

| Test measure | Value |
|---|---:|
| Success-probability threshold | {m['threshold']:.2f} |
| Accuracy | {t['accuracy']:.4f} |
| Success precision / recall / F1 | {t['precision']:.4f} / {t['recall']:.4f} / {t['f1']:.4f} |
| Failure recall (TN / (TN + FP)) | {failure:.4f} |
| ROC-AUC / Brier score | {t['roc_auc']:.4f} / {t['brier']:.4f} |
| Confusion [TN, FP; FN, TP] | [{c['tn']}, {c['fp']}; {c['fn']}, {c['tp']}] |

These are synthetic **outcome** metrics, not attack-detection rates. A Brier
score alone does not establish probability calibration. The included Colab
LSTM/1D-CNN notebook is prepared but **training has not been run**; it does not
support a deep-model winner claim.

## Run the tests

```bash
python -m pytest tests/ -q
```

The 26-test suite uses a temporary SQLite database and vault. It checks vault
integrity, GF arithmetic, sessions, TOTP vectors, concurrent sharing and audit
writes, training-only baselines, risk explanations and instance isolation.

## Boundaries and responsible use

- Suggested allow / step-up / review / block are not provider enforcement.
  The informational login risk score does not enforce review or block.
- TOTP enrollment and recovery are API flows; there is no enrollment screen.
- Local key rotation is a demo and is not a crash-safe managed-KMS workflow.
- Fewer than k demo shares may produce garbage instead of a clear error.
- Feedback is recorded, but is not used by retraining; PSI compares static
  synthetic CSVs, not live cloud telemetry. Retraining is manual.
- The review queue does not enforce independent separation of duties.
- An attacker controlling the whole audit chain could recompute it: the local
  hash chain is not non-repudiation or an externally anchored audit log.
- For real deployments use secure OTP delivery, HTTPS, managed secrets and keys,
  real telemetry, access-control integration, independent testing and review.

## Rebuild the visual assets

```bash
python -m pip install -r requirements-dev.txt
python scripts/make_deck.py
python scripts/make_report.py
python scripts/make_media.py
```

To retake screenshots, install Chromium with `python -m playwright install
chromium`, start a **separate, fictional demo instance**, and run
`python scripts/shoot.py`. The script logs in, replays sessions and performs a
vault tamper demonstration; do not point it at personal or production data.
Your operating system may require additional Playwright browser libraries.

## Repository map

```text
app/             Flask API, identity, vault, risk, ML, drift and web UI
artifacts/       synthetic reference/replay CSVs and trusted champion model
screenshots/     captures from a fictional, isolated demo instance
notebooks/       unexecuted LSTM / 1D-CNN experiment
scripts/         bootstrap and repeatable document/media builders
tests/           isolated pytest suite
docs/            presentation, technical overview, project and viva guides
media/           LinkedIn-ready project media and artwork
instance/        local private data, generated at runtime; not committed
```

`requirements-dev.txt` adds document and notebook generation dependencies.
The Dockerfile is provided only for local demonstration.

**Provenance:** AegisCloud reworks material from an earlier academic prototype;
this repository documents the current implementation. Presented by Praveen Sudireddy.
'''
(ROOT/'README.md').write_text(readme)

summary=f'''# AegisCloud — project guide

AegisCloud is an educational prototype combining identity controls, authenticated
file encryption, explainable synthetic session-risk scoring and an audit console.
It does **not** enforce cloud-provider access or detect validated real attacks.

## Verified experiment

- 9,000 generated sessions; chronological 6,300 / 1,350 / 1,350 split.
- Four candidates compared on validation at threshold 0.50; training-only
  baseline and category fitting; selected **{m['champion']}**.
- Validation-tuned threshold **{m['threshold']:.2f}**; synthetic test accuracy
  **{t['accuracy']:.4f}**, success F1 **{t['f1']:.4f}**, success recall
  **{t['recall']:.4f}**, failure recall **{failure:.4f}**, ROC-AUC **{t['roc_auc']:.4f}**.
- Confusion [TN, FP; FN, TP]: [{c['tn']}, {c['fp']}; {c['fn']}, {c['tp']}].
- LSTM / 1D-CNN notebook is prepared, **not trained or compared yet**.
- Automated tests: **26 passed**, using isolated temporary DB and vault paths.

## Deliverables

- `AegisCloud_Presentation.pptx` — project presentation (18 slides).
- `AegisCloud_Report_Additions.docx` — technical report material; adapt to the
  institution’s template if a formal report is required.
- `VIVA_QA.md` — examiner questions and a demonstration sequence.
- `../media/LinkedIn_Carousel.pdf` and `../media/LinkedIn_Post.md` — social kit.
- `../README.md` — setup, demo credentials, exact results and boundaries.

## Key limitations

1. TOTP enrollment exists through API, not a dedicated enrollment screen.
2. Secret sharing is independent of vault-key recovery; insufficient shares may
   produce garbled data rather than a reliable explicit error.
3. PSI compares synthetic files, retraining is manual and feedback is not used
   for training. No cloud-provider access policy is enforced.
4. Review records do not enforce separation of duties.
5. Local keys, demo secrets, on-screen OTP, HTTP and SQLite are not production
   controls. The local hash chain is not an externally anchored audit log.

For setup and demo logins, see `../README.md`.
'''
(ROOT/'docs/PROJECT_GUIDE.md').write_text(summary)

qa=[
('What is AegisCloud?', 'A Flask-based educational prototype combining multi-factor identity, an AES-GCM vault, synthetic session scoring and an audit console. It does not enforce real cloud access.'),
('What is the project’s main aim?', 'Show how multiple security components can be composed and how a simulated policy recommendation can be explained.'),
('Is this zero-trust enforcement?', 'No. It demonstrates zero-trust-inspired scoring, but it does not intercept provider requests or enforce its suggested outcomes.'),
('What are the main components?', 'The system combines identity and sessions, a local AES-GCM vault, synthetic session scoring, model evaluation, monitoring and an audit console.'),
('What is the most important scope boundary?', 'The risk engine provides simulated recommendations. It does not enforce actual access to AWS, Azure or GCP.'),
('Are the model results real attack-detection results?', 'No. The labels and sessions are synthetic, and the model predicts session success or failure, not verified attacks.'),
('What does positive class 1 represent?', 'A synthetic successful session. Class 0 is failure. Success recall is not attack-detection recall.'),
('What data is used?', 'A generated corpus of 9,000 sessions, plus a separate synthetic 2,500-row replay corpus. No real cloud telemetry is used.'),
('How is the data split?', 'Chronologically: 6,300 training, 1,350 validation and 1,350 later test rows.'),
('What prevents preprocessing leakage?', 'User-duration baselines and category vocabulary are fitted only on the training rows. Unknown users use global training statistics; scaling is fitted within the candidate training pipeline.'),
('What features are used?', 'Nine numeric fields, eight derived fields and one-hot categorical values: 37 columns in this version.'),
('Which candidate models are compared?', 'Logistic regression, random forest, histogram gradient boosting and a multilayer perceptron. They are compared on validation data.'),
('Which model was selected?', f'{m["champion"]} had the highest validation success F1 at threshold 0.50 in the saved experiment; threshold tuning happens afterwards.'),
('How was the probability threshold chosen?', f'The chosen threshold is {m["threshold"]:.2f}; validation success-class F1 was maximized subject to success-class recall of at least 0.80.'),
('What are the holdout results?', f'Accuracy {t["accuracy"]:.4f}, success F1 {t["f1"]:.4f}, success recall {t["recall"]:.4f}, failure recall {failure:.4f}, ROC-AUC {t["roc_auc"]:.4f}. These are synthetic-data results.'),
('What is the confusion matrix?', f'With success as the positive class: TN={c["tn"]}, FP={c["fp"]}, FN={c["fn"]}, TP={c["tp"]}. Failure recall is TN/(TN+FP).'),
('What does ROC-AUC show?', 'It summarizes how well the model ranks synthetic success outcomes above failures across thresholds; it does not show real-world attack detection.'),
('Does a Brier score prove calibration?', f'No. The test Brier score is {t["brier"]:.4f}, a mean squared probability error. Calibration needs a reliability plot and independent evaluation.'),
('Did an LSTM or CNN beat the baselines?', 'Unknown. The Colab notebook is prepared, but TensorFlow training and comparison have not been run.'),
('Why keep the Colab notebook?', 'It provides a proposed reproducible LSTM/1D-CNN experiment using sequences of up to five per-user sessions, with train-only preprocessing.'),
('What is the risk-score formula?', 'The model contributes 0.42 × 100 × (1 − P(success)); deterministic rule points and a baseline are added, then the result is bounded to 0–100.'),
('Do the displayed contributions sum exactly?', 'Yes, after rounding: when the raw total exceeds the allowed range, an explicit score-bound adjustment is included.'),
('Is this SHAP?', 'No. The additive fusion has explicit point contributions; the separate per-feature leave-one-out model probes are not exact Shapley values.'),
('How do thresholds adapt?', 'A bounded offset is computed from historical risk scores for the scored subject. It is a heuristic and is not empirically validated for fairness or safety.'),
('What do step-up and block actually do?', 'They are demo recommendations for simulated sessions. They are not wired to provider IAM enforcement.'),
('Is four-eyes approval enforced?', 'No. A review queue exists, but the current implementation does not enforce independent requester/approver separation.'),
('What is PSI?', 'Population Stability Index measures feature-distribution differences between the synthetic training CSV and replay CSV. It does not itself prove concept drift.'),
('Is retraining automatic?', 'No. An operator triggers it; it currently trains again from the reference CSV and promotes a version.'),
('Is feedback used in retraining?', 'No. The interface stores feedback and infers an outcome from the prediction, but the training job does not ingest it.'),
('How does MFA work in the demo?', 'The analyst uses TOTP. Other demo accounts see a generated OTP in the UI. No email provider is integrated; this is not a production factor.'),
('What is TOTP?', 'RFC 6238 derives a six-digit code from a secret and a 30-second time step; the verifier allows an adjacent-step window.'),
('How are passwords stored?', 'With scrypt and a random per-user 16-byte salt. Password verification compares derived hashes.'),
('How is brute force handled?', 'After five failed password attempts an account is locked temporarily, with a growing lockout duration. This is not a substitute for distributed rate limiting.'),
('Why AES-GCM?', 'It provides authenticated encryption: modified ciphertext or associated data fails tag verification rather than being silently decrypted.'),
('What is envelope encryption?', 'Each file has a random data-encryption key; that key is itself encrypted under a master key. The demo master key is local, not in a KMS.'),
('What is associated data?', 'The vault authenticates owner ID and filename as associated data, binding the ciphertext to those metadata values.'),
('Is Shamir sharing linked to the real vault key?', 'No. The UI splits a separately supplied demo secret. A true threshold master-key recovery process would need authenticated shares and key-management integration.'),
('What happens with too few shares?', 'They do not reveal the secret in the Shamir model. Because threshold metadata is not authenticated, this implementation can return incorrect bytes or garbled text rather than explicitly rejecting them.'),
('What does the audit hash chain guarantee?', 'It can reveal edits or missing entries relative to a trusted head. Without an external anchor, an attacker controlling the whole log can recompute the chain; it is not non-repudiation.'),
('What are the main next steps?', 'Run the deep-learning notebook, evaluate on real labelled telemetry, implement actual cloud enforcement and independent approvals, add secure OTP delivery, HTTPS and managed keys.'),
]
assert len(qa)==40
viva='# AegisCloud — viva questions and answers\n\nAnswers match the current prototype. Synthetic outcomes are not verified attacks.\n\n'
for i,(q,a) in enumerate(qa,1):viva+=f'**{i}. {q}**\n{a}\n\n'
viva+='''## Demonstration sequence

1. Sign in as `admin / Admin@Aegis2026`; enter the on-screen demo OTP.
2. In **Risk console**, compare normal and credential-stuffing presets; explain
   the numbers are simulated recommendations and the cap adjustment preserves the sum.
3. In **Synthetic replay**, replay generated sessions, then view the PSI comparison.
4. In **Crypto vault**, upload/download a test file and click **Tamper test**.
   Split a demo string 3-of-5: choose any three to recover it, then choose only
   two to show the result cannot be relied upon (it may be garbled, not an error).
5. In **Model lab**, distinguish the validation candidate table from the holdout
   metrics and show the exploratory threshold slider and manual retraining.
6. In **Audit**, verify the chain. Explain that feedback is stored but not yet
   incorporated into retraining.
'''
(ROOT/'docs/VIVA_QA.md').write_text(viva)
start=f'''# AegisCloud — start here

**AegisCloud** project, presentation, screenshots and social assets are in the
`aegiscloud/` folder. This is a **demo prototype**: its risk recommendations do
not enforce real cloud access.

## Quick start

```bash
cd aegiscloud
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/bootstrap.py
python run.py
python -m pytest tests/ -q
```

Visit `http://127.0.0.1:5000`. Demo login: `admin / Admin@Aegis2026`; the
one-time code appears on the screen. Never deploy these demo settings as-is.

## Results and honest limitations

The selected **{m['champion']}** achieved **{t['accuracy']:.4f}** accuracy,
**{t['f1']:.4f}** success F1 and **{t['roc_auc']:.4f}** ROC-AUC on synthetic
test data. Failure recall was **{failure:.4f}**. These are not attack-detection
rates. The LSTM/1D-CNN experiment is prepared but has not been trained.
Tests: **26 passed**.

## Main files

- `aegiscloud/docs/AegisCloud_Presentation.pptx` — presenter: Praveen Sudireddy
- `aegiscloud/docs/AegisCloud_Report_Additions.docx`
- `aegiscloud/docs/PROJECT_GUIDE.md` and `VIVA_QA.md`
- `aegiscloud/media/LinkedIn_Carousel.pdf` and `LinkedIn_Post.md`
- `AegisCloud_Comparison_and_Features.md` — separate comparison and resume advice
- `aegiscloud/README.md`, `screenshots/`, `notebooks/`

The earlier source dump contained an apparent application credential. If it is
still active, revoke/rotate it; never publish the original dump or local keys.
'''
(ROOT.parent/'START_HERE.md').write_text(start)
print('updated README, project guide, viva and start guide')
