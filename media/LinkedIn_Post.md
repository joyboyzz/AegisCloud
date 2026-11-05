# LinkedIn post — ready to copy

🚀 Excited to share **AegisCloud**, an educational security prototype I’ve been working on to explore how identity, encryption and data-driven risk scoring fit together.

The project brings together:

🔐 Password security, demo MFA and TOTP support  
🛡️ An AES-256-GCM encrypted vault with tamper checks  
🧠 Explainable session-risk scoring using an ML model + behavioral rules  
📊 Synthetic replay, model monitoring and a hash-linked audit trail

🧪 **What I measured:** On 1,350 held-out *synthetic* sessions, the selected MLP model achieved **83.04% accuracy**, **0.8829 success-class F1**, and **0.8701 ROC-AUC**. The project also has **26 passing automated tests**.

A key distinction: these are synthetic session-outcome metrics, **not real attack-detection rates**. The allow, step-up, review and block actions are recommendations—AegisCloud does not enforce access to cloud providers. The LSTM/CNN experiment is prepared, but its training has not yet been run.

The implementation builds on earlier academic project material. There’s plenty more to explore, including real-world telemetry, provider integration and stronger production controls.

🔗 Project: https://github.com/joyboyzz/AegisCloud

I’d love to hear your feedback and ideas! 👇

#CyberSecurity #CloudSecurity #MachineLearning #Python #InformationSecurity #PortfolioProject

---

## How to post

1. Copy the text above into a new LinkedIn post.
2. Select **Add a document** and upload `LinkedIn_Carousel.pdf` for the 6-page swipeable project showcase. Use `LinkedIn_Cover.png` if you prefer a single image post instead.
3. Preview on mobile, verify the GitHub link, and add any additional contributor credit that applies to your earlier work before publishing.

## Suggested accessible description

Six dark navy and cyan slides introduce AegisCloud, show its actual demo dashboard, risk console and encrypted vault, summarize synthetic holdout results, and explain the prototype’s limitations and next steps. The cover includes a decorative AI-generated shield.
