"""End-to-end run of main.py against fake sites (no internet).

Checks the things a reviewer checks: all output files exist, both sources
appear in the CSV, invalid and duplicate records are counted, and the
numbers in summary_report.json reconcile with the CSV row count.
"""
import csv
import json

import config
from main import main
from tests.conftest import (BOOKS_HOME, QUOTES_PAGE_2, FakeSession,
                            book_article, books_listing, quote_div,
                            quotes_listing)


def run(tmp_path, site, *extra_args, failures=None):
    out = tmp_path / "output"
    log = tmp_path / "logs" / "scraper.log"
    exit_code = main(["--delay", "0", "--output-dir", str(out), "--log-file", str(log),
                      *extra_args], session=FakeSession(site, failures))
    with open(out / "final_dataset.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    summary = json.loads((out / "summary_report.json").read_text(encoding="utf-8"))
    return exit_code, rows, summary, out, log


def test_full_pipeline_happy_path(tmp_path, books_site, quotes_site):
    exit_code, rows, summary, out, log = run(tmp_path, {**books_site, **quotes_site})

    assert exit_code == 0
    assert {r["source"] for r in rows} == {config.BOOKS_SOURCE, config.QUOTES_SOURCE}
    assert len(rows) == summary["totals"]["final_record_count"] == 6
    assert summary["reconciliation"]["passed"] is True

    book = next(r for r in rows if r["name_or_title"] == "Tipping the Velvet")
    assert book["price"] == "53.74"          # 'Â£53.74' cleaned to a number
    assert book["rating"] == "1"
    assert book["category"] == "Historical Fiction"
    assert book["author"] == ""              # not applicable -> empty cell

    for name in ("rejected_records.csv", "duplicates.csv"):
        assert (out / name).exists()
    assert "Page 2" in log.read_text(encoding="utf-8")


def test_pipeline_counts_rejections_and_duplicates(tmp_path, books_site, quotes_site):
    site = {**books_site, **quotes_site}
    # Page 2 of quotes: a duplicate of a page-1 quote (different case/spacing)
    # and a quote with no author (invalid).
    site[QUOTES_PAGE_2] = quotes_listing([
        quote_div("“  THE WORLD AS WE HAVE CREATED IT is a process of our thinking.”",
                  "Albert  Einstein", ["world"]),
        '<div class="quote"><span class="text">“Anonymous wisdom.”</span></div>',
    ])
    _, rows, summary, out, _ = run(tmp_path, site, "--skip-book-details")
    quotes = summary["per_source"][config.QUOTES_SOURCE]

    assert quotes["raw_collected"] == 4
    assert quotes["rejected"] == 1
    assert quotes["rejected_by_reason"] == {"missing_author": 1}
    assert quotes["duplicates"] == 1
    assert quotes["final"] == 2
    assert quotes["reconciles"] is True
    assert summary["reconciliation"]["passed"] is True
    assert len(rows) == summary["totals"]["final_record_count"]

    with open(out / "duplicates.csv", encoding="utf-8") as f:
        dupes = list(csv.DictReader(f))
    assert dupes[0]["duplicate_of"] == "https://quotes.toscrape.com/"


def test_one_source_failing_does_not_stop_the_other(tmp_path, quotes_site):
    # Books home page keeps returning 503 (after retries in real life); quotes still run.
    exit_code, rows, summary, _, _ = run(tmp_path, quotes_site, failures={BOOKS_HOME: 503})

    assert exit_code == 0
    assert summary["per_source"][config.BOOKS_SOURCE]["pages_failed"] == 1
    assert summary["per_source"][config.QUOTES_SOURCE]["final"] == 3
    assert len(rows) == summary["totals"]["final_record_count"] == 3


def test_unexpected_crash_in_one_source_is_contained(tmp_path, books_site, quotes_site, monkeypatch):
    from scrapers.books_scraper import BooksScraper

    def boom(self):
        raise RuntimeError("bug in books scraper")

    monkeypatch.setattr(BooksScraper, "scrape", boom)
    _, rows, summary, _, _ = run(tmp_path, {**books_site, **quotes_site})

    assert summary["per_source"][config.BOOKS_SOURCE]["status"] == "failed"
    assert "RuntimeError" in summary["source_errors"][config.BOOKS_SOURCE]
    assert {r["source"] for r in rows} == {config.QUOTES_SOURCE}


def test_bad_book_price_is_rejected(tmp_path):
    site = {BOOKS_HOME: books_listing([
        book_article("Good Book", "catalogue/good_1/index.html", "£10.00", "Two"),
        book_article("Bad Price", "catalogue/bad_2/index.html", "£-3.00", "Two"),
    ])}
    _, rows, summary, _, _ = run(tmp_path, site, "--sources", "books", "--skip-book-details")

    assert [r["name_or_title"] for r in rows] == ["Good Book"]
    assert summary["totals"]["rejected_by_reason"] == {"invalid_price": 1}
