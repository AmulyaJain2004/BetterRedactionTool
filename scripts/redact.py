"""CLI entry point: redact PII from a .docx file.

Usage:
    python scripts/redact.py "input.docx" "output.docx"
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow `import redactor` when run directly

from redactor.docx_io import redact_docx


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]
    print(f"Redacting {input_path} ...")
    replacement_log = redact_docx(input_path, output_path)
    print(f"Wrote {output_path} ({len(replacement_log)} values redacted)")

    log_path = Path(output_path).with_suffix(".redaction_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "original_value", "fake_value"])
        writer.writerows(replacement_log)
    print(f"Redaction log written to {log_path}")


if __name__ == "__main__":
    main()
