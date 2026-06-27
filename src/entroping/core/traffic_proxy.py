"""mitmproxy adapter for capture-only Eye traffic observation."""

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit

from entroping.core.traffic_redactor import DEFAULT_MAX_BODY_CHARS, redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

DEFAULT_WATCH_PORT = 8080
DEFAULT_MAX_EVENTS = 1_000
_LISTEN_HOST = "127.0.0.1"
_TEXT_BODY_REDACTION_SCAN_EXTRA_CHARS = 512
_TEXTUAL_CONTENT_TYPES = {
    "application/graphql",
    "application/json",
    "application/problem+json",
    "application/x-ndjson",
    "application/x-www-form-urlencoded",
    "application/xml",
}


class TrafficProxyError(ValueError):
    """Raised when traffic capture cannot start or parse a proxy flow."""


class MitmproxyUnavailableError(TrafficProxyError):
    """Raised when the optional mitmproxy dependency is not installed."""


class _AddonManager(Protocol):
    def add(self, *addons: object) -> None:
        """Register mitmproxy addons."""


class _DumpMasterLike(Protocol):
    addons: _AddonManager

    async def run(self) -> None:
        """Run mitmproxy until interrupted."""


_OptionsFactory = Callable[..., object]
_DumpMasterFactory = Callable[..., object]
_ImportModule = Callable[[str], object]
_PackageVersion = Callable[[str], str]
_HeaderItems = Callable[..., Iterable[tuple[object, object]]]
_MIN_SAFE_MSGPACK_VERSION = (1, 2, 1)
_MIN_SAFE_MSGPACK_SPEC = "msgpack>=1.2.1"
_MSGPACK_ADVISORY_ID = "GHSA-6v7p-g79w-8964"


