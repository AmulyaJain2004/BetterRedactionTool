# Evaluation report

Target document: `Red Herring Prospectus.docx` (a real IPO offer document
-- 1,006 paragraphs, 76 tables, ~446,000 characters). Numbers below are
from a full run of `scripts/evaluate.py` against a hand-verified ground
truth covering the **entire document**, not a sample.

## Methodology

Manually reading and labeling every one of the ~3,800 non-empty
paragraphs/table cells by eye is not how any real annotation project
would exhaustively cover a document this size -- and it isn't more
rigorous than the alternative below, just slower. Instead:

1. **`PERSON` and `ORGANIZATION`** -- every director/promoter/KMP table
   and every "Contact Person" field in every banker/underwriter/advisor
   listing was read by hand, plus a keyword sweep (`Limited`, `Bank`,
   `LLP`, `Trust`, `Associates`, ...) to catch company mentions outside
   those tables. This produced a master list of the **33 real people**
   and **~60 real companies** this document actually names
   (`ground_truth/known_entities.py`, with each entry commented on where
   it was found). Every occurrence of every name in that list, anywhere
   in the ~3,800 text units, was then found programmatically -- this is
   exhaustive over the whole document, not a sample, and avoids the
   transcription errors of manually marking start/end offsets by hand.
2. **`EMAIL_ADDRESS`, `PHONE_NUMBER`** -- these are syntactically
   distinctive enough that a precise regex pass *is* the ground truth
   (spot-checked: all 52 emails and 36 phone numbers found this way were
   read individually and confirmed real).
3. **`PHYSICAL_ADDRESS`, `DIRECTOR_ID_NUMBER`** -- the personnel table's
   own structure (a Name column next to a DIN/Designation column) is
   itself the ground-truth signal: a human reading that table would
   independently agree those are personal addresses/IDs. All 8 director
   rows were checked by hand.
4. **`DATE_OF_BIRTH`, `US_SSN`, `CREDIT_CARD`, `IP_ADDRESS`** -- confirmed
   by exhaustive regex sweep (see below) that this document contains
   **zero** real instances of any of these four. That's expected: this is
   an Indian securities filing, and none of the four are things it would
   disclose. Reported separately below on a small synthetic test instead,
   since "0 ground truth, 0 detections" would trivially score 100% on a
   category the detector was never actually challenged on.

