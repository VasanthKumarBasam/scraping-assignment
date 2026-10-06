"""Small, pure cleaning functions: value in, cleaned value out.

No internet, no files, no logging, so each one is trivial to unit test.
Every function accepts None and returns None for missing/empty input, which
is how "missing" is represented everywhere in this project.
"""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

RATING_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Non-breaking space, zero-width space, BOM
_INVISIBLE_CHARS = {"\xa0": " ", "\u200b": "", "\ufeff": ""}

# Optional minus sign is kept on purpose: "-5" must stay -5.0 so validation
# can reject it. Dropping the sign would silently turn bad data into good data.
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

_OPENING_QUOTES = "“\"'‘"
_CLOSING_QUOTES = "”\"'’"


def clean_text(value):
    """Trim and collapse all whitespace (spaces, tabs, newlines, nbsp) to single spaces."""
    if value is None:
        return None
    text = str(value)
    for char, replacement in _INVISIBLE_CHARS.items():
        text = text.replace(char, replacement)
    text = " ".join(text.split())
    return text or None  # "" becomes None, so "missing" has one representation


def strip_quotes(value):
    """Remove one pair of wrapping quote marks: '“Hello”' -> 'Hello'.

    Only the first and last character are touched, so quotes *inside* the
    text are preserved.
    """
    text = clean_text(value)
    if not text:
        return None
    if text[0] in _OPENING_QUOTES:
        text = text[1:]
    if text and text[-1] in _CLOSING_QUOTES:
        text = text[:-1]
    return clean_text(text)


def clean_price(raw):
    """'£51.77' -> 51.77, 'Â£1,234.50' -> 1234.5, 'free' -> None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return round(float(raw), 2)
    match = _NUMBER_PATTERN.search(str(raw).replace(",", ""))
    return round(float(match.group()), 2) if match else None


def clean_rating(raw):
    """'star-rating Three' -> 3, 'five' -> 5, '4' -> 4, 'unknown' -> None.

    Out-of-range numbers (e.g. '7') are returned as-is so validation can
    reject them with a clear reason instead of hiding the problem.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    for word in str(raw).lower().split():
        if word in RATING_WORDS:
            return RATING_WORDS[word]
        if word.isdigit():
            return int(word)
    return None


def clean_tags(raw):
    """['Love', ' life ', 'love'] -> 'life;love' (lowercase, unique, sorted)."""
    if raw is None:
        return None
    items = raw.split(";") if isinstance(raw, str) else raw
    tags = {clean_text(tag).lower() for tag in items if clean_text(tag)}
    return ";".join(sorted(tags)) or None


def clean_description(raw):
    """Clean whitespace and drop the trailing '...more' that the site appends."""
    text = clean_text(raw)
    if not text:
        return None
    text = re.sub(r"\s*\.{3}\s*more$", "", text)
    return text or None


def normalize_url(url, base=None):
    """Make a URL absolute and tidy (lowercase scheme/host, no #fragment).

    Anything that is not http(s) is returned unchanged rather than dropped,
    so validation can reject it with the reason 'invalid_url'.
    """
    url = clean_text(url)
    if not url:
        return None
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return url
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path or "/", parts.query, ""))
