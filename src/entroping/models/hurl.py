"""Pure models and parsers for Entroping-aware Hurl files."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

_METADATA_PREFIX = "# entroping:"
_METADATA_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUEST_LINE_RE = re.compile(
    r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE)\s+(\S+)(?:\s+.*)?$",
)
_TEMPLATE_BASE_URL_RE = re.compile(r"^\{\{[^}]+\}\}(?P<path>/.*)$")


class HurlMetadataSyntaxError(ValueError):
    """Raised when an Entroping metadata comment is malformed."""


@dataclass(frozen=True)
class HurlMetadata:
    """Metadata parsed from Entroping Hurl comments."""

    tags: frozenset[str] = field(default_factory=frozenset)
    meta: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def story_id(self) -> str | None:
        """Return the linked story identifier when present."""

        return self.meta.get("story_id")


@dataclass(frozen=True)
class HurlExchange:
    """Request target parsed from a Hurl transaction."""

    method: str
    url: str
    path: str


@dataclass(frozen=True)
class HurlTest:
    """Discovered Hurl test and its Entroping metadata."""

    path: Path
    metadata: HurlMetadata
    exchanges: tuple[HurlExchange, ...] = field(default_factory=tuple)

    @property
    def tags(self) -> frozenset[str]:
        """Expose tags directly for gate matching and selection."""

        return self.metadata.tags


def parse_hurl_metadata(content: str, *, source: Path | None = None) -> HurlMetadata:
    """Parse supported ``# entroping:`` comments from Hurl text."""

    tags: frozenset[str] | None = None
    meta: dict[str, str] = {}

    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped.startswith(_METADATA_PREFIX):
            continue

        payload = stripped.removeprefix(_METADATA_PREFIX).strip()
        if "=" not in payload:
            _raise_metadata_error(
                line_number,
                "expected 'key=value' after '# entroping:'",
                source=source,
            )

        key, raw_value = (part.strip() for part in payload.split("=", maxsplit=1))
        if not _METADATA_KEY_RE.fullmatch(key):
            _raise_metadata_error(line_number, f"invalid metadata key {key!r}", source=source)

        if key == "tags":
            if tags is not None:
                _raise_metadata_error(line_number, "duplicate metadata key 'tags'", source=source)
            tags = _parse_tags(raw_value, line_number=line_number, source=source)
            continue

        if raw_value == "":
            _raise_metadata_error(line_number, f"empty metadata value for {key!r}", source=source)
        if key in meta:
            _raise_metadata_error(line_number, f"duplicate metadata key {key!r}", source=source)
        meta[key] = raw_value

    return HurlMetadata(tags=tags or frozenset(), meta=MappingProxyType(dict(meta)))


def parse_hurl_exchanges(content: str) -> tuple[HurlExchange, ...]:
    """Parse Hurl request lines needed by deterministic gate matching.

    This is intentionally shallow. Entroping does not execute requests here; it only
    extracts the method and target string that Hurl will execute later.
    """

    exchanges: list[HurlExchange] = []
    for line in content.splitlines():
        match = _REQUEST_LINE_RE.fullmatch(line.strip())
        if match is None:
            continue

        method, url = match.groups()
        exchanges.append(
            HurlExchange(
                method=method.upper(),
                url=url,
                path=_extract_path(url),
            ),
        )

    return tuple(exchanges)


def _parse_tags(raw_value: str, *, line_number: int, source: Path | None) -> frozenset[str]:
    if raw_value == "":
        _raise_metadata_error(line_number, "empty tag value", source=source)

    tags: set[str] = set()
    for raw_tag in raw_value.split(","):
        tag = raw_tag.strip()
        if tag == "":
            _raise_metadata_error(line_number, "empty tag value", source=source)
        tags.add(tag)

    return frozenset(tags)


def _raise_metadata_error(
    line_number: int,
    message: str,
    *,
    source: Path | None,
) -> None:
    location = f"{source}: " if source is not None else ""
    raise HurlMetadataSyntaxError(f"{location}line {line_number}: {message}")


def _extract_path(url: str) -> str:
    if url.startswith(("http://", "https://")):
        parsed = urlsplit(url)
        return parsed.path or "/"

    template_match = _TEMPLATE_BASE_URL_RE.fullmatch(url)
    if template_match is not None:
        return _strip_query_and_fragment(template_match.group("path"))

    if url.startswith("/"):
        return _strip_query_and_fragment(url)

    parsed = urlsplit(url)
    if parsed.path.startswith("/"):
        return parsed.path

    return _strip_query_and_fragment(url)


def _strip_query_and_fragment(value: str) -> str:
    without_fragment = value.split("#", maxsplit=1)[0]
    return without_fragment.split("?", maxsplit=1)[0]
