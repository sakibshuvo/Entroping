"""mitmproxy adapter for capture-only Eye traffic observation."""

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import urlsplit

from entroping.core.traffic_redactor import DEFAULT_MAX_BODY_CHARS, redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

DEFAULT_WATCH_PORT = 8080
DEFAULT_MAX_EVENTS = 1_000
_LISTEN_HOST = "127.0.0.1"
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
_HeaderItems = Callable[..., Iterable[tuple[object, object]]]


@dataclass(frozen=True, slots=True)
class WatchConfig:
    """Configuration for capture-only traffic observation."""

    project_root: Path
    listen_port: int = DEFAULT_WATCH_PORT
    target_url: str | None = None
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
            return
        if _contains_control(self.target_url):
            msg = "target_url must not contain control characters"
            raise ValueError(msg)
        parsed = urlsplit(self.target_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "target_url must be an absolute http or https URL"
            raise ValueError(msg)


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
        max_body_chars: int = DEFAULT_MAX_BODY_CHARS,
    ) -> None:
        self._store = store
        self._target_scope = _target_scope(target_url)
        self._max_body_chars = max_body_chars

    def response(self, flow: object) -> int | None:
        """Persist one completed response flow, returning the event id when recorded."""

        request = _required_attribute(flow, "request")
        response = _required_attribute(flow, "response")
        url = _string_attribute(request, ("pretty_url", "url"))
        if not url:
            msg = "mitmproxy flow request is missing a URL"
            raise TrafficProxyError(msg)
        if not _matches_target_scope(url, self._target_scope):
            return None

        exchange = TrafficExchange(
            captured_at=_captured_at(request, response),
            duration_ms=_duration_ms(request, response),
            request=TrafficRequest(
                method=_string_attribute(request, ("method",)),
                url=url,
                headers=_headers_from(_optional_attribute(request, "headers")),
                body=_body_from(request),
            ),
            response=TrafficResponse(
                status_code=_status_code(response),
                headers=_headers_from(_optional_attribute(response, "headers")),
                body=_body_from(response),
            ),
        )
        redacted = redact_traffic_exchange(exchange, max_body_chars=self._max_body_chars)
        return self._store.record_exchange(redacted)


def load_mitmproxy_runtime(
    *,
    import_module: _ImportModule = importlib.import_module,
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

    return MitmproxyRuntime(
        options_factory=cast(_OptionsFactory, options_factory),
        dump_master_factory=cast(_DumpMasterFactory, dump_master_factory),
    )


async def run_watch(
    config: WatchConfig,
    *,
    runtime: MitmproxyRuntime | None = None,
    store: TrafficStore | None = None,
) -> None:
    """Start capture-only observation and block until mitmproxy exits."""

    active_runtime = runtime or load_mitmproxy_runtime()
    active_store = store or TrafficStore.open_project(
        config.project_root,
        max_events=config.max_events,
    )
    addon = TrafficCaptureAddon(
        store=active_store,
        target_url=config.target_url,
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


def _body_from(message: object) -> TrafficBody | None:
    content = _bytes_attribute(message, "content")
    if not content:
        return None
    headers = _headers_from(_optional_attribute(message, "headers"))
    content_type = _content_type(headers)
    return TrafficBody(
        content_type=content_type,
        size_bytes=len(content),
        text=_decode_text_body(content, content_type),
    )


def _content_type(headers: dict[str, str]) -> str | None:
    for name, value in headers.items():
        if name.lower() == "content-type":
            return value
    return None


def _decode_text_body(content: bytes, content_type: str | None) -> str | None:
    if content_type is None:
        return None
    media_type = content_type.split(";", maxsplit=1)[0].lower().strip()
    if media_type.startswith("text/") or media_type in _TEXTUAL_CONTENT_TYPES:
        return content.decode("utf-8", errors="replace")
    if media_type.endswith("+json") or media_type.endswith("+xml"):
        return content.decode("utf-8", errors="replace")
    return None


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


def _target_scope(target_url: str | None) -> tuple[str, str] | None:
    if target_url is None:
        return None
    parsed = urlsplit(target_url)
    return (parsed.scheme.lower(), parsed.netloc.lower())


def _matches_target_scope(url: str, target_scope: tuple[str, str] | None) -> bool:
    if target_scope is None:
        return True
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), parsed.netloc.lower()) == target_scope


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
