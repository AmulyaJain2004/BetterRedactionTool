"""FastAPI app entry point.

Run locally with:
    uvicorn api.main:app --reload

Then open http://127.0.0.1:8000 for the try-it-out page, or use the API
directly (see routers/jobs.py) -- interactive docs are auto-generated at
/docs.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from redactor.engine import RedactionEngine

from api.routers import config, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading RedactionEngine builds the spaCy/transformer pipeline, which
    # takes real time -- doing this once here (not per-request, not per-job)
    # is what makes job submission fast even though the model itself is slow.
    print("Loading RedactionEngine (this downloads/loads the spaCy model on first run)...")
    app.state.engine = RedactionEngine()
    print("RedactionEngine ready.")
    yield
    # Nothing to tear down: the in-memory job store and engine just go away
    # with the process, which is fine for this demo (see job_store.py).


app = FastAPI(title="BetterRedactionTool API", lifespan=lifespan)

# Permissive by default so a separately-hosted frontend (e.g. this same
# static page served from a different origin) can call the API. Tighten
# to your actual frontend's origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(config.router)

# The try-it-out page (upload form + progress bar). Mounted last so it
# doesn't shadow the /api routes above. Resolved relative to this file,
# not the process's working directory, so it works the same whether
# uvicorn is launched from the repo root or from inside a container.
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
