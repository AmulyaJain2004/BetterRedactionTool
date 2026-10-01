# Build/run:
#   docker build -t redaction-api .
#   docker run -p 8000:8000 redaction-api
# Then open http://localhost:8000
#
# This is sized for "run it somewhere with real memory" (see README's
# hosting notes) -- the transformer model alone needs headroom well past a
# typical free-tier 512MB container. The two fixes below (CPU-only torch,
# $PORT binding) remove unnecessary bloat and a real deploy bug, but don't
# change that underlying fact -- en_core_web_trf plus its dependencies
# still won't fit in 512MB. Confirmed by an actual Render free-tier deploy
# OOM-killing the process ("Out of memory (used over 512Mi)").

FROM python:3.11-slim

WORKDIR /app

# System deps for torch/transformers wheels to install cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch's default PyPI wheel bundles the full NVIDIA CUDA runtime
# (cublas, cudnn, the whole "cuda-toolkit" stack) even when nothing on
# the host has a GPU -- confirmed in an actual build log: ~20 nvidia-*
# packages pulled in for a CPU-only Render box. The CPU-only wheel index
# skips all of that, which both shrinks the image substantially and
# removes CUDA libraries that would otherwise sit loaded in memory unused.
RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY redactor/ redactor/
COPY config/ config/
COPY api/ api/

# Baked into the image at build time so the (slow, ~1GB) model download
# doesn't happen on every container start -- see redactor/engine.py's
# SPACY_MODEL_NAME.
RUN python -m spacy download en_core_web_trf

ENV JOBS_DIR=/app/api_jobs
RUN mkdir -p /app/api_jobs

EXPOSE 8000
# Shell form, not exec form with a hardcoded port: Render (and most PaaS
# hosts) assign a port dynamically via $PORT and expect the app to bind
# to it, not to a fixed 8000 -- the earlier deploy logged "No open ports
# detected" because of exactly this. Falls back to 8000 for plain
# `docker run` where $PORT isn't set.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
