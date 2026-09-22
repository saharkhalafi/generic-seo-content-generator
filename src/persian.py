from __future__ import annotations

import re
from html.parser import HTMLParser

ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "ۀ": "ه",
    }
)
DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")
HEADING_RE = re.compile(
    r"<h([1-3])[^>]*>(.*?)</h\1>",
    flags=re.IGNORECASE | re.DOTALL,
)


def normalize_fa(text: str) -> str:
    value = (text or "").translate(ARABIC_TO_PERSIAN)
    value = DIACRITICS_RE.sub("", value)
    value = value.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    return WHITESPACE_RE.sub(" ", value).strip()


def contains_term(text: str, term: str) -> bool:
    haystack = normalize_fa(text)
    needle = normalize_fa(term)
    return bool(needle) and needle in haystack


def strip_html(html: str) -> str:
    text = TAG_RE.sub(" ", html or "")
    return WHITESPACE_RE.sub(" ", text).replace("&nbsp;", " ").strip()


def count_words(text: str) -> int:
    cleaned = strip_html(text) if "<" in (text or "") else normalize_fa(text)
    if not cleaned:
        return 0
    return len(cleaned.split())


def char_count(text: str) -> int:
    return len((text or "").strip())


def similarity(a: str, b: str) -> float:
    left = set(normalize_fa(a).split())
    right = set(normalize_fa(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(html or "")
    except Exception:
        return strip_html(html)
    return WHITESPACE_RE.sub(" ", "".join(parser.parts)).strip()


def extract_headings(html: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for match in HEADING_RE.finditer(html or ""):
        level = f"H{match.group(1)}"
        text = strip_html(match.group(2))
        if text:
            found.append((level, text))
    return found


def slugify_ascii(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:80]


def lines_to_list(raw: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        item = WHITESPACE_RE.sub(" ", line).strip(" -•\t")
        key = normalize_fa(item)
        if item and key not in seen:
            seen.add(key)
            items.append(item)
    return items
