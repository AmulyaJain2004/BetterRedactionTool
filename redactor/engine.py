"""Finds every configured PII category in a piece of text and swaps each
match for a consistent fake value.

This is the one class the rest of the tool talks to. It combines three
sources of detections, then resolves overlaps and rewrites the text:
  1. Presidio's built-in recognizers (PERSON, EMAIL_ADDRESS, PHONE_NUMBER,
     CREDIT_CARD, IP_ADDRESS, US_SSN, plus any `kind: regex` category
     added to config/pii_categories.yaml).
  2. redactor/special_categories.py for ORGANIZATION and DATE_OF_BIRTH,
     which need a deny-list / a nearby keyword to avoid false positives.
  3. Whole-cell replacement for structured personnel tables, driven by
     redactor/docx_io.py (see `replace_whole_span` below).
"""

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

from redactor import config, special_categories
from redactor.mapping import PseudonymMapper

# en_core_web_trf (transformer/RoBERTa-based) instead of en_core_web_lg
# (static word vectors + a shallow CNN). Measured on this project's own
# ground truth (see EVALUATION.md): swapping only this model name, with
# every other line of detection logic unchanged, took PERSON from
# precision/recall 0.56/0.83 to 0.66/0.95, and ORGANIZATION from 0.40/0.79
# to 0.69/0.89 -- a transformer's contextual embeddings are far less
# thrown off by a short, context-free span (a bare "HDFC Bank Limited"
# paragraph with no sentence around it) than static word vectors are.
# Tradeoff: this model is slower per unit of text than en_core_web_lg --
# worth it for redaction quality on a batch job, not for a latency-sensitive
# path. Requires `pip install spacy-transformers` and
# `python -m spacy download en_core_web_trf`.
SPACY_MODEL_NAME = "en_core_web_trf"


