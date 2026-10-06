"""Shared test helpers: a fake HTTP session and small copies of the real pages.

The HTML below mirrors the structure of books.toscrape.com and
quotes.toscrape.com, so the scrapers can be tested with no internet.
"""
import pytest
import requests


class FakeResponse:
    def __init__(self, url, text, status_code=200):
        self.url = url
        self.text = text
        self.status_code = status_code
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error for url: {self.url}")


class FakeSession:
    """Returns canned HTML per URL.

    pages:    {url: html}
    failures: {url: exception instance or HTTP status code}
    Unknown URLs return 404.
    """

    def __init__(self, pages=None, failures=None):
        self.pages = pages or {}
        self.failures = failures or {}
        self.requested = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        failure = self.failures.get(url)
        if isinstance(failure, Exception):
            raise failure
        if isinstance(failure, int):
            return FakeResponse(url, "", failure)
        if url in self.pages:
            return FakeResponse(url, self.pages[url])
        return FakeResponse(url, "", 404)

    def close(self):
        pass


def book_article(title, href, price, rating_word):
    short = title if len(title) < 20 else title[:17] + "..."
    return f"""
    <article class="product_pod">
      <div class="image_container"><a href="{href}"><img src="x.jpg" alt="{title}"></a></div>
      <p class="star-rating {rating_word}"><i class="icon-star"></i></p>
      <h3><a href="{href}" title="{title}">{short}</a></h3>
      <div class="product_price">
        <p class="price_color">{price}</p>
        <p class="instock availability"><i class="icon-ok"></i> In stock</p>
      </div>
    </article>"""


def books_listing(articles, next_href=None):
    pager = f'<li class="next"><a href="{next_href}">next</a></li>' if next_href else ""
    return f"""<html><body><ol class="row">{''.join(articles)}</ol>
    <ul class="pager"><li class="current">Page x</li>{pager}</ul></body></html>"""


def book_detail(title, category, description):
    desc = (f'<div id="product_description" class="sub-header"><h2>Product Description</h2></div>'
            f'<p>{description}</p>') if description is not None else ""
    return f"""<html><body>
    <ul class="breadcrumb">
      <li><a href="../../index.html">Home</a></li>
      <li><a href="../category/books_1/index.html">Books</a></li>
      <li><a href="../category/books/x_1/index.html">{category}</a></li>
      <li class="active">{title}</li>
    </ul>
    <div class="col-sm-6 product_main"><h1>{title}</h1><p class="price_color">£1.00</p></div>
    {desc}
    </body></html>"""


def quote_div(text, author, tags):
    tag_html = "".join(f'<a class="tag" href="/tag/{t}/page/1/">{t}</a>' for t in tags)
    slug = author.replace(" ", "-")
    return f"""
    <div class="quote" itemscope itemtype="http://schema.org/CreativeWork">
      <span class="text" itemprop="text">{text}</span>
      <span>by <small class="author" itemprop="author">{author}</small>
      <a href="/author/{slug}">(about)</a></span>
      <div class="tags">Tags: <meta class="keywords" content="{','.join(tags)}"> {tag_html}</div>
    </div>"""


def quotes_listing(quotes, next_href=None):
    pager = f'<li class="next"><a href="{next_href}">Next <span>→</span></a></li>' if next_href else ""
    return f"""<html><body><div class="col-md-8">{''.join(quotes)}
    <nav><ul class="pager">{pager}</ul></nav></div></body></html>"""


BOOKS_HOME = "https://books.toscrape.com/"
BOOKS_PAGE_2 = "https://books.toscrape.com/catalogue/page-2.html"
QUOTES_HOME = "https://quotes.toscrape.com/"
QUOTES_PAGE_2 = "https://quotes.toscrape.com/page/2/"


@pytest.fixture
def books_site():
    """Two listing pages (2 + 1 books) and their detail pages.

    Note the real site's quirk: links on the home page start with
    'catalogue/', links on later pages don't, so urljoin must be used.
    """
    return {
        BOOKS_HOME: books_listing(
            [book_article("A Light in the Attic", "catalogue/a-light-in-the-attic_1000/index.html",
                          "£51.77", "Three"),
             book_article("Tipping the Velvet", "catalogue/tipping-the-velvet_999/index.html",
                          "Â£53.74", "One")],
            next_href="catalogue/page-2.html"),
        BOOKS_PAGE_2: books_listing(
            [book_article("Soumission", "soumission_998/index.html", "£50.10", "Five")]),
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html":
            book_detail("A Light in the Attic", "Poetry",
                        "It's hard to imagine a world without A Light in the Attic. ...more"),
        "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html":
            book_detail("Tipping the Velvet", "Historical Fiction", "Erotic and absorbing..."),
        "https://books.toscrape.com/catalogue/soumission_998/index.html":
            book_detail("Soumission", "Fiction", None),
    }


@pytest.fixture
def quotes_site():
    return {
        QUOTES_HOME: quotes_listing(
            [quote_div("“The world as we have created it is a process of our thinking.”",
                       "Albert Einstein", ["change", "deep-thoughts", "thinking", "world"]),
             quote_div("“It is our choices, Harry, that show what we truly are.”",
                       "J.K. Rowling", ["abilities", "choices"])],
            next_href="/page/2/"),
        QUOTES_PAGE_2: quotes_listing(
            [quote_div("“A day without sunshine is like, you know, night.”",
                       "Steve Martin", ["humor", "obvious", "simile"])]),
    }
