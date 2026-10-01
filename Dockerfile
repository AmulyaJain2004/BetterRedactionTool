# Build/run:
#   docker build -t redaction-api .
#   docker run -p 8000:8000 redaction-api
# Then open http://localhost:8000
#
# This is sized for "run it somewhere with real memory" (see README's
# hosting notes) -- the transformer model alone needs headroom well past a
# typical free-tier 512MB container.

FROM python:3.11-slim

WORKDIR /app

# System deps for torch/transformers wheels to install cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
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
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
