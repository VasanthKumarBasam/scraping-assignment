"""Scraper tests against saved HTML (no internet needed)."""
import requests

from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper
from tests.conftest import (BOOKS_HOME, BOOKS_PAGE_2, QUOTES_HOME,
                            QUOTES_PAGE_2, FakeSession, books_listing,
                            quotes_listing)


def make_books(session, **kwargs):
    return BooksScraper(session, delay=0, **kwargs)


def make_quotes(session, **kwargs):
    return QuotesScraper(session, delay=0, **kwargs)


# ---------- pagination ----------
def test_books_follows_next_links_across_pages(books_site):
    session = FakeSession(books_site)
    records = make_books(session, fetch_details=False).scrape()

    assert [r["title"] for r in records] == ["A Light in the Attic", "Tipping the Velvet", "Soumission"]
    # Page 2 was reached by following the relative link, not by building the URL.
    assert session.requested == [BOOKS_HOME, BOOKS_PAGE_2]


def test_books_relative_links_resolve_on_every_page(books_site):
    records = make_books(FakeSession(books_site), fetch_details=False).scrape()
    assert records[0]["detail_url"] == \
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    # On page 2 the href has no 'catalogue/' prefix; urljoin still gets it right.
    assert records[2]["detail_url"] == "https://books.toscrape.com/catalogue/soumission_998/index.html"


def test_quotes_follows_next_links_and_stops_on_last_page(quotes_site):
    session = FakeSession(quotes_site)
    scraper = make_quotes(session)
    records = scraper.scrape()

    assert len(records) == 3
    assert session.requested == [QUOTES_HOME, QUOTES_PAGE_2]
    assert scraper.stats["pages_scraped"] == 2


def test_max_pages_limits_pagination(quotes_site):
    session = FakeSession(quotes_site)
    records = make_quotes(session, max_pages=1).scrape()
    assert len(records) == 2 and session.requested == [QUOTES_HOME]


def test_next_link_loop_is_detected():
    looping = {QUOTES_HOME: quotes_listing([], next_href="/")}
    session = FakeSession(looping)
    make_quotes(session).scrape()
    assert session.requested == [QUOTES_HOME]  # did not loop forever


# ---------- parsing ----------
def test_book_raw_fields(books_site):
    first = make_books(FakeSession(books_site), fetch_details=False).scrape()[0]
    assert first["title"] == "A Light in the Attic"   # full title from the title attribute
    assert first["price_raw"] == "£51.77"
    assert first["rating_raw"] == "star-rating Three"
    assert first["page_url"] == BOOKS_HOME
    assert first["scraped_at"].endswith("+00:00")


def test_quote_raw_fields(quotes_site):
    first = make_quotes(FakeSession(quotes_site)).scrape()[0]
    assert first["text_raw"].startswith("“The world")
    assert first["author_raw"] == "Albert Einstein"
    assert first["tags_raw"] == ["change", "deep-thoughts", "thinking", "world"]
    assert first["author_url"] == "https://quotes.toscrape.com/author/Albert-Einstein"


def test_missing_elements_give_none_instead_of_crashing():
    html = books_listing(['<article class="product_pod"><h3>No link here</h3></article>'])
    records = make_books(FakeSession({BOOKS_HOME: html}), fetch_details=False).scrape()
    assert records[0]["title"] is None
    assert records[0]["price_raw"] is None
    assert records[0]["detail_url"] is None


def test_quote_without_tags():
    html = quotes_listing(['<div class="quote"><span class="text">“Hi”</span>'
                           '<small class="author">Someone</small></div>'])
    record = make_quotes(FakeSession({QUOTES_HOME: html})).scrape()[0]
    assert record["tags_raw"] == [] and record["author_url"] is None


# ---------- detail pages ----------
def test_book_details_add_category_and_description(books_site):
    records = make_books(FakeSession(books_site), fetch_details=True).scrape()
    assert records[0]["category_raw"] == "Poetry"
    assert records[0]["description_raw"].endswith("...more")   # cleaned later
    assert records[2]["description_raw"] is None                # book with no description


def test_failed_detail_page_keeps_the_book(books_site):
    detail = "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"
    session = FakeSession(books_site, failures={detail: 503})
    scraper = make_books(session, fetch_details=True)
    records = scraper.scrape()

    assert len(records) == 3
    assert records[1]["category_raw"] is None
    assert scraper.stats["detail_pages_failed"] == 1


# ---------- failures ----------
def test_failed_page_stops_source_but_keeps_earlier_records(books_site):
    session = FakeSession(books_site, failures={BOOKS_PAGE_2: requests.Timeout("timed out")})
    scraper = make_books(session, fetch_details=False)
    records = scraper.scrape()

    assert len(records) == 2                      # page 1 records survive
    assert scraper.stats["pages_failed"] == 1
    assert scraper.stats["requests_failed"] == 1


def test_connection_error_on_first_page_returns_empty_list():
    session = FakeSession(failures={QUOTES_HOME: requests.ConnectionError("no network")})
    scraper = make_quotes(session)
    assert scraper.scrape() == []
    assert scraper.stats["pages_failed"] == 1


def test_http_error_status_is_handled():
    scraper = make_quotes(FakeSession(failures={QUOTES_HOME: 500}))
    assert scraper.scrape() == []


def test_one_bad_record_does_not_stop_the_page(quotes_site, monkeypatch):
    scraper = make_quotes(FakeSession(quotes_site))
    original = QuotesScraper.parse_item
    calls = {"n": 0}

    def flaky(self, item, page_url):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("unexpected markup")
        return original(self, item, page_url)

    monkeypatch.setattr(QuotesScraper, "parse_item", flaky)
    records = scraper.scrape()
    assert len(records) == 2
    assert scraper.stats["parse_errors"] == 1
