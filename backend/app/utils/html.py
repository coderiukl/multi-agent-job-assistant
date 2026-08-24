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
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        lines = (
            " ".join(line.split())
            for line in "".join(self._parts).splitlines()
        )
        return "\n".join(line for line in lines if line)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""

    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.get_text()