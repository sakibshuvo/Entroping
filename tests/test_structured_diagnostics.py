"""Tests for value-free structured diagnostics."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from entroping.core import structured_diagnostics
from entroping.core.safe_write import SafeWriteError
from entroping.core.structured_diagnostics import (
    STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
    StructuredDiagnosticAttribute,
    StructuredDiagnosticEvent,
    StructuredDiagnosticLog,
    StructuredDiagnosticsError,
    build_diagnostic_event,
    diagnostic_event_to_dict,
    read_diagnostic_events,
)


def test_build_diagnostic_event_redacts_secret_like_text_and_keeps_safe_fields() -> None:
    event = build_diagnostic_event(
        component="run",
        operation="hurl.timeout",
        severity="warning",
        code="hurl_timeout",
        summary="token=live-token timed out",
        attributes={
            "artifact_path": "reports/run-latest.json",
            "duration_ms": 125,
            "optional_reason": None,
            "selected_count": 2,
            "status": "timeout",
        },
        timestamp="2026-06-19T00:00:00+00:00",
    )

    payload = diagnostic_event_to_dict(event)

    assert payload == {
        "schema_version": STRUCTURED_DIAGNOSTICS_SCHEMA_VERSION,
        "timestamp": "2026-06-19T00:00:00+00:00",
        "component": "run",
        "operation": "hurl.timeout",
        "severity": "warning",
        "code": "hurl_timeout",
        "summary": "token=[REDACTED] timed out",
        "attributes": [
            {"name": "artifact_path", "value": "reports/run-latest.json"},
            {"name": "duration_ms", "value": 125},
            {"name": "optional_reason", "value": None},
            {"name": "selected_count", "value": 2},
            {"name": "status", "value": "timeout"},
        ],
    }
    assert "live-token" not in json.dumps(payload)


@pytest.mark.parametrize(
    "attribute_name",
    [
        "api_token",
        "authorization",
        "cookie",
        "env_value",
        "prompt",
        "provider_output",
        "request_body",
        "response_body",
        "source_hurl",
    ],
)
def test_build_diagnostic_event_rejects_value_bearing_attribute_names(
    attribute_name: str,
) -> None:
    with pytest.raises(StructuredDiagnosticsError, match="value-free attribute name"):
        build_diagnostic_event(
            component="run",
            operation="unsafe.field",
            severity="error",
            code="unsafe_field",
            summary="Unsafe field",
            attributes={attribute_name: "redacted-or-raw-value"},
            timestamp="2026-06-19T00:00:00+00:00",
        )


def test_build_diagnostic_event_rejects_control_text_and_unsupported_values() -> None:
    with pytest.raises(StructuredDiagnosticsError, match="control characters"):
        build_diagnostic_event(
            component="run",
            operation="bad.summary",
            severity="error",
            code="bad_summary",
            summary="bad\0summary",
            timestamp="2026-06-19T00:00:00+00:00",
        )

    with pytest.raises(StructuredDiagnosticsError, match="unsupported attribute value"):
        build_diagnostic_event(
            component="run",
            operation="bad.attribute",
            severity="error",
            code="bad_attribute",
            summary="Bad attribute",
            attributes={"details": {"nested": "value"}},
            timestamp="2026-06-19T00:00:00+00:00",
        )


def test_build_diagnostic_event_wraps_schema_validation_errors() -> None:
    with pytest.raises(StructuredDiagnosticsError, match="failed schema validation"):
        build_diagnostic_event(
            component="Run",
            operation="run.started",
            severity="info",
            code="run_started",
            summary="Run started",
            timestamp="2026-06-19T00:00:00+00:00",
        )


def test_build_diagnostic_event_rejects_secret_like_text_after_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        structured_diagnostics,
        "redact_secret_like_values",
        lambda value: value,
    )

    with pytest.raises(StructuredDiagnosticsError, match="secret-like content"):
        build_diagnostic_event(
            component="run",
            operation="run.error",
            severity="error",
            code="run_error",
            summary="token=live-secret",
            timestamp="2026-06-19T00:00:00+00:00",
        )


def test_direct_event_model_construction_sanitizes_before_recording(
    tmp_path: Path,
) -> None:
    event = StructuredDiagnosticEvent(
        timestamp="2026-06-19T00:00:00+00:00",
        component="run",
        operation="run.error",
        severity="error",
        code="run_error",
        summary="token=live-secret",
        attributes=(
            StructuredDiagnosticAttribute(
                name="artifact_path",
                value="reports/run-latest.json",
            ),
            StructuredDiagnosticAttribute(name="status", value="token=live-secret"),
        ),
    )
    log = StructuredDiagnosticLog.open_project(tmp_path)

    log.record(event)
    payload = log.path.read_text(encoding="utf-8")

    assert "live-secret" not in payload
    assert "token=[REDACTED]" in payload


def test_direct_event_model_construction_rejects_unsafe_fields() -> None:
    with pytest.raises(ValidationError, match="control characters"):
        StructuredDiagnosticEvent(
            timestamp="2026-06-19T00:00:00+00:00",
            component="run",
            operation="run.error",
            severity="error",
            code="run_error",
            summary="bad\0summary",
        )

    with pytest.raises(ValidationError, match="value-free attribute name"):
        StructuredDiagnosticAttribute(name="api_token", value="redacted")


def test_attribute_name_rechecks_normalized_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_is_sensitive_key(value: str) -> bool:
        nonlocal calls
        _ = value
        calls += 1
        return calls == 2

    monkeypatch.setattr(structured_diagnostics, "is_sensitive_key", fake_is_sensitive_key)

    with pytest.raises(ValidationError, match="value-free attribute name"):
        StructuredDiagnosticAttribute(name="safe_name", value="redacted")


def test_structured_diagnostic_log_writes_jsonl_and_reads_valid_prefix(
    tmp_path: Path,
) -> None:
    log = StructuredDiagnosticLog.open_project(tmp_path)

    log.record(
        build_diagnostic_event(
            component="run",
            operation="run.started",
            severity="info",
            code="run_started",
            summary="Run started",
            attributes={"selected_count": 2},
            timestamp="2026-06-19T00:00:00+00:00",
        )
    )
    log.record(
        build_diagnostic_event(
            component="report",
            operation="artifact.written",
            severity="info",
            code="artifact_written",
            summary="Artifact written",
            attributes={"artifact_path": "reports/run-latest.json"},
            timestamp="2026-06-19T00:00:01+00:00",
        )
    )
    log.path.write_text(log.path.read_text(encoding="utf-8") + '{"partial"', encoding="utf-8")

    events = read_diagnostic_events(log.path)

    assert log.path == tmp_path / ".entroping" / "latest-diagnostics.jsonl"
    assert [event.code for event in events] == ["run_started", "artifact_written"]
    assert [event.operation for event in events] == ["run.started", "artifact.written"]


def test_read_diagnostic_events_rejects_completed_malformed_or_non_object_lines(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / ".entroping" / "latest-diagnostics.jsonl"
    log_path.parent.mkdir()
    log_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(StructuredDiagnosticsError, match="line 1 is not an object"):
        read_diagnostic_events(log_path)

    valid_event = diagnostic_event_to_dict(
        build_diagnostic_event(
            component="run",
            operation="run.started",
            severity="info",
            code="run_started",
            summary="Run started",
            timestamp="2026-06-19T00:00:00+00:00",
        )
    )
    log_path.write_text(json.dumps(valid_event) + "\nnot-json\n", encoding="utf-8")
    with pytest.raises(StructuredDiagnosticsError, match="invalid JSON on line 2"):
        read_diagnostic_events(log_path)


def test_read_diagnostic_events_skips_blank_lines_and_rejects_invalid_events(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / ".entroping" / "latest-diagnostics.jsonl"
    log_path.parent.mkdir()
    log_path.write_text(
        "\n"
        '{"schema_version":"entroping.diagnostics.v1","component":"run"}\n',
        encoding="utf-8",
    )

    with pytest.raises(StructuredDiagnosticsError, match="invalid event on line 2"):
        read_diagnostic_events(log_path)


def test_read_diagnostic_events_returns_empty_list_when_missing(tmp_path: Path) -> None:
    assert read_diagnostic_events(tmp_path / ".entroping" / "latest-diagnostics.jsonl") == []


def test_read_diagnostic_events_rejects_oversized_log_before_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / ".entroping" / "latest-diagnostics.jsonl"
    log_path.parent.mkdir()
    event = diagnostic_event_to_dict(
        build_diagnostic_event(
            component="run",
            operation="run.started",
            severity="info",
            code="run_started",
            summary="Run started",
            timestamp="2026-06-19T00:00:00+00:00",
        )
    )
    content = json.dumps(event) + "\n"
    log_path.write_text(content, encoding="utf-8")
    original_read_text = Path.read_text

    def reject_full_diagnostic_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == log_path:
            msg = "diagnostic log used unbounded read_text"
            raise AssertionError(msg)
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(
        structured_diagnostics,
        "_MAX_DIAGNOSTIC_EVENT_LOG_BYTES",
        len(content) - 1,
    )
    monkeypatch.setattr(Path, "read_text", reject_full_diagnostic_read)

    with pytest.raises(StructuredDiagnosticsError, match="diagnostic event log .* exceeds"):
        read_diagnostic_events(log_path)


def test_structured_diagnostic_log_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = StructuredDiagnosticLog.open_project(tmp_path)
    event = build_diagnostic_event(
        component="run",
        operation="run.error",
        severity="error",
        code="run_error",
        summary="Run error",
        timestamp="2026-06-19T00:00:00+00:00",
    )

    def fail_safe_write_text(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = (path, content, artifact, root)
        raise SafeWriteError("blocked")

    monkeypatch.setattr(structured_diagnostics, "safe_write_text", fail_safe_write_text)

    with pytest.raises(StructuredDiagnosticsError, match="blocked"):
        log.record(event)
