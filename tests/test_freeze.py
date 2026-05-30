"""Tests for the freeze workflow filesystem boundary."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

import entroping.core.freeze as freeze
from entroping.bridge.traffic_to_hurl import GeneratedTrafficHurlFile
from entroping.bridge.traffic_to_wiremock import GeneratedWireMockMapping
from entroping.core.freeze import FreezeError, run_freeze, run_freeze_mock
from entroping.core.hurl_validator import HurlValidationError
from entroping.core.safe_write import SafeWriteError
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse


def _record_exchange(project_root: Path) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        duration_ms=25,
        request=TrafficRequest(
            method="GET",
            url="https://api.example.test/checkout",
            headers={"Content-Type": "application/json"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=15,
                text='{"ok":true}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def _record_dependency_exchange(project_root: Path) -> None:
    exchange = TrafficExchange(
        captured_at=datetime(2026, 5, 30, 12, 1, tzinfo=UTC),
        duration_ms=40,
        request=TrafficRequest(
            method="POST",
            url="https://payments.example.test/charge",
            headers={"Content-Type": "application/json"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=17,
                text='{"ok":true}',
            ),
        ),
    )
    TrafficStore.open_project(project_root).record_exchange(redact_traffic_exchange(exchange))


def test_run_freeze_reports_missing_or_empty_traffic_state(tmp_path: Path) -> None:
    with pytest.raises(FreezeError, match="No traffic state found"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    TrafficStore.open_project(tmp_path)
    with pytest.raises(FreezeError, match="contains no traffic"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )


def test_run_freeze_writes_generated_hurl(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    result = run_freeze(
        project_root=tmp_path,
        name="checkout_flow",
        golden=False,
        hurl_validator=lambda content, display_path: None,
    )

    assert result.record_count == 1
    assert result.output_path == tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    assert "GET https://api.example.test/checkout" in result.output_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("name", ["", "bad\nname", "../flow", ".hidden", "bad name!"])
def test_run_freeze_rejects_unsafe_names_before_state_lookup(tmp_path: Path, name: str) -> None:
    with pytest.raises(FreezeError, match="freeze name"):
        run_freeze(
            project_root=tmp_path,
            name=name,
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )


def test_run_freeze_wraps_hurl_validation_errors(tmp_path: Path) -> None:
    _record_exchange(tmp_path)

    def fail_validation(content: str, display_path: str) -> None:
        _ = content, display_path
        raise HurlValidationError("invalid hurl")

    with pytest.raises(FreezeError, match="invalid hurl"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=fail_validation,
        )


def test_run_freeze_refuses_symlink_generated_target(tmp_path: Path) -> None:
    _record_exchange(tmp_path)
    output_dir = tmp_path / "tests" / "generated"
    output_dir.mkdir(parents=True)
    victim = tmp_path / "victim.hurl"
    victim.write_text("victim\n", encoding="utf-8")
    (output_dir / "checkout_flow.hurl").symlink_to(victim)

    with pytest.raises(FreezeError, match="symlinked generated Hurl file"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_run_freeze_preserves_existing_target_when_atomic_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_exchange(tmp_path)
    output = tmp_path / "tests" / "generated" / "checkout_flow.hurl"
    output.parent.mkdir(parents=True)
    output.write_text("old\n", encoding="utf-8")

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("temporary write failed")

    monkeypatch.setattr(freeze, "safe_write_text", fail_safe_write)

    with pytest.raises(FreezeError, match="temporary write failed"):
        run_freeze(
            project_root=tmp_path,
            name="checkout_flow",
            golden=False,
            hurl_validator=lambda content, display_path: None,
        )

    assert output.read_text(encoding="utf-8") == "old\n"


def test_run_freeze_mock_refuses_symlink_mapping_target(tmp_path: Path) -> None:
    _record_dependency_exchange(tmp_path)
    output_dir = tmp_path / "mocks" / "payments"
    output_dir.mkdir(parents=True)
    victim = tmp_path / "victim.json"
    victim.write_text("victim\n", encoding="utf-8")
    (output_dir / "refund_flow-001.json").symlink_to(victim)

    with pytest.raises(FreezeError, match="symlinked WireMock mapping"):
        run_freeze_mock(
            project_root=tmp_path,
            name="refund_flow",
            service="payments",
        )

    assert victim.read_text(encoding="utf-8") == "victim\n"


def test_run_freeze_mock_reports_missing_state_and_writes_mappings(tmp_path: Path) -> None:
    with pytest.raises(FreezeError, match="No traffic state found"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")

    _record_dependency_exchange(tmp_path)

    result = run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")

    assert result.record_count == 1
    assert result.output_paths == (tmp_path / "mocks" / "payments" / "refund_flow-001.json",)
    assert '"request"' in result.output_paths[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("service", ["", "bad\nservice", "../payments", ".hidden", "bad service!"])
def test_run_freeze_mock_rejects_unsafe_service_names(tmp_path: Path, service: str) -> None:
    with pytest.raises(FreezeError, match="mock service"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service=service)


def test_run_freeze_mock_rejects_invalid_generated_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_dependency_exchange(tmp_path)

    def invalid_mapping(*args: object, **kwargs: object) -> tuple[GeneratedWireMockMapping, ...]:
        _ = args, kwargs
        return (GeneratedWireMockMapping("mocks/payments/refund_flow-001.json", "{"),)

    monkeypatch.setattr(freeze, "compile_traffic_session_to_wiremock", invalid_mapping)

    with pytest.raises(FreezeError, match="Expecting property name"):
        run_freeze_mock(project_root=tmp_path, name="refund_flow", service="payments")


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("tests\\generated\\flow.hurl", "POSIX separators"),
        ("../flow.hurl", "stay inside"),
        ("tests/manual/flow.hurl", "tests/generated"),
        ("tests/generated/flow.txt", "tests/generated"),
    ],
)
def test_generated_hurl_path_validation_rejects_unsafe_paths(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    generated = GeneratedTrafficHurlFile(relative_path=relative_path, content="GET https://x.test")

    with pytest.raises(FreezeError, match=message):
        freeze._resolve_generated_hurl_path(generated, root=tmp_path)


def test_generated_hurl_path_validation_rejects_non_file_target(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "generated" / "flow.hurl"
    target.mkdir(parents=True)

    with pytest.raises(FreezeError, match="non-file generated Hurl"):
        freeze._resolve_generated_hurl_path(
            GeneratedTrafficHurlFile("tests/generated/flow.hurl", "GET https://x.test"),
            root=tmp_path,
        )


def test_generated_hurl_path_validation_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "tests" / "generated" / "flow.hurl"
    output.parent.mkdir(parents=True)
    outside = tmp_path / "outside.hurl"
    outside.write_text("GET https://x.test\n", encoding="utf-8")
    output.symlink_to(outside)
    monkeypatch.setattr(freeze, "_reject_symlink_path", lambda *args, **kwargs: None)

    with pytest.raises(FreezeError, match="tests/generated"):
        freeze._resolve_generated_hurl_path(
            GeneratedTrafficHurlFile("tests/generated/flow.hurl", "GET https://x.test"),
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("mocks\\payments\\flow.json", "POSIX separators"),
        ("../flow.json", "stay inside"),
        ("tests/generated/flow.json", "mocks/<service>"),
        ("mocks/payments/flow.txt", "mocks/<service>"),
    ],
)
def test_wiremock_mapping_path_validation_rejects_unsafe_paths(
    tmp_path: Path,
    relative_path: str,
    message: str,
) -> None:
    generated = GeneratedWireMockMapping(relative_path=relative_path, content="{}")

    with pytest.raises(FreezeError, match=message):
        freeze._resolve_wiremock_mapping_path(generated, root=tmp_path)


def test_wiremock_mapping_path_validation_rejects_non_file_target(tmp_path: Path) -> None:
    target = tmp_path / "mocks" / "payments" / "flow.json"
    target.mkdir(parents=True)

    with pytest.raises(FreezeError, match="non-file WireMock mapping"):
        freeze._resolve_wiremock_mapping_path(
            GeneratedWireMockMapping("mocks/payments/flow.json", "{}"),
            root=tmp_path,
        )


def test_wiremock_mapping_path_validation_rejects_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "mocks" / "payments" / "flow.json"
    output.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    output.symlink_to(outside)
    monkeypatch.setattr(freeze, "_reject_symlink_path", lambda *args, **kwargs: None)

    with pytest.raises(FreezeError, match="under mocks"):
        freeze._resolve_wiremock_mapping_path(
            GeneratedWireMockMapping("mocks/payments/flow.json", "{}"),
            root=tmp_path,
        )
