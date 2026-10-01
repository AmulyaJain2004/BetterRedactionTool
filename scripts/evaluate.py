"""Compares what the redactor detects against ground_truth/ground_truth.jsonl
and prints precision/recall/F1/accuracy per PII category.

A detection counts as matching a ground-truth span if they're in the same
text unit, tagged with the same category, and their character ranges
overlap by at least one character (a common, slightly lenient rule for NER
evaluation -- it doesn't penalize a detector for trimming a trailing comma
off a name, for example).

Usage:
    python scripts/evaluate.py "input.docx" ground_truth/ground_truth.jsonl
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from redactor.docx_io import _collect_glossary_terms, _collect_known_person_names, _match_structural_columns
from redactor.engine import RedactionEngine
from scripts.extract_text import extract_units

WHOLE_CELL_CATEGORIES = {"PERSON", "PHYSICAL_ADDRESS", "DIRECTOR_ID_NUMBER"}


def detect_all_units(docx_path: str, engine: RedactionEngine):
    """Mirrors redactor/docx_io.py's traversal, but only detects (no rewrite)."""
    units = {unit["id"]: unit["text"] for unit in extract_units(docx_path)}
    detections = []  # (unit_id, category, start, end, text)

    document = Document(docx_path)
    # Same setup redact_docx() does before walking the document -- without
    # this, ORGANIZATION detection floods with false positives from the
    # document's own glossary terms, and misses the PERSON reclassification
    # rescue (see redactor/docx_io.py's docstring).
    engine.org_exclude_terms |= _collect_glossary_terms(document)
    engine.known_person_names |= _collect_known_person_names(document)

    structural_cells = set()  # unit_ids handled whole-cell, so they're not double-detected as free text
    for table_index, table in enumerate(document.tables):
        column_categories = _match_structural_columns(table)
        for row_index, row in enumerate(table.rows[1:], start=1):
            for column_index, category in column_categories.items():
                unit_id = f"t{table_index}_r{row_index}_c{column_index}"
                cell_text = row.cells[column_index].text
                structural_cells.add(unit_id)
                if cell_text.strip():
                    detections.append((unit_id, category, 0, len(cell_text), cell_text))

    for unit_id, text in units.items():
        if unit_id in structural_cells:
            continue
        for start, end, category, matched_text in engine.detect(text):
            detections.append((unit_id, category, start, end, matched_text))

    return detections


def spans_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def evaluate(docx_path: str, ground_truth_path: str):
    ground_truth = [json.loads(line) for line in open(ground_truth_path, encoding="utf-8")]
    detections = detect_all_units(docx_path, RedactionEngine())

    categories = sorted({row["category"] for row in ground_truth} | {d[1] for d in detections})
    results = {}

    for category in categories:
        gt_spans = [(g["unit_id"], g["start"], g["end"]) for g in ground_truth if g["category"] == category]
        det_spans = [(d[0], d[2], d[3]) for d in detections if d[1] == category]

        matched_gt = [False] * len(gt_spans)
        true_positives = 0
        for det_unit, det_start, det_end in det_spans:
            for i, (gt_unit, gt_start, gt_end) in enumerate(gt_spans):
                if matched_gt[i] or gt_unit != det_unit:
                    continue
                if spans_overlap(det_start, det_end, gt_start, gt_end):
                    matched_gt[i] = True
                    true_positives += 1
                    break

        false_positives = len(det_spans) - true_positives
        false_negatives = matched_gt.count(False)
        precision = true_positives / (true_positives + false_positives) if det_spans else 1.0
        recall = true_positives / (true_positives + false_negatives) if gt_spans else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        results[category] = {
            "ground_truth_count": len(gt_spans),
            "detected_count": len(det_spans),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    return results


def print_report(results: dict):
    header = f"{'CATEGORY':<20}{'GT':>6}{'DET':>6}{'TP':>6}{'FP':>6}{'FN':>6}{'PREC':>8}{'REC':>8}{'F1':>8}"
    print(header)
    print("-" * len(header))
    total_tp = total_fp = total_fn = 0
    for category, r in results.items():
        print(
            f"{category:<20}{r['ground_truth_count']:>6}{r['detected_count']:>6}{r['true_positives']:>6}"
            f"{r['false_positives']:>6}{r['false_negatives']:>6}{r['precision']:>8.2f}{r['recall']:>8.2f}{r['f1']:>8.2f}"
        )
        total_tp += r["true_positives"]
        total_fp += r["false_positives"]
        total_fn += r["false_negatives"]

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    print("-" * len(header))
    print(f"Overall precision: {overall_precision:.3f}  recall: {overall_recall:.3f}")


if __name__ == "__main__":
    input_path, ground_truth_path = sys.argv[1], sys.argv[2]
    results = evaluate(input_path, ground_truth_path)
    print_report(results)