A detection counts as matching a ground-truth entry if it's in the same
text unit (same paragraph or table cell), tagged with the same category,
and its character range overlaps the ground truth's by at least one
character -- a standard, slightly lenient rule for NER evaluation (it
doesn't penalize trimming a trailing comma off a name, for instance).

Reproduce this with:
```bash
python scripts/build_ground_truth.py "Red Herring Prospectus.docx" ground_truth/ground_truth.jsonl
python scripts/evaluate.py "Red Herring Prospectus.docx" ground_truth/ground_truth.jsonl
```

## Model choice: en_core_web_lg -> en_core_web_trf

The first working version of this tool used spaCy's `en_core_web_lg`
(static word vectors + a shallow CNN) for the PERSON/ORGANIZATION NER
backend. Its precision/recall on this document's PERSON and ORGANIZATION
categories were the weakest numbers in the whole report, and investigation
pointed at one specific, well-understood mechanism: `en_core_web_lg` is
noticeably less reliable on a short, context-free span (a paragraph that
is *just* `"HDFC Bank Limited"`, no sentence around it) than on the same
string inside a full sentence -- confirmed directly, not just inferred.

Two alternatives were evaluated head-to-head, on this exact ground truth,
before picking a replacement:

| Category | Metric | en_core_web_lg | GLiNER-PII (small, best config) | **en_core_web_trf** |
|---|---|---|---|---|
| PERSON | Precision | 0.56 | 0.58 | **0.72** |
| PERSON | Recall | 0.83 | 0.90 | **0.95** |
| ORGANIZATION | Precision | 0.40 | 0.17 | **0.69** |
| ORGANIZATION | Recall | 0.79 | 0.36 | **0.89** |

- **GLiNER-PII** (`knowledgator/gliner-pii-small-v1.0`, a zero-shot,
  PII-specific pretrained model) improved PERSON recall but was
  *dramatically* worse on ORGANIZATION, even after applying the exact
  same regulator/glossary deny-list this project already built for
  ORGANIZATION. Separately, every dedicated open-source "PII model"
  checked (OpenAI's Apache-2.0 Privacy Filter, GLiNER2-PII) turned out to
  not attempt organization/company detection *at all* -- worth knowing on
  its own: under most privacy frameworks (GDPR/CCPA), PII specifically
  means identifying a natural person, so a company generally isn't in
  scope for a "PII model." spec.md asks for it anyway (reasonably -- a
  company name can still be sensitive), but it means the right tool
  category for ORGANIZATION was never going to be a PII-specific model.
- **`en_core_web_trf`** (RoBERTa-based, MIT license, same spaCy family
  already in use) won on every single number above, using the *exact
  same* deny-list/reclassification code already in
  `redactor/special_categories.py` -- only the model changed. A
  transformer's contextual embeddings are far less thrown off by a short,
  context-free span than static word vectors are, which is precisely the
  failure mode identified. It's also a strictly lower-friction choice:
  no new dependency ecosystem, no new license to evaluate, no new hosting
  question (see `api/README.md`'s hosting notes for what *does* change:
  more memory, more CPU time).

**Cost of the swap**: full-document redaction went from ~45 seconds
(`en_core_web_lg`) to **5m40s** (`en_core_web_trf`), measured end-to-end
via `scripts/redact.py` on this same 446,000-character document, CPU-only.
Worth it for redaction quality on a batch job (which is why `api/`'s
design treats every job as async with a progress bar rather than a
synchronous request -- see `api/README.md`), not appropriate for a
latency-sensitive path.

## Results -- full document

(Current pipeline, `en_core_web_trf`; the `en_core_web_lg` numbers above
are kept for the comparison, not repeated here.)

| Category | Ground truth | Detected | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| DIRECTOR_ID_NUMBER | 8 | 8 | 8 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| EMAIL_ADDRESS | 52 | 52 | 52 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PHONE_NUMBER | 36 | 38 | 36 | 2 | 0 | 0.95 | 1.00 | 0.97 |
| PHYSICAL_ADDRESS | 8 | 8 | 8 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PERSON | 200 | 265 | 190 | 75 | 10 | 0.72 | 0.95 | 0.82 |
| ORGANIZATION | 218 | 278 | 193 | 85 | 25 | 0.69 | 0.89 | 0.78 |
| **Overall (micro-averaged)** | 522 | 649 | 487 | 162 | 35 | **0.75** | **0.93** | 0.83 |

Accuracy (micro, span-level: TP / (TP + FP + FN)) = 487 / 684 = **0.71**
(up from 0.49 with `en_core_web_lg`). Still not a meaningful "percent of
the document correctly handled" figure on its own -- a redacted false
positive is usually harmless over-redaction, not a privacy leak -- but
the direction and size of the jump is the real signal here.

### The remaining PERSON/ORGANIZATION gap

The four structured categories (email, phone, address, ID number) are
at or near 1.00 because they're syntactically distinctive -- a regex or a
government ID format doesn't get confused by surrounding legal prose.
PERSON and ORGANIZATION are NER-driven and, even improved, aren't
perfect, for two known reasons documented from the pre-swap investigation
(both categories, not just wording -- confirmed to still be the same kind
of error, at lower volume, not a new failure mode):

- **False negatives**: a real name/company sitting completely alone in a
  short paragraph/cell, with zero surrounding sentence, is still
  occasionally missed even by a transformer -- less often than before
  (PERSON FN dropped 33 -> 10, ORGANIZATION 45 -> 25), but not zero.
- **False positives**: place-name/building-name fragments inside a
  corporate address (deliberately *not* redacted at all -- see README
  "Address scope", it's public letterhead information, not a person's)
  and financial/legal jargon not covered by the glossary-derived
  deny-list both still occasionally get mistagged. Same mechanism as
  before, smaller volume (PERSON FP 131 -> 75, ORGANIZATION FP 255 -> 85).

Three real bugs were found and fixed while building this evaluation
(each made a measurable difference, kept here for the record rather than
silently fixed):
- Merged table cells were being redacted twice, corrupting already-fake
  text into further fake text (python-docx returns the same cell for
  every row/column a merge spans).
- The ORGANIZATION deny-list did substring matching in both directions
  for every glossary term, including single generic words like `"Bank"`
  or `"Trust"` -- which silently excluded almost every real bank/trust
  name in the document (`"HDFC Bank Limited"` contains `"Bank"`). Fixed by
  requiring an exact match for single-word deny-list terms.
- The address-context keyword `"resident of"` matched as a plain
  substring inside unrelated words (`"President of India"` contains
  `"...resident of..."`), triggering a bogus address redaction. Fixed
  with word-boundary regex matching.

## Supplementary synthetic test (DATE_OF_BIRTH, SSN, credit card, IP)

Since the real document has zero instances of these four, each detector
was run once against a hand-written sentence designed to exercise it,
plus one negative control for DATE_OF_BIRTH (a non-birth date, to check
it isn't just flagging every date):

| Input | Detected as | Redacted to |
|---|---|---|
| `His Social Security Number is 219-09-9999.` | US_SSN | `797-57-1915` |
| `Please charge card number 4111 1111 1111 1111 for the deposit.` | CREDIT_CARD | `676311530007` |
| `The server can be reached at 192.168.1.100 for diagnostics.` | IP_ADDRESS | `191.126.241.73` |
| `Her date of birth is 14 March 1990.` | DATE_OF_BIRTH | `December 15, 2022` |
| `Date of Birth: 03/14/1990` | DATE_OF_BIRTH | `29/12/1999` |
| `The agreement was signed on 14 March 1990.` (negative control) | *(nothing -- correct)* | *(unchanged -- correct)* |

All four categories work as designed: they detect and consistently
pseudonymize their target pattern, and DATE_OF_BIRTH correctly leaves a
structurally identical but non-birth date alone.

## Precision/recall policy note (spec.md's "Order"/"Ticket" question)

Applying the same reasoning spec.md invites for "Order"/"Ticket" numbers:
this tool treats regulator/exchange/statute names (SEBI, BSE, "Companies
Act", ...) as **not** PII (see README "Company scope"), and a company's
own registered/corporate office address as **not** PII (see README
"Address scope"). Both are explicit, documented policy choices, not
detector failures -- ground truth in this report is built consistently
with those choices.
