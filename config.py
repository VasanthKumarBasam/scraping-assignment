"""Central settings for the scraper.

Everything that someone might want to tweak lives here, so no magic numbers
are scattered through the code. Most values can also be overridden with
command-line flags in main.py (run `python main.py --help`).
"""
from pathlib import Path

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_FILE = BASE_DIR / "logs" / "scraper.log"

# ---------- Sources ----------
BOOKS_SOURCE = "Books to Scrape"
QUOTES_SOURCE = "Quotes to Scrape"
BOOKS_START_URL = "https://books.toscrape.com/"
QUOTES_START_URL = "https://quotes.toscrape.com/"

# ---------- Networking ----------
USER_AGENT = "ScrapingAssignment/1.0 (learning project; python-requests)"
REQUEST_TIMEOUT = 10        # seconds to wait for a server response
REQUEST_DELAY = 0.5         # minimum seconds between two requests (politeness)
MAX_RETRIES = 3             # retries for connection errors and temporary HTTP errors
BACKOFF_FACTOR = 1.0        # urllib3 waits 0s, 2s, 4s between retries with this value
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

# ---------- Behaviour ----------
# Visiting each book's detail page gives us category and description,
# at the cost of ~1,000 extra requests (about 10 extra minutes at 0.5s each).
FETCH_BOOK_DETAILS = True

# Quotes are identified by author + the first N characters of the quote text.
QUOTE_FINGERPRINT_CHARS = 50
