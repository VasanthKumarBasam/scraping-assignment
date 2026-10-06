import pytest

import config
from processing.validation import split_valid_invalid, validate_record


def make_book(**overrides):
    rec = {
        "source": config.BOOKS_SOURCE,
        "source_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "name_or_title": "A Light in the Attic",
        "price": 51.77,
        "rating": 3,
        "author": None,
    }
    rec.update(overrides)
    return rec


def make_quote(**overrides):
    rec = {
        "source": config.QUOTES_SOURCE,
        "source_url": "https://quotes.toscrape.com/",
        "name_or_title": "A day without sunshine is like, you know, night.",
        "author": "Steve Martin",
        "price": None,
        "rating": None,
    }
    rec.update(overrides)
    return rec


def test_valid_records_have_no_problems():
    assert validate_record(make_book()) == []
    assert validate_record(make_quote()) == []


def test_free_book_is_valid():
    assert validate_record(make_book(price=0.0)) == []


@pytest.mark.parametrize("overrides, reason", [
    ({"source": "Some Other Site"}, "unknown_source"),
    ({"name_or_title": None}, "missing_name"),
    ({"name_or_title": ""}, "missing_name"),
    ({"source_url": None}, "invalid_url"),
    ({"source_url": "catalogue/page-2.html"}, "invalid_url"),
    ({"source_url": "ftp://books.toscrape.com/x"}, "invalid_url"),
    ({"source_url": "https://"}, "invalid_url"),
    ({"price": -1.0}, "invalid_price"),
    ({"price": "51.77"}, "invalid_price"),
    ({"price": float("nan")}, "invalid_price"),
    ({"price": None}, "missing_price"),
    ({"rating": 0}, "invalid_rating"),
    ({"rating": 6}, "invalid_rating"),
    ({"rating": 4.5}, "invalid_rating"),
    ({"rating": True}, "invalid_rating"),   # True == 1 in Python, must still be rejected
    ({"rating": None}, "missing_rating"),
])
def test_book_rules(overrides, reason):
    assert reason in validate_record(make_book(**overrides))


def test_quote_requires_author():
    assert validate_record(make_quote(author=None)) == ["missing_author"]


def test_quote_without_price_or_rating_is_fine():
    # Books need price/rating, quotes don't: required fields are per source.
    assert "missing_price" not in validate_record(make_quote())


def test_multiple_problems_are_all_reported():
    problems = validate_record(make_book(name_or_title=None, source_url="bad", rating=9))
    assert set(problems) == {"missing_name", "invalid_url", "invalid_rating"}


def test_split_valid_invalid_counts_reasons():
    records = [make_book(), make_book(price=-5.0), make_quote(author=None),
               make_book(name_or_title=None, price=-1.0)]
    valid, rejected, reasons = split_valid_invalid(records)

    assert len(valid) == 1
    assert len(rejected) == 3
    assert reasons == {"invalid_price": 2, "missing_author": 1, "missing_name": 1}
    assert rejected[-1]["rejection_reasons"] == "missing_name;invalid_price"