class RedactionEngine:
    def __init__(self):
        self.categories = config.load_categories()
        self.org_exclude_terms = config.load_org_exclude_terms()
        # Filled in by docx_io.py from the document's own personnel table,
        # before redaction starts -- see special_categories.find_organizations.
        self.known_person_names: set[str] = set()
        self.mapper = PseudonymMapper()

        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": SPACY_MODEL_NAME}],
        }).create_engine()
        self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        self._registered_regex_names: set[str] = set()  # tracks what's live in self.analyzer.registry
        self._sync_regex_recognizers()

        self._presidio_entity_names = [
            name for name, cfg in self.categories.items()
            if cfg["kind"] in ("presidio_builtin", "regex")
        ]

    def reload_categories(self):
        """Re-reads config/pii_categories.yaml and config/org_exclude_list.txt
        from disk, without reloading the (slow) transformer model.

        Used by the settings UI (api/routers/config.py) so adding/removing a
        category or an exclude-list entry takes effect on the *next* job,
        without restarting the server or re-downloading/re-loading
        en_core_web_trf (the expensive part -- see SPACY_MODEL_NAME above).
        """
        self.categories = config.load_categories()
        self.org_exclude_terms = config.load_org_exclude_terms()
        self._presidio_entity_names = [
            name for name, cfg in self.categories.items()
            if cfg["kind"] in ("presidio_builtin", "regex")
        ]
        self._sync_regex_recognizers()

    def _sync_regex_recognizers(self):
        """Adds recognizers for any `kind: regex` category not yet
        registered, and removes ones for categories no longer configured
        (e.g. deleted via the settings UI). Idempotent -- safe to call
        after every reload, not just the first time."""
        configured = {name for name, cfg in self.categories.items() if cfg["kind"] == "regex"}

        for name in configured - self._registered_regex_names:
            cfg = self.categories[name]
            patterns = [
                Pattern(name=f"{name}_{i}", regex=pattern, score=cfg["score_threshold"])
                for i, pattern in enumerate(cfg["patterns"])
            ]
            self.analyzer.registry.add_recognizer(
                PatternRecognizer(supported_entity=name, patterns=patterns, name=f"{name}_recognizer")
            )

        for name in self._registered_regex_names - configured:
            self.analyzer.registry.remove_recognizer(f"{name}_recognizer")

        self._registered_regex_names = configured

    def redact_text(self, text: str):
        """Detects and replaces PII in free-flowing text (a paragraph or table cell).

        Returns (redacted_text, [(category, original_value, fake_value), ...]).
        """
        if not text.strip():
            return text, []

        matches = self._drop_overlaps(self._detect_all(text))
        return self._replace_matches(text, matches)

    def detect(self, text: str):
        """Same detection as redact_text, without rewriting the text.

        Used by scripts/evaluate.py to compare what would be redacted
        against the ground truth. Returns [(start, end, category, matched_text), ...].
        """
        if not text.strip():
            return []
        return self._drop_overlaps(self._detect_all(text))

    def replace_whole_span(self, text: str, category: str):
        """Redacts an entire span (e.g. a table cell known to hold one name/address/ID).

        Used when the document's structure already tells us what a cell is,
        which is more reliable than NER on a short, context-free cell.
        Returns (redacted_text, (category, original_value, fake_value)) or
        (text, None) if there was nothing to redact.
        """
        if not text.strip():
            return text, None
        fake_value = self.mapper.fake_value(category, text, self.categories[category]["fake_provider"])
        return fake_value, (category, text, fake_value)

    def _detect_all(self, text: str):
        matches = []  # list of (start, end, category, matched_text)

        # Parse once, reuse everywhere below. Presidio's analyze() runs the
        # spaCy pipeline internally; passing it a pre-computed NlpArtifacts
        # (nlp_artifacts.tokens is the actual spaCy Doc) means ORGANIZATION
        # detection can reuse that same parse instead of running the whole
        # (expensive, transformer-based) pipeline on the same text a second
        # time. This alone roughly halves per-unit NLP time.
        nlp_artifacts = self.analyzer.nlp_engine.process_text(text, "en")
        spacy_doc = nlp_artifacts.tokens

        presidio_results = self.analyzer.analyze(
            text=text, entities=self._presidio_entity_names, language="en", nlp_artifacts=nlp_artifacts
        )
        for result in presidio_results:
            category_cfg = self.categories[result.entity_type]
            if result.score >= category_cfg["score_threshold"]:
                matches.append((result.start, result.end, result.entity_type, text[result.start:result.end]))

        if "PERSON" in self.categories:
            for start, end, name_text in special_categories.find_names_from_labels(text):
                matches.append((start, end, "PERSON", name_text))

        if "ORGANIZATION" in self.categories:
            organizations, reclassified_as_person = special_categories.find_organizations(
                spacy_doc, self.org_exclude_terms, self.known_person_names
            )
            for start, end, org_text in organizations:
                matches.append((start, end, "ORGANIZATION", org_text))
            for start, end, person_text in reclassified_as_person:
                matches.append((start, end, "PERSON", person_text))

        if "DATE_OF_BIRTH" in self.categories:
            for start, end, dob_text in special_categories.find_dates_of_birth(text):
                matches.append((start, end, "DATE_OF_BIRTH", dob_text))

        if "PHYSICAL_ADDRESS" in self.categories:
            # find_address_after_keyword only returns a match when a
            # birth/residence-style keyword ("residing at", ...) is
            # present, so no extra "is this personal?" gate is needed here.
            hit = special_categories.find_address_after_keyword(text)
            if hit:
                matches.append((hit[0], hit[1], "PHYSICAL_ADDRESS", hit[2]))

        return matches

    @staticmethod
    def _drop_overlaps(matches):
        """When two detections overlap, keep the longer (more specific) one."""
        by_start_then_longest_first = sorted(matches, key=lambda m: (m[0], -(m[1] - m[0])))
        kept, last_end = [], -1
        for start, end, category, matched_text in by_start_then_longest_first:
            if start >= last_end:
                kept.append((start, end, category, matched_text))
                last_end = end
        return kept

    def _replace_matches(self, text: str, matches):
        replacements_log = []
        redacted_text = text
        # Replace right-to-left so earlier span offsets stay valid.
        for start, end, category, original_value in sorted(matches, key=lambda m: m[0], reverse=True):
            fake_value = self.mapper.fake_value(category, original_value, self.categories[category]["fake_provider"])
            redacted_text = redacted_text[:start] + fake_value + redacted_text[end:]
            replacements_log.append((category, original_value, fake_value))
        replacements_log.reverse()  # restore left-to-right document order
        return redacted_text, replacements_log
