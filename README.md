# Multi-Source Web Scraping & Data Consolidation

A Python ETL pipeline that scrapes **Books to Scrape** and **Quotes to Scrape**, converts both into one common data model, cleans and validates every record, removes duplicates, and writes one consolidated CSV plus a summary report.

```
Books to Scrape  ─┐
Quotes to Scrape ─┴─> Scrape -> Clean -> Validate -> Deduplicate -> Consolidate -> output/
```

One command runs everything: `python main.py`

---

## 1. Python version

Developed and tested with **Python 3.11 / 3.12**. Any version from **3.10 to 3.12** works (`requests` and `pytest` need 3.10+).

## 2. Setup

**Option A: venv (any OS)**

```bash
cd scraping_assignment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Option B: Anaconda / Miniconda**

```bash
cd scraping_assignment
conda create -n scraping python=3.11 -y
conda activate scraping
pip install -r requirements.txt
```

**Option C: Docker (optional)**

```bash
docker build -t scraping-assignment .
docker run --rm -v "$(pwd)/output:/app/output" -v "$(pwd)/logs:/app/logs" scraping-assignment
```

## 3. Dependencies

| Library | Version | Why |
| --- | --- | --- |
| `requests` | 2.33.1 | Downloads pages; `Session` reuses connections |
| `urllib3` | 2.6.3 | `Retry` class for automatic retries with exponential backoff |
| `beautifulsoup4` | 4.14.3 | Finds elements in the HTML with CSS selectors |
| `lxml` | 6.0.2 | Fast HTML parser used by BeautifulSoup |
| `pytest` | 9.1.1 | Runs the tests (not needed to run the scraper) |

Everything else (`csv`, `json`, `logging`, `re`, `hashlib`, `unicodedata`, `urllib.parse`, `pathlib`, `argparse`, `dataclasses`) is standard library.

**Why Requests + BeautifulSoup and not Selenium/Playwright/Scrapy?** Both sites are plain server-rendered HTML with no JavaScript needed to show the data. A browser tool would only add startup time and memory. Scrapy would work but is a whole framework for a ~1,060-request job; Requests + BeautifulSoup keeps the code small and easy to follow.

## 4. How to run

```bash
python main.py                                  # full run (both sites + book detail pages), ~20-25 min
python main.py --skip-book-details              # fast run (~1 min), category/description left empty
python main.py --max-pages 2                    # quick smoke test: 2 listing pages per source
python main.py --sources quotes                 # only one source
python main.py --help                           # all options
pytest                                          # run the 103 tests (no internet needed)
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--sources` | `books quotes` | Which sites to scrape |
| `--skip-book-details` | off | Don't visit each book's detail page |
| `--max-pages N` | no limit | Stop after N listing pages per source |
| `--delay S` | `0.5` | Minimum seconds between requests |
| `--output-dir` | `output/` | Where the CSV/JSON files go |
| `--log-file` | `logs/scraper.log` | Log file path (overwritten each run) |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Other settings (timeout, retries, backoff, user agent) are in `config.py`.

**Why the full run takes ~20-25 minutes:** the book listing pages do not show category or description, so the scraper opens all ~1,000 book detail pages. Each one costs the 0.5 s politeness pause plus the network round trip; in the real run that averaged ~1.3 s per page, and the whole run took 1,368 s (~23 min).

## 5. Site observations (Step 1)

| Item | Books to Scrape | Quotes to Scrape |
| --- | --- | --- |
| One record | `article.product_pod` | `div.quote` |
| Main text | `h3 > a`, **`title` attribute** (visible text is truncated with `...`) | `span.text` (wrapped in curly quotes `“ ”`) |
| Price | `p.price_color`, e.g. `£51.77` | n/a |
| Rating | 2nd class of `p.star-rating`, e.g. `Three` | n/a |
| Author | n/a | `small.author` |
| Tags | n/a | `a.tag` (0 or more) |
| Record link | `h3 > a[href]` (relative) | `a[href^="/author/"]` (author page) |
| Category / description | Only on the detail page: breadcrumb (3rd link) and the `<p>` after `#product_description` | n/a |
| Next page | `li.next > a` | `li.next > a` |
| Size | 50 pages × 20 = 1,000 books | 10 pages × 10 = 100 quotes |

Other things worth knowing:

- **Relative links change shape.** On the books home page links start with `catalogue/` (`catalogue/page-2.html`); on later pages they don't (`page-3.html`). Building URLs by string concatenation breaks; `urljoin(current_page_url, href)` handles both.
- **Encoding.** The books site doesn't always send a charset header, so `requests` guesses ISO-8859-1 and `£` becomes `Â£`. Fix: `response.encoding = "utf-8"` before reading the text.
- **Descriptions end with `...more`**, which is display text, not part of the description.
- **Some books have no description** on their detail page. That's real data, so it stays empty.

