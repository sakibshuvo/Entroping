"""Tests for safe captured-traffic session summaries."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from entroping.bridge.capture_summary import (
    CAPTURE_SUMMARY_SCHEMA_VERSION,
    CaptureSummaryCount,
    capture_summary_report_to_dict,
    compile_capture_summary,
    render_capture_summary_markdown,
)
from entroping.core import capture_summary_report
from entroping.core.capture_summary_report import (
    MAX_CAPTURE_SUMMARY_EXCHANGES,
    CaptureSummaryError,
    run_capture_summary_report,
)
from entroping.core.traffic_redactor import redact_traffic_exchange
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import TrafficBody, TrafficExchange, TrafficRequest, TrafficResponse

BASE_TIME = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def _raw_exchange(
    *,
    url: str,
    method: str = "GET",
    status_code: int | None = 200,
    offset_minutes: int = 0,
    secret: str = "capture-secret",
) -> TrafficExchange:
    response = (
        None
        if status_code is None
        else TrafficResponse(
            status_code=status_code,
            headers={"Set-Cookie": f"session={secret}"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=42,
                text=f'{{"token":"{secret}","ok":true}}',
            ),
        )
    )
    return TrafficExchange(
        captured_at=BASE_TIME + timedelta(minutes=offset_minutes),
        duration_ms=25,
        request=TrafficRequest(
            method=method,
            url=f"{url}?token={secret}",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            body=TrafficBody(
                content_type="application/json",
                size_bytes=64,
                text=f'{{"password":"{secret}"}}',
            ),
        ),
        response=response,
    )


def _redacted_exchange(
    *,
    url: str,
    method: str = "GET",
    status_code: int | None = 200,
    offset_minutes: int = 0,
    secret: str = "capture-secret",
) -> TrafficExchange:
    return redact_traffic_exchange(
        _raw_exchange(
            url=url,
            method=method,
            status_code=status_code,
            offset_minutes=offset_minutes,
            secret=secret,
        )
    )


def _counts(rows: tuple[CaptureSummaryCount, ...]) -> dict[str, int]:
    return {row.label: row.count for row in rows}


def test_capture_summary_aggregates_safe_counts_without_values() -> None:
    exchanges = (
        _redacted_exchange(
            url="https://api.example.test/checkout",
            method="POST",
            status_code=201,
            offset_minutes=0,
            secret="checkout-secret",
        ),
        _redacted_exchange(
            url="https://payments.example.test/charge",
            method="POST",
            status_code=502,
            offset_minutes=1,
            secret="payment-secret",
        ),
        _redacted_exchange(
            url="https://api.example.test/orders",
            method="GET",
            status_code=404,
            offset_minutes=2,
            secret="order-secret",
        ),
    )

    report = compile_capture_summary(exchanges)
    payload = capture_summary_report_to_dict(report)
    markdown = render_capture_summary_markdown(report)

    assert payload["schema_version"] == CAPTURE_SUMMARY_SCHEMA_VERSION
    assert payload["summary"] == {
        "total_records": 3,
        "total_sessions": 1,
        "redacted_records": 3,
        "unredacted_records": 0,
    }
    assert _counts(report.methods) == {"POST": 2, "GET": 1}
    assert _counts(report.hosts) == {"api.example.test": 2, "payments.example.test": 1}
    assert _counts(report.dependency_targets) == {"payments.example.test": 1}
    assert _counts(report.status_families) == {"2xx": 1, "4xx": 1, "5xx": 1}
    assert report.sessions[0].id == "session-001"
    assert report.sessions[0].primary_host == "api.example.test"
    assert _counts(report.sessions[0].dependency_targets) == {"payments.example.test": 1}
    assert "request authorization header" in _counts(report.redaction_categories)
    assert "request password body field" in _counts(report.redaction_categories)
    assert "# Entroping Capture Summary" in markdown
    assert "payments.example.test" in markdown
    assert "checkout-secret" not in markdown
    assert "payment-secret" not in markdown
    assert "order-secret" not in markdown
    assert "[REDACTED]" not in markdown
    assert "?token=" not in markdown


def test_capture_summary_splits_multiple_sessions_by_inactivity_gap() -> None:
    report = compile_capture_summary(
        (
            _redacted_exchange(url="https://api.example.test/first", offset_minutes=0),
            _redacted_exchange(url="https://api.example.test/second", offset_minutes=29),
            _redacted_exchange(url="https://api.example.test/third", offset_minutes=61),
        )
    )

    assert [session.id for session in report.sessions] == ["session-001", "session-002"]
    assert [session.record_count for session in report.sessions] == [2, 1]


def test_capture_summary_counts_no_response_status_family() -> None:
    report = compile_capture_summary(
        (
            _redacted_exchange(
                url="https://api.example.test/timeout",
                status_code=None,
            ),
        )
    )

    assert _counts(report.status_families) == {"no response": 1}
    assert _counts(report.sessions[0].status_families) == {"no response": 1}


def test_capture_summary_handles_empty_state() -> None:
    report = compile_capture_summary(())
    payload = capture_summary_report_to_dict(report)
    markdown = render_capture_summary_markdown(report)

    summary = cast(dict[str, object], payload["summary"])
    assert summary["total_records"] == 0
    assert payload["sessions"] == []
    assert "No captured traffic records found." in markdown


def test_capture_summary_marks_unredacted_records_without_rendering_values() -> None:
    report = compile_capture_summary(
        (
            _raw_exchange(
                url="https://api.example.test/unsafe",
                secret="unsafe-secret",
            ),
        )
    )

    markdown = render_capture_summary_markdown(report)

    assert report.summary.unredacted_records == 1
    assert "unsafe-secret" not in markdown
    assert "Unredacted records | 1" in markdown


def test_run_capture_summary_report_writes_json_from_readonly_state(
    tmp_path: Path,
) -> None:
    store = TrafficStore.open_project(tmp_path)
    store.record_exchange(
        _redacted_exchange(
            url="https://api.example.test/checkout",
            method="POST",
            status_code=201,
            secret="write-secret",
        )
    )
    state_path = tmp_path / ".entroping" / "state.db"
    before = state_path.stat().st_mtime_ns

    result = run_capture_summary_report(project_root=tmp_path, output="json")
    after = state_path.stat().st_mtime_ns
    content = (tmp_path / "reports" / "capture-summary.json").read_text(encoding="utf-8")

    assert result.output_path == tmp_path / "reports" / "capture-summary.json"
    assert result.report.summary.total_records == 1
    assert after == before
    assert CAPTURE_SUMMARY_SCHEMA_VERSION in content
    assert "write-secret" not in content
    assert "[REDACTED]" not in content


def test_run_capture_summary_report_writes_empty_markdown_for_empty_state(
    tmp_path: Path,
) -> None:
    TrafficStore.open_project(tmp_path)

    result = run_capture_summary_report(project_root=tmp_path, output="md")
    content = (tmp_path / "reports" / "capture-summary.md").read_text(encoding="utf-8")

    assert result.report.summary.total_records == 0
    assert "No captured traffic records found." in content


def test_run_capture_summary_report_reads_one_past_maximum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrafficStore.open_project(tmp_path)
    requested_limits: list[int | None] = []

    def read_bounded(
        project_root: Path,
        *,
        limit: int | None = None,
    ) -> tuple[TrafficExchange, ...]:
        _ = project_root
        requested_limits.append(limit)
        return ()

    monkeypatch.setattr(capture_summary_report, "list_project_exchanges_readonly", read_bounded)

    run_capture_summary_report(project_root=tmp_path, output="md")

    assert requested_limits == [MAX_CAPTURE_SUMMARY_EXCHANGES + 1]


def test_run_capture_summary_report_allows_maximum_in_memory_exchanges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrafficStore.open_project(tmp_path)
    exchange = _redacted_exchange(url="https://api.example.test/bounded")
    exchanges = (exchange,) * MAX_CAPTURE_SUMMARY_EXCHANGES

    def read_bounded(
        project_root: Path,
        *,
        limit: int | None = None,
    ) -> tuple[TrafficExchange, ...]:
        _ = project_root, limit
        return exchanges

    monkeypatch.setattr(
        capture_summary_report,
        "list_project_exchanges_readonly",
        read_bounded,
    )

    markdown_result = run_capture_summary_report(project_root=tmp_path, output="md")
    markdown = (tmp_path / "reports" / "capture-summary.md").read_text(encoding="utf-8")
    json_result = run_capture_summary_report(project_root=tmp_path, output="json")
    content = (tmp_path / "reports" / "capture-summary.json").read_text(encoding="utf-8")

    assert markdown_result.report.summary.total_records == MAX_CAPTURE_SUMMARY_EXCHANGES
    assert json_result.report.summary.total_records == MAX_CAPTURE_SUMMARY_EXCHANGES
    assert "# Entroping Capture Summary" in markdown
    assert CAPTURE_SUMMARY_SCHEMA_VERSION in content


def test_run_capture_summary_report_rejects_oversized_state_before_compile_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrafficStore.open_project(tmp_path)
    exchange = _redacted_exchange(url="https://api.example.test/oversized")
    exchanges = (exchange,) * (MAX_CAPTURE_SUMMARY_EXCHANGES + 1)

    def read_oversized(
        project_root: Path,
        *,
        limit: int | None = None,
    ) -> tuple[TrafficExchange, ...]:
        _ = project_root, limit
        return exchanges

    monkeypatch.setattr(
        capture_summary_report,
        "list_project_exchanges_readonly",
        read_oversized,
    )

    def fail_compile(exchanges: tuple[TrafficExchange, ...]) -> object:
        _ = exchanges
        pytest.fail("compile_capture_summary must not run for oversized state")

    def fail_render(report: object, output: str) -> str:
        _ = report, output
        pytest.fail("_render_report must not run for oversized state")

    def fail_write(path: Path, content: str, *, root: Path) -> None:
        _ = path, content, root
        pytest.fail("_write_text_atomically must not run for oversized state")

    monkeypatch.setattr(capture_summary_report, "compile_capture_summary", fail_compile)
    monkeypatch.setattr(capture_summary_report, "_render_report", fail_render)
    monkeypatch.setattr(capture_summary_report, "_write_text_atomically", fail_write)

    with pytest.raises(
        CaptureSummaryError,
        match="^Capture summary exceeds the maximum supported exchange count\\.$",
    ):
        run_capture_summary_report(project_root=tmp_path, output="md")

    assert not (tmp_path / "reports" / "capture-summary.md").exists()
    assert not (tmp_path / "reports" / "capture-summary.json").exists()


def test_run_capture_summary_report_reports_missing_state(tmp_path: Path) -> None:
    with pytest.raises(CaptureSummaryError, match="No traffic state found"):
        run_capture_summary_report(project_root=tmp_path, output="md")

    assert not (tmp_path / ".entroping").exists()


def test_run_capture_summary_report_wraps_traffic_store_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrafficStore.open_project(tmp_path)

    def fail_readonly(
        project_root: Path,
        *,
        limit: int | None = None,
    ) -> tuple[TrafficExchange, ...]:
        _ = project_root, limit
        from entroping.core.traffic_store import TrafficStoreError

        raise TrafficStoreError("readonly traffic failed")

    monkeypatch.setattr(capture_summary_report, "list_project_exchanges_readonly", fail_readonly)

    with pytest.raises(CaptureSummaryError, match="readonly traffic failed"):
        run_capture_summary_report(project_root=tmp_path, output="md")


def test_run_capture_summary_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrafficStore.open_project(tmp_path)

    def fail_write(path: Path, content: str, *, artifact: str, root: Path | None = None) -> Path:
        _ = path, content, artifact, root
        from entroping.core.safe_write import SafeWriteError

        raise SafeWriteError("cannot write capture summary")

    monkeypatch.setattr(capture_summary_report, "safe_write_text", fail_write)

    with pytest.raises(CaptureSummaryError, match="cannot write capture summary"):
        run_capture_summary_report(project_root=tmp_path, output="md")
