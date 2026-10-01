// Upload -> poll -> progress bar -> download, against the API in routers/jobs.py.
// No build step, no framework: this is a demo page, kept deliberately simple.

const POLL_INTERVAL_MS = 1000;

const views = {
  upload: document.getElementById("upload-view"),
  progress: document.getElementById("progress-view"),
  done: document.getElementById("done-view"),
  error: document.getElementById("error-view"),
};

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileNameLabel = document.getElementById("file-name");
const progressFill = document.getElementById("progress-fill");
const statusLabel = document.getElementById("status-label");
const etaLabel = document.getElementById("eta-label");
const resultSummary = document.getElementById("result-summary");

function showView(name) {
  for (const [key, el] of Object.entries(views)) {
    el.hidden = key !== name;
  }
}

// Click-to-open is handled natively by <label for="file-input">; only
// drag-and-drop needs JS.
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

document.getElementById("reset-button").addEventListener("click", resetToUpload);
document.getElementById("error-reset-button").addEventListener("click", resetToUpload);

function resetToUpload() {
  fileInput.value = "";
  progressFill.style.width = "0%";
  showView("upload");
}

async function uploadFile(file) {
  fileNameLabel.textContent = file.name;
  statusLabel.textContent = "Uploading…";
  etaLabel.textContent = "";
  progressFill.style.width = "0%";
  showView("progress");

  const formData = new FormData();
  formData.append("file", file);

  let jobId;
  try {
    const res = await fetch("/api/jobs", { method: "POST", body: formData });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "Upload failed.");
    jobId = body.job_id;
  } catch (err) {
    showError(err.message);
    return;
  }

  pollStatus(jobId);
}

function pollStatus(jobId) {
  const interval = setInterval(async () => {
    let status;
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error("Lost track of this job.");
      status = await res.json();
    } catch (err) {
      clearInterval(interval);
      showError(err.message);
      return;
    }

    renderProgress(status);

    if (status.status === "done") {
      clearInterval(interval);
      showDone(status, jobId);
    } else if (status.status === "failed") {
      clearInterval(interval);
      showError(status.error || "Redaction failed.");
    }
  }, POLL_INTERVAL_MS);
}

function renderProgress(status) {
  const pct = status.progress_percent ?? 0;
  progressFill.style.width = `${pct}%`;
  statusLabel.textContent = `${status.status} — ${status.units_done}/${status.units_total} sections`;
  etaLabel.textContent = formatEta(status.estimated_seconds_remaining);
}

function showDone(status, jobId) {
  progressFill.style.width = "100%";
  resultSummary.textContent = `${status.redactions_made} value${status.redactions_made === 1 ? "" : "s"} redacted.`;
  document.getElementById("download-docx").href = `/api/jobs/${jobId}/download`;
  document.getElementById("download-log").href = `/api/jobs/${jobId}/log`;
  showView("done");
}

function showError(message) {
  document.getElementById("error-message").textContent = message;
  showView("error");
}

/** Turns a number of seconds into "~2m 30s left" / "~45s left", or "" if unknown yet. */
function formatEta(secondsRemaining) {
  if (secondsRemaining == null) return "estimating time remaining…";
  const total = Math.round(secondsRemaining);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  const text = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
  return `~${text} left`;
}
