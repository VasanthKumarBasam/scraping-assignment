"""Shared networking and pagination logic used by every source scraper.

A source-specific scraper only has to say:
  * where to start            (start_url)
  * what one record looks like (item_selector)
  * how to read one record     (parse_item)
Everything else (HTTP session, retries, polite delay, following the "next"
link, error handling) lives here, so it is written and tested once.
"""
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

import config

logger = logging.getLogger(__name__)


class LoggingRetry(Retry):
    """urllib3's Retry, plus a WARNING log line every time a retry happens.

    urllib3 only logs status-code retries at DEBUG level, so without this
    the log would never show that a page needed retries.
    """

    def increment(self, method=None, url=None, response=None, error=None, *args, **kwargs):
        new_retry = super().increment(method, url, response, error, *args, **kwargs)
        reason = f"HTTP {response.status}" if response is not None else type(error).__name__
        logger.warning("Retrying %s %s after %s (%s retries left)", method, url, reason,
                       new_retry.total)
        return new_retry


def create_session(
    user_agent: str = config.USER_AGENT,
    max_retries: int = config.MAX_RETRIES,
    backoff_factor: float = config.BACKOFF_FACTOR,
) -> requests.Session:
    """Create one HTTP session that retries temporary failures automatically.

    Retries cover connection errors, read timeouts and the HTTP codes in
    config.RETRY_STATUS_CODES, with exponential backoff between attempts.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    retries = LoggingRetry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=config.RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        # After the last retry, hand back the final response instead of raising
        # urllib3's generic RetryError, so raise_for_status() reports the real code.
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def utc_now_iso() -> str:
    """Current UTC time, e.g. '2026-10-06T10:15:30+00:00'."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BaseScraper(ABC):
    """Template for a paginated listing scraper."""

    source_name: str = ""
    start_url: str = ""
    item_selector: str = ""
    next_selector: str = "li.next > a"  # same on both practice sites

    def __init__(self, session, delay=config.REQUEST_DELAY,
                 timeout=config.REQUEST_TIMEOUT, max_pages=None):
        self.session = session
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages
        self._last_request_at = None
        # Counters that end up in summary_report.json
        self.stats = {
            "pages_scraped": 0,
            "pages_failed": 0,
            "requests_failed": 0,
            "parse_errors": 0,
        }

    # ------------------------------------------------------------------ #
    # Networking
    # ------------------------------------------------------------------ #
    def _wait_politely(self) -> None:
        """Simple rate limiter: keep at least `delay` seconds between requests.

        If parsing the previous page already took that long, we don't sleep.
        """
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def fetch_soup(self, url: str):
        """Download a page and return parsed HTML, or None if it failed.

        Never raises for network/HTTP problems: the error is logged and the
        caller decides what to do (stop pagination, skip a detail page, ...).
        """
        self._wait_politely()
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()  # turns 404/500/... into an exception
        except requests.RequestException as exc:  # timeouts, connection errors, HTTP errors
            self.stats["requests_failed"] += 1
            logger.error("[%s] Request failed for %s (%s): %s",
                         self.source_name, url, type(exc).__name__, exc)
            return None
        finally:
            self._last_request_at = time.monotonic()

        # The sites are UTF-8 but don't always say so in the headers. Without
        # this, requests guesses ISO-8859-1 and '£' turns into 'Â£'.
        response.encoding = "utf-8"
        return BeautifulSoup(response.text, "lxml")

    # ------------------------------------------------------------------ #
    # Pagination
    # ------------------------------------------------------------------ #
    def next_page_url(self, soup, current_url: str):
        """Absolute URL of the next page, or None on the last page."""
        link = soup.select_one(self.next_selector)
        if link is None or not link.get("href"):
            return None
        # hrefs are relative ("catalogue/page-2.html", "/page/2/"), so resolve
        # them against the page we are on.
        return urljoin(current_url, link["href"])

    def scrape(self) -> list[dict]:
        """Follow 'next' links from start_url until there are none left.

        Returns raw records: text exactly as found on the page, plus
        page_url and scraped_at. Cleaning happens later, in processing/.
        """
        logger.info("[%s] Starting at %s", self.source_name, self.start_url)
        records: list[dict] = []
        visited: set[str] = set()
        url, page = self.start_url, 1

        while url:
            if self.max_pages is not None and page > self.max_pages:
                logger.info("[%s] Reached --max-pages=%d, stopping early",
                            self.source_name, self.max_pages)
                break
            if url in visited:  # protects against a "next" link that loops back
                logger.warning("[%s] Next link points to an already visited page (%s); stopping",
                               self.source_name, url)
                break
            visited.add(url)

            logger.info("[%s] Page %d: %s", self.source_name, page, url)
            soup = self.fetch_soup(url)
            if soup is None:
                # Without the page we can't see its "next" link, so we stop this
                # source. Records from earlier pages are kept, and the other
                # source still runs.
                self.stats["pages_failed"] += 1
                logger.error("[%s] Page %d could not be loaded after retries; stopping "
                             "pagination for this source (keeping %d records already collected)",
                             self.source_name, page, len(records))
                break

            scraped_at = utc_now_iso()
            items = soup.select(self.item_selector)
            if not items:
                logger.warning("[%s] No records found on %s (did the layout change?)",
                               self.source_name, url)

            for position, item in enumerate(items, start=1):
                try:
                    raw = self.parse_item(item, url)
                except Exception as exc:  # one broken record must not stop the run
                    self.stats["parse_errors"] += 1
                    logger.warning("[%s] Could not parse record %d on %s: %s",
                                   self.source_name, position, url, exc)
                    continue
                raw["page_url"] = url
                raw["scraped_at"] = scraped_at
                records.append(raw)

            self.stats["pages_scraped"] += 1
            logger.info("[%s] Page %d: %d records (total so far: %d)",
                        self.source_name, page, len(items), len(records))

            url = self.next_page_url(soup, url)
            page += 1

        logger.info("[%s] Pagination finished: %d pages, %d raw records",
                    self.source_name, self.stats["pages_scraped"], len(records))
        return records

    @abstractmethod
    def parse_item(self, item, page_url: str) -> dict:
        """Turn one HTML element into a raw dict (no cleaning here)."""
