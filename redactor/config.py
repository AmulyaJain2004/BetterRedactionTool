"""Loads config/pii_categories.yaml and config/org_exclude_list.txt.

This is the only place that knows the config file's shape, so the rest of
the codebase just works with plain Python objects.
"""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATEGORIES_FILE = PROJECT_ROOT / "config" / "pii_categories.yaml"


def load_categories() -> dict:
    """Returns {category_name: {kind, score_threshold, fake_provider, patterns?}}."""
    raw = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return {category["name"]: category for category in raw["categories"]}


def load_structural_table_columns() -> list[dict]:
    """Returns the header-column -> category rules used for personnel tables."""
    raw = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return raw.get("structural_table_columns", [])


def load_org_exclude_terms() -> set[str]:
    """Regulator/statute names that are never treated as a company name."""
    exclude_file = PROJECT_ROOT / "config" / "org_exclude_list.txt"
    lines = exclude_file.read_text(encoding="utf-8").splitlines()
    return {
        line.strip().lower()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }
