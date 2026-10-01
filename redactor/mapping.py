"""Generates consistent fake replacements for detected PII.

The same real value always maps to the same fake value everywhere in the
document (e.g. every "Rohan Dey" becomes the same fake name), matching the
example in spec.md. Faker is seeded so re-running the tool on the same
input always produces the same redacted output.
"""

from faker import Faker

FAKE_SEED = 1234  # fixed seed -> reproducible redactions across runs


class PseudonymMapper:
    """Looks up (or creates) a fake replacement for a piece of PII."""

    def __init__(self):
        self._faker = Faker()
        Faker.seed(FAKE_SEED)
        self._cache = {}  # (category, original_text) -> fake_text

    def fake_value(self, category: str, original_text: str, fake_provider: str) -> str:
        cache_key = (category, original_text.strip().lower())
        if cache_key in self._cache:
            return self._cache[cache_key]

        fake_text = self._generate(category, original_text, fake_provider)
        self._cache[cache_key] = fake_text
        return fake_text

    def _generate(self, category: str, original_text: str, fake_provider: str) -> str:
        # A few categories get a hand-written generator so the fake value
        # keeps the same *shape* as the real one (digit count, "India"
        # suffix, etc.) instead of a generic Faker default that could look
        # obviously wrong in context.
        if category == "PHONE_NUMBER":
            return self._fake_phone_number(original_text)
        if category == "EMAIL_ADDRESS":
            return self._fake_email(original_text)
        if category == "PHYSICAL_ADDRESS":
            return self._fake_indian_address()
        if category == "DATE_OF_BIRTH":
            return self._fake_date_like(original_text)
        if category == "DIRECTOR_ID_NUMBER":
            return self._faker.numerify("#" * len(original_text.strip()))

        # Everything else: call the configured faker.Faker() method directly,
        # e.g. fake_provider="name" -> self._faker.name().
        return str(getattr(self._faker, fake_provider)())

    def _fake_phone_number(self, original: str) -> str:
        """Keeps the original's punctuation/spacing, replaces only digits."""
        digits = [c for c in original if c.isdigit()]
        fake_digits = self._faker.numerify("#" * len(digits))
        fake_digits_iter = iter(fake_digits)
        return "".join(next(fake_digits_iter) if c.isdigit() else c for c in original)

    def _fake_email(self, original: str) -> str:
        """Mirrors spec.md's example: real.name@company.com -> fake.name@example.com."""
        local_part = self._faker.first_name().lower() + "." + self._faker.last_name().lower()
        return f"{local_part}@example.com"

    def _fake_indian_address(self) -> str:
        return (
            f"{self._faker.building_number()} {self._faker.street_name()}, "
            f"{self._faker.city()} – {self._faker.postcode()}, "
            f"{self._faker.state()}, India"
        )

    def _fake_date_like(self, original: str) -> str:
        """Generates a fake date matching the original's format (numeric vs. 'Month D, YYYY')."""
        if any(char.isalpha() for char in original):
            return self._faker.date(pattern="%B %d, %Y")
        separator = "-" if "-" in original else "/"
        return self._faker.date(pattern=f"%d{separator}%m{separator}%Y")
