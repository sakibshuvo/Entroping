import json
import os
from pathlib import Path

from entroping.core.evidence.otlp_preview import (
    OTLP_PREVIEW_SCHEMA_VERSION,
    build_otlp_preview_packet,
    render_otlp_preview_markdown,
)


def _write_run_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-checkout-service",
                "environment": "local",
                "generated_at": "2026-07-04T00:00:00+00:00",
                "summary": {
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "exit_code": 1,
                },
                "tests": [
                    {
                        "path": "tests/private-checkout-flow.hurl",
                        "execution_path": ".entroping/run/private-checkout-flow.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 42,
                        "rule_ids": ["status"],
                        "stdout": "raw-output-should-not-render",
                        "stderr": "stderr-should-not-render",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_otlp_preview_reports_missing_sources_explicitly(tmp_path: Path) -> None:
    packet = build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.schema_version == OTLP_PREVIEW_SCHEMA_VERSION
    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "missing"
    assert by_id["otel_mapping"].state == "missing"
    assert packet.fixture.log_records == ()
    assert packet.fixture.metrics == ()
    assert packet.fixture.spans == ()
    assert packet.next_actions[0].source_ids == ("run_report",)


def test_otlp_preview_uses_counts_without_raw_run_values(tmp_path: Path) -> None:
    _write_run_report(tmp_path / "reports" / "run-latest.json")

    packet = build_otlp_preview_packet(project_root=tmp_path)
    payload = json.dumps(packet.model_dump(mode="json"), sort_keys=True)
    markdown = render_otlp_preview_markdown(packet)

    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 1
    assert packet.summary.metrics_total == 3
    assert packet.fixture.log_records[0].name == "entroping.run.summary"
    assert packet.fixture.metrics[0].name == "entroping.tests.total"
    assert packet.fixture.metrics[0].value == 2
    assert packet.fixture.spans[0].status_code == "ERROR"
    assert "private-checkout-service" not in payload
    assert "private-checkout-flow" not in payload
    assert "raw-output-should-not-render" not in payload
    assert "stderr-should-not-render" not in markdown


def test_otlp_preview_marks_wrong_schema_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _ = (reports / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v999"}\n',
        encoding="utf-8",
    )

    packet = build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "invalid"
    assert by_id["run_report"].summary == (
        "schema mismatch: expected entroping.run-report.v1"
    )


def test_otlp_preview_marks_symlinked_source_unsafe(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    target = tmp_path / "run-latest.json"
    _ = target.write_text('{"schema_version":"entroping.run-report.v1"}\n', encoding="utf-8")
    os.symlink(target, reports / "run-latest.json")

    packet = build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "unsafe"
    assert by_id["run_report"].summary == "symlinked path component"
