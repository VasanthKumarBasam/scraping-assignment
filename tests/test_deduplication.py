"""The real sites contain no duplicates, so these tests use deliberately
duplicated records to prove the logic works."""
import config
from processing.deduplication import find_duplicates, make_fingerprint, normalize_key

BOOK = config.BOOKS_SOURCE
QUOTE = config.QUOTES_SOURCE


def book(title, url="https://books.toscrape.com/x"):
    return {"source": BOOK, "name_or_title": title, "author": None, "source_url": url}


def quote(text, author, url="https://quotes.toscrape.com/"):
    return {"source": QUOTE, "name_or_title": text, "author": author, "source_url": url}


def test_normalize_key():
    assert normalize_key("  The  Book: Vol. 1 ") == "the book vol 1"
    assert normalize_key(None) == ""


def test_assignment_example_case_and_spacing():
    """The exact three variants from the assignment brief count as one record."""
    records = [book("Example Book Title", "https://a/1"),
               book(" Example Book Title ", "https://a/2"),
               book("EXAMPLE BOOK TITLE", "https://a/3")]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 1 and len(dupes) == 2
    assert unique[0]["source_url"] == "https://a/1"               # first one is kept
    assert all(d["duplicate_of"] == "https://a/1" for d in dupes)


def test_punctuation_and_unicode_width_are_ignored():
    assert make_fingerprint(book("Sapiens: A Brief History")) == \
        make_fingerprint(book("Sapiens - A Brief History"))
    # Full-width letters are folded to normal ones by NFKC normalization.
    assert make_fingerprint(book("ＢＯＯＫ")) == make_fingerprint(book("book"))


def test_different_titles_are_not_duplicates():
    unique, dupes = find_duplicates([book("Book One"), book("Book Two")])
    assert len(unique) == 2 and dupes == []


def test_quotes_match_on_author_and_first_50_chars():
    text = "The world as we have created it is a process of our thinking. It cannot be changed"
    variant = "  “THE WORLD as we have created it is a process of our thinking. Totally different ending”"
    unique, dupes = find_duplicates([quote(text, "Albert Einstein"),
                                     quote(variant, "albert  einstein")])
    assert len(unique) == 1 and len(dupes) == 1


def test_same_quote_by_different_authors_is_not_a_duplicate():
    text = "Be yourself; everyone else is already taken."
    unique, dupes = find_duplicates([quote(text, "Oscar Wilde"), quote(text, "Someone Else")])
    assert len(unique) == 2 and dupes == []


def test_same_text_in_different_sources_is_not_a_duplicate():
    unique, dupes = find_duplicates([book("Night"), quote("Night", None)])
    assert len(unique) == 2 and dupes == []


def test_order_is_preserved():
    records = [book("C"), book("A"), book("c"), book("B")]
    unique, _ = find_duplicates(records)
    assert [r["name_or_title"] for r in unique] == ["C", "A", "B"]
