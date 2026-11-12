"""Runs one redaction job to completion, updating JOB_STORE as it goes.

This is the only place the API touches redactor/ -- everything else in
here is HTTP/job plumbing. Runs on a background thread (see routers/jobs.py),
never on the FastAPI event loop, because redaction is CPU-bound and would
otherwise freeze every other request the server is handling.
"""

import csv
import threading
import traceback

from redactor.docx_io import redact_docx
from redactor.engine import RedactionEngine

from api.job_store import JOB_STORE, Job


# One shared RedactionEngine serves every job, and it is not thread-safe:
# it holds per-document state (glossary terms, known names, the fake-value
# cache) and Presidio's recognizer registry. Two uploads at once used to
# run on two threads against that same object and corrupt each other's
# output. Jobs now run one at a time; a waiting job simply stays "queued"
# (the upload page shows that). On CPU-only hosts this costs almost
# nothing anyway -- two transformer passes in parallel just split the cores.
_ENGINE_LOCK = threading.Lock()


def run_redaction_job(job: Job, engine: RedactionEngine):
    with _ENGINE_LOCK:
        _run_locked(job, engine)


def _run_locked(job: Job, engine: RedactionEngine):
    try:
        def on_unit_done(units_done: int, units_total: int):
            JOB_STORE.update_progress(job.job_id, units_done, units_total)

        replacement_log = redact_docx(
            str(job.input_path),
            str(job.output_path),
            engine=engine,
            on_unit_done=on_unit_done,
        )

        with open(job.log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["category", "original_value", "fake_value"])
            writer.writerows(replacement_log)

        JOB_STORE.mark_done(job.job_id, redactions_made=len(replacement_log))

    except Exception:
        # traceback.format_exc(), not str(e): a corrupt/unexpected .docx is
        # exactly the kind of thing worth seeing the real stack trace for
        # in server logs, even though only a short message goes to the client.
        print(f"Job {job.job_id} failed:\n{traceback.format_exc()}")
        JOB_STORE.mark_failed(job.job_id, error="Redaction failed -- see server logs for details.")
