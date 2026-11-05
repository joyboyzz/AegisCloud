# AegisCloud — project guide

AegisCloud is an educational prototype combining identity controls, authenticated
file encryption, explainable synthetic session-risk scoring and an audit console.
It does **not** enforce cloud-provider access or detect validated real attacks.

## Verified experiment

- 9,000 generated sessions; chronological 6,300 / 1,350 / 1,350 split.
- Four candidates compared on validation at threshold 0.50; training-only
  baseline and category fitting; selected **MLPClassifier**.
- Validation-tuned threshold **0.44**; synthetic test accuracy
  **0.8304**, success F1 **0.8829**, success recall
  **0.9320**, failure recall **0.6085**, ROC-AUC **0.8701**.
- Confusion [TN, FP; FN, TP]: [258, 166; 63, 863].
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
