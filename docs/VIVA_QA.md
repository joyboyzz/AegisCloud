# AegisCloud — viva questions and answers

Answers match the current prototype. Synthetic outcomes are not verified attacks.

**1. What is AegisCloud?**
A Flask-based educational prototype combining multi-factor identity, an AES-GCM vault, synthetic session scoring and an audit console. It does not enforce real cloud access.

**2. What is the project’s main aim?**
Show how multiple security components can be composed and how a simulated policy recommendation can be explained.

**3. Is this zero-trust enforcement?**
No. It demonstrates zero-trust-inspired scoring, but it does not intercept provider requests or enforce its suggested outcomes.

**4. What are the main components?**
The system combines identity and sessions, a local AES-GCM vault, synthetic session scoring, model evaluation, monitoring and an audit console.

**5. What is the most important scope boundary?**
The risk engine provides simulated recommendations. It does not enforce actual access to AWS, Azure or GCP.

**6. Are the model results real attack-detection results?**
No. The labels and sessions are synthetic, and the model predicts session success or failure, not verified attacks.

**7. What does positive class 1 represent?**
A synthetic successful session. Class 0 is failure. Success recall is not attack-detection recall.

**8. What data is used?**
A generated corpus of 9,000 sessions, plus a separate synthetic 2,500-row replay corpus. No real cloud telemetry is used.

**9. How is the data split?**
Chronologically: 6,300 training, 1,350 validation and 1,350 later test rows.

**10. What prevents preprocessing leakage?**
User-duration baselines and category vocabulary are fitted only on the training rows. Unknown users use global training statistics; scaling is fitted within the candidate training pipeline.

**11. What features are used?**
Nine numeric fields, eight derived fields and one-hot categorical values: 37 columns in this version.

**12. Which candidate models are compared?**
Logistic regression, random forest, histogram gradient boosting and a multilayer perceptron. They are compared on validation data.

**13. Which model was selected?**
MLPClassifier had the highest validation success F1 at threshold 0.50 in the saved experiment; threshold tuning happens afterwards.

**14. How was the probability threshold chosen?**
The chosen threshold is 0.44; validation success-class F1 was maximized subject to success-class recall of at least 0.80.

**15. What are the holdout results?**
Accuracy 0.8304, success F1 0.8829, success recall 0.9320, failure recall 0.6085, ROC-AUC 0.8701. These are synthetic-data results.

**16. What is the confusion matrix?**
With success as the positive class: TN=258, FP=166, FN=63, TP=863. Failure recall is TN/(TN+FP).

**17. What does ROC-AUC show?**
It summarizes how well the model ranks synthetic success outcomes above failures across thresholds; it does not show real-world attack detection.

**18. Does a Brier score prove calibration?**
No. The test Brier score is 0.1292, a mean squared probability error. Calibration needs a reliability plot and independent evaluation.

**19. Did an LSTM or CNN beat the baselines?**
Unknown. The Colab notebook is prepared, but TensorFlow training and comparison have not been run.

**20. Why keep the Colab notebook?**
It provides a proposed reproducible LSTM/1D-CNN experiment using sequences of up to five per-user sessions, with train-only preprocessing.

**21. What is the risk-score formula?**
The model contributes 0.42 × 100 × (1 − P(success)); deterministic rule points and a baseline are added, then the result is bounded to 0–100.

**22. Do the displayed contributions sum exactly?**
Yes, after rounding: when the raw total exceeds the allowed range, an explicit score-bound adjustment is included.

**23. Is this SHAP?**
No. The additive fusion has explicit point contributions; the separate per-feature leave-one-out model probes are not exact Shapley values.

**24. How do thresholds adapt?**
A bounded offset is computed from historical risk scores for the scored subject. It is a heuristic and is not empirically validated for fairness or safety.

**25. What do step-up and block actually do?**
They are demo recommendations for simulated sessions. They are not wired to provider IAM enforcement.

**26. Is four-eyes approval enforced?**
No. A review queue exists, but the current implementation does not enforce independent requester/approver separation.

**27. What is PSI?**
Population Stability Index measures feature-distribution differences between the synthetic training CSV and replay CSV. It does not itself prove concept drift.

**28. Is retraining automatic?**
No. An operator triggers it; it currently trains again from the reference CSV and promotes a version.

**29. Is feedback used in retraining?**
No. The interface stores feedback and infers an outcome from the prediction, but the training job does not ingest it.

**30. How does MFA work in the demo?**
The analyst uses TOTP. Other demo accounts see a generated OTP in the UI. No email provider is integrated; this is not a production factor.

**31. What is TOTP?**
RFC 6238 derives a six-digit code from a secret and a 30-second time step; the verifier allows an adjacent-step window.

**32. How are passwords stored?**
With scrypt and a random per-user 16-byte salt. Password verification compares derived hashes.

**33. How is brute force handled?**
After five failed password attempts an account is locked temporarily, with a growing lockout duration. This is not a substitute for distributed rate limiting.

**34. Why AES-GCM?**
It provides authenticated encryption: modified ciphertext or associated data fails tag verification rather than being silently decrypted.

**35. What is envelope encryption?**
Each file has a random data-encryption key; that key is itself encrypted under a master key. The demo master key is local, not in a KMS.

**36. What is associated data?**
The vault authenticates owner ID and filename as associated data, binding the ciphertext to those metadata values.

**37. Is Shamir sharing linked to the real vault key?**
No. The UI splits a separately supplied demo secret. A true threshold master-key recovery process would need authenticated shares and key-management integration.

**38. What happens with too few shares?**
They do not reveal the secret in the Shamir model. Because threshold metadata is not authenticated, this implementation can return incorrect bytes or garbled text rather than explicitly rejecting them.

**39. What does the audit hash chain guarantee?**
It can reveal edits or missing entries relative to a trusted head. Without an external anchor, an attacker controlling the whole log can recompute the chain; it is not non-repudiation.

**40. What are the main next steps?**
Run the deep-learning notebook, evaluate on real labelled telemetry, implement actual cloud enforcement and independent approvals, add secure OTP delivery, HTTPS and managed keys.

## Demonstration sequence

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
