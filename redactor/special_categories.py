"""Four PII categories that need context Presidio's plain pattern/entity
matching can't express by itself, so each gets one small, direct function
instead of a config-only entry:

  * ORGANIZATION      - Presidio has no built-in "company name" recognizer.
                        We use spaCy's ORG entities, minus a deny-list of
                        regulators/statutes (config/org_exclude_list.txt)
                        that are cited for legal compliance, not PII -- the
                        same reasoning spec.md applies to "Order"/"Ticket"
                        numbers.
  * PHYSICAL_ADDRESS  - Only a named individual's own address counts as
                        PII; the company's registered/corporate office
                        address is public letterhead information and is
                        deliberately left alone (see README "Address
                        scope"). The common case -- a personnel table's own
                        Address column -- is handled whole-cell by
                        docx_io.py; find_address_after_keyword() below is
                        only the prose fallback ("...residing at <address>.")
                        for addresses mentioned outside of such a table.
  * DATE_OF_BIRTH     - A bare date isn't PII (this document alone has
                        hundreds of legal/business dates). Only a date
                        sitting next to a birth-related keyword counts.
  * AADHAAR_NUMBER    - A bare 12-digit span is way too common (phone
                        numbers, financial figures, concatenated IDs) to
                        redact on shape alone. Real Aadhaar numbers carry
                        a Verhoeff check digit (the same algorithm UIDAI
                        itself uses), so validating that -- not a nearby
                        keyword -- is what keeps this precise.
"""

import re


# spaCy's NER can miss a name sitting right next to a label instead of in a
# full sentence (verified empirically: it dropped "Sarthak Malvadkar" in
# "Contact Person: Sarthak Malvadkar, Company Secretary..." and dropped
# "Rashi Patil" in spec.md's own "Rashi Patil: rashi.patil@gmail.com"
# ticket-log style). Both patterns below are narrow, label-anchored
# regexes that catch those two common, low-ambiguity shapes without
# guessing at names in open text (that's still NER's job).
_NAME_AFTER_TITLE_CASE = r"[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,3}"
_CONTACT_LABEL_PATTERN = re.compile(rf"Contact\s*Person\s*:\s*({_NAME_AFTER_TITLE_CASE})")
_NAME_BEFORE_EMAIL_PATTERN = re.compile(
    rf"({_NAME_AFTER_TITLE_CASE})\s*:\s*(?=[\w.+-]+@[\w-]+\.[\w.-]+)"
)


# Words that, right before a colon, are a field label ("Email: x@y.com"),
# not the tail of a person's name.
_LABEL_WORDS = {"email", "e-mail", "mail", "id", "address", "contact", "website", "web", "to", "from", "cc"}


def _looks_like_name(candidate: str) -> bool:
    words = candidate.split()
    if words[-1].lower() in _LABEL_WORDS:
        return False  # e.g. "Compliance Officer. Email: rohan.dey@acme.com"
    # A word ending in "." mid-match is a sentence boundary ("Officer."),
    # unless it's an initial or short honorific ("R.", "Mr.", "Dr.").
    return all(not w.endswith(".") or len(w) <= 3 for w in words[:-1])


def find_names_from_labels(text: str) -> list[tuple[int, int, str]]:
    """Names anchored by a "Contact Person:" label or immediately before an email."""
    matches = []
    for pattern in (_CONTACT_LABEL_PATTERN, _NAME_BEFORE_EMAIL_PATTERN):
        for match in pattern.finditer(text):
            if _looks_like_name(match.group(1)):
                matches.append((match.start(1), match.end(1), match.group(1)))
    return matches


_REGISTRATION_CODE_PATTERN = re.compile(r"^[A-Z]{2,6}\d{4,}$")


