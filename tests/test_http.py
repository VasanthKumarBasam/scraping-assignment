"""Networking tests against a tiny local web server (localhost only, no internet).

These go through the real requests + urllib3 retry stack, unlike the
FakeSession tests.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scrapers.base_scraper import create_session
from scrapers.quotes_scraper import QuotesScraper


@pytest.fixture
def server():
    """Serves /flaky (503 twice, then OK), /broken (always 500) and /pound (UTF-8, no charset)."""
    hits = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits[self.path] = hits.get(self.path, 0) + 1
            if self.path == "/flaky" and hits[self.path] <= 2:
                return self._send(503, b"")
            if self.path == "/broken":
                return self._send(500, b"")
            if self.path in ("/flaky", "/pound"):
                return self._send(200, '<p class="price_color">£51.77</p>'.encode("utf-8"))
            return self._send(404, b"")

        def _send(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "text/html")  # deliberately no charset
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", hits
    httpd.shutdown()
    httpd.server_close()


def make_scraper():
    session = create_session(max_retries=3, backoff_factor=0)  # no waiting in tests
    return QuotesScraper(session, delay=0, timeout=5)


def test_temporary_503_is_retried_then_succeeds(server, caplog):
    base, hits = server
    soup = make_scraper().fetch_soup(f"{base}/flaky")
    assert soup is not None
    assert hits["/flaky"] == 3                        # 2 failures + 1 success
    assert caplog.text.count("Retrying GET /flaky after HTTP 503") == 2


def test_permanent_error_gives_up_without_raising(server):
    base, hits = server
    scraper = make_scraper()
    assert scraper.fetch_soup(f"{base}/broken") is None
    assert hits["/broken"] == 4                       # 1 try + 3 retries
    assert scraper.stats["requests_failed"] == 1


def test_404_is_not_retried(server):
    base, hits = server
    assert make_scraper().fetch_soup(f"{base}/missing") is None
    assert hits["/missing"] == 1


def test_pound_sign_decoded_correctly_without_charset_header(server):
    base, _ = server
    soup = make_scraper().fetch_soup(f"{base}/pound")
    assert soup.select_one("p.price_color").get_text() == "£51.77"   # not 'Â£51.77'
