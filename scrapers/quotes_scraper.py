"""Scraper for https://quotes.toscrape.com/

Listing page (one record = div.quote):
  * quote text  -> span.text          (wrapped in curly quotes “ ”)
  * author      -> small.author
  * author page -> a[href^="/author/"] (relative)
  * tags        -> a.tag              (zero or more)
"""
from urllib.parse import urljoin

import config
from scrapers.base_scraper import BaseScraper


class QuotesScraper(BaseScraper):
    source_name = config.QUOTES_SOURCE
    start_url = config.QUOTES_START_URL
    item_selector = "div.quote"

    def parse_item(self, item, page_url: str) -> dict:
        text = item.select_one("span.text")
        author = item.select_one("small.author")
        author_link = item.select_one('a[href^="/author/"]')
        author_href = author_link.get("href") if author_link else None

        return {
            "text_raw": text.get_text() if text else None,
            "author_raw": author.get_text() if author else None,
            "tags_raw": [tag.get_text() for tag in item.select("a.tag")],
            # Collected for reference only; source_url uses the page URL (see README).
            "author_url": urljoin(page_url, author_href) if author_href else None,
        }
