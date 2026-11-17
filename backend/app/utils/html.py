import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "br",
    "p",
    "div",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "table",
    "section",
    "article",
}

# Elements whose *content* is code or metadata, never readable text (BUG-024).
_IGNORED_CONTENT_TAGS = {"script", "style", "noscript", "template", "head", "title"}

# Escaped markup such as "&lt;p&gt;Python&lt;/p&gt;" (HTML encoded twice by the
# source). Only then is the decoded text parsed a second time, so ordinary
# text like "a < b" or "<3" is never mistaken for markup.
_ESCAPED_TAG_PATTERN = re.compile(
    r"&lt;\s*/?\s*[a-zA-Z][a-zA-Z0-9]*[\s/&>]", re.IGNORECASE
)
_TAG_PATTERN = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?>")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _IGNORED_CONTENT_TAGS:
            self._ignored_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_CONTENT_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._parts.append(data)

    def get_text(self) -> str:
        lines = (
            " ".join(line.split())
            for line in "".join(self._parts).splitlines()
        )
        return "\n".join(line for line in lines if line)


def _extract_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.get_text()


def html_to_text(value: str | None) -> str:
    if not value:
        return ""

    text = _extract_text(value)

    if _ESCAPED_TAG_PATTERN.search(value) and _TAG_PATTERN.search(text):
        text = _extract_text(text)

    return text
