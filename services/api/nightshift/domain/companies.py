"""Company name normalization.

``normalized_name`` is unique on ``companies``, so this function decides whether
two postings belong to one employer. Getting it wrong in one direction splits a
company in two; getting it wrong in the other merges two real companies. It is
therefore deliberately conservative: strip legal suffixes and punctuation, and
stop there. No fuzzy matching, no edit distance, no "Meta" ≈ "Metabase".
"""

from __future__ import annotations

import re
import unicodedata

# Only suffixes that are unambiguously legal-entity noise. "Group", "Labs",
# "Technologies", and "Systems" are excluded on purpose — they distinguish real,
# different companies far more often than they decorate one.
_LEGAL_SUFFIXES = (
    "incorporated",
    "inc",
    "llc",
    "l.l.c",
    "ltd",
    "limited",
    "corporation",
    "corp",
    "co",
    "gmbh",
    "b.v",
    "bv",
    "n.v",
    "nv",
    "s.a",
    "sa",
    "plc",
    "pty",
    "ag",
    "ab",
    "oy",
    "as",
)

# Apostrophes are deleted rather than turned into a space. Replacing them would
# leave a dangling token — "Moody's" -> "moody s" — which would then not match
# "Moodys", splitting one employer into two. Real NYC employers this affects:
# Moody's, McDonald's, Lowe's, Macy's.
# The RUF001 suppression is deliberate: matching the typographic apostrophe
# alongside the typewriter one is the entire point of this pattern.
_APOSTROPHE = re.compile(r"[’'`]")  # noqa: RUF001
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_company_name(name: str) -> str:
    """Casefolded, de-punctuated, legal-suffix-stripped company key.

    >>> normalize_company_name("Datadog, Inc.")
    'datadog'
    >>> normalize_company_name("Moody's Analytics")
    'moodys analytics'
    """
    # NFKD so "Société" and "Societe" do not become two companies.
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_ish = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # Apostrophes first, and deleted — see _APOSTROPHE.
    cleaned = _PUNCTUATION.sub(" ", _APOSTROPHE.sub("", ascii_ish)).casefold()
    tokens = [token for token in _WHITESPACE.split(cleaned) if token]

    # Strip trailing legal suffixes, possibly stacked ("Foo Co Ltd").
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()

    normalized = " ".join(tokens)
    if not normalized:
        # Never return an empty key: it is a unique column, so an empty value
        # would collide every unnameable company into one row.
        raise ValueError(f"company name {name!r} normalizes to nothing")
    return normalized