## 6. How pagination works

Implemented once in `BaseScraper.scrape()` and used by both scrapers:

1. Start at the home page.
2. Download and parse it; read every record on the page.
3. Look for `li.next > a`. If found, turn its relative `href` into a full URL with `urljoin` and repeat. If not found, that was the last page.

No page numbers or page counts are hard-coded, so it keeps working if the site gains or loses pages. Two safety nets: a `visited` set stops the loop if a "next" link ever points back to a page already seen, and `--max-pages` gives a hard upper limit.

## 7. Data model

Defined as a dataclass in `processing/schema.py`. Every row in the CSV has the same columns, in this order:

| Column | Books | Quotes |
| --- | --- | --- |
| `source` | `Books to Scrape` | `Quotes to Scrape` |
| `source_url` | Book detail page URL | URL of the listing page the quote appeared on |
| `name_or_title` | Full book title | Quote text without the wrapping quote marks |
| `category` | From the detail page breadcrumb | empty |
| `price` | Number in GBP, e.g. `51.77` | empty |
| `rating` | Integer 1-5 | empty |
| `author` | empty | Author name |
| `tags` | empty | `tag1;tag2` (lowercase, sorted) |
| `description` | From the detail page | empty |
| `scraped_at` | UTC ISO-8601 time the listing page was fetched | same |

**Missing values:** `None` in Python, empty cell in the CSV. Fields that don't apply to a source are left empty rather than filled with fake values (a quote never gets `price = 0`).

**Why the page URL as `source_url` for quotes?** It is the exact page the record was collected from, so anyone can open it and find the quote. The author page describes the author, not the quote. (The author URL is still collected in the raw record.)

## 8. Cleaning approach

The scrapers return **raw** text exactly as found. All cleaning lives in `processing/cleaning.py` as small pure functions (value in, value out, no internet), and `processing/transform.py` maps each source's raw fields to the common model.

| Function | Example |
| --- | --- |
| `clean_text` | `"  Hello \n\xa0World "` -> `"Hello World"`; empty string -> `None` |
| `strip_quotes` | `"“Hello”"` -> `"Hello"` (only the outer pair; quotes inside the text are kept) |
| `clean_price` | `"£51.77"` -> `51.77`, `"Â£1,234.50"` -> `1234.5`, `"free"` -> `None` |
| `clean_rating` | `"star-rating Three"` -> `3`, `"4"` -> `4`, unknown -> `None` |
| `clean_tags` | `["Love", " life ", "love"]` -> `"life;love"` |
| `clean_description` | trims whitespace and the trailing `...more` |
| `normalize_url` | resolves relative links, lowercases scheme and host, drops `#fragment` |

Design choices:

- **Cleaning never hides bad data.** `clean_price("-5")` returns `-5.0` (not `5.0`) and `clean_rating("7")` returns `7` (not `None`), so validation rejects them with an explicit reason instead of the problem disappearing silently.
- **One "missing" representation.** Every cleaner turns empty/blank input into `None`.
- If cleaning a record throws an unexpected error, that record is rejected with reason `cleaning_error` and the run continues.

## 9. Validation approach

`processing/validation.py` checks every cleaned record and returns a **list of problems** (empty = valid), so the summary can count rejections per reason.

| Rule | Reason code |
| --- | --- |
| `source` is one of the two known sources | `unknown_source` |
| `name_or_title` is not empty | `missing_name` |
| `source_url` has `http`/`https` scheme and a host | `invalid_url` |
| Books must have a price and a rating | `missing_price`, `missing_rating` |
| Quotes must have an author | `missing_author` |
| Price, if present, is a real number ≥ 0 (not text, not NaN) | `invalid_price` |
| Rating, if present, is an integer 1-5 | `invalid_rating` |

Note: `True` and `5.0` are rejected as ratings. In Python `True == 1` and `5.0 == 5`, so a check like `rating in (1, 2, 3, 4, 5)` would wrongly accept them.

Rejected records are logged as warnings and written to `output/rejected_records.csv` with a `rejection_reasons` column.

## 10. Deduplication approach

`processing/deduplication.py` builds a **fingerprint** for each valid record:

1. **Identifying fields**
   - Books: `source` + `title`
   - Quotes: `source` + `author` + first **50 characters** of the quote text
2. **Normalize** each field: Unicode NFKC (folds look-alike characters), `casefold()` (lowercase), remove punctuation, collapse whitespace.
3. Join the fields with `|` and hash with **SHA-256**.

Records with the same fingerprint are duplicates; the first one seen is kept. So `"Example Book Title"`, `" Example Book Title "` and `"EXAMPLE BOOK TITLE"` are one record.

Details that matter:

