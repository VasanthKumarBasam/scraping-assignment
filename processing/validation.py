"""Validation: check one cleaned record and say *why* it is invalid.

validate_record() returns a list of problem codes. An empty list means the
record is valid. Returning reasons (instead of True/False) lets the summary
report count rejections per reason.
"""
import logging
import math
from collections import Counter
from urllib.parse import urlsplit

import config

logger = logging.getLogger(__name__)

VALID_SOURCES = {config.BOOKS_SOURCE, config.QUOTES_SOURCE}

# Fields that must be present for a given source ("required where applicable").
REQUIRED_BY_SOURCE = {
    config.BOOKS_SOURCE: ("price", "rating"),
    config.QUOTES_SOURCE: ("author",),
}


def is_valid_url(value) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _is_number(value) -> bool:
    # bool is a subclass of int in Python (True == 1), so exclude it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_record(rec: dict) -> list[str]:
    problems = []
    source = rec.get("source")

    if source not in VALID_SOURCES:
        problems.append("unknown_source")
    if not rec.get("name_or_title"):
        problems.append("missing_name")
    if not is_valid_url(rec.get("source_url")):
        problems.append("invalid_url")

    for field in REQUIRED_BY_SOURCE.get(source, ()):
        if rec.get(field) is None:
            problems.append(f"missing_{field}")

    price = rec.get("price")
    if price is not None and (not _is_number(price) or math.isnan(price) or price < 0):
        problems.append("invalid_price")

    rating = rec.get("rating")
    # isinstance(int) also rejects 5.0 and True, which `rating in (1, 2, 3, 4, 5)` would accept.
    if rating is not None and (not isinstance(rating, int) or isinstance(rating, bool)
                               or not 1 <= rating <= 5):
        problems.append("invalid_rating")

    return problems


def split_valid_invalid(records: list[dict]):
    """Return (valid_records, rejected_records, Counter of reasons).

    Rejected records get a 'rejection_reasons' column so they can be
    written to output/rejected_records.csv for review.
    """
    valid, rejected, reasons = [], [], Counter()
    for rec in records:
        problems = validate_record(rec)
        if problems:
            reasons.update(problems)
            rejected.append({**rec, "rejection_reasons": ";".join(problems)})
            logger.warning("[%s] Rejected %r: %s", rec.get("source"),
                           (rec.get("name_or_title") or "")[:60], ", ".join(problems))
        else:
            valid.append(rec)
    return valid, rejected, reasons
