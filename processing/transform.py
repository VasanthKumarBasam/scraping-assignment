"""Map each source's raw dicts onto the common data model.

This is the only place that knows both the raw field names a scraper
produces and the final column names, so a layout change on a website only
touches the scraper, and a schema change only touches this file + schema.py.
"""
import logging

import config
from processing.cleaning import (clean_description, clean_price, clean_rating,
                                 clean_tags, clean_text, normalize_url,
                                 strip_quotes)
from processing.schema import Record

logger = logging.getLogger(__name__)


def clean_book(raw: dict) -> dict:
    return Record(
        source=config.BOOKS_SOURCE,
        source_url=normalize_url(raw.get("detail_url")),
        # Listing title first; the detail page <h1> is the fallback.
        name_or_title=clean_text(raw.get("title")) or clean_text(raw.get("detail_title")),
        category=clean_text(raw.get("category_raw")),
        price=clean_price(raw.get("price_raw")),
        rating=clean_rating(raw.get("rating_raw")),
        description=clean_description(raw.get("description_raw")),
        scraped_at=raw.get("scraped_at"),
    ).to_dict()


def clean_quote(raw: dict) -> dict:
    return Record(
        source=config.QUOTES_SOURCE,
        source_url=normalize_url(raw.get("page_url")),
        name_or_title=strip_quotes(raw.get("text_raw")),
        author=clean_text(raw.get("author_raw")),
        tags=clean_tags(raw.get("tags_raw")),
        scraped_at=raw.get("scraped_at"),
    ).to_dict()


CLEANERS = {
    config.BOOKS_SOURCE: clean_book,
    config.QUOTES_SOURCE: clean_quote,
}


def clean_records(raw_records: list[dict], source: str):
    """Clean every raw record of one source.

    Returns (cleaned_records, failures). A record whose cleaning raises an
    unexpected error becomes a failure with reason 'cleaning_error' instead of
    crashing the run.
    """
    cleaner = CLEANERS[source]
    cleaned, failures = [], []
    for raw in raw_records:
        try:
            cleaned.append(cleaner(raw))
        except Exception as exc:
            logger.warning("[%s] Cleaning failed for %r: %s", source, raw, exc)
            failures.append({
                "source": source,
                "source_url": raw.get("detail_url") or raw.get("page_url"),
                "name_or_title": raw.get("title") or raw.get("text_raw"),
                "scraped_at": raw.get("scraped_at"),
                "rejection_reasons": f"cleaning_error: {type(exc).__name__}",
            })
    return cleaned, failures
