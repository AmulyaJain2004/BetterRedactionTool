# FastAPI web app (api/) with the full transformer model, for any Docker host
# with a few GB of RAM. (HF Docker Spaces would also work but need PRO; the
# free HF Space uses app.py instead, and Render free uses the root Dockerfile.)

#   docker build -f deploy/docker/Dockerfile -t redaction-api .   (from the repo root)
#   docker run -p 7860:7860 redaction-api
# Then open http://localhost:7860
#
# Memory: en_core_web_trf is a transformer -- it needs a few GB of RAM
# (it OOM'd on a 512MB Render free tier). HF's free "cpu-basic" Space
# (2 vCPU / 16 GB) has plenty of headroom; it's just slow per document.

FROM python:3.11-slim

# Some transitive deps occasionally build from source on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces runs the container as uid 1000; create that user up front so
# every path the app writes to is owned by it.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
# The default torch wheel bundles the full CUDA runtime (~20 nvidia-*
# packages) even on a CPU-only box. The CPU index skips all of that.
# requirements.txt's torch==2.14.0 is then already satisfied by 2.14.0+cpu.
RUN pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
# (en_core_web_trf is installed from requirements.txt's pinned wheel URL,
# so the model is baked into the image -- no download at container start.)

COPY --chown=user redactor/ redactor/
COPY --chown=user config/ config/
COPY --chown=user api/ api/

# Public deployment defaults: config is global, so visitors can view but
# not change it (see api/settings.py). Override with -e to enable edits.
ENV JOBS_DIR=/app/api_jobs \
    ALLOW_CONFIG_EDITS=false \
    PUBLIC_NOTICE="Public demo: files are processed on this server and deleted after 24 hours. Don't upload confidential documents." \
    PORT=7860
RUN mkdir -p /app/api_jobs && chown -R user /app
USER user

EXPOSE 7860
# Shell form so $PORT (set by some hosts) is honored; defaults to 7860 (HF).
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}
