"""The one common data model that both sources are converted into.

Fields that don't apply to a source stay None (an empty cell in the CSV).
We never invent values, e.g. a quote does not get price = 0.
"""
from dataclasses import asdict, dataclass, fields
from typing import Optional


@dataclass
class Record:
    source: str                          # "Books to Scrape" | "Quotes to Scrape"
    source_url: Optional[str]            # book detail page | page the quote appeared on
    name_or_title: Optional[str]         # book title | quote text
    category: Optional[str] = None       # books only (from the detail page)
    price: Optional[float] = None        # books only, e.g. 51.77 (GBP)
    rating: Optional[int] = None         # books only, 1-5
    author: Optional[str] = None         # quotes only
    tags: Optional[str] = None           # quotes only, "tag1;tag2"
    description: Optional[str] = None    # books only (from the detail page)
    scraped_at: Optional[str] = None     # UTC ISO-8601 timestamp

    def to_dict(self) -> dict:
        return asdict(self)


# Fixed column order for the CSV.
FIELDNAMES = [f.name for f in fields(Record)]
