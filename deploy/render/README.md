# Render deploy (free tier)

The root `Dockerfile` builds the same Gradio UI as the Hugging Face Space
(`app.py`), sized for Render's free web service (512 MB RAM). An existing
Render **Docker** web service connected to this repo picks it up on the next
push to `main`. To create one from scratch, use `render.yaml` (New > Blueprint)
or New > Web Service > this repo > Runtime: Docker > Instance: Free.

## Why a different model than the HF Space

| Model | Idle RAM | Peak RAM (full sample prospectus) | Fits 512 MB? |
|---|---|---|---|
| `en_core_web_trf` (HF Space) | ~2 GB with torch | — | No (OOM-killed on an earlier Render deploy) |
| `en_core_web_md` | ~430 MB | ~660 MB | No |
| **`en_core_web_sm`** (Render) | **~220 MB** | **~450 MB** | **Yes** |

Measured locally on a clean install of `deploy/render/requirements.txt`. The
model is chosen with `REDACTOR_SPACY_MODEL` (see `redactor/engine.py`), set in
the Dockerfile; nothing else differs.

## Accuracy tradeoff (`scripts/evaluate.py`, this repo's ground truth)

| | trf (HF Space) | sm (Render) |
|---|---|---|
| PERSON precision / recall | 0.72 / 0.95 | 0.32 / 0.81 |
| ORGANIZATION precision / recall | 0.69 / 0.89 | 0.31 / 0.80 |
| Email / phone / DIN / address | ~1.00 | ~0.96–1.00 |
| Overall precision / recall | 0.75 / 0.93 | 0.37 / 0.84 |

The regex-, checksum- and table-based categories are barely affected. Name and
company detection is noticeably weaker: the small model tags many capitalized
terms ("Offer", "Banker") as names/companies, so it over-redacts. For the best
results use the HF Space; Render free is a lightweight mirror.

## Free-tier behavior to expect

- The instance sleeps after ~15 min idle; the first visit after that takes
  about a minute to wake up.
- The CPU share is small, so the sample prospectus takes several minutes
  (the UI's hint says so). Small documents finish in seconds.
- Uploaded/redacted files live in the container's temp directory and vanish
  on restart/sleep (and are deleted after 24 hours anyway).
