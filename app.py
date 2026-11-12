"""Gradio entry point -- the free Hugging Face Spaces deploy (SDK: gradio,
hardware: ZeroGPU). See deploy/hf-space/README.md.

Why Gradio and not the FastAPI app in api/: Hugging Face only hosts
Docker-SDK Spaces (which api/ would need) with a PRO subscription, while an
existing Gradio-SDK Space on ZeroGPU hardware (2 vCPU / 16 GB RAM) is free.
ZeroGPU in turn only works for apps served through Gradio's own launch().
redactor/ -- the actual detection/redaction logic -- is imported directly,
exactly as scripts/redact.py and api/ do; nothing about it is Gradio-specific.

Run locally:  pip install gradio  &&  python app.py
"""

# `spaces` MUST be imported before anything that loads torch (redactor/
# pulls it in via spaCy's transformer model). On ZeroGPU, importing it
# after CUDA initializes crashes at startup: "CUDA has been initialized
# before importing the `spaces` package" (seen on a real deploy).
try:  # Only present on Hugging Face Spaces; optional locally.
    import spaces
except ImportError:
    spaces = None

import csv
import html
import os
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import gradio as gr

from redactor import config
from redactor.docx_io import redact_docx
from redactor.engine import SPACY_MODEL_NAME, RedactionEngine

OUTPUT_ROOT = Path(tempfile.gettempdir()) / "redaction_outputs"

# Sample document offered in the UI. On the Space it lives in samples/; in
# the repo it sits at the project root -- use whichever exists.
APP_DIR = Path(__file__).resolve().parent
# Per-host: ~1-2 min on the HF Space; the Render free tier's CPU is much slower.
SAMPLE_HINT = os.environ.get(
    "REDACTOR_SAMPLE_HINT", "A real ~4,000-section IPO prospectus. Takes about 1–2 minutes."
)
SAMPLE_NAME = "Red Herring Prospectus.docx"
SAMPLE_PATH = next(
    (p for p in (APP_DIR / "samples" / SAMPLE_NAME, APP_DIR / SAMPLE_NAME) if p.exists()), None
)
OUTPUT_RETENTION_SECONDS = 24 * 3600

# Built once at startup: loading the transformer model is the slow part.
# Every upload reuses it; RedactionEngine.start_document() (called inside
# redact_docx) resets all per-document state between uploads.
print(f"Loading RedactionEngine ({SPACY_MODEL_NAME})...")
ENGINE = RedactionEngine()
print("RedactionEngine ready.")


if spaces is not None:
    @spaces.GPU
    def _zerogpu_placeholder():
        """ZeroGPU refuses to start a Space with no @spaces.GPU function
        reachable through Gradio's event system (seen on a real deploy:
        "No @spaces.GPU function detected during startup"). Wired to
        demo.load() below. Redaction itself is deliberately NOT decorated:
        it runs fine on CPU, and the free GPU quota is a few minutes a day."""
        return None


def _cleanup_old_outputs():
    """Removes redacted outputs older than OUTPUT_RETENTION_SECONDS."""
    if not OUTPUT_ROOT.exists():
        return
    cutoff = time.time() - OUTPUT_RETENTION_SECONDS
    for job_dir in OUTPUT_ROOT.iterdir():
        if job_dir.is_dir() and job_dir.stat().st_mtime < cutoff:
            shutil.rmtree(job_dir, ignore_errors=True)


def redact(file_path, progress=gr.Progress()):
    if not file_path:
        raise gr.Error("Upload a .docx file first.")
    if not str(file_path).lower().endswith(".docx"):
        raise gr.Error("Only .docx files are supported.")

    _cleanup_old_outputs()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(dir=OUTPUT_ROOT))
    stem = Path(file_path).stem
    output_docx = job_dir / f"{stem}_redacted.docx"
    output_csv = job_dir / f"{stem}_redaction_log.csv"

    progress(0, desc="Reading document...")
    started = time.time()

    def on_unit_done(done, total):
        progress(done / total if total else 0, desc=f"Redacting {done:,} / {total:,} sections")

    try:
        log = redact_docx(file_path, str(output_docx), engine=ENGINE, on_unit_done=on_unit_done)
    except Exception as e:  # corrupt / non-Word file, etc.
        print(f"Redaction failed: {e!r}")
        raise gr.Error("Couldn't redact this file. Is it a valid .docx document?")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "original_value", "fake_value"])
        writer.writerows(log)

    elapsed = time.time() - started
    counts = Counter(category for category, _, _ in log)
    unique = len({(c, o.strip().lower()) for c, o, _ in log})

    # One row per unique (category, original) so the preview stays readable.
    seen, rows = set(), []
    for category, original, fake in log:
        key = (category, original.strip().lower())
        if key not in seen:
            seen.add(key)
            rows.append([_pretty(category), original.strip(), fake])

    return (
        gr.File(value=str(output_docx), visible=True),
        gr.File(value=str(output_csv), visible=True),
        _summary_html(len(log), unique, elapsed, counts),
        rows,
    )


