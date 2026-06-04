"""Deterministic filters for already-redacted traffic captures."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

from entroping.models.traffic import TrafficExchange


class TrafficFilterError(ValueError):
    """Raised when capture filters are unsafe or cannot be applied."""


@dataclass(frozen=True, slots=True)
class TrafficCaptureFilters:
    """Include/exclude filters for redacted traffic capture workflows."""

    include_hosts: tuple[str, ...] = ()
    exclude_hosts: tuple[str, ...] = ()
    include_methods: tuple[str, ...] = ()
    exclude_methods: tuple[str, ...] = ()
    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "include_hosts", _normalize_hosts(self.include_hosts))
        object.__setattr__(self, "exclude_hosts", _normalize_hosts(self.exclude_hosts))
        object.__setattr__(self, "include_methods", _normalize_methods(self.include_methods))
        object.__setattr__(self, "exclude_methods", _normalize_methods(self.exclude_methods))
        object.__setattr__(self, "include_paths", _normalize_paths(self.include_paths))
        object.__setattr__(self, "exclude_paths", _normalize_paths(self.exclude_paths))

    @property
    def is_active(self) -> bool:
        """Return whether any include or exclude filter was configured."""

        return any(
            (
                self.include_hosts,
                self.exclude_hosts,
                self.include_methods,
                self.exclude_methods,
                self.include_paths,
                self.exclude_paths,
            )
        )


def filter_traffic_exchanges(
    exchanges: Iterable[TrafficExchange],
    filters: TrafficCaptureFilters,
) -> tuple[TrafficExchange, ...]:
    """Return redacted exchanges matching include filters minus exclude filters."""

    filtered: list[TrafficExchange] = []
    for exchange in exchanges:
        if not exchange.redacted:
            msg = "capture filtering requires redacted traffic"
            raise TrafficFilterError(msg)
        if _included(exchange, filters) and not _excluded(exchange, filters):
            filtered.append(exchange)
    return tuple(filtered)


def _included(exchange: TrafficExchange, filters: TrafficCaptureFilters) -> bool:
    request = exchange.request
    return (
        _matches_optional(request.host.lower(), filters.include_hosts, _exact_match)
        and _matches_optional(request.method.upper(), filters.include_methods, _exact_match)
        and _matches_optional(request.path, filters.include_paths, _path_match)
    )


def _excluded(exchange: TrafficExchange, filters: TrafficCaptureFilters) -> bool:
    request = exchange.request
    return (
        _matches_any(request.host.lower(), filters.exclude_hosts, _exact_match)
        or _matches_any(request.method.upper(), filters.exclude_methods, _exact_match)
        or _matches_any(request.path, filters.exclude_paths, _path_match)
    )


def _matches_optional(
    value: str,
    patterns: tuple[str, ...],
    matcher: "FilterMatcher",
) -> bool:
    if not patterns:
        return True
    return _matches_any(value, patterns, matcher)


def _matches_any(value: str, patterns: tuple[str, ...], matcher: "FilterMatcher") -> bool:
    return any(matcher(value, pattern) for pattern in patterns)


type FilterMatcher = Callable[[str, str], bool]


def _exact_match(value: str, pattern: str) -> bool:
    return value == pattern


def _path_match(path: str, pattern: str) -> bool:
    if _has_path_glob(pattern):
        return fnmatchcase(path, pattern)
    return path == pattern or path.startswith(pattern.rstrip("/") + "/")


def _has_path_glob(pattern: str) -> bool:
    return "*" in pattern or "[" in pattern


def _normalize_hosts(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        if _contains_control(raw_value):
            msg = "host filters must be host names without control characters"
            raise TrafficFilterError(msg)
        value = raw_value.strip().lower()
        if (
            not value
            or any(character.isspace() for character in value)
            or "://" in value
            or "/" in value
            or "?" in value
            or "#" in value
        ):
            msg = "host filters must be host names without schemes, paths, queries, or fragments"
            raise TrafficFilterError(msg)
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _normalize_methods(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        if _contains_control(raw_value):
            msg = "method filters must be HTTP method tokens without control characters"
            raise TrafficFilterError(msg)
        value = raw_value.strip().upper()
        if (
            not value
            or any(character.isspace() for character in value)
            or not all(character.isalpha() or character == "-" for character in value)
        ):
            msg = "method filters must be HTTP method tokens without spaces"
            raise TrafficFilterError(msg)
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _normalize_paths(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        if _contains_control(raw_value):
            msg = "path filters must start with / and must not contain control characters"
            raise TrafficFilterError(msg)
        value = raw_value.strip()
        if (
            not value
            or not value.startswith("/")
            or any(character.isspace() for character in value)
            or "://" in value
            or "?" in value
            or "#" in value
        ):
            msg = "path filters must start with / and must not include queries or fragments"
            raise TrafficFilterError(msg)
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
