# Render (free tier, 512 MB RAM) image: the same Gradio UI as the Hugging
# Face Space (app.py), with spaCy's small en_core_web_sm model instead of
# the transformer -- see deploy/render/README.md for why and the measured
# memory/accuracy tradeoff. Render builds this file by default.
#
# Local test:
#   docker build -t redaction-render .
#   docker run -p 10000:10000 -m 512m redaction-render
#   open http://localhost:10000

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd -m -u 1000 app
WORKDIR /app

COPY deploy/render/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY --chown=app redactor/ redactor/
COPY --chown=app config/ config/
COPY --chown=app app.py LICENSE ./
COPY --chown=app ["Red Herring Prospectus.docx", "samples/"]

# REDACTOR_SPACY_MODEL: the one model that fits in 512 MB (see engine.py).
# GRADIO_ANALYTICS_ENABLED: no phone-home from a server deployment.
# Render injects $PORT (10000 by default); Gradio must bind 0.0.0.0 to it.
ENV REDACTOR_SPACY_MODEL=en_core_web_sm \
    REDACTOR_SAMPLE_HINT="A real ~4,000-section IPO prospectus. Takes several minutes on this free server." \
    GRADIO_ANALYTICS_ENABLED=False \
    GRADIO_SERVER_NAME=0.0.0.0 \
    PORT=10000
USER app

EXPOSE 10000
CMD GRADIO_SERVER_PORT=${PORT} python app.py
