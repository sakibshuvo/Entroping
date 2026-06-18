"""Pure models and parsers for Entroping-aware Hurl files."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

_METADATA_PREFIX = "# entroping:"
_METADATA_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AUTH_FLOW_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
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

    @property
    def operation_id(self) -> str | None:
        """Return the linked OpenAPI operation identifier when present."""

        return self.meta.get("operation_id")

    @property
    def auth_flow(self) -> str | None:
        """Return the value-free auth flow identifier when present."""

        return self.meta.get("auth_flow")

    @property
    def auth_requires(self) -> tuple[str, ...]:
        """Return Hurl variable names required by this auth flow."""

        return _parse_auth_variable_names(self.meta.get("auth_requires"), key="auth_requires")

    @property
    def auth_produces(self) -> tuple[str, ...]:
        """Return Hurl variable names produced by this auth flow."""

        return _parse_auth_variable_names(self.meta.get("auth_produces"), key="auth_produces")


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
        if _has_control_character(raw_value):
            _raise_metadata_error(
                line_number,
                f"metadata value for {key!r} must not contain control characters",
                source=source,
            )
        if key == "auth_flow":
            _validate_auth_flow(raw_value, line_number=line_number, source=source)
        elif key in {"auth_requires", "auth_produces"}:
            _parse_auth_variable_names(
                raw_value,
                key=key,
                line_number=line_number,
                source=source,
            )
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
        if _has_control_character(tag):
            _raise_metadata_error(
                line_number,
                "tag value must not contain control characters",
                source=source,
            )
        tags.add(tag)

    return frozenset(tags)


def _validate_auth_flow(raw_value: str, *, line_number: int, source: Path | None) -> None:
    if _AUTH_FLOW_RE.fullmatch(raw_value) is None:
        _raise_metadata_error(
            line_number,
            "auth_flow must be a value-free identifier",
            source=source,
        )


def _parse_auth_variable_names(
    raw_value: str | None,
    *,
    key: str,
    line_number: int | None = None,
    source: Path | None = None,
) -> tuple[str, ...]:
    if raw_value is None:
        return ()

    names: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_value.split(","):
        name = raw_name.strip()
        if not name or _VARIABLE_NAME_RE.fullmatch(name) is None:
            _raise_auth_metadata_error(
                line_number=line_number,
                source=source,
                message=f"invalid variable name in {key}",
            )
        if name in seen:
            _raise_auth_metadata_error(
                line_number=line_number,
                source=source,
                message=f"duplicate variable name in {key}",
            )
        names.append(name)
        seen.add(name)
    return tuple(names)


def _raise_auth_metadata_error(
    *,
    line_number: int | None,
    source: Path | None,
    message: str,
) -> None:
    if line_number is None:
        raise HurlMetadataSyntaxError(message)
    _raise_metadata_error(line_number, message, source=source)


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


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