def find_organizations(
    spacy_doc, exclude_terms: set[str], known_person_names: set[str] = frozenset()
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """Returns (organization_matches, reclassified_person_matches).

    spaCy sometimes tags a bare person's name as ORG when it appears
    without a sentence around it for context (verified empirically on
    "Kushal Subbayya Hegde" -- correctly PERSON in a full sentence, but
    ORG when the surrounding text is sparse). Names already confirmed via
    the document's own personnel table (`known_person_names`, collected in
    docx_io.py) are reclassified to PERSON instead of being dropped as an
    ORGANIZATION false positive.
    """
    organizations, reclassified_as_person = [], []
    for entity in spacy_doc.ents:
        if entity.label_ != "ORG":
            continue
        entity_text_lower = entity.text.strip().lower()
        if not any(char.isalpha() for char in entity_text_lower):
            continue  # e.g. a lone currency symbol or number spaCy mistags as ORG
        if "\n" in entity.text:
            continue  # a real company name never spans a line break; this is a
            # tokenization artifact (seen wrongly swallowing a whole email address
            # plus the word "Telephone" from the next line in a table cell)
        if "http" in entity_text_lower or "www." in entity_text_lower:
            continue  # a URL, not a company name
        if _REGISTRATION_CODE_PATTERN.match(entity.text.strip()):
            continue  # e.g. a SEBI registration number like "INR000004058"
        if _is_excluded(entity_text_lower, exclude_terms):
            continue
        span = (entity.start_char, entity.end_char, entity.text)
        if _matches_known_person(entity_text_lower, known_person_names):
            reclassified_as_person.append(span)
        else:
            organizations.append(span)
    return organizations, reclassified_as_person


def _matches_known_person(entity_text_lower: str, known_person_names: set[str]) -> bool:
    """True if entity_text's words appear, in order, within a known full name
    (so "Kushal Hegde" matches the known name "Kushal Subbayya Hegde")."""
    entity_words = entity_text_lower.split()
    for known_name in known_person_names:
        remaining_words = iter(known_name.split())
        if all(word in remaining_words for word in entity_words):
            return True
    return False


def _is_excluded(entity_text_lower: str, exclude_terms: set[str]) -> bool:
    """An entity is excluded if it (roughly) IS a known regulator/statute name.

    Substring matching (in either direction) only applies to multi-word
    terms. A single generic word like "Bank" or "Trust" (common in this
    document's own glossary) would otherwise substring-match -- and wrongly
    exclude -- almost every real bank/trust name ("HDFC Bank Limited",
    "Everest Family Trust", ...), which is exactly what happened before
    this check was added.
    """
    for term in exclude_terms:
        if entity_text_lower == term:
            return True
        if " " in term and (entity_text_lower in term or term in entity_text_lower):
            return True
    return False


# \b word boundaries matter here: a naive substring search for "resident
# of" also matches inside "Pres-ident of" ("President of India"), which is
# exactly the false positive this pattern caused before word boundaries
# were added.
_ADDRESS_CONTEXT_PATTERN = re.compile(r"\b(?:residing at|resident of)\b", re.IGNORECASE)


def find_address_after_keyword(text: str) -> tuple[int, int, str] | None:
    """Fallback for prose like '...residing at <address>.' outside of tables."""
    match = _ADDRESS_CONTEXT_PATTERN.search(text)
    if not match:
        return None
    address_start = match.end()
    # Skip the space after "residing at", so the replacement doesn't
    # swallow it ("residing at475 ...").
    while address_start < len(text) and text[address_start].isspace():
        address_start += 1
    sentence_end = text.find(".", address_start)
    address_end = sentence_end if sentence_end != -1 else len(text)
    return (address_start, address_end, text[address_start:address_end])


_MONTH_NAMES = (
    r"January|February|March|April|May|June|July|August|September|October|November|December"
)
_DOB_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(rf"\b(?:{_MONTH_NAMES})\s+\d{{1,2}},?\s+\d{{4}}\b"),  # "March 14, 1990"
    re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTH_NAMES})\s+\d{{4}}\b"),  # "14 March 1990"
]
_DOB_CONTEXT_WINDOW_CHARS = 40
_DOB_CONTEXT_KEYWORDS = ["date of birth", "born on", "dob"]


def find_dates_of_birth(text: str) -> list[tuple[int, int, str]]:
    """A date only counts as a DOB if a birth-related keyword is nearby."""
    lowered = text.lower()
    matches = []
    for pattern in _DOB_DATE_PATTERNS:
        for match in pattern.finditer(text):
            window_start = max(0, match.start() - _DOB_CONTEXT_WINDOW_CHARS)
            window_text = lowered[window_start:match.start()]
            if any(keyword in window_text for keyword in _DOB_CONTEXT_KEYWORDS):
                matches.append((match.start(), match.end(), match.group()))
    return matches


# Indian Aadhaar number: 12 digits, official rule is the first digit is
# never 0 or 1, printed as three groups of 4 (space/dash/no separator all
# seen in practice). Captured as three groups so the digits can be
# re-joined for checksum validation regardless of which separator (or
# none) was used.
_AADHAAR_PATTERN = re.compile(r"\b([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})\b")

# Verhoeff algorithm tables (multiplication table `_D`, permutation table
# `_P`) -- the same check-digit scheme UIDAI uses for real Aadhaar numbers.
# Standard reference tables, not anything Aadhaar-specific in themselves.
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def _has_valid_verhoeff_checksum(digits: str) -> bool:
    """True if the last digit of `digits` is a correct Verhoeff check
    digit for the digits before it. Processes right-to-left, including
    the check digit itself -- a valid number always reduces to 0."""
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[i % 8][int(digit)]]
    return checksum == 0


def find_aadhaar_numbers(text: str) -> list[tuple[int, int, str]]:
    """Every 12-digit span matching Aadhaar's shape AND carrying a valid
    Verhoeff check digit. No nearby keyword is required (unlike
    DATE_OF_BIRTH) -- the checksum alone already rejects the overwhelming
    majority of random 12-digit sequences (roughly 9 in 10), which is more
    precise than any label we could anticipate."""
    matches = []
    for match in _AADHAAR_PATTERN.finditer(text):
        digits = "".join(match.groups())
        if _has_valid_verhoeff_checksum(digits):
            matches.append((match.start(), match.end(), match.group()))
    return matches
