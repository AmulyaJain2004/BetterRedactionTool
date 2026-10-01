"""Pydantic request/response models for the API -- the wire format, kept
separate from job_store.py's internal Job object so the two can evolve
independently (e.g. Job can hold a file path, JobStatusResponse never should)."""

from enum import Enum

from pydantic import BaseModel


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobState


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobState
    units_done: int
    units_total: int
    # 0-100, or null while units_total isn't known yet (very first moments of a run)
    progress_percent: float | None
    estimated_seconds_remaining: float | None = None
    redactions_made: int | None = None
    error: str | None = None


# --- Settings / config-editor payloads (api/config_editor.py, api/routers/config.py) ---

class CategoryOut(BaseModel):
    name: str
    kind: str
    score_threshold: float | None = None
    fake_provider: str | None = None
    patterns: list[str] | None = None


class NewRegexCategory(BaseModel):
    name: str
    patterns: list[str]
    score_threshold: float = 0.7
    fake_provider: str = "word"


class StructuralColumnRule(BaseModel):
    column_header: str
    category: str
    requires_any_of: list[str]


class ExcludeTerm(BaseModel):
    term: str
