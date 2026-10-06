"""Duplicate detection with normalized fingerprints.

Exact comparison would treat "Example Book Title", " Example Book Title "
and "EXAMPLE BOOK TITLE" as three different books. Instead each record is
reduced to a fingerprint:

  1. pick the identifying fields
       Books:  source + title
       Quotes: source + author + first 50 characters of the quote text
  2. normalize each field: Unicode NFKC, casefold (lowercase),
     remove punctuation, collapse whitespace
  3. join the fields with "|" and SHA-256 hash the result

Two records with the same fingerprint are duplicates. The first one seen is
kept; later ones are removed from the final dataset and written to
output/duplicates.csv with a pointer to the record they duplicate.
"""
import hashlib
import logging
import re
import unicodedata

import config

logger = logging.getLogger(__name__)

_PUNCTUATION = re.compile(r"[^\w\s]")


def normalize_key(value) -> str:
    """'  The  Book: Vol. 1 ' -> 'the book vol 1'"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _PUNCTUATION.sub("", text)
    return " ".join(text.split())


def make_fingerprint(rec: dict) -> str:
    source = rec.get("source")
    # Normalize *before* slicing: otherwise a leading space or quote mark
    # would shift the 50-character window and break the match.
    title = normalize_key(rec.get("name_or_title"))

    if source == config.QUOTES_SOURCE:
        parts = [normalize_key(source), normalize_key(rec.get("author")),
                 title[:config.QUOTE_FINGERPRINT_CHARS]]
    else:
        parts = [normalize_key(source), title]

    # "|" separator: ("a b", "c") and ("a", "b c") must not collide.
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def find_duplicates(records: list[dict]):
    """Return (unique_records, duplicate_records), preserving input order.

    Each duplicate gets a 'duplicate_of' column with the source_url of the
    record that was kept.
    """
    first_seen: dict[str, dict] = {}
    unique, duplicates = [], []
    for rec in records:
        fingerprint = make_fingerprint(rec)
        original = first_seen.get(fingerprint)
        if original is None:
            first_seen[fingerprint] = rec
            unique.append(rec)
        else:
            duplicates.append({**rec, "duplicate_of": original.get("source_url")})
            logger.info("[%s] Duplicate found: %r (same as %s)", rec.get("source"),
                        (rec.get("name_or_title") or "")[:60], original.get("source_url"))
    return unique, duplicates
