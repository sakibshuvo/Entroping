"""Tests for capture-only mitmproxy traffic observation."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

import entroping.core.traffic_proxy as traffic_proxy
from entroping.core.traffic_proxy import (
    MitmproxyRuntime,
    MitmproxyUnavailableError,
    TrafficCaptureAddon,
    TrafficProxyError,
    WatchConfig,
    _body_from,
    load_mitmproxy_runtime,
    run_watch,
)
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody


@dataclass(frozen=True)
class _Headers:
    values: dict[str, str]

    def items(self, multi: bool = False) -> Iterable[tuple[str, str]]:
        _ = multi
        return self.values.items()


@dataclass(frozen=True)
class _HeadersWithoutMulti:
    values: dict[str, str]

    def items(self) -> Iterable[tuple[str, str]]:
        return self.values.items()


@dataclass(frozen=True)
class _Request:
    method: str
    pretty_url: str
    headers: _Headers
    content: object
    timestamp_start: float


@dataclass(frozen=True)
class _Response:
    status_code: int
    headers: _Headers
    content: bytes
    timestamp_end: float


@dataclass(frozen=True)
class _Flow:
    request: _Request
    response: _Response


class _Addons:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, *addons: object) -> None:
        self.added.extend(addons)


class _Master:
    addons: _Addons
    ran: bool

    def __init__(self) -> None:
        self.addons = _Addons()
        self.ran = False

    async def run(self) -> None:
        self.ran = True


def _flow(url: str = "https://api.example.test/checkout?token=query-secret") -> _Flow:
    return _Flow(
        request=_Request(
            method="POST",
            pretty_url=url,
            headers=_Headers(
                {
                    "Authorization": "Bearer header-secret",
                    "Content-Type": "application/json",
                    "X-Request-ID": "req-123",
                }
            ),
            content=b'{"password":"body-secret","cart_id":"cart-1"}',
            timestamp_start=1_780_000_000.0,
        ),
        response=_Response(
            status_code=201,
            headers=_Headers(
                {
                    "Content-Type": "application/json",
                    "Set-Cookie": "session_id=response-secret",
                }
            ),
            content=b'{"token":"response-token","ok":true}',
            timestamp_end=1_780_000_001.25,
        ),
    )


def test_capture_addon_redacts_before_persisting_flow(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = TrafficCaptureAddon(store=store, target_url="https://api.example.test")

    event_id = addon.response(_flow())
    loaded = store.list_exchanges()

    assert event_id == 1
    assert len(loaded) == 1
    exchange = loaded[0]
    assert exchange.redacted is True
    assert exchange.duration_ms == 1250
    assert exchange.request.headers["Authorization"] == "[REDACTED]"
    assert exchange.request.url == (
        "https://api.example.test/checkout?token=%5BREDACTED%5D"
    )
    assert exchange.request.body is not None
    assert '"password":"[REDACTED]"' in (exchange.request.body.text or "")
    assert exchange.response is not None
    assert exchange.response.headers["Set-Cookie"] == "[REDACTED]"
    assert "header-secret" not in store.db_path.read_text(encoding="utf-8", errors="ignore")
    assert "body-secret" not in store.db_path.read_text(encoding="utf-8", errors="ignore")
    assert "response-token" not in store.db_path.read_text(encoding="utf-8", errors="ignore")


def test_capture_addon_records_all_hosts_when_target_scope_is_absent(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = TrafficCaptureAddon(store=store, target_url=None)

    event_id = addon.response(_flow(url="https://other.example.test/checkout"))

    assert event_id == 1
    assert store.list_exchanges()[0].request.host == "other.example.test"


def test_capture_addon_rejects_malformed_flow_objects(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = TrafficCaptureAddon(store=store)

    with pytest.raises(TrafficProxyError, match="missing request"):
        addon.response(object())

    with pytest.raises(TrafficProxyError, match="missing a URL"):
        addon.response(_flow(url=""))

    bad_response_flow = _Flow(
        request=_flow().request,
        response=_Response(
            status_code=True,
            headers=_Headers({}),
            content=b"",
            timestamp_end=1_780_000_001.0,
        ),
    )
    with pytest.raises(TrafficProxyError, match="integer status_code"):
        addon.response(bad_response_flow)


def test_body_from_caps_text_before_redaction_processing() -> None:
    content = b'{"token":"' + (b"a" * 128) + b'"}'
    message = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/json"}),
        content=content,
        timestamp_start=1_780_000_000.0,
    )

    body = _body_from(message, max_body_chars=16)

    assert body == TrafficBody(
        content_type="application/json",
        size_bytes=len(content),
        text='{"token":"aaaaaa',
        truncated=True,
    )


def test_body_and_header_helpers_handle_mitmproxy_variants() -> None:
    assert traffic_proxy._headers_from(None) == {}
    assert traffic_proxy._headers_from(object()) == {}
    assert traffic_proxy._headers_from(_HeadersWithoutMulti({"X-Test": "1"})) == {"X-Test": "1"}

    empty = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({}),
        content=b"",
        timestamp_start=1.0,
    )
    assert _body_from(empty) is None

    no_content_type = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({}),
        content=b"hello",
        timestamp_start=1.0,
    )
    assert _body_from(no_content_type) == TrafficBody(
        content_type=None,
        size_bytes=5,
        text=None,
    )

    binary = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "image/png"}),
        content=b"\x89PNG",
        timestamp_start=1.0,
    )
    assert _body_from(binary) == TrafficBody(content_type="image/png", size_bytes=4, text=None)

    vendor_json = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/vnd.api+json; charset=utf-8"}),
        content=bytearray(b'{"ok":true}'),
        timestamp_start=1.0,
    )
    vendor_json_body = _body_from(vendor_json)
    assert vendor_json_body is not None
    assert vendor_json_body.text == '{"ok":true}'

    vendor_xml = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/vnd.test+xml"}),
        content=memoryview(b"<ok />"),
        timestamp_start=1.0,
    )
    vendor_xml_body = _body_from(vendor_xml)
    assert vendor_xml_body is not None
    assert vendor_xml_body.text == "<ok />"

    text_message = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "text/plain"}),
        content="hello",
        timestamp_start=1.0,
    )
    text_body = _body_from(text_message)
    assert text_body is not None
    assert text_body.text == "hello"

    unsupported_content = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "text/plain"}),
        content=object(),
        timestamp_start=1.0,
    )
    assert _body_from(unsupported_content) is None


def test_time_and_target_helpers_handle_missing_or_invalid_values() -> None:
    request = _Request(
        method="GET",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({}),
        content=b"",
        timestamp_start=10.0,
    )
    response_before_request = _Response(
        status_code=200,
        headers=_Headers({}),
        content=b"",
        timestamp_end=9.0,
    )

    assert traffic_proxy._duration_ms(request, response_before_request) is None
    assert traffic_proxy._timestamp_attribute(response_before_request, "missing") is None
    bool_time = type("BoolTime", (), {"value": True})()
    assert traffic_proxy._timestamp_attribute(bool_time, "value") is None
    assert traffic_proxy._captured_at(request, object()).timestamp() == 10.0
    assert traffic_proxy._captured_at(object(), object()).tzinfo is not None
    assert traffic_proxy._string_attribute(object(), ("missing",)) == ""
    assert traffic_proxy._target_scope(None) is None
    assert traffic_proxy._matches_target_scope("https://api.example.test", None) is True


def test_capture_addon_ignores_urls_outside_target_scope(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = TrafficCaptureAddon(store=store, target_url="https://api.example.test")

    event_id = addon.response(_flow(url="https://cdn.example.test/app.js"))

    assert event_id is None
    assert store.list_exchanges() == ()


def test_watch_config_rejects_unsafe_proxy_inputs(tmp_path: Path) -> None:
    assert WatchConfig(project_root=tmp_path, target_url=None).project_root == tmp_path.resolve()

    with pytest.raises(ValueError, match="listen_port must be between 1 and 65535"):
        WatchConfig(project_root=tmp_path, listen_port=0)

    with pytest.raises(ValueError, match="max_events must be positive"):
        WatchConfig(project_root=tmp_path, max_events=0)

    with pytest.raises(ValueError, match="max_body_chars must be positive"):
        WatchConfig(project_root=tmp_path, max_body_chars=0)

    with pytest.raises(ValueError, match="target_url must be an absolute http or https URL"):
        WatchConfig(project_root=tmp_path, listen_port=8080, target_url="ssh://api.example.test")

    with pytest.raises(ValueError, match="target_url must not contain control characters"):
        WatchConfig(
            project_root=tmp_path,
            listen_port=8080,
            target_url="https://api.example.test/\nInjected: yes",
        )


def test_missing_mitmproxy_dependency_error_is_actionable() -> None:
    def fail_import(name: str) -> object:
        raise ModuleNotFoundError("No module named 'mitmproxy'", name="mitmproxy")

    with pytest.raises(MitmproxyUnavailableError, match="uv sync --extra proxy"):
        load_mitmproxy_runtime(import_module=fail_import)


def test_mitmproxy_runtime_rejects_missing_factories_and_reraises_unrelated_imports() -> None:
    class EmptyModule:
        pass

    def empty_import(name: str) -> object:
        _ = name
        return EmptyModule()

    with pytest.raises(MitmproxyUnavailableError, match="missing Options or DumpMaster"):
        load_mitmproxy_runtime(import_module=empty_import)

    def unrelated_import(name: str) -> object:
        _ = name
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    with pytest.raises(ModuleNotFoundError, match="yaml"):
        load_mitmproxy_runtime(import_module=unrelated_import)


def test_mitmproxy_runtime_loads_callable_factories() -> None:
    class OptionsModule:
        @staticmethod
        def Options(**kwargs: object) -> object:
            return {"options": kwargs}

    class DumpModule:
        @staticmethod
        def DumpMaster(*args: object, **kwargs: object) -> object:
            return {"args": args, "kwargs": kwargs}

    def fake_import(name: str) -> object:
        if name == "mitmproxy.options":
            return OptionsModule()
        if name == "mitmproxy.tools.dump":
            return DumpModule()
        raise AssertionError(name)

    runtime = load_mitmproxy_runtime(import_module=fake_import)

    assert runtime.options_factory(listen_port=8080) == {"options": {"listen_port": 8080}}
    assert runtime.dump_master_factory("options") == {"args": ("options",), "kwargs": {}}


def test_run_watch_registers_capture_addon_without_live_proxy(tmp_path: Path) -> None:
    options_kwargs: dict[str, object] = {}
    master = _Master()

    def options_factory(**kwargs: object) -> object:
        options_kwargs.update(kwargs)
        return {"options": kwargs}

    def dump_master_factory(options: object, **kwargs: object) -> _Master:
        assert options == {"options": options_kwargs}
        assert kwargs == {"with_termlog": False, "with_dumper": False}
        return master

    runtime = MitmproxyRuntime(
        options_factory=options_factory,
        dump_master_factory=dump_master_factory,
    )

    asyncio.run(
        run_watch(
            WatchConfig(
                project_root=tmp_path,
                listen_port=8090,
                target_url="https://api.example.test",
            ),
            runtime=runtime,
            store=TrafficStore.open_project(tmp_path),
        )
    )

    assert options_kwargs == {"listen_host": "127.0.0.1", "listen_port": 8090}
    assert master.ran is True
    assert len(master.addons.added) == 1
    assert isinstance(master.addons.added[0], TrafficCaptureAddon)
