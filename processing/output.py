"""Writing results to disk + a small data-quality report."""
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import config
from processing.schema import FIELDNAMES


def write_csv(path: Path, records: list[dict], fieldnames: list[str]) -> None:
    """Write records with a fixed column order. None becomes an empty cell."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def data_quality_report(records: list[dict]) -> dict:
    """Per-source fill rates and simple stats for the final dataset."""
    by_source = defaultdict(list)
    for rec in records:
        by_source[rec["source"]].append(rec)

    report = {}
    for source, recs in by_source.items():
        report[source] = {
            "records": len(recs),
            "empty_values_per_column": {
                field: sum(1 for r in recs if r.get(field) in (None, ""))
                for field in FIELDNAMES
            },
        }

    books = by_source.get(config.BOOKS_SOURCE, [])
    prices = [r["price"] for r in books if r.get("price") is not None]
    if prices:
        report[config.BOOKS_SOURCE]["price_gbp"] = {
            "min": min(prices),
            "max": max(prices),
            "average": round(statistics.mean(prices), 2),
        }
    ratings = Counter(r["rating"] for r in books if r.get("rating") is not None)
    if ratings:
        report[config.BOOKS_SOURCE]["rating_distribution"] = {
            str(k): ratings[k] for k in sorted(ratings)
        }
    categories = {r["category"] for r in books if r.get("category")}
    if books:
        report[config.BOOKS_SOURCE]["distinct_categories"] = len(categories)

    quotes = by_source.get(config.QUOTES_SOURCE, [])
    if quotes:
        tags = {t for r in quotes if r.get("tags") for t in r["tags"].split(";")}
        report[config.QUOTES_SOURCE]["distinct_authors"] = len(
            {r["author"] for r in quotes if r.get("author")})
        report[config.QUOTES_SOURCE]["distinct_tags"] = len(tags)

    return report
