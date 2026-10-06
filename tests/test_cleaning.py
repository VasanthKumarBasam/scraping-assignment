import pytest

import config
from processing.cleaning import (clean_description, clean_price, clean_rating,
                                 clean_tags, clean_text, normalize_url,
                                 strip_quotes)
from processing.schema import FIELDNAMES
from processing.transform import clean_book, clean_quote, clean_records


# ---------- clean_text ----------
@pytest.mark.parametrize("raw, expected", [
    ("  Hello \n  World ", "Hello World"),
    ("Tab\tand\xa0nbsp", "Tab and nbsp"),
    ("zero\u200bwidth", "zerowidth"),
    ("   ", None),
    ("", None),
    (None, None),
])
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


# ---------- strip_quotes ----------
@pytest.mark.parametrize("raw, expected", [
    ("“Hello world”", "Hello world"),
    ('  "Straight quotes"  ', "Straight quotes"),
    ("No quotes here", "No quotes here"),
    ("“He said “hi” to me”", "He said “hi” to me"),  # inner quotes kept
    ("“”", None),
    (None, None),
])
def test_strip_quotes(raw, expected):
    assert strip_quotes(raw) == expected


# ---------- clean_price ----------
@pytest.mark.parametrize("raw, expected", [
    ("£51.77", 51.77),
    ("Â£53.74", 53.74),          # mis-decoded pound sign
    (" £1,234.50 ", 1234.5),
    ("£10", 10.0),
    ("-5.00", -5.0),             # sign kept so validation can reject it
    (12.345, 12.35),
    ("free", None),
    ("", None),
    (None, None),
])
def test_clean_price(raw, expected):
    assert clean_price(raw) == expected


# ---------- clean_rating ----------
@pytest.mark.parametrize("raw, expected", [
    ("star-rating Three", 3),
    ("star-rating five", 5),
    ("One", 1),
    ("4", 4),
    (2, 2),
    ("7", 7),                    # returned so validation rejects it
    ("star-rating", None),
    ("unknown", None),
    (None, None),
    (True, None),
])
def test_clean_rating(raw, expected):
    assert clean_rating(raw) == expected


# ---------- clean_tags ----------
@pytest.mark.parametrize("raw, expected", [
    (["Love", " life ", "love"], "life;love"),
    (["world", "change"], "change;world"),
    ("b; a ;b", "a;b"),
    ([], None),
    (["  "], None),
    (None, None),
])
def test_clean_tags(raw, expected):
    assert clean_tags(raw) == expected


# ---------- clean_description ----------
def test_clean_description_removes_more_suffix():
    assert clean_description("Great book.   ...more") == "Great book."
    assert clean_description("Great book...more") == "Great book"
    assert clean_description("Ends with dots...") == "Ends with dots..."
    assert clean_description(None) is None


# ---------- normalize_url ----------
@pytest.mark.parametrize("url, base, expected", [
    ("catalogue/page-2.html", "https://books.toscrape.com/",
     "https://books.toscrape.com/catalogue/page-2.html"),
    ("/page/2/", "https://quotes.toscrape.com/page/1/", "https://quotes.toscrape.com/page/2/"),
    ("HTTPS://Books.ToScrape.com/x#top", None, "https://books.toscrape.com/x"),
    ("https://quotes.toscrape.com", None, "https://quotes.toscrape.com/"),
    ("ftp://example.com/file", None, "ftp://example.com/file"),  # left for validation
    ("  ", None, None),
    (None, None, None),
])
def test_normalize_url(url, base, expected):
    assert normalize_url(url, base) == expected


# ---------- transforms (raw dict -> common model) ----------
def test_clean_book_maps_to_common_model():
    raw = {
        "title": "  A Light in the Attic ",
        "detail_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "price_raw": "£51.77",
        "rating_raw": "star-rating Three",
        "category_raw": "\n Poetry \n",
        "description_raw": "It's hard to imagine... ...more",
        "scraped_at": "2026-10-06T10:00:00+00:00",
    }
    rec = clean_book(raw)
    assert list(rec) == FIELDNAMES
    assert rec["source"] == config.BOOKS_SOURCE
    assert rec["name_or_title"] == "A Light in the Attic"
    assert rec["price"] == 51.77 and rec["rating"] == 3
    assert rec["category"] == "Poetry"
    assert rec["description"] == "It's hard to imagine..."
    assert rec["author"] is None and rec["tags"] is None


def test_clean_book_uses_detail_title_when_listing_title_missing():
    rec = clean_book({"title": None, "detail_title": "Full Title From H1"})
    assert rec["name_or_title"] == "Full Title From H1"


def test_clean_quote_maps_to_common_model():
    raw = {
        "text_raw": "“The world as we have created it is a process of our thinking.”",
        "author_raw": " Albert Einstein ",
        "tags_raw": ["world", "change"],
        "page_url": "https://quotes.toscrape.com/",
        "scraped_at": "2026-10-06T10:00:00+00:00",
    }
    rec = clean_quote(raw)
    assert rec["name_or_title"].startswith("The world as")
    assert not rec["name_or_title"].endswith("”")
    assert rec["author"] == "Albert Einstein"
    assert rec["tags"] == "change;world"
    assert rec["price"] is None and rec["rating"] is None and rec["category"] is None


def test_clean_records_turns_unexpected_errors_into_failures(monkeypatch):
    import processing.transform as transform

    def exploding_cleaner(raw):
        if raw["title"] == "Broken":
            raise ValueError("unexpected format")
        return clean_book(raw)

    monkeypatch.setitem(transform.CLEANERS, config.BOOKS_SOURCE, exploding_cleaner)
    records = [{"title": "Good", "price_raw": "£1"}, {"title": "Broken", "page_url": "u"}]
    cleaned, failures = clean_records(records, config.BOOKS_SOURCE)

    assert [r["name_or_title"] for r in cleaned] == ["Good"]
    assert len(failures) == 1
    assert failures[0]["name_or_title"] == "Broken"
    assert failures[0]["rejection_reasons"] == "cleaning_error: ValueError"
