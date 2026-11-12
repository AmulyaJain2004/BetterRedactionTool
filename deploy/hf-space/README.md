---
title: BetterRedactionTool
emoji: 🛡️
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: Redact PII from .docx files with consistent fake values
---

# BetterRedactionTool

Upload a `.docx` and get back a redacted copy where every piece of PII is swapped for a
**consistent, realistic fake value**: the same real name always becomes the same fake name
throughout the document. You also get a CSV audit log of every replacement.

- **Detects:** person names, company names, emails, phone numbers, personal addresses,
  dates of birth, Aadhaar numbers (Verhoeff-checksum validated), DIN numbers, SSNs,
  credit cards, IP addresses.
- **How:** Microsoft Presidio + spaCy `en_core_web_trf` (transformer NER), plus
  purpose-built rules for personnel/KYC tables, addresses and dates of birth.
- **Private by design:** runs entirely inside this Space, and no third-party APIs are called.
  Files are deleted within 24 hours. This is still a public demo, so don't upload
  confidential documents.

Configuration is read-only here (it's shared by every visitor). Run the project locally to
customize categories, table rules and the exclude list through its settings UI.

## Deploying (maintainers)

This Space is a **Gradio-SDK Space on ZeroGPU hardware**. That's the free option for a personal
account (Docker Spaces need PRO). Space root = `app.py`, `redactor/`, `config/`, `LICENSE`, plus
this folder's `README.md` and `requirements.txt`. Redaction runs on CPU. `app.py` has one
`@spaces.GPU` placeholder only because ZeroGPU refuses to start without one.
