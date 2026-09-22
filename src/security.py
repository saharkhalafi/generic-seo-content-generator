from __future__ import annotations

from html.parser import HTMLParser

_ALLOWED_TAGS = {
    "article",
    "section",
    "div",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "p",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "b",
    "i",
    "a",
    "br",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "form", "svg", "math"}
_VOID = {"br"}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in _ALLOWED_TAGS:
            return
        rendered = _safe_attrs(tag, attrs)
        if tag in _VOID:
            self.parts.append(f"<{tag}{rendered}>")
            return
        self.parts.append(f"<{tag}{rendered}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if self._drop_depth or tag not in _ALLOWED_TAGS or tag in _VOID:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        self.parts.append(_escape_text(data))

    def handle_entityref(self, name: str) -> None:
        if not self._drop_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._drop_depth:
            self.parts.append(f"&#{name};")


def _escape_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _safe_attrs(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    if tag != "a":
        return ""
    for key, value in attrs:
        if key.lower() != "href" or not value:
            continue
        href = value.strip()
        lowered = href.lower()
        if lowered.startswith(("javascript:", "data:", "vbscript:")):
            continue
        if href.startswith(("#", "/", "http://", "https://", "mailto:")):
            safe = href.replace('"', "&quot;")
            return f' href="{safe}" rel="noopener noreferrer"'
    return ""


def sanitize_html(raw: str) -> str:
    parser = _Sanitizer()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.parts)


def sanitize_markdown(raw: str) -> str:
    """Keep markdown text and drop embedded active HTML."""
    text = raw or ""
    lowered = text.lower()
    if any(token in lowered for token in ("<script", "<iframe", "javascript:", "onerror=", "onload=")):
        return sanitize_html(text)
    return text


class SecurityHeadersMiddleware:
    """Pure ASGI middleware so Streamlit websockets are left untouched."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-frame-options", b"SAMEORIGIN"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
