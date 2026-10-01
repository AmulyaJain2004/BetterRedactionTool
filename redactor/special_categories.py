"""Three PII categories that need context Presidio's plain pattern/entity
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


def find_names_from_labels(text: str) -> list[tuple[int, int, str]]:
    """Names anchored by a "Contact Person:" label or immediately before an email."""
    matches = []
    for pattern in (_CONTACT_LABEL_PATTERN, _NAME_BEFORE_EMAIL_PATTERN):
        for match in pattern.finditer(text):
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