@dataclass(frozen=True, slots=True)
class WatchConfig:
    """Configuration for capture-only traffic observation."""

    project_root: Path
    listen_port: int = DEFAULT_WATCH_PORT
    target_url: str | None = None
    scope_hosts: tuple[str, ...] = ()
    scope_url_prefixes: tuple[str, ...] = ()
    max_events: int = DEFAULT_MAX_EVENTS
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS

    def __post_init__(self) -> None:
        if not 1 <= self.listen_port <= 65_535:
            msg = "listen_port must be between 1 and 65535"
            raise ValueError(msg)
        if self.max_events <= 0:
            msg = "max_events must be positive"
            raise ValueError(msg)
        if self.max_body_chars <= 0:
            msg = "max_body_chars must be positive"
            raise ValueError(msg)

        object.__setattr__(self, "project_root", self.project_root.expanduser().resolve())

        if self.target_url is None:
            target_scope = None
        else:
            if _contains_control(self.target_url):
                msg = "target_url must not contain control characters"
                raise ValueError(msg)
            target_scope = _target_scope(self.target_url)
            if target_scope is None:
                msg = "target_url must be an absolute http or https URL"
                raise ValueError(msg)

        scope_hosts = _normalize_scope_hosts(self.scope_hosts)
        scope_url_prefixes = _normalize_scope_url_prefixes(self.scope_url_prefixes)
        object.__setattr__(self, "scope_hosts", scope_hosts)
        object.__setattr__(self, "scope_url_prefixes", scope_url_prefixes)

        if target_scope is None and not scope_hosts and not scope_url_prefixes:
            msg = (
                "watch requires an explicit capture scope; use --target, "
                "--scope-host, or --scope-url-prefix"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class WatchRunSummary:
    """Count-only traffic capture summary safe for CLI output."""

    recorded_count: int = 0
    ignored_count: int = 0
    malformed_count: int = 0


@dataclass(frozen=True, slots=True)
class MitmproxyRuntime:
    """Lazy-loaded mitmproxy factories."""

    options_factory: _OptionsFactory
    dump_master_factory: _DumpMasterFactory


class TrafficCaptureAddon:
    """mitmproxy addon that redacts and persists completed HTTP flows."""

    def __init__(
        self,
        *,
        store: TrafficStore,
        target_url: str | None = None,
        scope_hosts: tuple[str, ...] = (),
        scope_url_prefixes: tuple[str, ...] = (),
        max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
    ) -> None:
        self._store = store
        self._target_scope = _target_scope(target_url)
        self._scope_hosts = _normalize_scope_hosts(scope_hosts)
        self._scope_url_prefixes = _normalize_scope_url_prefixes(scope_url_prefixes)
        self._max_body_chars = max_body_chars
        self._recorded_count = 0
        self._ignored_count = 0
        self._malformed_count = 0

        if (
            self._target_scope is None
            and not self._scope_hosts
            and not self._scope_url_prefixes
        ):
            msg = "traffic capture requires an explicit scope"
            raise TrafficProxyError(msg)

    @property
    def summary(self) -> WatchRunSummary:
        """Return count-only capture evidence without URLs or headers."""

        return WatchRunSummary(
            recorded_count=self._recorded_count,
            ignored_count=self._ignored_count,
            malformed_count=self._malformed_count,
        )

    def response(self, flow: object) -> int | None:
        """Persist one completed response flow, returning the event id when recorded."""

        request = _required_attribute(flow, "request")
        response = _required_attribute(flow, "response")
        url = _string_attribute(request, ("pretty_url", "url"))
        if not url:
            msg = "mitmproxy flow request is missing a URL"
            raise TrafficProxyError(msg)
        scope_decision = _capture_scope_decision(
            url,
            target_scope=self._target_scope,
            scope_hosts=self._scope_hosts,
            scope_url_prefixes=self._scope_url_prefixes,
        )
        if scope_decision == "malformed":
            self._malformed_count += 1
            return None
        if scope_decision == "out-of-scope":
            self._ignored_count += 1
            return None

        exchange = TrafficExchange(
            captured_at=_captured_at(request, response),
            duration_ms=_duration_ms(request, response),
            request=TrafficRequest(
                method=_string_attribute(request, ("method",)),
                url=url,
                headers=_headers_from(_optional_attribute(request, "headers")),
                body=_body_from(request, max_body_chars=self._max_body_chars),
            ),
            response=TrafficResponse(
                status_code=_status_code(response),
                headers=_headers_from(_optional_attribute(response, "headers")),
                body=_body_from(response, max_body_chars=self._max_body_chars),
            ),
        )
        redacted = redact_traffic_exchange(exchange, max_body_chars=self._max_body_chars)
        event_id = self._store.record_exchange(redacted)
        self._recorded_count += 1
        return event_id


def load_mitmproxy_runtime(
    *,
    import_module: _ImportModule = importlib.import_module,
    package_version: _PackageVersion = importlib_metadata.version,
) -> MitmproxyRuntime:
    """Load mitmproxy lazily so default installs can show an actionable error."""

    try:
        options_module = import_module("mitmproxy.options")
        dump_module = import_module("mitmproxy.tools.dump")
    except ModuleNotFoundError as exc:
        if exc.name is None or exc.name.startswith("mitmproxy"):
            msg = (
                "mitmproxy is required for entroping watch. Install optional proxy "
                "dependencies with `uv sync --extra proxy`, or run "
                "`uv run --extra proxy entroping watch ...`."
            )
            raise MitmproxyUnavailableError(msg) from exc
        raise

    options_factory = getattr(options_module, "Options", None)
    dump_master_factory = getattr(dump_module, "DumpMaster", None)
    if not callable(options_factory) or not callable(dump_master_factory):
        msg = "mitmproxy runtime is missing Options or DumpMaster"
        raise MitmproxyUnavailableError(msg)

    _validate_safe_msgpack_runtime(package_version)

    return MitmproxyRuntime(
        options_factory=cast(_OptionsFactory, options_factory),
        dump_master_factory=cast(_DumpMasterFactory, dump_master_factory),
    )


def _validate_safe_msgpack_runtime(package_version: _PackageVersion) -> None:
    try:
        current_version = package_version("msgpack")
    except importlib_metadata.PackageNotFoundError as exc:
        msg = "mitmproxy runtime is missing msgpack; install the reviewed proxy extra."
        raise MitmproxyUnavailableError(msg) from exc

    if _version_tuple(current_version) < _MIN_SAFE_MSGPACK_VERSION:
        msg = (
            "mitmproxy runtime uses vulnerable msgpack "
            f"{current_version}; {_MSGPACK_ADVISORY_ID} requires {_MIN_SAFE_MSGPACK_SPEC}."
        )
        raise MitmproxyUnavailableError(msg)


def _version_tuple(version: str) -> tuple[int, int, int]:
    release = version.split("+", maxsplit=1)[0].split("-", maxsplit=1)[0]
    parts = release.split(".")
    if len(parts) < 3 or not all(part.isdigit() for part in parts[:3]):
        return (0, 0, 0)
    return (int(parts[0]), int(parts[1]), int(parts[2]))


async def run_watch(
    config: WatchConfig,
    *,
    runtime: MitmproxyRuntime | None = None,
    store: TrafficStore | None = None,
) -> WatchRunSummary:
    """Start capture-only observation and block until mitmproxy exits."""

    active_runtime = runtime or load_mitmproxy_runtime()
    active_store = store or TrafficStore.open_project(
        config.project_root,
        max_events=config.max_events,
    )
    addon = TrafficCaptureAddon(
        store=active_store,
        target_url=config.target_url,
        scope_hosts=config.scope_hosts,
        scope_url_prefixes=config.scope_url_prefixes,
        max_body_chars=config.max_body_chars,
    )
    options = active_runtime.options_factory(
        listen_host=_LISTEN_HOST,
        listen_port=config.listen_port,
    )
    master = cast(
        _DumpMasterLike,
        active_runtime.dump_master_factory(options, with_termlog=False, with_dumper=False),
    )
    master.addons.add(addon)
    await master.run()
    return addon.summary


def _required_attribute(source: object, name: str) -> object:
    value = getattr(source, name, None)
    if value is None:
        msg = f"mitmproxy flow is missing {name}"
        raise TrafficProxyError(msg)
    return value


def _optional_attribute(source: object, name: str) -> object:
    return getattr(source, name, None)


def _string_attribute(source: object, names: tuple[str, ...]) -> str:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return str(value)
    return ""


def _status_code(response: object) -> int:
    value = getattr(response, "status_code", None)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "mitmproxy flow response is missing an integer status_code"
        raise TrafficProxyError(msg)
    return value


def _headers_from(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    items_method = getattr(headers, "items", None)
    if not callable(items_method):
        return {}
    return {
        str(name): str(value)
        for name, value in _call_header_items(cast(_HeaderItems, items_method))
    }


def _call_header_items(items_method: _HeaderItems) -> tuple[tuple[object, object], ...]:
    try:
        items = items_method(multi=True)
    except TypeError:
        items = items_method()
    return tuple(items)


def _body_from(
    message: object,
    *,
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
) -> TrafficBody | None:
    content = _bytes_attribute(message, "content")
    if not content:
        return None
    headers = _headers_from(_optional_attribute(message, "headers"))
    content_type = _content_type(headers)
    text, truncated = _decode_text_body(
        content,
        content_type,
        max_body_chars=max_body_chars,
    )
    return TrafficBody(
        content_type=content_type,
        size_bytes=len(content),
        text=text,
        truncated=truncated,
    )


def _content_type(headers: dict[str, str]) -> str | None:
    for name, value in headers.items():
        if name.lower() == "content-type":
            return value
    return None


def _decode_text_body(
    content: bytes,
    content_type: str | None,
    *,
    max_body_chars: int,
) -> tuple[str | None, bool]:
    if content_type is None:
        return None, False
    media_type = content_type.split(";", maxsplit=1)[0].lower().strip()
    if media_type.startswith("text/") or media_type in _TEXTUAL_CONTENT_TYPES:
        return _decode_text_for_redaction(content, max_body_chars=max_body_chars)
    if media_type.endswith("+json") or media_type.endswith("+xml"):
        return _decode_text_for_redaction(content, max_body_chars=max_body_chars)
    return None, False


def _decode_text_for_redaction(content: bytes, *, max_body_chars: int) -> tuple[str, bool]:
    decode_limit = max_body_chars + _TEXT_BODY_REDACTION_SCAN_EXTRA_CHARS
    bounded_content = content[:decode_limit]
    text = bounded_content.decode("utf-8", errors="replace")
    return text, len(content) > len(bounded_content) or len(text) > max_body_chars


def _bytes_attribute(source: object, name: str) -> bytes:
    value = getattr(source, name, b"")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        return value.encode("utf-8")
    return b""


def _duration_ms(request: object, response: object) -> int | None:
    start = _timestamp_attribute(request, "timestamp_start")
    end = _timestamp_attribute(response, "timestamp_end")
    if start is None or end is None or end < start:
        return None
    return int(round((end - start) * 1000))


def _captured_at(request: object, response: object) -> datetime:
    timestamp = _timestamp_attribute(response, "timestamp_end")
    if timestamp is None:
        timestamp = _timestamp_attribute(request, "timestamp_start")
    if timestamp is None:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _timestamp_attribute(source: object, name: str) -> float | None:
    value = getattr(source, name, None)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _target_scope(target_url: str | None) -> str | None:
    if target_url is None:
        return None
    parsed = _parse_http_url(target_url)
    if parsed is None:
        return None
    return parsed.origin


def _matches_target_scope(url: str, target_scope: str | None) -> bool:
    if target_scope is None:
        return True
    parsed = _parse_http_url(url)
    return parsed is not None and parsed.origin == target_scope


type _ScopeDecision = Literal["in-scope", "out-of-scope", "malformed"]


def _capture_scope_decision(
    url: str,
    *,
    target_scope: str | None,
    scope_hosts: tuple[str, ...],
    scope_url_prefixes: tuple[str, ...],
) -> _ScopeDecision:
    parsed = _parse_http_url(url)
    if parsed is None:
        return "malformed"
    if target_scope is not None and parsed.origin == target_scope:
        return "in-scope"
    if parsed.host in scope_hosts:
        return "in-scope"
    if any(_matches_url_prefix(parsed.comparable_url, prefix) for prefix in scope_url_prefixes):
        return "in-scope"
    return "out-of-scope"


@dataclass(frozen=True, slots=True)
class _ParsedHttpUrl:
    scheme: str
    host: str
    port: int | None
    path: str

    @property
    def origin(self) -> str:
        if self.port is None:
            return f"{self.scheme}://{self.host}"
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def comparable_url(self) -> str:
        return f"{self.origin}{self.path}"


def _parse_http_url(value: str) -> _ParsedHttpUrl | None:
    if _contains_control(value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    hostname = parsed.hostname
    if hostname is None:
        return None
    normalized_port = _normalize_url_port(parsed.scheme, port)
    return _ParsedHttpUrl(
        scheme=parsed.scheme.lower(),
        host=hostname.lower(),
        port=normalized_port,
        path=parsed.path or "/",
    )


def _normalize_url_port(scheme: str, port: int | None) -> int | None:
    if port is None:
        return None
    if scheme == "http" and port == 80:
        return None
    if scheme == "https" and port == 443:
        return None
    return port


def _normalize_scope_hosts(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        if _contains_control(raw_value):
            msg = "scope hosts must be host names without control characters"
            raise ValueError(msg)
        value = raw_value.strip().lower()
        if (
            not value
            or any(character.isspace() for character in value)
            or "://" in value
            or "/" in value
            or "?" in value
            or "#" in value
            or "@" in value
            or ":" in value
        ):
            msg = "scope hosts must be host names without schemes, ports, paths, or queries"
            raise ValueError(msg)
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _normalize_scope_url_prefixes(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_value in values:
        if _contains_control(raw_value):
            msg = "scope URL prefixes must not contain control characters"
            raise ValueError(msg)
        if "?" in raw_value or "#" in raw_value:
            msg = "scope URL prefixes must not include queries or fragments"
            raise ValueError(msg)
        parsed = _parse_http_url(raw_value.strip())
        if parsed is None:
            msg = "scope URL prefixes must be absolute http or https URLs"
            raise ValueError(msg)
        value = parsed.comparable_url.rstrip("/")
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _matches_url_prefix(value: str, prefix: str) -> bool:
    normalized_value = value.rstrip("/")
    return normalized_value == prefix or normalized_value.startswith(f"{prefix}/")


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
