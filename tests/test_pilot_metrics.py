"""Tests for local pilot metrics report generation."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.pilot_metrics as pilot_metrics
from entroping.core.pilot_metrics import (
    PILOT_METRICS_SCHEMA_VERSION,
    PilotMetricsError,
    build_pilot_metrics_report,
    render_pilot_metrics_markdown,
    run_pilot_metrics_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_report() -> dict[str, object]:
    return {
        "schema_version": "entroping.run-report.v1",
        "project": "checkout|api token=live-secret",
        "environment": "ci",
        "generated_at": "2026-06-19T00:00:00+00:00",
        "summary": {
            "total": 2,
            "passed": 1,
            "failed": 1,
            "exit_code": 1,
            "selected": 2,
            "executed": 2,
            "not_scheduled": 0,
        },
        "tests": [
            {
                "path": "tests/checkout.hurl",
                "execution_path": ".entroping/run/checkout.hurl",
                "status": "failed",
                "exit_code": 1,
                "duration_ms": 12,
                "rule_ids": ["global_latency"],
                "stdout": "raw-output-secret-must-not-render",
                "stderr": "",
                "known_failures": [
                    {
                        "test": "tests/checkout.hurl",
                        "rule_id": "global_latency",
                        "issue_id": "PAY-1024",
                        "expires": "2026-12-31",
                        "reason": "Temporary exception",
                    },
                    {
                        "test": "tests/checkout.hurl",
                        "rule_id": "payment_timeout",
                        "issue_id": "PAY-1025",
                        "expires": "2026-12-31",
                        "reason": "Temporary exception",
                    },
                ],
            },
            {
                "path": "tests/health.hurl",
                "execution_path": ".entroping/run/health.hurl",
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 8,
                "rule_ids": [],
                "stdout": "",
                "stderr": "",
            },
        ],
    }


def _evidence_bundle(*, status: str = "ready") -> dict[str, object]:
    return {
        "schema_version": "entroping.evidence-bundle.v1",
        "generated_at": "2026-06-19T00:00:00+00:00",
        "purpose": "design-partner-upload-readiness",
        "project": "checkout-api",
        "summary": {
            "status": status,
            "required_total": 3,
            "required_present": 3 if status == "ready" else 2,
            "required_missing": 0 if status == "ready" else 1,
            "required_invalid": 0,
            "artifacts_total": 3 if status == "ready" else 2,
            "diagnostics_total": 0 if status == "ready" else 1,
        },
        "artifacts": [],
        "missing_artifacts": [],
        "diagnostics": [],
        "manifest_audit": {
            "path": "reports/artifact-manifest.json",
            "status": "verified",
            "chain_path": ".entroping/report-audit-chain.jsonl",
            "checked_events": 1,
            "latest_event_hash": "0" * 64,
            "diagnostics": [],
        },
    }


def _write_all_sanitized_inputs(root: Path) -> None:
    _write_json(root / "reports" / "run-latest.json", _run_report())
    _write_json(root / "reports" / "evidence-bundle.json", _evidence_bundle())
    _write_json(
        root / "reports" / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "attention", "findings": 1, "evidence_links": 2},
        },
    )
    _write_json(
        root / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "verified"}},
        },
    )
    _write_json(
        root / "reports" / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {
                "status": "attention",
                "configured_roles": 2,
                "manifests": 2,
                "findings": 1,
            },
        },
    )


def _metrics_by_id(report: Any) -> dict[str, Any]:
    return {metric.id: metric for metric in report.metrics}


def _sources_by_id(report: Any) -> dict[str, Any]:
    return {source.id: source for source in report.sources}


def test_run_pilot_metrics_report_summarizes_available_sanitized_evidence(
    tmp_path: Path,
) -> None:
    _write_all_sanitized_inputs(tmp_path)

    result = run_pilot_metrics_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "pilot-metrics.json"
    assert result.report.schema_version == PILOT_METRICS_SCHEMA_VERSION
    assert result.report.summary.status == "partial"
    assert result.report.summary.metrics_known == 2
    assert result.report.summary.metrics_manual_input_required == 4
    assert result.report.summary.metrics_unknown == 0
    assert result.report.summary.sources_present == 5

    metrics = _metrics_by_id(result.report)
    assert metrics["evidence_bundle_ready_rate"].state == "known"
    assert metrics["evidence_bundle_ready_rate"].value == 1.0
    assert metrics["evidence_bundle_ready_rate"].numerator == 1
    assert metrics["evidence_bundle_ready_rate"].denominator == 1
    assert metrics["evidence_bundle_ready_rate"].source_paths == (
        "reports/evidence-bundle.json",
    )
    assert metrics["waived_gates"].state == "known"
    assert metrics["waived_gates"].value == 2
    assert metrics["waived_gates"].source_paths == ("reports/run-latest.json",)
    assert metrics["setup_time_minutes"].state == "manual_input_required"
    assert metrics["useful_failures"].state == "manual_input_required"
    assert metrics["false_positives"].state == "manual_input_required"
    assert metrics["human_steering_events"].state == "manual_input_required"

    sources = _sources_by_id(result.report)
    assert sources["run_report"].state == "present"
    assert sources["run_report"].schema_version == "entroping.run-report.v1"
    assert sources["evidence_bundle"].state == "present"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pilot-metrics.v1"
    assert "raw-output-secret-must-not-render" not in json.dumps(payload)
    assert "live-secret" not in json.dumps(payload)


def test_pilot_metrics_marks_missing_artifacts_unknown_or_manual(
    tmp_path: Path,
) -> None:
    result = run_pilot_metrics_report(project_root=tmp_path, output="json")

    assert result.report.summary.status == "insufficient"
    assert result.report.summary.metrics_known == 0
    assert result.report.summary.metrics_unknown == 2
    assert result.report.summary.metrics_manual_input_required == 4
    assert result.report.summary.sources_missing == 5
    metrics = _metrics_by_id(result.report)
    assert metrics["evidence_bundle_ready_rate"].state == "unknown"
    assert metrics["waived_gates"].state == "unknown"
    assert metrics["setup_time_minutes"].state == "manual_input_required"
    sources = _sources_by_id(result.report)
    assert sources["runtime_card"].state == "missing"
    assert sources["agent_bundle"].state == "missing"
    assert result.output_path.exists()


def test_pilot_metrics_summarizes_partial_source_evidence(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _run_report())
    _write_json(tmp_path / "reports" / "evidence-bundle.json", _evidence_bundle())

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert report.summary.status == "partial"
    assert report.summary.sources_present == 2
    assert report.summary.sources_missing == 3
    assert report.summary.metrics_known == 2
    assert report.summary.metrics_manual_input_required == 4
    assert _sources_by_id(report)["runtime_card"].state == "missing"
    assert _sources_by_id(report)["agent_bundle"].state == "missing"


def test_pilot_metrics_marks_malformed_sources_without_rendering_contents(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_text(
        '{"schema_version": "entroping.run-report.v1", "stdout": "raw-output-bad"}',
        encoding="utf-8",
    )
    _write_json(
        reports / "evidence-bundle.json",
        {"schema_version": "entroping.evidence-bundle.v999", "summary": {"status": "ready"}},
    )
    (reports / "artifact-manifest.json").mkdir()

    report = build_pilot_metrics_report(project_root=tmp_path)

    sources = _sources_by_id(report)
    assert sources["run_report"].state == "invalid"
    assert sources["evidence_bundle"].state == "invalid"
    assert sources["artifact_manifest"].state == "unsafe"
    metrics = _metrics_by_id(report)
    assert metrics["waived_gates"].state == "unknown"
    assert metrics["evidence_bundle_ready_rate"].state == "unknown"
    rendered = render_pilot_metrics_markdown(report)
    assert "raw-output-bad" not in rendered
    assert "unsupported schema_version" in rendered


def test_pilot_metrics_markdown_escapes_and_lists_manual_metrics(tmp_path: Path) -> None:
    _write_all_sanitized_inputs(tmp_path)

    result = run_pilot_metrics_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "pilot-metrics.md"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Pilot Metrics" in markdown
    assert "evidence_bundle_ready_rate" in markdown
    assert "1.0" in markdown
    assert "setup_time_minutes" in markdown
    assert "manual_input_required" in markdown
    assert "minutes" in markdown
    assert "checkout\\|api" in markdown
    assert "live-secret" not in markdown
    assert "raw-output-secret-must-not-render" not in markdown


def test_pilot_metrics_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(PilotMetricsError, match="Unsupported pilot metrics output"):
        run_pilot_metrics_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_pilot_metrics_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(PilotMetricsError, match="pilot metrics path must stay under"):
        run_pilot_metrics_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "pilot-metrics.json",
        )


def test_pilot_metrics_rejects_dot_entroping_output_path(tmp_path: Path) -> None:
    with pytest.raises(PilotMetricsError, match="must not be written into .entroping"):
        run_pilot_metrics_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "pilot-metrics.json",
        )


def test_pilot_metrics_rejects_secret_like_rendered_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pilot_metrics,
        "render_pilot_metrics_markdown",
        lambda _report: "token=live-secret\n",
    )

    with pytest.raises(PilotMetricsError, match="contains secret-like content"):
        run_pilot_metrics_report(project_root=tmp_path, output="md")


def test_pilot_metrics_marks_symlinked_report_artifact_unsafe(tmp_path: Path) -> None:
    actual = tmp_path / "actual-reports"
    actual.mkdir()
    (tmp_path / "reports").symlink_to(actual, target_is_directory=True)
    _write_json(actual / "run-latest.json", _run_report())

    report = build_pilot_metrics_report(project_root=tmp_path)

    sources = _sources_by_id(report)
    assert sources["run_report"].state == "unsafe"
    assert _metrics_by_id(report)["waived_gates"].state == "unknown"


def test_pilot_metrics_marks_oversized_artifact_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _run_report())
    original_stat = Path.stat

    def fake_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = original_stat(path, follow_symlinks=follow_symlinks)
        if path.name != "run-latest.json":
            return result
        values = list(result)
        values[6] = pilot_metrics._MAX_PILOT_METRICS_ARTIFACT_BYTES + 1
        return type(result)(values)

    monkeypatch.setattr(Path, "stat", fake_stat)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"


def test_pilot_metrics_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> None:
        raise SafeWriteError("write refused")

    monkeypatch.setattr(pilot_metrics, "safe_write_text", fail_write)

    with pytest.raises(PilotMetricsError, match="write refused"):
        run_pilot_metrics_report(project_root=tmp_path, output="json")


def test_pilot_metrics_marks_invalid_json_source_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_text("{", encoding="utf-8")

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"
    assert "Could not parse run report" in _sources_by_id(report)["run_report"].summary


def test_pilot_metrics_marks_non_object_json_source_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_text("[]", encoding="utf-8")

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"
    assert "must be a JSON object" in _sources_by_id(report)["run_report"].summary


def test_pilot_metrics_marks_non_utf8_source_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_bytes(b"\xff")

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"
    assert "Could not decode run report" in _sources_by_id(report)["run_report"].summary


def test_pilot_metrics_marks_unreadable_source_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _run_report())
    original_read_text = Path.read_text

    def fail_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.name == "run-latest.json":
            raise OSError("permission denied")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"
    assert "Could not read run report" in _sources_by_id(report)["run_report"].summary


def test_pilot_metrics_marks_source_boundary_error_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_symlink_check(_candidate: Path, *, root: Path) -> Path:
        _ = root
        raise ValueError("outside")

    monkeypatch.setattr(pilot_metrics, "first_symlink_path_component", fail_symlink_check)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert report.summary.sources_unsafe == 5
    assert _sources_by_id(report)["run_report"].state == "unsafe"


def test_pilot_metrics_rejects_symlinked_output_path(tmp_path: Path) -> None:
    actual = tmp_path / "actual-reports"
    actual.mkdir()
    (tmp_path / "linked-reports").symlink_to(actual, target_is_directory=True)

    with pytest.raises(PilotMetricsError, match="uses symlinked component"):
        run_pilot_metrics_report(
            project_root=tmp_path,
            output="md",
            output_path=Path("linked-reports") / "pilot-metrics.md",
        )


def test_pilot_metrics_rejects_resolved_output_outside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pilot_metrics,
        "first_symlink_path_component",
        lambda _path, *, root: None,
    )

    with pytest.raises(PilotMetricsError, match="must stay under the project root"):
        run_pilot_metrics_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "pilot-metrics.json",
        )


def test_pilot_metrics_rejects_resolved_source_outside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pilot_metrics,
        "first_symlink_path_component",
        lambda _path, *, root: None,
    )

    with pytest.raises(PilotMetricsError, match="must stay inside the project"):
        pilot_metrics._resolve_source_path(Path("..") / "run-latest.json", root=tmp_path)


def test_pilot_metrics_marks_bad_evidence_bundle_status_invalid(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        _evidence_bundle(status="mystery"),
    )

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["evidence_bundle"].state == "invalid"
    assert _metrics_by_id(report)["evidence_bundle_ready_rate"].state == "unknown"


def test_pilot_metrics_marks_bad_artifact_manifest_status_invalid(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "mystery"}},
        },
    )

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["artifact_manifest"].state == "invalid"


def test_pilot_metrics_marks_malformed_run_known_failures_invalid(tmp_path: Path) -> None:
    payload = _run_report()
    tests = payload["tests"]
    assert isinstance(tests, list)
    first = tests[0]
    assert isinstance(first, dict)
    first["known_failures"] = {"rule_id": "global_latency"}
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"


def test_pilot_metrics_marks_malformed_run_tests_invalid(tmp_path: Path) -> None:
    payload = _run_report()
    payload["tests"] = {}
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"


def test_pilot_metrics_marks_bad_run_count_invalid(tmp_path: Path) -> None:
    payload = _run_report()
    summary = payload["summary"]
    assert isinstance(summary, dict)
    summary["total"] = True
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "invalid"


def test_pilot_metrics_accepts_run_without_selected_count(tmp_path: Path) -> None:
    payload = _run_report()
    summary = payload["summary"]
    assert isinstance(summary, dict)
    summary.pop("selected")
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].summary.startswith("2 selected tests")


def test_pilot_metrics_ignores_non_object_run_test_rows(tmp_path: Path) -> None:
    payload = _run_report()
    tests = payload["tests"]
    assert isinstance(tests, list)
    tests.insert(0, "ignored")
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["run_report"].state == "present"
    assert _metrics_by_id(report)["waived_gates"].value == 2


def test_pilot_metrics_marks_empty_runtime_status_invalid(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "", "findings": 0},
        },
    )

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["runtime_card"].state == "invalid"


def test_pilot_metrics_marks_runtime_card_schema_mismatch_invalid(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {"schema_version": "entroping.runtime-card.v999", "summary": {"status": "pass"}},
    )

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["runtime_card"].state == "invalid"
    assert "unsupported schema_version" in _sources_by_id(report)["runtime_card"].summary


def test_pilot_metrics_marks_agent_bundle_missing_summary_invalid(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "agent-bundle.json",
        {"schema_version": "entroping.agent-review-bundle.v1"},
    )

    report = build_pilot_metrics_report(project_root=tmp_path)

    assert _sources_by_id(report)["agent_bundle"].state == "invalid"
    assert "field summary must be an object" in _sources_by_id(report)["agent_bundle"].summary


def test_pilot_metrics_internal_unsupported_source_guard() -> None:
    definition = pilot_metrics._SourceDefinition(
        id=cast(Any, "unsupported"),
        label="Unsupported",
        path=Path("reports") / "unsupported.json",
        schema_version="entroping.unsupported.v1",
    )

    with pytest.raises(PilotMetricsError, match="Unsupported pilot metrics source"):
        pilot_metrics._source_summary(definition, {})