- **Normalize first, then take 50 characters.** Slicing the raw text first would let a leading space or quote mark shift the window and miss a match.
- **Author is part of the quote key** so the same words attributed to two different people stay separate.
- **Source is part of every key**, so a book and a quote can never be duplicates of each other.
- **Deduplication runs after validation**, so an invalid record can't "claim" a fingerprint and cause a valid copy to be dropped.

**Remove or flag?** Duplicates are **removed** from `final_dataset.csv` (so it can be used directly, one row per real item) but **not thrown away**: they're written to `output/duplicates.csv` with a `duplicate_of` column pointing at the kept record's URL. That gives a clean dataset and a full audit trail.

**Result on the real sites: 1 duplicate.** The reference material predicted 0, but Books to Scrape has two separate product pages with the exact title *The Star-Touched Queen*. Under the title-based rule they are one record, so the first listing (`the-star-touched-queen_764`) is kept and the second is moved to `duplicates.csv`. Quotes to Scrape had no duplicates. This is exactly why duplicates are kept in a separate file instead of being deleted silently: the decision can be reviewed.

The logic is also proven by `tests/test_deduplication.py` and `tests/test_pipeline.py`, which use deliberately duplicated records (including the exact three variants from the assignment brief).

## 11. Error-handling approach

| Failure | What happens |
| --- | --- |
| Timeout, connection error, HTTP 429/500/502/503/504 | Retried automatically up to 3 times with exponential backoff (urllib3 `Retry`; waits 0 s, 2 s, 4 s). `Retry-After` headers are respected. Every retry is logged as a WARNING. |
| Page still failing after retries | Logged as ERROR. That source stops paginating (the "next" link is on the page we couldn't load), **records already collected are kept**, and the other source still runs. |
| 404 and other non-temporary errors | Not retried; logged as ERROR. |
| Book detail page fails | Book is kept with empty category/description; counted as `detail_pages_failed`. |
| Missing HTML element | `select_one()` returns `None`; every field is checked before use, so the field becomes `None` instead of crashing. |
| One record fails to parse | Logged, counted as `parse_errors`, skipped; the rest of the page continues. |
| Unexpected value format | Cleaning returns `None` or the record is rejected by validation with a reason. |
| Unexpected crash inside one source | Caught in `main.py`; logged with traceback, reported in `summary_report.json` under `source_errors`; other sources still run. |

**Politeness:** a simple rate limiter guarantees at least 0.5 s between requests, and the session sends an honest User-Agent.

## 12. Output description

| File | Contents |
| --- | --- |
| `output/final_dataset.csv` | One row per valid, unique record from both sites (UTF-8). 1,099 rows in the real run (999 books + 100 quotes). |
| `output/summary_report.json` | Per-source and total counts (see below), run time, settings, data-quality stats, errors |
| `output/rejected_records.csv` | Records that failed validation, with `rejection_reasons` (header only if none) |
| `output/duplicates.csv` | Removed duplicates, with `duplicate_of` (header only if none) |
| `logs/scraper.log` | Timestamped log of every page, retry, warning and error |

`summary_report.json` sections:

- `run`: start/end time (UTC), duration, Python version, settings used
- `per_source`: `pages_scraped`, `pages_failed`, `requests_failed`, `parse_errors`, `detail_pages_failed`, `raw_collected`, `after_cleaning`, `rejected`, `rejected_by_reason`, `duplicates`, `final`, `reconciles`
- `totals`: the same counts across both sources, plus `final_record_count`
- `reconciliation`: checks **raw_collected - rejected - duplicates = final_record_count** (and `final_record_count` equals the CSV row count)
- `data_quality`: empty values per column, price min/max/average, rating distribution, distinct categories/authors/tags
- `source_errors`: any source that crashed

### Results of the real run

| Metric | Books to Scrape | Quotes to Scrape | Total |
| --- | --- | --- | --- |
| Listing pages scraped (via "next" links) | 50 | 10 | 60 |
| Book detail pages fetched | 1,000 | n/a | 1,000 |
| Failed pages / retries needed | 0 | 0 | 0 |
| Raw records collected | 1,000 | 100 | 1,100 |
| Rejected by validation | 0 | 0 | 0 |
| Duplicates removed | 1 | 0 | 1 |
| **Final records** | **999** | **100** | **1,099** |

Run time: 1,368 s (~23 min). Reconciliation check passed (1,100 - 0 - 1 = 1,099, equal to the CSV row count).

Checks on the final CSV:

- Prices are all numeric, from 10.00 to 59.99 (average 35.07); ratings are all integers 1-5.
- All 999 books have a category (50 distinct categories); 2 books have no description because their product page has none.
- No mis-decoded characters (`Â£`, non-breaking spaces), no leftover `...more`, no quote text still wrapped in quote marks.
- Fields that don't apply are empty: no book has an author or tags, no quote has a price, rating or category.
- 50 distinct quote authors; 3 quotes have no tags because they have none on the site.
- 999 distinct book URLs; every `source_url` is a valid https URL.

## 13. Testing

```bash
pytest          # 103 tests, ~2 seconds, no internet needed
```

| File | What it proves |
| --- | --- |
| `test_cleaning.py` | Every cleaner on normal, messy and empty input; raw -> common model mapping |
| `test_validation.py` | Every rule and reason code, including edge cases (`True`, `5.0`, NaN, relative URLs) |
| `test_deduplication.py` | Case/space/punctuation-insensitive matching, the brief's 3 examples, quote 50-char rule, no false matches |
| `test_scrapers.py` | Pagination via "next" links, relative URL quirks, missing elements, failed pages/detail pages, loop protection (saved HTML, fake session) |
| `test_http.py` | Real `requests` + retry stack against a local test server: 503 retried then succeeds, permanent 500 gives up cleanly, 404 not retried, `£` decoded correctly |
| `test_pipeline.py` | Whole `main.py` run end to end: output files exist, both sources present, rejections and duplicates counted, numbers reconcile, one failing source doesn't stop the other |

Manual checks after a real run: open the CSV and confirm both sources are present, prices are numbers, ratings are 1-5, and the JSON `final_record_count` matches the CSV row count.

## 14. Project structure

```
scraping_assignment/
├── main.py                    # entry point: runs every stage in order, writes outputs
├── config.py                  # all settings in one place
├── scrapers/                  # everything that talks to websites
│   ├── base_scraper.py        # session, retries, rate limit, pagination loop
│   ├── books_scraper.py       # Books to Scrape selectors + detail pages
│   └── quotes_scraper.py      # Quotes to Scrape selectors
├── processing/                # everything that only transforms data
│   ├── schema.py              # common data model (dataclass + column order)
│   ├── cleaning.py            # small pure cleaning functions
│   ├── transform.py           # raw source dict -> common model
│   ├── validation.py          # rules -> list of reasons
│   ├── deduplication.py       # fingerprints + duplicate detection
│   └── output.py              # CSV/JSON writers + data-quality stats
├── tests/                     # 103 offline tests
├── output/                    # generated results
├── logs/                      # generated log
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── README.md
└── AI_USAGE.md
```

Rule of thumb: touches the internet -> `scrapers/`; only transforms data -> `processing/`; connects the stages -> `main.py`.

## 15. Assumptions

- Prices on Books to Scrape are in GBP; the currency symbol is dropped and the number kept.
- The listing-page title attribute is the authoritative book title (the detail page `<h1>` is a fallback).
- `scraped_at` is the time the listing page was fetched, in UTC.
- A book without a price or rating is not usable and is rejected; a book without a description is valid (some real books have none).
- Tags are lowercased and sorted so the same set of tags always looks the same.

## 16. Known limitations

- **A page that fails after all retries ends pagination for that source**, because the next link lives on that page. URL patterns (`page-N.html`) could be used to skip ahead, but that would be hard-coding the site structure, which the assignment asks us to avoid.
- **Title-only book keys:** two books with the same title are treated as one record, even if they are separate product pages. This happened once in the real run (*The Star-Touched Queen*). The removed listing is kept in `duplicates.csv` so it's visible; if same-title books had to be kept apart, the UPC from the detail page could be added to the key.
- **Requests are sequential.** With the 0.5 s politeness delay plus network time, a full run takes ~20-25 minutes. Concurrency wouldn't help much without also relaxing the delay.
- **No author details for quotes** (birth date, bio). The author page URL is collected, but those pages aren't scraped because the common schema has no fields for them.
- **No incremental scraping/resume:** each run starts from scratch and overwrites the outputs.
- Selectors are tied to the current HTML. If the layout changes, records come back empty and are rejected by validation, and "No records found" warnings appear in the log, so the failure is loud rather than silent.

## 17. What I'd change for a regular production run

- Store results in PostgreSQL with a unique index on the fingerprint, so re-runs upsert instead of overwriting files.
- Incremental runs: skip detail pages already scraped (by URL) and keep a checkpoint so a crash can resume.
- Schedule it (cron, Airflow) and alert when `pages_failed` or the rejection rate goes above a threshold.
- Add contract tests that fetch one live page and fail fast if selectors stop matching.
- Use a bounded thread pool with a shared rate limiter for the detail pages, only if the site owner allows a higher request rate.

## 18. AI usage summary

AI (Claude by Anthropic) was used to generate the initial implementation, tests and documentation. All code was reviewed, run and tested before submission. See **AI_USAGE.md** for tools, prompts, what was changed, problems found, and how the result was verified.
