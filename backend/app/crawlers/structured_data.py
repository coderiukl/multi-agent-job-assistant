import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit


class _PageDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._inside_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)

        if tag.casefold() == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))

        if (
            tag.casefold() == "script"
            and (attributes.get("type") or "").casefold()
            == "application/ld+json"
        ):
            self._inside_json_ld = True
            self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_json_ld:
            self._json_ld_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or not self._inside_json_ld:
            return

        self._inside_json_ld = False
        block = "".join(self._json_ld_parts).strip()

        if block:
            self.json_ld_blocks.append(block)

        self._json_ld_parts = []


def extract_links(
    html: str,
    *,
    base_url: str,
    allowed_hosts: frozenset[str],
    path_prefix: str,
) -> list[str]:
    parser = _PageDataParser()
    parser.feed(html)

    links: list[str] = []
    seen: set[str] = set()

    for href in parser.links:
        absolute_url = urljoin(base_url, href)
        parsed = urlsplit(absolute_url)

        if parsed.hostname not in allowed_hosts:
            continue

        if not parsed.path.startswith(path_prefix):
            continue

        canonical_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )

        if canonical_url in seen:
            continue

        seen.add(canonical_url)
        links.append(canonical_url)

    return links


def extract_job_posting(html: str) -> dict[str, Any] | None:
    parser = _PageDataParser()
    parser.feed(html)

    for block in parser.json_ld_blocks:
        try:
            document = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _walk_json(document):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]

            if any(
                str(value).casefold() == "jobposting"
                for value in types
                if value is not None
            ):
                return node

    return None


def _walk_json(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    if isinstance(value, dict):
        nodes.append(value)

        for child in value.values():
            nodes.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_walk_json(child))

    return nodes
