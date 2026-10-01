"""In-memory tracking of redaction jobs.

Deliberately simple for a demo: a dict guarded by a lock, not a database
or a Redis-backed queue. That means job state is lost on restart and
doesn't work across multiple server processes/workers -- fine for trying
this out or running behind a single instance, not for a multi-replica
production deployment (swap this module for something backed by
Redis/Postgres if that's ever needed; nothing else in the API should have
to change, since routers only talk to the JOB_STORE singleton below).
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from api.schemas import JobState
from api.settings import JOBS_DIR


@dataclass
class Job:
    job_id: str
    status: JobState = JobState.queued
    units_done: int = 0
    units_total: int = 0
    redactions_made: int | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    # Set on the first progress update, i.e. when work actually starts --
    # deliberately not created_at, so time spent queued (however briefly,
    # today essentially zero since jobs start immediately) doesn't inflate
    # the "how fast are we actually going" estimate below.
    started_at: float | None = None

    @property
    def dir(self) -> Path:
        return JOBS_DIR / self.job_id

    @property
    def input_path(self) -> Path:
        return self.dir / "input.docx"

    @property
    def output_path(self) -> Path:
        return self.dir / "redacted.docx"

    @property
    def log_path(self) -> Path:
        return self.dir / "redaction_log.csv"

    @property
    def progress_percent(self) -> float | None:
        if self.units_total == 0:
            return None
        return round(100 * self.units_done / self.units_total, 1)

    @property
    def estimated_seconds_remaining(self) -> float | None:
        """Linear extrapolation from the observed rate so far: elapsed time
        per unit done, times units left. Simple on purpose -- this is an
        estimate for a progress bar, not a scheduling guarantee, and a
        document's paragraphs/cells are similar enough in cost that a
        fancier model isn't worth the complexity."""
        if not self.started_at or self.units_done == 0 or self.units_total == 0:
            return None
        elapsed = time.time() - self.started_at
        seconds_per_unit = elapsed / self.units_done
        return round(seconds_per_unit * (self.units_total - self.units_done), 1)


class JobStore:
    """Thread-safe create/read/update for Job records.

    The redaction worker runs in a background thread (see
    redaction_worker.py) and calls update_progress()/mark_done()/
    mark_failed() from that thread, while API request handlers read job
    state from the request thread at the same time -- the lock is what
    makes that safe.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(job_id=uuid.uuid4().hex)
        job.dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_progress(self, job_id: str, units_done: int, units_total: int):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JobState.running
            if job.started_at is None:
                job.started_at = time.time()
            job.units_done = units_done
            job.units_total = units_total

    def mark_done(self, job_id: str, redactions_made: int):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JobState.done
            job.redactions_made = redactions_made
            job.units_done = job.units_total  # snap the bar to 100%

    def mark_failed(self, job_id: str, error: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JobState.failed
            job.error = error


# One store for the whole process -- imported by routers and the worker.
JOB_STORE = JobStore()