def _pretty(category: str) -> str:
    """PHYSICAL_ADDRESS -> Physical address."""
    return category.replace("_", " ").capitalize()


def _summary_html(total: int, unique: int, elapsed: float, counts: Counter) -> str:
    if total == 0:
        return '<div class="summary"><p class="muted">No personal data found in this document.</p></div>'
    chips = "".join(
        f'<span class="chip">{html.escape(_pretty(cat))}<b>{n}</b></span>' for cat, n in counts.most_common()
    )
    return f"""
<div class="summary">
  <div class="stats">
    <div><span class="num">{total:,}</span><span class="lbl">replacements</span></div>
    <div><span class="num">{unique:,}</span><span class="lbl">unique values</span></div>
    <div><span class="num">{elapsed:.1f}s</span><span class="lbl">processing</span></div>
  </div>
  <div class="chips">{chips}</div>
</div>"""


EMPTY_SUMMARY = """
<div class="summary empty">
  <p class="muted">Your redacted document and audit log will appear here.</p>
</div>"""


def _categories_table():
    return [
        [_pretty(name), cfg["kind"].replace("_", " "), cfg.get("fake_provider", "—")]
        for name, cfg in config.load_categories().items()
    ]


HEADER = """
<div class="hdr">
  <div class="mark" aria-hidden="true">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
         stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 4 6v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6l-8-4Z"/>
      <path d="M9 12.5 11.2 14.5 15.5 9.5"/></svg>
  </div>
  <div>
    <h1>BetterRedactionTool</h1>
    <p>Swap personal data in a Word document for consistent, realistic fake values.
       Formatting and tables are kept.</p>
  </div>
</div>
<div class="notice">Public demo. Files are deleted within 24 hours. Please don't upload confidential documents.</div>
"""

FOOTER = f"""
<div class="foot">Presidio + spaCy <code>{SPACY_MODEL_NAME}</code> · names, companies, emails, phones,
addresses, dates of birth, Aadhaar, DIN, SSN, cards, IPs</div>
"""

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.teal,
    secondary_hue=gr.themes.colors.yellow,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
    radius_size=gr.themes.sizes.radius_lg,
).set(
    body_background_fill="*neutral_50",
    body_background_fill_dark="*neutral_950",
    block_shadow="none",
    block_border_width="1px",
    block_label_background_fill="transparent",
    block_label_background_fill_dark="transparent",
    block_title_text_weight="600",
    button_primary_background_fill="*primary_600",
    button_primary_background_fill_hover="*primary_700",
    button_primary_background_fill_dark="*primary_500",
    button_primary_background_fill_hover_dark="*primary_400",
    button_primary_text_color="white",
    button_primary_text_color_dark="*neutral_950",
    loader_color="*secondary_400",
)

CSS = """
.gradio-container { max-width: 960px !important; margin: 0 auto !important; padding-top: 28px !important; }
footer { display: none !important; }

.hdr { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; }
.hdr h1 { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.015em; margin: 0; }
.hdr p { margin: 3px 0 0; color: var(--body-text-color-subdued); font-size: 0.95rem; }
.mark { flex: none; width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center;
        background: var(--primary-600); color: var(--secondary-300); }

.notice { border-left: 3px solid var(--secondary-400);
          background: color-mix(in srgb, var(--secondary-300) 18%, transparent);
          padding: 9px 14px; border-radius: 8px; font-size: 0.86rem; margin-bottom: 6px; }

.card { border: 1px solid var(--border-color-primary) !important; border-radius: 16px !important;
        background: var(--block-background-fill) !important; padding: 18px !important; gap: 14px !important; }
.step { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase;
        color: var(--primary-600); margin: 0; }
.dark .step { color: var(--primary-400); }

.step-wrap, .step-wrap > div { min-height: 0 !important; padding: 0 !important; flex: none !important; }
.upload-box { flex: 1 1 auto !important; }
.tbl, .tbl table, .tbl td, .tbl th, .tbl span { font-family: var(--font) !important; font-size: 0.86rem; }
.tbl th { font-weight: 600 !important; }
.go { flex: none !important; }
.sample-btn { flex: none !important; background: transparent !important; border: 1px dashed var(--secondary-400) !important;
              color: var(--body-text-color) !important; font-weight: 500 !important; box-shadow: none !important; }
.hint { margin: -6px 0 0; text-align: center; font-size: 0.75rem; color: var(--body-text-color-subdued); }
.sample-btn:hover { background: color-mix(in srgb, var(--secondary-300) 22%, transparent) !important; }
.summary-wrap { flex: 1 1 auto !important; }
.summary-wrap > div { height: 100%; }
.dl { flex: none !important; }

.summary { min-height: 180px; height: 100%; box-sizing: border-box; padding: 4px 2px; display: flex; flex-direction: column; justify-content: center; gap: 12px; }
.summary.empty { border: 1px dashed var(--border-color-primary); border-radius: 12px; align-items: center;
                 text-align: center; padding: 16px; }
.muted { color: var(--body-text-color-subdued); margin: 0; font-size: 0.9rem; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.stats div { display: flex; flex-direction: column; }
.num { font-size: 1.7rem; font-weight: 700; line-height: 1.1; color: var(--primary-700);
       font-variant-numeric: tabular-nums; }
.dark .num { color: var(--primary-300); }
.lbl { font-size: 0.75rem; color: var(--body-text-color-subdued); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { display: inline-flex; gap: 6px; align-items: center; font-size: 0.78rem; padding: 3px 10px;
        border-radius: 999px; background: color-mix(in srgb, var(--secondary-300) 30%, transparent); }
.chip b { color: var(--primary-700); }
.dark .chip b { color: var(--primary-300); }

.quiet { border: none !important; background: transparent !important; }
.foot { text-align: center; font-size: 0.78rem; color: var(--body-text-color-subdued); margin-top: 10px; }
.foot code { font-size: 0.75rem; }
"""

