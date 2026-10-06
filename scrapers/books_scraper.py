"""Scraper for https://books.toscrape.com/

Listing page (one record = article.product_pod):
  * full title   -> h3 > a[title]   (the visible link text is cut off with "...")
  * detail link  -> h3 > a[href]    (relative)
  * price        -> p.price_color   e.g. "£51.77"
  * rating       -> class of p.star-rating, e.g. ["star-rating", "Three"]

Detail page (only if fetch_details is True):
  * category     -> 3rd link in ul.breadcrumb  (Home > Books > <Category>)
  * description  -> the <p> right after div#product_description
  * full title   -> div.product_main h1        (fallback if the listing title is missing)
"""
import logging
from urllib.parse import urljoin

import config
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class BooksScraper(BaseScraper):
    source_name = config.BOOKS_SOURCE
    start_url = config.BOOKS_START_URL
    item_selector = "article.product_pod"

    def __init__(self, session, fetch_details: bool = config.FETCH_BOOK_DETAILS, **kwargs):
        super().__init__(session, **kwargs)
        self.fetch_details = fetch_details
        self.stats["detail_pages_failed"] = 0

    def parse_item(self, item, page_url: str) -> dict:
        link = item.select_one("h3 > a")
        price = item.select_one("p.price_color")
        rating = item.select_one("p.star-rating")
        href = link.get("href") if link else None

        return {
            "title": link.get("title") if link else None,
            "detail_url": urljoin(page_url, href) if href else None,
            "price_raw": price.get_text() if price else None,
            # BeautifulSoup gives the class attribute as a list; join it into
            # one string ("star-rating Three") and let the cleaner find the word.
            "rating_raw": " ".join(rating.get("class", [])) if rating else None,
            "category_raw": None,
            "description_raw": None,
            "detail_title": None,
        }

    def scrape(self) -> list[dict]:
        records = super().scrape()
        if self.fetch_details and records:
            self._add_details(records)
        return records

    def _add_details(self, records: list[dict]) -> None:
        """Visit each book page to fill in category and description.

        A failed detail page is not fatal: the book is kept with empty
        category/description and the failure is counted and logged.
        """
        total = len(records)
        logger.info("[%s] Fetching %d book detail pages for category + description "
                    "(this is the slow part)", self.source_name, total)

        for position, record in enumerate(records, start=1):
            url = record.get("detail_url")
            if url:
                soup = self.fetch_soup(url)
                if soup is None:
                    self.stats["detail_pages_failed"] += 1
                    logger.warning("[%s] Detail page failed, keeping book without "
                                   "category/description: %s", self.source_name, url)
                else:
                    try:
                        record.update(self.parse_detail(soup))
                    except Exception as exc:
                        self.stats["parse_errors"] += 1
                        logger.warning("[%s] Could not parse detail page %s: %s",
                                       self.source_name, url, exc)

            if position % 50 == 0 or position == total:
                logger.info("[%s] Detail pages: %d/%d done", self.source_name, position, total)

    @staticmethod
    def parse_detail(soup) -> dict:
        crumbs = soup.select("ul.breadcrumb li a")
        description = soup.select_one("#product_description + p")
        heading = soup.select_one("div.product_main h1")
        return {
            # Breadcrumb links: Home > Books > <Category>. The title is plain text, not a link.
            "category_raw": crumbs[2].get_text() if len(crumbs) >= 3 else None,
            # Some books genuinely have no description; that stays None.
            "description_raw": description.get_text() if description else None,
            "detail_title": heading.get_text() if heading else None,
        }
