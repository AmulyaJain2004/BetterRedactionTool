"""Reads a .docx, redacts every paragraph and table cell, writes a new .docx.

Two redaction paths are used side by side:
  * Free text (ordinary paragraphs, most table cells) goes through
    RedactionEngine.redact_text(), which runs NER + regex detection.
  * Cells that structurally belong to a "Name / Designation / DIN /
    Address" style personnel table are redacted whole-cell, by column
    position (see config/pii_categories.yaml: structural_table_columns).
    A bare name or address with no surrounding sentence is unreliable to
    classify with NER alone, but the table's own header row already tells
    us exactly what that column is.

Formatting note: a paragraph can be split across several `runs` (e.g. one
bold word inside a plain sentence). Redaction rewrites the whole
paragraph's text into the first run and clears the rest, which keeps the
paragraph's overall look but does not preserve formatting that changed
*mid-sentence*. This is a deliberate, documented tradeoff (see README).
"""

from typing import Callable

from docx import Document

from redactor.config import load_structural_table_columns
from redactor.engine import RedactionEngine

# Called as on_unit_done(units_done, units_total) after each paragraph or
# table cell is processed, whether or not it contained any PII. Optional --
# the CLI (scripts/redact.py) doesn't pass one; the FastAPI backend
# (api/redaction_worker.py) does, to drive its progress bar.
ProgressCallback = Callable[[int, int], None]


def redact_docx(
    input_path: str,
    output_path: str,
    engine: RedactionEngine = None,
    on_unit_done: ProgressCallback = None,
):
    """Redacts `input_path` and writes the result to `output_path`.

    Returns the full replacement log: [(category, original_value, fake_value), ...]
    """
    engine = engine or RedactionEngine()
    document = Document(input_path)
    replacement_log = []

    total_units = _count_units(document) if on_unit_done else 0
    units_done = 0

    def tick():
        nonlocal units_done
        units_done += 1
        if on_unit_done:
            on_unit_done(units_done, total_units)

    # Legal/financial documents like this one define dozens of Capitalized
    # terms in a "Term | Description" glossary table ("Anchor Investors",
    # "the Offer", "ASBA", ...). spaCy's NER frequently mistakes these for
    # company names since they look just like one. Any term the document
    # itself defines this way is added to the ORGANIZATION deny-list for
    # this run, on top of the static list in config/org_exclude_list.txt.
    engine.org_exclude_terms |= _collect_glossary_terms(document)

    # Names already confirmed by the personnel table (structural detection
    # below) are used to rescue any later ORG-mislabeled mention of the
    # same person elsewhere in the free-flowing text.
    engine.known_person_names |= _collect_known_person_names(document)

    for paragraph in document.paragraphs:
        _redact_paragraph(paragraph, engine, replacement_log, tick)

    # Merged table cells: python-docx returns the *same* underlying cell
    # for every row/column a merge spans, so a naive walk would redact a
    # merged cell's text again on each repeat -- and the second pass would
    # be redacting an already-fake value. `redacted_cells` remembers which
    # physical cells (by XML element) were already handled, across the
    # whole document. It must hold the actual elements, not e.g. their
    # id(): python-docx/lxml recreate a cell's proxy object on every
    # access, and without a live reference keeping the old proxy alive,
    # Python is free to reuse its id() for something unrelated.
    redacted_cells = set()
    for table in document.tables:
        _redact_table(table, engine, replacement_log, redacted_cells, tick)

    document.save(output_path)
    return replacement_log


def _count_units(document) -> int:
    """Counts non-empty paragraphs/cells up front, so progress can be
    reported as "X of Y" instead of just "X so far". Mirrors the same
    merged-cell dedup rule the actual redaction walk below uses, so the
    count matches how many `tick()` calls there will actually be."""
    total = sum(1 for p in document.paragraphs if p.text.strip())

    seen_cells = set()
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell._tc in seen_cells:
                    continue
                seen_cells.add(cell._tc)
                total += sum(1 for p in cell.paragraphs if p.text.strip())
    return total


def _collect_glossary_terms(document) -> set[str]:
    """Finds "Term | Description" style tables and returns every defined term, lowercased."""
    terms = set()
    for table in document.tables:
        if not table.rows:
            continue
        header_cells = [cell.text.strip().lower() for cell in table.rows[0].cells]
        if header_cells[:2] != ["term", "description"]:
            continue
        for row in table.rows[1:]:
            term = row.cells[0].text.strip().lower()
            if term:
                terms.add(term)
    return terms


def _collect_known_person_names(document) -> set[str]:
    """Names found in a personnel table's Name column (see structural_table_columns)."""
    names = set()
    for table in document.tables:
        for column_index, category in _match_structural_columns(table).items():
            if category != "PERSON":
                continue
            for row in table.rows[1:]:
                name = row.cells[column_index].text.strip().lower()
                if name:
                    names.add(name)
    return names


def _redact_table(table, engine, replacement_log, redacted_cells, tick=lambda: None):
    column_categories = _match_structural_columns(table)
    # If the table matched a known personnel layout, its first row is a
    # real header and should be skipped; otherwise every row is data.
    data_rows = table.rows[1:] if column_categories else table.rows

    for row in data_rows:
        for column_index, cell in enumerate(row.cells):
            if cell._tc in redacted_cells:
                continue
            redacted_cells.add(cell._tc)

            category = column_categories.get(column_index)
            if category:
                _redact_cell_whole(cell, category, engine, replacement_log, tick)
            else:
                _redact_cell_freetext(cell, engine, replacement_log, tick)

            # A cell can itself contain a nested table (occasionally used
            # for sub-layouts in long legal documents).
            for nested_table in cell.tables:
                _redact_table(nested_table, engine, replacement_log, redacted_cells, tick)


def _match_structural_columns(table) -> dict:
    """Returns {column_index: category} if this table's header row matches
    a configured personnel-table layout, else {}."""
    if not table.rows:
        return {}

    header_cells = [cell.text.strip().lower() for cell in table.rows[0].cells]
    column_categories = {}
    for rule in load_structural_table_columns():
        header_matches = rule["column_header"] in header_cells
        has_required_sibling = any(req in header_cells for req in rule["requires_any_of"])
        if header_matches and has_required_sibling:
            column_index = header_cells.index(rule["column_header"])
            column_categories[column_index] = rule["category"]
    return column_categories


def _redact_cell_whole(cell, category, engine, replacement_log, tick=lambda: None):
    for paragraph in cell.paragraphs:
        text = paragraph.text
        if not text.strip():
            continue
        new_text, replacement = engine.replace_whole_span(text, category)
        if replacement:
            _set_paragraph_text(paragraph, new_text)
            replacement_log.append(replacement)
        tick()


def _redact_cell_freetext(cell, engine, replacement_log, tick=lambda: None):
    for paragraph in cell.paragraphs:
        _redact_paragraph(paragraph, engine, replacement_log, tick)


def _redact_paragraph(paragraph, engine, replacement_log, tick=lambda: None):
    text = paragraph.text
    if not text.strip():
        return
    new_text, replacements = engine.redact_text(text)
    if replacements:
        _set_paragraph_text(paragraph, new_text)
        replacement_log.extend(replacements)
    tick()


def _set_paragraph_text(paragraph, new_text: str):
    runs = paragraph.runs
    if not runs:
        return
    runs[0].text = new_text
    for run in runs[1:]:
        run.text = ""
