// Drives settings.html against /api/config/* (see api/routers/config.py).
// Every mutation re-fetches its own section from the server afterward
// rather than guessing the new state locally -- the server is the one
// source of truth for what's actually in the YAML/txt files.

const KINDS_EDITABLE_HERE = new Set(["presidio_builtin", "regex"]);

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = true));
    tab.classList.add("active");
    document.getElementById(tab.dataset.panel).hidden = false;
  });
});

init();

async function init() {
  await Promise.all([loadCategories(), loadColumns(), loadExcludeList()]);

  document.getElementById("category-form").addEventListener("submit", onAddCategory);
  document.getElementById("column-form").addEventListener("submit", onAddColumn);
  document.getElementById("exclude-form").addEventListener("submit", onAddExcludeTerm);
}

// ------------------------------------------------------------- categories

async function loadCategories() {
  const categories = await getJSON("/api/config/categories");
  const tbody = document.querySelector("#categories-table tbody");
  tbody.innerHTML = "";

  for (const c of categories) {
    const editable = KINDS_EDITABLE_HERE.has(c.kind);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(c.name)}</td>
      <td>${editable ? c.kind : `<span class="badge code-backed" title="Backed by a function in redactor/special_categories.py -- edit the YAML directly to remove it">${c.kind}</span>`}</td>
      <td>${c.score_threshold ?? "—"}</td>
      <td>${escapeHtml(c.fake_provider ?? "—")}</td>
      <td><button class="row-delete" ${editable ? "" : "disabled"} title="${editable ? "Remove this category" : "Code-backed category -- can't be removed here"}">&times;</button></td>
    `;
    if (editable) {
      row.querySelector(".row-delete").addEventListener("click", () => deleteCategory(c.name));
    }
    tbody.appendChild(row);
  }
}

async function onAddCategory(e) {
  e.preventDefault();
  const form = e.target;
  const payload = {
    name: form.name.value.trim().toUpperCase(),
    patterns: form.patterns.value.split("\n").map((p) => p.trim()).filter(Boolean),
    score_threshold: parseFloat(form.score_threshold.value),
    fake_provider: form.fake_provider.value.trim(),
  };
  try {
    await postJSON("/api/config/categories", payload);
    form.reset();
    form.closest("details").open = false;
    await loadCategories();
  } catch (err) {
    showError(err.message);
  }
}

async function deleteCategory(name) {
  try {
    await deleteJSON(`/api/config/categories/${encodeURIComponent(name)}`);
    await loadCategories();
  } catch (err) {
    showError(err.message);
  }
}

// --------------------------------------------------------- table layouts

async function loadColumns() {
  const rules = await getJSON("/api/config/structural-columns");
  const tbody = document.querySelector("#columns-table tbody");
  tbody.innerHTML = "";

  rules.forEach((rule, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(rule.column_header)}</td>
      <td>${escapeHtml(rule.category)}</td>
      <td>${rule.requires_any_of.map(escapeHtml).join(", ")}</td>
      <td><button class="row-delete" title="Remove this rule">&times;</button></td>
    `;
    row.querySelector(".row-delete").addEventListener("click", () => deleteColumn(index));
    tbody.appendChild(row);
  });
}

async function onAddColumn(e) {
  e.preventDefault();
  const form = e.target;
  const payload = {
    column_header: form.column_header.value.trim().toLowerCase(),
    category: form.category.value,
    requires_any_of: form.requires_any_of.value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
  };
  try {
    await postJSON("/api/config/structural-columns", payload);
    form.reset();
    form.closest("details").open = false;
    await loadColumns();
  } catch (err) {
    showError(err.message);
  }
}

async function deleteColumn(index) {
  try {
    await deleteJSON(`/api/config/structural-columns/${index}`);
    await loadColumns();
  } catch (err) {
    showError(err.message);
  }
}

// ------------------------------------------------------------ exclude list

async function loadExcludeList() {
  const terms = await getJSON("/api/config/exclude-list");
  const list = document.getElementById("exclude-list");
  list.innerHTML = "";

  for (const term of terms) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escapeHtml(term)}</span><button title="Remove">&times;</button>`;
    li.querySelector("button").addEventListener("click", () => deleteExcludeTerm(term));
    list.appendChild(li);
  }
}

async function onAddExcludeTerm(e) {
  e.preventDefault();
  const form = e.target;
  try {
    await postJSON("/api/config/exclude-list", { term: form.term.value.trim() });
    form.reset();
    await loadExcludeList();
  } catch (err) {
    showError(err.message);
  }
}

async function deleteExcludeTerm(term) {
  try {
    await deleteJSON(`/api/config/exclude-list/${encodeURIComponent(term)}`);
    await loadExcludeList();
  } catch (err) {
    showError(err.message);
  }
}

// ------------------------------------------------------------------ utils

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

async function deleteJSON(url) {
  const res = await fetch(url, { method: "DELETE" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

function showError(message) {
  const box = document.getElementById("settings-error");
  box.textContent = message;
  box.hidden = false;
  setTimeout(() => (box.hidden = true), 4000);
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
