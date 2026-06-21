"""Tests for read-only local evidence artifact indexing."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

import entroping.core.evidence_index as evidence_index
import entroping.core.evidence_index_report as evidence_index_report
from entroping.core.evidence_index import build_local_evidence_index
from entroping.core.evidence_index_report import (
    EVIDENCE_INDEX_SCHEMA_VERSION,
    EvidenceIndexArtifact,
    EvidenceIndexError,
    EvidenceIndexPacket,
    EvidenceIndexSummary,
    render_evidence_index_markdown,
    run_evidence_index_report,
)
from entroping.core.external_test_evidence import EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
from entroping.core.otel_mapping import OTEL_MAPPING_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _opened_name(path: Any) -> str:
    try:
        return Path(os.fspath(path)).name
    except TypeError:
        return ""


def _external_test_evidence_payload(*, marker: str = "raw-test-name") -> dict[str, object]:
    return {
        "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "sources_total": 8,
            "sources_present": 5,
            "sources_missing": 3,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "layers_total": 5,
            "layers_with_evidence": 5,
            "layers_missing": 0,
            "layers_blocked": 0,
            "total_tests": 10,
            "total_failures": 0,
            "total_errors": 0,
            "total_skipped": 1,
            "line_coverage_percent": 87.5,
            "branch_coverage_percent": 50.0,
            "sarif_results_total": 2,
            "sarif_error_results": 0,
            "next_actions_total": 1,
        },
        "sources": [
            {
                "id": "unit_junit",
                "label": "unit JUnit",
                "path": "reports/external-tests/unit-junit.xml",
                "kind": "junit",
                "layer": "unit",
                "state": "present",
                "sha256": "a" * 64,
                "summary": marker,
                "suites": 1,
                "tests": 10,
                "failures": 0,
                "errors": 0,
                "skipped": 1,
                "line_coverage_percent": None,
                "branch_coverage_percent": None,
                "lines_covered": None,
                "lines_valid": None,
                "branches_covered": None,
                "branches_valid": None,
                "sarif_runs": None,
                "sarif_results_total": None,
                "sarif_error_results": None,
                "sarif_warning_results": None,
                "sarif_note_results": None,
                "sarif_none_results": None,
            },
        ],
        "layers": [
            {
                "id": "unit",
                "label": "Unit",
                "status": "covered",
                "source_ids": ["unit_junit"],
                "tests": 10,
                "failures": 0,
                "errors": 0,
                "skipped": 1,
                "blockers": [],
                "next_action": "Review counts-only evidence.",
            },
        ],
        "next_actions": [
            {
                "priority": "medium",
                "action": "Generate integration JUnit evidence.",
                "source_ids": ["integration_junit"],
                "layer_ids": ["integration"],
            }
        ],
    }


def test_evidence_index_discovers_stable_report_artifact_ids_without_raw_values(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    sensitive_marker = "sensitive-marker-should-not-render"
    _write_json(
        reports_dir / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
            "tests": [{"stderr": sensitive_marker}],
        },
    )
    _write_json(
        reports_dir / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 3,
                "redacted_records": 3,
                "unredacted_records": 0,
            },
        },
    )
    _write_json(
        reports_dir / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "summary": {"findings": 0, "drifted": 0},
        },
    )
    _write_json(
        reports_dir / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "summary": {"total_present": 4, "total_missing": 1},
            "audit": {"verification": {"status": "verified"}},
        },
    )
    _write_json(
        reports_dir / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "summary": {"status": "ready"},
        },
    )
    _write_json(
        reports_dir / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass"},
        },
    )
    _write_json(
        reports_dir / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {"status": "attention", "manifests": 2, "findings": 1},
        },
    )
    _write_json(
        reports_dir / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {
                "status": "warn",
                "score": 72,
                "generated_tests": 3,
                "findings": 4,
            },
        },
    )
    (reports_dir / "review-summary.md").write_text(
        "# Entroping Review Summary\n\n- Status: `pass`\n",
        encoding="utf-8",
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "present"
    assert by_id["run-json"].path == "reports/run-latest.json"
    assert by_id["run-json"].schema_version == "entroping.run-report.v1"
    assert by_id["run-json"].summary == "2 total, 1 passed, 1 failed"
    assert by_id["drift-json"].summary == "0 findings, 0 drifted"
    assert by_id["capture-summary-json"].summary == "3/3 records redacted, 0 unredacted"
    assert by_id["artifact-manifest-json"].summary == "4 present, 1 missing, audit verified"
    assert by_id["evidence-bundle-json"].summary == "ready"
    assert by_id["runtime-card-json"].summary == "pass"
    assert by_id["agent-bundle-json"].summary == "attention, 2 manifests, 1 findings"
    assert by_id["test-quality-json"].summary == "warn, score 72, 3 generated, 4 findings"
    assert by_id["review-summary-md"].state == "present"
    assert by_id["review-summary-md"].schema_version == "entroping.review-summary.md"
    assert sensitive_marker not in repr(artifacts)


def test_evidence_index_uses_shared_schema_constants_for_report_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evidence_index,
        "OTEL_MAPPING_SCHEMA_VERSION",
        "entroping.otel-mapping.test",
        raising=False,
    )
    monkeypatch.setattr(
        evidence_index,
        "EVIDENCE_INDEX_SCHEMA_VERSION",
        "entroping.evidence-index.test",
        raising=False,
    )

    definitions = {
        definition.id: definition for definition in evidence_index._artifact_definitions()
    }

    assert definitions["otel-mapping-json"].schema_version == "entroping.otel-mapping.test"
    assert definitions["evidence-index-json"].schema_version == "entroping.evidence-index.test"
    assert OTEL_MAPPING_SCHEMA_VERSION == "entroping.otel-mapping.v1"
    assert EVIDENCE_INDEX_SCHEMA_VERSION == "entroping.evidence-index.v1"


def test_evidence_index_report_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceIndexError, match="Unsupported evidence-index output"):
        run_evidence_index_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]
    with pytest.raises(EvidenceIndexError, match="must stay under"):
        run_evidence_index_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-index.json",
        )
    with pytest.raises(EvidenceIndexError, match="must not be written into"):
        run_evidence_index_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-index.json",
        )
    with pytest.raises(EvidenceIndexError, match="must not be written into"):
        run_evidence_index_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "evidence-index.json",
        )


def test_evidence_index_report_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(EvidenceIndexError, match="symlinked component"):
        run_evidence_index_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "evidence-index.json",
        )


def test_evidence_index_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(evidence_index_report, "safe_write_text", fail_safe_write)

    with pytest.raises(EvidenceIndexError, match="disk full"):
        run_evidence_index_report(project_root=tmp_path, output="json")


def test_evidence_index_report_relative_display_falls_back_to_name(tmp_path: Path) -> None:
    assert (
        evidence_index_report._relative_display(tmp_path.parent / "outside", root=tmp_path)
        == "outside"
    )


def test_evidence_index_markdown_escapes_table_cells() -> None:
    packet = EvidenceIndexPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="checkout-api",
        summary=EvidenceIndexSummary(
            status="ready",
            artifacts_total=1,
            artifacts_present=1,
            artifacts_missing=0,
            artifacts_invalid=0,
            artifacts_unsafe=0,
        ),
        artifacts=(
            EvidenceIndexArtifact(
                id="artifact",
                label="Artifact",
                path="reports/artifact.json",
                state="present",
                schema_version="entroping.artifact.v1",
                summary="ready\\|split *bold*_under_`code`\nnext",
            ),
        ),
    )

    markdown = render_evidence_index_markdown(packet)

    assert (
        "ready&#92;\\|split &#42;bold&#42;&#95;under&#95;&#96;code&#96; next"
        in markdown
    )


def test_evidence_index_marks_unsafe_artifact_paths_without_following_them(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    outside = tmp_path.parent / "outside-run-latest.json"
    outside.write_text(
        '{"schema_version":"entroping.run-report.v1","summary":{"total":999}}\n',
        encoding="utf-8",
    )
    (reports_dir / "run-latest.json").symlink_to(outside)
    (reports_dir / "evidence-bundle.json").mkdir()

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "unsafe"
    assert by_id["run-json"].summary == "symlinked path component"
    assert by_id["evidence-bundle-json"].state == "unsafe"
    assert by_id["evidence-bundle-json"].summary == "not a file"
    assert "999" not in repr(artifacts)


def test_evidence_index_marks_parent_symlinked_report_directory_unsafe(
    tmp_path: Path,
) -> None:
    outside_reports = tmp_path.parent / "outside-reports"
    outside_reports.mkdir()
    (outside_reports / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v1","summary":{"total":999}}\n',
        encoding="utf-8",
    )
    (tmp_path / "reports").symlink_to(outside_reports, target_is_directory=True)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "unsafe"
    assert by_id["run-json"].summary == "symlinked path component"
    assert "999" not in repr(artifacts)


@pytest.mark.parametrize(
    ("filename", "payload", "expected_summary"),
    (
        ("run-latest.json", "{not-json", "invalid JSON"),
        (
            "drift.json",
            '{"schema_version":"wrong.schema","summary":{"findings":0}}\n',
            "schema mismatch",
        ),
    ),
)
def test_evidence_index_marks_malformed_present_json_artifacts_invalid(
    tmp_path: Path,
    filename: str,
    payload: str,
    expected_summary: str,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / filename).write_text(payload, encoding="utf-8")

    artifacts = build_local_evidence_index(project_root=tmp_path)
    invalid = [artifact for artifact in artifacts if artifact.path == f"reports/{filename}"]

    assert invalid[0].state == "invalid"
    assert invalid[0].schema_version is None
    assert invalid[0].summary == expected_summary


def test_evidence_index_marks_oversized_json_artifacts_invalid_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text('{"schema_version":"x"}\n', encoding="utf-8")
    monkeypatch.setattr(evidence_index, "_MAX_JSON_ARTIFACT_BYTES", 8)

    def fail_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        _ = (self, args, kwargs)
        raise AssertionError("oversized artifact should not be read")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "invalid"
    assert by_id["run-json"].summary == "artifact too large"


def test_evidence_index_marks_unreadable_json_artifacts_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v1"}\n',
        encoding="utf-8",
    )
    original_open = os.open

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if _opened_name(path) == "run-latest.json":
            raise PermissionError("denied")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_open)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "invalid"
    assert by_id["run-json"].summary == "unreadable"


def test_evidence_index_marks_invalid_utf8_json_artifacts_invalid(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_bytes(b"\xff")

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "invalid"
    assert by_id["run-json"].summary == "invalid JSON"


def test_evidence_index_uses_controlled_fallback_summaries_for_partial_metadata(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    _write_json(
        reports_dir / "run-latest.json",
        {"schema_version": "entroping.run-report.v1", "summary": {}},
    )
    _write_json(
        reports_dir / "run-plan.json",
        {"schema_version": "entroping.run-plan.v1", "summary": {}},
    )
    _write_json(
        reports_dir / "drift.json",
        {"schema_version": "entroping.drift-report.v1", "summary": {}},
    )
    _write_json(
        reports_dir / "capture-summary.json",
        {"schema_version": "entroping.capture-summary.v1", "summary": {}},
    )
    _write_json(
        reports_dir / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "summary": {},
            "audit": {"verification": {"status": "broken"}},
        },
    )
    _write_json(
        reports_dir / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {"status": "unexpected-provider-string"},
        },
    )
    _write_json(
        reports_dir / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "unknown"},
        },
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].summary == "run summary available"
    assert by_id["run-plan-json"].summary == "Run Plan present"
    assert by_id["drift-json"].summary == "drift summary available"
    assert by_id["capture-summary-json"].summary == "capture summary available"
    assert by_id["artifact-manifest-json"].summary == "audit broken"
    assert by_id["agent-bundle-json"].summary == "unknown"
    assert by_id["test-quality-json"].summary == "unknown"


def test_evidence_index_uses_fallback_summaries_for_negative_counts(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    _write_json(
        reports_dir / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": -1, "passed": 1, "failed": 0},
        },
    )
    _write_json(
        reports_dir / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 1,
                "redacted_records": -1,
                "unredacted_records": 0,
            },
        },
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].summary == "run summary available"
    assert by_id["capture-summary-json"].summary == "capture summary available"
    assert "-1" not in repr(artifacts)


def test_evidence_index_uses_fallback_summaries_for_boolean_counts(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    _write_json(
        reports_dir / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": True, "passed": 1, "failed": 0},
        },
    )
    _write_json(
        reports_dir / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": True,
                "redacted_records": 1,
                "unredacted_records": 0,
            },
        },
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].summary == "run summary available"
    assert by_id["capture-summary-json"].summary == "capture summary available"
    assert "True" not in repr(artifacts)


def test_evidence_index_includes_recent_value_free_packet_artifacts(
    tmp_path: Path,
) -> None:
    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["notification-packet-json"].path == "reports/notification-packet.json"
    assert by_id["notification-packet-json"].state == "missing"
    assert by_id["observability-packet-json"].path == "reports/observability-packet.json"
    assert by_id["otel-mapping-md"].path == "reports/otel-mapping.md"
    assert by_id["otel-mapping-json"].path == "reports/otel-mapping.json"
    assert by_id["observability-adapter-readiness-md"].path == (
        "reports/observability-adapter-readiness.md"
    )
    assert by_id["observability-adapter-readiness-json"].path == (
        "reports/observability-adapter-readiness.json"
    )
    assert by_id["api-inventory-json"].path == "reports/api-inventory.json"
    assert by_id["mutation-readiness-json"].path == "reports/mutation-readiness.json"
    assert by_id["evidence-index-json"].path == "reports/evidence-index.json"
    assert by_id["external-test-evidence-json"].path == "reports/external-test-evidence.json"
    assert by_id["external-test-evidence-json"].state == "missing"
    assert by_id["external-test-evidence-md"].path == "reports/external-test-evidence.md"
    assert by_id["external-test-evidence-md"].state == "missing"
    assert by_id["evidence-cloud-dashboard-html"].path == (
        "reports/evidence-cloud-dashboard.html"
    )
    assert by_id["evidence-cloud-dashboard-json"].path == (
        "reports/evidence-cloud-dashboard.json"
    )
    assert by_id["pr-evidence-card-md"].path == "reports/pr-evidence-card.md"
    assert by_id["pr-evidence-card-json"].path == "reports/pr-evidence-card.json"
    assert by_id["evidence-action-plan-md"].path == "reports/evidence-action-plan.md"
    assert by_id["evidence-action-plan-json"].path == "reports/evidence-action-plan.json"
    assert by_id["work-item-draft-md"].path == "reports/work-item-draft.md"
    assert by_id["work-item-draft-json"].path == "reports/work-item-draft.json"
    assert by_id["work-item-import-bundle-json"].path == (
        "reports/work-item-import-bundle.json"
    )
    assert by_id["work-item-import-bundle-csv"].path == (
        "reports/work-item-import-bundle.csv"
    )
    assert by_id["pilot-outcome-md"].path == "reports/pilot-outcome.md"
    assert by_id["pilot-outcome-json"].path == "reports/pilot-outcome.json"
    assert by_id["pilot-cohort-md"].path == "reports/pilot-cohort.md"
    assert by_id["pilot-cohort-json"].path == "reports/pilot-cohort.json"


def test_evidence_index_rejects_secret_like_otel_mapping_json(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "otel-mapping.json",
        {
            "schema_version": "entroping.otel-mapping.v1",
            "summary": {"status": "ready"},
            "leaked": "sk-proj-" + ("a" * 24),
        },
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["otel-mapping-json"].state == "unsafe"
    assert by_id["otel-mapping-json"].summary == "secret-like content"


def test_evidence_index_rejects_secret_like_observability_adapter_readiness_json(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "observability-adapter-readiness.json",
        {
            "schema_version": "entroping.observability-adapter-readiness.v1",
            "summary": {"status": "ready"},
            "leaked": "sk-proj-" + ("a" * 24),
        },
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["observability-adapter-readiness-json"].state == "unsafe"
    assert by_id["observability-adapter-readiness-json"].summary == "secret-like content"


def test_evidence_index_discovers_external_test_evidence_without_raw_values(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    raw_marker = "raw_test_name_should_not_render"
    _write_json(
        reports_dir / "external-test-evidence.json",
        _external_test_evidence_payload(marker=raw_marker),
    )
    (reports_dir / "external-test-evidence.md").write_text(
        "# External Test Evidence\n\nraw_test_name_should_not_render\n",
        encoding="utf-8",
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "present"
    assert by_id["external-test-evidence-json"].schema_version == (
        EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
    )
    assert by_id["external-test-evidence-json"].summary == (
        "partial, 5/5 layers, 10 tests, 0 failures, 0 errors, 1 skipped"
    )
    assert by_id["external-test-evidence-md"].state == "present"
    assert by_id["external-test-evidence-md"].schema_version == (
        "entroping.external-test-evidence.md"
    )
    assert raw_marker not in repr(artifacts)


def test_evidence_index_marks_wrong_schema_external_test_evidence_invalid(
    tmp_path: Path,
) -> None:
    payload = _external_test_evidence_payload()
    payload["schema_version"] = "wrong.schema"
    _write_json(tmp_path / "reports" / "external-test-evidence.json", payload)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "invalid"
    assert by_id["external-test-evidence-json"].schema_version is None
    assert by_id["external-test-evidence-json"].summary == "schema mismatch"


def test_evidence_index_uses_external_test_evidence_status_fallback(
    tmp_path: Path,
) -> None:
    payload = _external_test_evidence_payload()
    assert isinstance(payload["summary"], dict)
    payload["summary"].pop("layers_total")
    _write_json(tmp_path / "reports" / "external-test-evidence.json", payload)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "present"
    assert by_id["external-test-evidence-json"].summary == "partial"


def test_evidence_index_marks_oversized_external_test_evidence_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(),
    )
    monkeypatch.setattr(evidence_index, "_MAX_JSON_ARTIFACT_BYTES", 1)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "invalid"
    assert by_id["external-test-evidence-json"].summary == "artifact too large"


def test_evidence_index_marks_unreadable_external_test_evidence_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(),
    )
    original_open = os.open

    def fail_external_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if _opened_name(path) == "external-test-evidence.json":
            raise PermissionError("denied")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_external_open)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "invalid"
    assert by_id["external-test-evidence-json"].summary == "unreadable"


def test_evidence_index_reads_secret_checked_external_test_evidence_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_path = tmp_path / "reports" / "external-test-evidence.json"
    _write_json(reports_path, _external_test_evidence_payload())
    original_open = os.open
    external_opens = 0

    def count_external_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        nonlocal external_opens
        if _opened_name(path) == "external-test-evidence.json":
            external_opens += 1
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", count_external_open)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "present"
    assert external_opens == 1


def test_evidence_index_does_not_retry_external_test_evidence_after_failed_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_path = tmp_path / "reports" / "external-test-evidence.json"
    _write_json(reports_path, _external_test_evidence_payload())
    original_open = os.open
    external_opens = 0

    def fail_then_succeed_external_open(
        path: Any,
        flags: int,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        nonlocal external_opens
        if _opened_name(path) == "external-test-evidence.json":
            external_opens += 1
            if external_opens == 1:
                raise PermissionError("denied")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", fail_then_succeed_external_open)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "invalid"
    assert by_id["external-test-evidence-json"].summary == "unreadable"
    assert external_opens == 1


@pytest.mark.skipif(
    not evidence_index._supports_no_follow_tree_open(),
    reason="requires no-follow descriptor traversal",
)
def test_evidence_index_rejects_external_test_evidence_replaced_by_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_path = tmp_path / "reports" / "external-test-evidence.json"
    _write_json(reports_path, _external_test_evidence_payload())
    outside = tmp_path.parent / "outside-external-test-evidence.json"
    outside_marker = "outside_secret_marker"
    _write_json(outside, _external_test_evidence_payload(marker=outside_marker))
    original_open = os.open
    replaced = False

    def replace_with_symlink_before_open(
        path: Any,
        flags: int,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        nonlocal replaced
        if _opened_name(path) == "external-test-evidence.json" and not replaced:
            reports_path.unlink()
            reports_path.symlink_to(outside)
            replaced = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_with_symlink_before_open)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "unsafe"
    assert by_id["external-test-evidence-json"].summary == "symlinked path component"
    assert outside_marker not in repr(artifacts)


def test_evidence_index_rejects_secret_like_external_test_evidence(
    tmp_path: Path,
) -> None:
    secret_marker = "sk-proj-" + ("a" * 24)
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(marker=secret_marker),
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "unsafe"
    assert by_id["external-test-evidence-json"].schema_version is None
    assert by_id["external-test-evidence-json"].summary == "secret-like content"
    assert "sk-proj" not in repr(artifacts)


def test_evidence_index_masks_mixed_case_sha_before_secret_detection(
    tmp_path: Path,
) -> None:
    mixed_case_sha = ("0123456789ABCDEFabcdef" * 3)[:64]
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(marker=mixed_case_sha),
    )

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["external-test-evidence-json"].state == "present"
    assert by_id["external-test-evidence-json"].summary == (
        "partial, 5/5 layers, 10 tests, 0 failures, 0 errors, 1 skipped"
    )
    assert mixed_case_sha not in repr(artifacts)


@pytest.mark.parametrize(
    ("payload", "expected_state", "expected_summary", "expected_schema"),
    (
        ('{"version":"2.1.0","runs":[]}\n', "present", "SARIF 2.1.0", "SARIF 2.1.0"),
        ('{"version":"2.0.0","runs":[]}\n', "invalid", "schema mismatch", None),
        ("not-json\n", "invalid", "invalid JSON", None),
    ),
)
def test_evidence_index_reports_sarif_state_without_rendering_contents(
    tmp_path: Path,
    payload: str,
    expected_state: str,
    expected_summary: str,
    expected_schema: str | None,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "entroping.sarif").write_text(payload, encoding="utf-8")

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["sarif"].state == expected_state
    assert by_id["sarif"].summary == expected_summary
    assert by_id["sarif"].schema_version == expected_schema


def test_evidence_index_marks_oversized_sarif_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "entroping.sarif").write_text(
        '{"version":"2.1.0","runs":[]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(evidence_index, "_MAX_JSON_ARTIFACT_BYTES", 8)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["sarif"].state == "invalid"
    assert by_id["sarif"].summary == "artifact too large"


def test_evidence_index_json_reader_rejects_path_outside_root(tmp_path: Path) -> None:
    assert evidence_index._read_json_artifact_bytes(
        tmp_path.parent / "outside.json",
        root=tmp_path,
    ) == (None, "path outside project")


@pytest.mark.skipif(
    not evidence_index._supports_no_follow_tree_open(),
    reason="requires no-follow descriptor traversal",
)
def test_evidence_index_no_follow_reader_rejects_invalid_relative_parts(
    tmp_path: Path,
) -> None:
    assert evidence_index._read_json_artifact_bytes_no_follow(
        root=tmp_path,
        relative_path=Path("..") / "outside.json",
    ) == (None, "path outside project")


@pytest.mark.skipif(
    not evidence_index._supports_no_follow_tree_open(),
    reason="requires no-follow descriptor traversal",
)
def test_evidence_index_no_follow_reader_reports_missing_artifact(tmp_path: Path) -> None:
    assert evidence_index._read_json_artifact_bytes_no_follow(
        root=tmp_path,
        relative_path=Path("missing.json"),
    ) == (None, "unreadable")


def test_evidence_index_best_effort_reader_handles_platform_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b'{"schema_version":"entroping.run-report.v1"}\n'
    reports_path = tmp_path / "reports" / "run-latest.json"
    reports_path.parent.mkdir()
    reports_path.write_bytes(payload)
    monkeypatch.setattr(evidence_index, "_supports_no_follow_tree_open", lambda: False)

    assert evidence_index._read_json_artifact_bytes(reports_path, root=tmp_path) == (
        payload,
        "",
    )


def test_evidence_index_best_effort_reader_rejects_non_file(tmp_path: Path) -> None:
    assert evidence_index._read_json_artifact_bytes_best_effort(tmp_path) == (
        None,
        "not a file",
    )


def test_evidence_index_best_effort_reader_rejects_changed_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "run-latest.json"
    path.write_text('{"schema_version":"entroping.run-report.v1"}\n', encoding="utf-8")
    path_stat = path.stat()

    class ChangedStat:
        st_mode = path_stat.st_mode
        st_dev = path_stat.st_dev + 1
        st_ino = path_stat.st_ino + 1
        st_size = path_stat.st_size

    monkeypatch.setattr(os, "fstat", lambda _fd: ChangedStat())

    assert evidence_index._read_json_artifact_bytes_best_effort(path) == (
        None,
        "unreadable",
    )


def test_evidence_index_best_effort_reader_reports_open_errors(tmp_path: Path) -> None:
    assert evidence_index._read_json_artifact_bytes_best_effort(
        tmp_path / "missing.json",
    ) == (None, "unreadable")


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="requires directory fds")
def test_evidence_index_descriptor_reader_rejects_non_regular_descriptor(
    tmp_path: Path,
) -> None:
    directory_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert evidence_index._read_bounded_bytes_from_descriptor(
            directory_descriptor,
        ) == (None, "not a file")
    finally:
        os.close(directory_descriptor)


def test_evidence_index_descriptor_reader_rejects_file_growth_after_fstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "run-latest.json"
    path.write_text("{}", encoding="utf-8")
    path_stat = path.stat()
    file_descriptor = os.open(path, os.O_RDONLY)

    class TinyStat:
        st_mode = path_stat.st_mode
        st_size = 1

    monkeypatch.setattr(evidence_index, "_MAX_JSON_ARTIFACT_BYTES", 2)
    monkeypatch.setattr(os, "fstat", lambda _fd: TinyStat())
    monkeypatch.setattr(os, "read", lambda _fd, _size: b"abc")
    try:
        assert evidence_index._read_bounded_bytes_from_descriptor(
            file_descriptor,
        ) == (None, "artifact too large")
    finally:
        os.close(file_descriptor)


def test_evidence_index_rejects_paths_that_escape_after_normalization(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    path = tmp_path / "reports" / ".." / ".." / outside.name

    assert evidence_index._unsafe_summary(path, root=tmp_path) == "path outside project"


def test_evidence_index_rejects_paths_that_are_not_under_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"

    assert evidence_index._unsafe_summary(outside, root=tmp_path) == "path outside project"
