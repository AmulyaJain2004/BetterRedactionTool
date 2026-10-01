"""Builds the hand-verified ground truth used by scripts/evaluate.py.

Methodology (documented in EVALUATION.md): the master entity lists in
ground_truth/known_entities.py were compiled by reading every director/
promoter/KMP table and every "Contact Person" field in the document by
hand, plus a keyword sweep (Limited/Bank/LLP/Trust/...) to catch company
mentions outside those tables. Every occurrence of a known name is then
found automatically across the *entire* document -- this gives exhaustive,
human-verified coverage without re-reading all ~3,800 paragraphs/cells by
eye. EMAIL_ADDRESS, PHONE_NUMBER, PHYSICAL_ADDRESS and DIRECTOR_ID_NUMBER
are syntactically distinctive enough that a precise regex/structural pass
*is* the exhaustive ground truth for them (spot-checked by hand).

Usage:
    python scripts/build_ground_truth.py "input.docx" ground_truth/ground_truth.jsonl
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from ground_truth.known_entities import KNOWN_ORGANIZATION_NAMES, KNOWN_PERSON_NAMES
from redactor.docx_io import _match_structural_columns
from scripts.extract_text import extract_units

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Real phone numbers in this document are always either "+<country code> ..."
# or immediately follow a Tel/Telephone/Phone/Mobile label -- unlike bare
# digit runs (DIN, CIN, PIN codes, SEBI registration numbers), which never
# have either of those markers. Matching only these two shapes avoids
# mistaking an unrelated ID number for a phone number.
PHONE_PATTERNS = [
    re.compile(r"\+\s?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{0,4}"),
    re.compile(r"(?:Tel(?:ephone)?|Phone|Mobile)\s*[:.]?\s*([\d][\d\s()-]{6,17}\d)"),
]


def find_known_entity_spans(text: str, category: str, known_names: list[str]):
    """Every non-overlapping occurrence of any name in `known_names`, longest first."""
    spans = []
    claimed = [False] * len(text)
    for name in sorted(known_names, key=len, reverse=True):
        start_search = 0
        while (start := text.find(name, start_search)) != -1:
            end = start + len(name)
            if not any(claimed[start:end]):
                spans.append((start, end, category, name))
                for i in range(start, end):
                    claimed[i] = True
            start_search = end
    return spans


def find_emails(text: str):
    return [(m.start(), m.end(), "EMAIL_ADDRESS", m.group()) for m in EMAIL_PATTERN.finditer(text)]


def find_phones(text: str):
    spans = []
    for pattern in PHONE_PATTERNS:
        for m in pattern.finditer(text):
            group_index = 1 if m.groups() else 0
            spans.append((m.start(group_index), m.end(group_index), "PHONE_NUMBER", m.group(group_index)))
    return spans


def build_ground_truth(docx_path: str):
    units = {unit["id"]: unit["text"] for unit in extract_units(docx_path)}
    annotations = []

    for unit_id, text in units.items():
        spans = []
        spans += find_known_entity_spans(text, "PERSON", KNOWN_PERSON_NAMES)
        spans += find_known_entity_spans(text, "ORGANIZATION", KNOWN_ORGANIZATION_NAMES)
        spans += find_emails(text)
        spans += find_phones(text)
        for start, end, category, matched_text in spans:
            annotations.append(
                {"unit_id": unit_id, "category": category, "start": start, "end": end, "text": matched_text}
            )

    # PHYSICAL_ADDRESS and DIRECTOR_ID_NUMBER: the personnel table's own
    # structure (Name + DIN + Address columns together) is itself the
    # ground truth signal -- see redactor/docx_io.py's docstring.
    document = Document(docx_path)
    for table_index, table in enumerate(document.tables):
        column_categories = _match_structural_columns(table)
        whole_cell_categories = {"PHYSICAL_ADDRESS", "DIRECTOR_ID_NUMBER"}
        for row_index, row in enumerate(table.rows[1:], start=1):
            for column_index, category in column_categories.items():
                if category not in whole_cell_categories:
                    continue
                cell_text = row.cells[column_index].text
                if cell_text.strip():
                    annotations.append({
                        "unit_id": f"t{table_index}_r{row_index}_c{column_index}",
                        "category": category,
                        "start": 0,
                        "end": len(cell_text),
                        "text": cell_text,
                    })

    return annotations


if __name__ == "__main__":
    input_path, output_path = sys.argv[1], sys.argv[2]
    annotations = build_ground_truth(input_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for annotation in annotations:
            f.write(json.dumps(annotation, ensure_ascii=False) + "\n")
    print(f"Wrote {len(annotations)} ground-truth annotations to {output_path}")
