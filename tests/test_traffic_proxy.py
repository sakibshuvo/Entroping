"""Tests for capture-only mitmproxy traffic observation."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path

import pytest

import entroping.core.traffic_proxy as traffic_proxy
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
    addon = traffic_proxy.TrafficCaptureAddon(store=store, target_url="https://api.example.test")

    event_id = addon.response(_flow())
    loaded = store.list_exchanges()

    assert event_id == 1
    assert len(loaded) == 1
    exchange = loaded[0]
    assert exchange.redacted is True
    assert exchange.duration_ms == 1250
    assert exchange.request.headers["Authorization"] == "[REDACTED]"
    assert exchange.request.url == ("https://api.example.test/checkout?token=%5BREDACTED%5D")
    assert exchange.request.body is not None
    assert '"password":"[REDACTED]"' in (exchange.request.body.text or "")
    assert exchange.response is not None
    assert exchange.response.headers["Set-Cookie"] == "[REDACTED]"
    assert "header-secret" not in store.db_path.read_text(encoding="utf-8", errors="ignore")
    assert "body-secret" not in store.db_path.read_text(encoding="utf-8", errors="ignore")
    assert "response-token" not in store.db_path.read_text(encoding="utf-8", errors="ignore")


def test_capture_addon_redacts_body_before_truncating_boundary_crossing_secret(
    tmp_path: Path,
) -> None:
    secret = "".join(("Aa1Bb2Cc3Dd4", "Ee5Ff6Gg7Hh", "8Ii9Jj0Kk1Ll", "2Mm3Nn4"))
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(
        store=store,
        target_url="https://api.example.test",
        max_body_chars=16,
    )
    flow = _Flow(
        request=_Request(
            method="POST",
            pretty_url="https://api.example.test/checkout",
            headers=_Headers({"Content-Type": "text/plain"}),
            content=f"note={secret}&safe=ok".encode(),
            timestamp_start=1_780_000_000.0,
        ),
        response=_Response(
            status_code=200,
            headers=_Headers({}),
            content=b"",
            timestamp_end=1_780_000_000.5,
        ),
    )

    event_id = addon.response(flow)
    loaded = store.list_exchanges()
    db_text = store.db_path.read_text(encoding="utf-8", errors="ignore")

    assert event_id == 1
    assert len(loaded) == 1
    request_body = loaded[0].request.body
    assert request_body is not None
    assert request_body.truncated is True
    assert "[REDACTED]" in (request_body.text or "")
    assert secret not in db_text
    assert "Aa1Bb2Cc" not in db_text


def test_capture_addon_records_all_hosts_when_target_scope_is_absent(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(store=store, scope_hosts=("other.example.test",))

    event_id = addon.response(_flow(url="https://other.example.test/checkout"))

    assert event_id == 1
    assert store.list_exchanges()[0].request.host == "other.example.test"


def test_capture_addon_enforces_host_and_url_prefix_scope(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(
        store=store,
        scope_hosts=("API.EXAMPLE.TEST",),
        scope_url_prefixes=("https://payments.example.test/api/v1",),
    )

    out_of_scope = addon.response(
        _flow(url="https://evil.example.test/checkout?token=out-of-scope-secret")
    )
    host_match = addon.response(
        _flow(url="https://API.EXAMPLE.TEST:443/checkout?token=query-secret")
    )
    prefix_match = addon.response(
        _flow(url="https://payments.example.test:443/api/v1/refunds?token=query-secret")
    )
    sibling_prefix = addon.response(
        _flow(url="https://payments.example.test/api/v10/refunds?token=sibling-secret")
    )

    loaded = store.list_exchanges()
    db_text = store.db_path.read_text(encoding="utf-8", errors="ignore")
    assert out_of_scope is None
    assert host_match == 1
    assert prefix_match == 2
    assert sibling_prefix is None
    assert addon.summary == traffic_proxy.WatchRunSummary(recorded_count=2, ignored_count=2)
    assert [exchange.request.host for exchange in loaded] == [
        "API.EXAMPLE.TEST:443",
        "payments.example.test:443",
    ]
    assert "out-of-scope-secret" not in db_text
    assert "sibling-secret" not in db_text


def test_capture_addon_ignores_malformed_scope_urls_without_persistence(
    tmp_path: Path,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(store=store, scope_hosts=("api.example.test",))

    event_id = addon.response(_flow(url="not a url?token=malformed-secret"))

    assert event_id is None
    assert addon.summary == traffic_proxy.WatchRunSummary(recorded_count=0, malformed_count=1)
    assert store.list_exchanges() == ()
    assert "malformed-secret" not in store.db_path.read_text(encoding="utf-8", errors="ignore")


def test_capture_addon_rejects_malformed_flow_objects(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(store=store, scope_hosts=("api.example.test",))

    with pytest.raises(traffic_proxy.TrafficProxyError, match="missing request"):
        addon.response(object())

    with pytest.raises(traffic_proxy.TrafficProxyError, match="missing a URL"):
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
    with pytest.raises(traffic_proxy.TrafficProxyError, match="integer status_code"):
        addon.response(bad_response_flow)


def test_body_from_bounds_text_before_redaction_processing() -> None:
    content = b'{"token":"' + (b"a" * 8_192) + b'"}'
    message = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/json"}),
        content=content,
        timestamp_start=1_780_000_000.0,
    )

    body = traffic_proxy._body_from(message, max_body_chars=16)

    expected_text = content[: 16 + traffic_proxy._TEXT_BODY_REDACTION_SCAN_EXTRA_CHARS].decode(
        "utf-8"
    )
    assert body == TrafficBody(
        content_type="application/json",
        size_bytes=len(content),
        text=expected_text,
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
    assert traffic_proxy._body_from(empty) is None

    no_content_type = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({}),
        content=b"hello",
        timestamp_start=1.0,
    )
    assert traffic_proxy._body_from(no_content_type) == TrafficBody(
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
    assert traffic_proxy._body_from(binary) == TrafficBody(
        content_type="image/png", size_bytes=4, text=None
    )

    vendor_json = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/vnd.api+json; charset=utf-8"}),
        content=bytearray(b'{"ok":true}'),
        timestamp_start=1.0,
    )
    vendor_json_body = traffic_proxy._body_from(vendor_json)
    assert vendor_json_body is not None
    assert vendor_json_body.text == '{"ok":true}'

    vendor_xml = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/vnd.test+xml"}),
        content=memoryview(b"<ok />"),
        timestamp_start=1.0,
    )
    vendor_xml_body = traffic_proxy._body_from(vendor_xml)
    assert vendor_xml_body is not None
    assert vendor_xml_body.text == "<ok />"

    text_message = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "text/plain"}),
        content="hello",
        timestamp_start=1.0,
    )
    text_body = traffic_proxy._body_from(text_message)
    assert text_body is not None
    assert text_body.text == "hello"

    unsupported_content = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "text/plain"}),
        content=object(),
        timestamp_start=1.0,
    )
    assert traffic_proxy._body_from(unsupported_content) is None


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


def test_capture_scope_helpers_cover_validation_edges(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)

    with pytest.raises(traffic_proxy.TrafficProxyError, match="explicit scope"):
        traffic_proxy.TrafficCaptureAddon(store=store)

    assert (
        traffic_proxy._target_scope("https://api.example.test:8443/root")
        == "https://api.example.test:8443"
    )
    assert (
        traffic_proxy._matches_target_scope(
            "https://api.example.test:8443/checkout",
            "https://api.example.test:8443",
        )
        is True
    )
    assert traffic_proxy._matches_target_scope("not a url", "https://api.example.test") is False
    assert traffic_proxy._parse_http_url("https://api.example.test/\nsecret") is None
    assert traffic_proxy._parse_http_url("https://api.example.test:bad/path") is None
    assert traffic_proxy._parse_http_url("https:///path") is None
    default_port_url = traffic_proxy._parse_http_url("http://api.example.test:80/path")
    non_default_port_url = traffic_proxy._parse_http_url("http://api.example.test:8080/path")
    assert default_port_url is not None
    assert non_default_port_url is not None
    assert default_port_url.origin == "http://api.example.test"
    assert non_default_port_url.origin == "http://api.example.test:8080"

    with pytest.raises(ValueError, match="scope hosts must be host names"):
        traffic_proxy.WatchConfig(project_root=tmp_path, scope_hosts=("api.example.test\n",))

    with pytest.raises(ValueError, match="scope URL prefixes must not contain control"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path,
            scope_url_prefixes=("https://api.example.test/\nsecret",),
        )

    with pytest.raises(ValueError, match="scope URL prefixes must be absolute"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path, scope_url_prefixes=("ftp://api.example.test",)
        )


def test_capture_addon_ignores_urls_outside_target_scope(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = traffic_proxy.TrafficCaptureAddon(store=store, target_url="https://api.example.test")

    event_id = addon.response(_flow(url="https://cdn.example.test/app.js"))

    assert event_id is None
    assert store.list_exchanges() == ()


def test_watch_config_rejects_unsafe_proxy_inputs(tmp_path: Path) -> None:
    assert (
        traffic_proxy.WatchConfig(
            project_root=tmp_path, scope_hosts=("api.example.test",)
        ).project_root
        == tmp_path.resolve()
    )

    with pytest.raises(ValueError, match="watch requires an explicit capture scope"):
        traffic_proxy.WatchConfig(project_root=tmp_path)

    with pytest.raises(ValueError, match="listen_port must be between 1 and 65535"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path, listen_port=0, scope_hosts=("api.example.test",)
        )

    with pytest.raises(ValueError, match="max_events must be positive"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path, max_events=0, scope_hosts=("api.example.test",)
        )

    with pytest.raises(ValueError, match="max_body_chars must be positive"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path, max_body_chars=0, scope_hosts=("api.example.test",)
        )

    with pytest.raises(ValueError, match="target_url must be an absolute http or https URL"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path, listen_port=8080, target_url="ssh://api.example.test"
        )

    with pytest.raises(ValueError, match="target_url must not contain control characters"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path,
            listen_port=8080,
            target_url="https://api.example.test/\nInjected: yes",
        )

    with pytest.raises(ValueError, match="scope hosts must be host names"):
        traffic_proxy.WatchConfig(project_root=tmp_path, scope_hosts=("https://api.example.test",))

    with pytest.raises(ValueError, match="scope URL prefixes must not include queries"):
        traffic_proxy.WatchConfig(
            project_root=tmp_path,
            scope_url_prefixes=("https://api.example.test/checkout?token=secret",),
        )


def test_missing_mitmproxy_dependency_error_is_actionable() -> None:
    def fail_import(name: str) -> object:
        raise ModuleNotFoundError("No module named 'mitmproxy'", name="mitmproxy")

    with pytest.raises(traffic_proxy.MitmproxyUnavailableError, match="uv sync --extra proxy"):
        traffic_proxy.load_mitmproxy_runtime(import_module=fail_import)


def test_mitmproxy_runtime_rejects_missing_factories_and_reraises_unrelated_imports() -> None:
    class EmptyModule:
        pass

    def empty_import(name: str) -> object:
        _ = name
        return EmptyModule()

    with pytest.raises(
        traffic_proxy.MitmproxyUnavailableError, match="missing Options or DumpMaster"
    ):
        traffic_proxy.load_mitmproxy_runtime(import_module=empty_import)

    def unrelated_import(name: str) -> object:
        _ = name
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    with pytest.raises(ModuleNotFoundError, match="yaml"):
        traffic_proxy.load_mitmproxy_runtime(import_module=unrelated_import)


def test_mitmproxy_runtime_rejects_vulnerable_msgpack_version() -> None:
    class OptionsModule:
        @staticmethod
        def Options(**kwargs: object) -> object:
            return {"options": kwargs}

    class DumpModule:
        DumpMaster = _Master

    def fake_import(name: str) -> object:
        if name == "mitmproxy.options":
            return OptionsModule()
        if name == "mitmproxy.tools.dump":
            return DumpModule()
        raise AssertionError(name)

    def package_version(name: str) -> str:
        assert name == "msgpack"
        return "1.1.2"

    with pytest.raises(traffic_proxy.MitmproxyUnavailableError, match="msgpack>=1.2.1"):
        traffic_proxy.load_mitmproxy_runtime(
            import_module=fake_import, package_version=package_version
        )


def test_mitmproxy_runtime_rejects_missing_msgpack_package() -> None:
    class OptionsModule:
        @staticmethod
        def Options(**kwargs: object) -> object:
            return {"options": kwargs}

    class DumpModule:
        DumpMaster = _Master

    def fake_import(name: str) -> object:
        if name == "mitmproxy.options":
            return OptionsModule()
        if name == "mitmproxy.tools.dump":
            return DumpModule()
        raise AssertionError(name)

    def package_version(name: str) -> str:
        assert name == "msgpack"
        raise importlib_metadata.PackageNotFoundError

    with pytest.raises(traffic_proxy.MitmproxyUnavailableError, match="missing msgpack"):
        traffic_proxy.load_mitmproxy_runtime(
            import_module=fake_import, package_version=package_version
        )


def test_mitmproxy_runtime_rejects_unparseable_msgpack_version() -> None:
    class OptionsModule:
        @staticmethod
        def Options(**kwargs: object) -> object:
            return {"options": kwargs}

    class DumpModule:
        DumpMaster = _Master

    def fake_import(name: str) -> object:
        if name == "mitmproxy.options":
            return OptionsModule()
        if name == "mitmproxy.tools.dump":
            return DumpModule()
        raise AssertionError(name)

    def package_version(name: str) -> str:
        assert name == "msgpack"
        return "1.2.rc1"

    with pytest.raises(traffic_proxy.MitmproxyUnavailableError, match="vulnerable msgpack 1.2.rc1"):
        traffic_proxy.load_mitmproxy_runtime(
            import_module=fake_import, package_version=package_version
        )


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

    def package_version(name: str) -> str:
        assert name == "msgpack"
        return "1.2.1"

    runtime = traffic_proxy.load_mitmproxy_runtime(
        import_module=fake_import,
        package_version=package_version,
    )

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

    runtime = traffic_proxy.MitmproxyRuntime(
        options_factory=options_factory,
        dump_master_factory=dump_master_factory,
    )

    asyncio.run(
        traffic_proxy.run_watch(
            traffic_proxy.WatchConfig(
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
    assert isinstance(master.addons.added[0], traffic_proxy.TrafficCaptureAddon)
