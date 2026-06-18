"""Tests for read-only local evidence artifact indexing."""

import json
from pathlib import Path
from typing import Any

import pytest

import entroping.core.evidence_index as evidence_index
from entroping.core.evidence_index import build_local_evidence_index


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    original_read_text = Path.read_text

    def fail_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "run-latest.json":
            raise PermissionError("denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    artifacts = build_local_evidence_index(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in artifacts}

    assert by_id["run-json"].state == "invalid"
    assert by_id["run-json"].summary == "unreadable"


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


def test_evidence_index_rejects_paths_that_escape_after_normalization(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    path = tmp_path / "reports" / ".." / ".." / outside.name

    assert evidence_index._unsafe_summary(path, root=tmp_path) == "path outside project"


def test_evidence_index_rejects_paths_that_are_not_under_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"

    assert evidence_index._unsafe_summary(outside, root=tmp_path) == "path outside project"
