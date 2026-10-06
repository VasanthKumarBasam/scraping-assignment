"""Entry point: scrape -> clean -> validate -> deduplicate -> write outputs.

Run:  python main.py            (full run, ~10-15 min because of book detail pages)
      python main.py --help     (all options)
"""
import argparse
import logging
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import config
from processing.deduplication import find_duplicates
from processing.output import data_quality_report, write_csv, write_json
from processing.schema import FIELDNAMES
from processing.transform import clean_records
from processing.validation import split_valid_invalid
from scrapers.base_scraper import create_session
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

logger = logging.getLogger("main")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Books to Scrape + Quotes to Scrape into one clean dataset.")
    parser.add_argument("--sources", nargs="+", choices=["books", "quotes"],
                        default=["books", "quotes"], help="Which sources to scrape (default: both).")
    parser.add_argument("--skip-book-details", action="store_true",
                        help="Don't open each book page. Much faster (~1 min) but "
                             "category and description stay empty.")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Stop after N listing pages per source (handy for quick tests).")
    parser.add_argument("--delay", type=float, default=config.REQUEST_DELAY,
                        help=f"Seconds between requests (default {config.REQUEST_DELAY}).")
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    parser.add_argument("--log-file", type=Path, default=config.LOG_FILE)
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def setup_logging(log_file: Path, level: str) -> None:
    """Log to the console and to a file (overwritten each run)."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):  # avoid duplicate lines if called twice
        root.removeHandler(handler)
        handler.close()
    for handler in (logging.FileHandler(log_file, mode="w", encoding="utf-8"),
                    logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    # Our LoggingRetry already reports every retry in a readable way;
    # this stops urllib3 from printing a second, noisier line for the same retry.
    logging.getLogger("urllib3").setLevel(logging.ERROR)


def build_scrapers(args, session) -> list:
    common = {"delay": args.delay, "max_pages": args.max_pages}
    available = {
        "books": lambda: BooksScraper(session, fetch_details=not args.skip_book_details, **common),
        "quotes": lambda: QuotesScraper(session, **common),
    }
    return [available[name]() for name in args.sources]


def run_source(scraper) -> dict:
    """Scrape, clean and validate one source. Returns everything main() needs."""
    raw = scraper.scrape()
    cleaned, cleaning_failures = clean_records(raw, scraper.source_name)
    valid, rejected, reasons = split_valid_invalid(cleaned)
    if cleaning_failures:
        rejected.extend(cleaning_failures)
        reasons["cleaning_error"] += len(cleaning_failures)
    logger.info("[%s] raw=%d, cleaned=%d, valid=%d, rejected=%d",
                scraper.source_name, len(raw), len(cleaned), len(valid), len(rejected))
    return {"raw": len(raw), "cleaned": len(cleaned), "valid": valid,
            "rejected": rejected, "reasons": reasons, "stats": scraper.stats}


def main(argv=None, session=None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_file, args.log_level)
    started_at = datetime.now(timezone.utc)
    timer = time.perf_counter()
    logger.info("Run started (sources=%s, book details=%s, max_pages=%s, delay=%.2fs)",
                args.sources, not args.skip_book_details, args.max_pages, args.delay)

    session = session or create_session()
    per_source: dict[str, dict] = {}
    source_errors: dict[str, str] = {}
    all_valid, all_rejected = [], []
    total_reasons = Counter()

    # Each source runs in its own try/except: if one blows up, the other still runs.
    for scraper in build_scrapers(args, session):
        name = scraper.source_name
        try:
            result = run_source(scraper)
        except Exception as exc:
            logger.exception("[%s] Source failed unexpectedly; continuing with the others", name)
            source_errors[name] = f"{type(exc).__name__}: {exc}"
            per_source[name] = {"status": "failed", **scraper.stats}
            continue

        all_valid.extend(result["valid"])
        all_rejected.extend(result["rejected"])
        total_reasons.update(result["reasons"])
        per_source[name] = {
            "status": "ok",
            **result["stats"],
            "raw_collected": result["raw"],
            "after_cleaning": result["cleaned"],
            "rejected": len(result["rejected"]),
            "rejected_by_reason": dict(result["reasons"]),
        }

    # Deduplicate after validation, so an invalid record can't "claim" a fingerprint.
    unique, duplicates = find_duplicates(all_valid)
    for name, stats in per_source.items():
        if stats["status"] != "ok":
            continue
        stats["duplicates"] = sum(1 for r in duplicates if r["source"] == name)
        stats["final"] = sum(1 for r in unique if r["source"] == name)
        stats["reconciles"] = (stats["raw_collected"] - stats["rejected"]
                               - stats["duplicates"] == stats["final"])

    # ---------- write outputs ----------
    out = args.output_dir
    paths = {
        "final_dataset": out / "final_dataset.csv",
        "summary_report": out / "summary_report.json",
        "rejected_records": out / "rejected_records.csv",
        "duplicates": out / "duplicates.csv",
        "log": args.log_file,
    }
    write_csv(paths["final_dataset"], unique, FIELDNAMES)
    write_csv(paths["rejected_records"], all_rejected, FIELDNAMES + ["rejection_reasons"])
    write_csv(paths["duplicates"], duplicates, FIELDNAMES + ["duplicate_of"])

    ok = [s for s in per_source.values() if s["status"] == "ok"]
    totals = {
        "raw_collected": sum(s["raw_collected"] for s in ok),
        "after_cleaning": sum(s["after_cleaning"] for s in ok),
        "rejected": len(all_rejected),
        "rejected_by_reason": dict(total_reasons),
        "duplicates": len(duplicates),
        "final_record_count": len(unique),
    }
    finished_at = datetime.now(timezone.utc)
    summary = {
        "run": {
            "started_at_utc": started_at.isoformat(timespec="seconds"),
            "finished_at_utc": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round(time.perf_counter() - timer, 2),
            "python_version": platform.python_version(),
            "settings": {
                "sources": args.sources,
                "book_details_fetched": not args.skip_book_details,
                "max_pages": args.max_pages,
                "delay_seconds": args.delay,
                "duplicate_handling": "removed from final dataset, listed in duplicates.csv",
            },
        },
        "per_source": per_source,
        "totals": totals,
        "reconciliation": {
            "rule": "raw_collected - rejected - duplicates = final_record_count",
            "passed": (totals["raw_collected"] - totals["rejected"] - totals["duplicates"]
                       == totals["final_record_count"]),
            "note": "rejected_by_reason can add up to more than 'rejected' "
                    "because one record can fail several rules",
        },
        "data_quality": data_quality_report(unique),
        "source_errors": source_errors,
        "output_files": {key: str(path) for key, path in paths.items()},
    }
    write_json(paths["summary_report"], summary)
    session.close()

    logger.info("Done in %.1fs: raw=%d, rejected=%d, duplicates=%d, final=%d (reconciles: %s)",
                summary["run"]["duration_seconds"], totals["raw_collected"], totals["rejected"],
                totals["duplicates"], totals["final_record_count"],
                summary["reconciliation"]["passed"])
    logger.info("Final dataset: %s", paths["final_dataset"])
    return 0 if unique else 1


if __name__ == "__main__":
    sys.exit(main())
