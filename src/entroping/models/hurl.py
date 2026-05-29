"""Pure models and parsers for Entroping-aware Hurl files."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

_METADATA_PREFIX = "# entroping:"
_METADATA_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
class HurlTest:
    """Discovered Hurl test and its Entroping metadata."""

    path: Path
    metadata: HurlMetadata

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
