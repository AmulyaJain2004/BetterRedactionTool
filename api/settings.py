"""All the small, environment-tunable knobs the API needs, in one place.

Nothing here is secret or deployment-specific enough to need a .env file
for a demo -- override via real environment variables if you deploy this
(e.g. JOBS_DIR on a host with a different writable path).
"""

import os
from pathlib import Path

# Where uploaded input files and their redacted output live, one
# sub-folder per job (see job_store.py). Kept outside the repo's own
# source tree so it's obvious this is runtime data, not code.
JOBS_DIR = Path(os.environ.get("JOBS_DIR", Path(__file__).resolve().parent.parent / "api_jobs"))

# Reject uploads above this size before we even try to parse them --
# redaction time scales with document size, and this stops someone from
# accidentally (or not) handing the demo a 500MB file.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))  # 25 MB

# How long a finished (or failed) job's files are kept before cleanup()
# removes them. A demo doesn't need indefinite storage.
JOB_RETENTION_HOURS = int(os.environ.get("JOB_RETENTION_HOURS", 24))
