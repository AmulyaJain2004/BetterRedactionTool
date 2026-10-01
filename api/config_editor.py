"""Reads and writes the same two files a developer would otherwise hand-edit:
config/pii_categories.yaml and config/org_exclude_list.txt. This is what
lets the settings page in the frontend add a regex category, a
structural-table-column rule, or an exclude-list entry WITHOUT anyone
touching YAML or Python -- the whole point of this module is to be the one
place that knows how to safely rewrite those files.

Uses ruamel.yaml (round-trip mode), not plain PyYAML, specifically so the
explanatory comments already in pii_categories.yaml survive being edited
through the API -- plain PyYAML's dump() would silently delete every
comment in the file on the first save.
"""

from pathlib import Path

from ruamel.yaml import YAML

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CATEGORIES_FILE = CONFIG_DIR / "pii_categories.yaml"
EXCLUDE_LIST_FILE = CONFIG_DIR / "org_exclude_list.txt"

def _make_yaml() -> YAML:
    # A fresh instance per load/dump, deliberately -- ruamel.yaml's YAML
    # object accumulates internal composer/anchor state across reuse, and
    # sharing one instance across this module's many load() and dump()
    # calls (one per HTTP request, interleaved) intermittently corrupted
    # that state (`AttributeError: 'NoneType' object has no attribute
    # 'anchor'` from ruamel's composer). Instances are cheap; this is not
    # a hot path.
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


# Only these two category "kind"s can be created through the API without
# writing code: both are pure data (a regex, or a column-header rule) with
# no logic of their own. ORGANIZATION/PHYSICAL_ADDRESS/DATE_OF_BIRTH/etc.
# (kind: spacy_org / structural / context_regex) are backed by specific
# functions in redactor/special_categories.py, so adding a *new* one of
# those genuinely does need a code change -- seeREADME's "Customizing"
# section for why that line is drawn there.
API_EDITABLE_KINDS = {"presidio_builtin", "regex"}


def _load_yaml() -> dict:
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        return _make_yaml().load(f)


def _save_yaml(data: dict):
    # newline="\n": without it, Python's text-mode write translates to the
    # OS line ending (CRLF on Windows), which would otherwise turn every
    # settings-UI edit into a full-file diff of line-ending churn.
    with open(CATEGORIES_FILE, "w", encoding="utf-8", newline="\n") as f:
        _make_yaml().dump(data, f)


# ---------------------------------------------------------------- categories

def list_categories() -> list[dict]:
    data = _load_yaml()
    return [dict(c) for c in data["categories"]]


def add_regex_category(name: str, patterns: list[str], score_threshold: float, fake_provider: str):
    data = _load_yaml()
    if any(c["name"] == name for c in data["categories"]):
        raise ValueError(f"A category named {name!r} already exists.")
    data["categories"].append({
        "name": name,
        "kind": "regex",
        "score_threshold": score_threshold,
        "patterns": list(patterns),
        "fake_provider": fake_provider,
    })
    _save_yaml(data)


def remove_category(name: str):
    data = _load_yaml()
    category = next((c for c in data["categories"] if c["name"] == name), None)
    if category is None:
        raise ValueError(f"No category named {name!r}.")
    if category["kind"] not in API_EDITABLE_KINDS:
        raise ValueError(
            f"{name!r} is a {category['kind']!r} category, backed by code in "
            "redactor/special_categories.py -- remove its block from "
            "pii_categories.yaml directly if you really want to disable it."
        )
    data["categories"].remove(category)
    _save_yaml(data)


# ------------------------------------------------------ structural columns

def list_structural_columns() -> list[dict]:
    data = _load_yaml()
    return [dict(rule) for rule in data.get("structural_table_columns", [])]


def add_structural_column(column_header: str, category: str, requires_any_of: list[str]):
    data = _load_yaml()
    data.setdefault("structural_table_columns", [])
    data["structural_table_columns"].append({
        "column_header": column_header.strip().lower(),
        "category": category,
        "requires_any_of": [r.strip().lower() for r in requires_any_of],
    })
    _save_yaml(data)


def remove_structural_column(index: int):
    data = _load_yaml()
    rules = data.get("structural_table_columns", [])
    if not (0 <= index < len(rules)):
        raise ValueError(f"No structural column rule at index {index}.")
    del rules[index]
    _save_yaml(data)


# -------------------------------------------------------------- deny-list
# config/org_exclude_list.txt is plain text (one term per line, '#'
# comments allowed) -- no YAML structure to preserve, so this is simpler
# than the functions above.

def list_exclude_terms() -> list[str]:
    lines = EXCLUDE_LIST_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def add_exclude_term(term: str):
    term = term.strip()
    if not term:
        raise ValueError("Term can't be empty.")
    if term.lower() in {t.lower() for t in list_exclude_terms()}:
        raise ValueError(f"{term!r} is already on the list.")
    with open(EXCLUDE_LIST_FILE, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"{term}\n")


def remove_exclude_term(term: str):
    lines = EXCLUDE_LIST_FILE.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip().lower() != term.strip().lower()]
    if len(kept) == len(lines):
        raise ValueError(f"{term!r} isn't on the list.")
    EXCLUDE_LIST_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
