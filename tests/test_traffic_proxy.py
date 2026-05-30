"""Tests for capture-only mitmproxy traffic observation."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

from entroping.core.traffic_proxy import (
    MitmproxyRuntime,
    MitmproxyUnavailableError,
    TrafficCaptureAddon,
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
class _Request:
    method: str
    pretty_url: str
    headers: _Headers
    content: bytes
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


def test_body_from_caps_text_before_redaction_processing() -> None:
    message = _Request(
        method="POST",
        pretty_url="https://api.example.test/checkout",
        headers=_Headers({"Content-Type": "application/json"}),
        content=(b'{"token":"' + (b"a" * 128) + b'"}'),
        timestamp_start=1_780_000_000.0,
    )

    body = _body_from(message, max_body_chars=16)

    assert body == TrafficBody(
        content_type="application/json",
        size_bytes=len(message.content),
        text='{"token":"aaaaaa',
        truncated=True,
    )


def test_capture_addon_ignores_urls_outside_target_scope(tmp_path: Path) -> None:
    store = TrafficStore.open_project(tmp_path)
    addon = TrafficCaptureAddon(store=store, target_url="https://api.example.test")

    event_id = addon.response(_flow(url="https://cdn.example.test/app.js"))

    assert event_id is None
    assert store.list_exchanges() == ()


def test_watch_config_rejects_unsafe_proxy_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="listen_port must be between 1 and 65535"):
        WatchConfig(project_root=tmp_path, listen_port=0)

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
