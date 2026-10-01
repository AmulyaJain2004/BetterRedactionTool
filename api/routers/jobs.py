"""HTTP endpoints for submitting a redaction job and checking on it.

    POST /api/jobs             upload a .docx, get back a job_id
    GET  /api/jobs/{id}        poll status + progress (for the progress bar)
    GET  /api/jobs/{id}/download   the redacted .docx, once status == done
    GET  /api/jobs/{id}/log        the (category, original, fake) CSV audit trail

The actual redaction work happens on a background thread (see
redaction_worker.py) so a big document doesn't block the server from
answering other requests, including status polls for this same job.
"""

import threading

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from api.job_store import JOB_STORE
from api.redaction_worker import run_redaction_job
from api.schemas import JobCreatedResponse, JobState, JobStatusResponse
from api.settings import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobCreatedResponse)
async def create_job(request: Request, file: UploadFile):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Only .docx files are supported.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    job = JOB_STORE.create()
    job.input_path.write_bytes(contents)

    # engine is loaded once at startup (see main.py's lifespan) -- reused
    # across every job, never rebuilt per-request.
    engine = request.app.state.engine
    threading.Thread(target=run_redaction_job, args=(job, engine), daemon=True).start()

    return JobCreatedResponse(job_id=job.job_id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = _get_job_or_404(job_id)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        units_done=job.units_done,
        units_total=job.units_total,
        progress_percent=job.progress_percent,
        estimated_seconds_remaining=job.estimated_seconds_remaining,
        redactions_made=job.redactions_made,
        error=job.error,
    )


@router.get("/{job_id}/download")
def download_result(job_id: str):
    job = _get_job_or_404(job_id)
    if job.status != JobState.done:
        raise HTTPException(409, f"Job is '{job.status.value}', not finished yet.")
    return FileResponse(
        job.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="redacted.docx",
    )


@router.get("/{job_id}/log")
def download_log(job_id: str):
    job = _get_job_or_404(job_id)
    if job.status != JobState.done:
        raise HTTPException(409, f"Job is '{job.status.value}', not finished yet.")
    return FileResponse(job.log_path, media_type="text/csv", filename="redaction_log.csv")


def _get_job_or_404(job_id: str):
    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(404, "No job with that id.")
    return job