with gr.Blocks(title="BetterRedactionTool", delete_cache=(3600, 86400)) as demo:
    gr.HTML(HEADER)

    with gr.Row(equal_height=True):
        with gr.Column(scale=1, elem_classes="card"):
            gr.HTML('<p class="step">1 · Upload</p>', elem_classes="step-wrap")
            file_in = gr.File(label="Word document (.docx)", file_types=[".docx"], type="filepath", height=180, elem_classes="upload-box")
            run_btn = gr.Button("Redact document", variant="primary", elem_classes="go")
            if SAMPLE_PATH:
                sample_btn = gr.Button(
                    "Try the sample prospectus", variant="secondary", size="sm", elem_classes="sample-btn"
                )
                gr.HTML(f'<p class="hint">{SAMPLE_HINT}</p>', elem_classes="step-wrap")
        with gr.Column(scale=1, elem_classes="card"):
            gr.HTML('<p class="step">2 · Result</p>', elem_classes="step-wrap")
            summary_out = gr.HTML(EMPTY_SUMMARY, elem_classes="summary-wrap")
            # Hidden until there's something to download (see redact()).
            docx_out = gr.File(label="Redacted document", visible=False, elem_classes="dl")
            csv_out = gr.File(label="Audit log (CSV)", visible=False, elem_classes="dl")

    with gr.Accordion("Replacements", open=True, elem_classes="quiet"):
        table_out = gr.Dataframe(
            headers=["Category", "Original", "Replaced with"],
            datatype=["str", "str", "str"],
            interactive=False,
            wrap=True,
            max_height=420,
            column_widths=["20%", "34%", "46%"],
            elem_classes="tbl",
        )

    with gr.Accordion("What gets redacted", open=False, elem_classes="quiet"):
        gr.Markdown(
            "Configuration is shared by everyone using this Space, so it's read-only here. "
            "Run the project locally to add your own regex categories, table rules or exclude-list terms."
        )
        gr.Dataframe(value=_categories_table(), headers=["Category", "Detection", "Fake value"], interactive=False, elem_classes="tbl")

    gr.HTML(FOOTER)

    # concurrency_limit=1: one shared engine, one document at a time (others queue).
    run_btn.click(
        redact,
        inputs=file_in,
        outputs=[docx_out, csv_out, summary_out, table_out],
        concurrency_limit=1,
        concurrency_id="redact",
    )
    if SAMPLE_PATH:
        # Load the sample into the upload box (so it's visible what's being
        # redacted), then run the same redact() as a manual upload.
        sample_btn.click(lambda: str(SAMPLE_PATH), outputs=file_in).then(
            redact,
            inputs=file_in,
            outputs=[docx_out, csv_out, summary_out, table_out],
            concurrency_limit=1,
            concurrency_id="redact",
        )
    if spaces is not None:
        demo.load(_zerogpu_placeholder)


if __name__ == "__main__":
    # Gradio 6: theme/css are launch() arguments (passed to Blocks() they're ignored).
    demo.queue(max_size=20).launch(
        # Allow exactly the sample file, not its folder (locally that's the
        # project root, which would expose every file in the repo).
        theme=THEME, css=CSS, allowed_paths=[str(SAMPLE_PATH)] if SAMPLE_PATH else None
    )
