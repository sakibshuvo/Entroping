"""Local test-pyramid evidence report tests."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence.test_pyramid_report as test_pyramid_report
from entroping.bridge.test_pyramid import (
    TestPyramidArtifactEvidence as PyramidArtifactEvidenceModel,
)
from entroping.bridge.test_pyramid import (
    compile_test_pyramid_report,
    render_test_pyramid_markdown,
)
from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.evidence.external_test_evidence import EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _write_text(path, json.dumps(payload))


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


def test_run_test_pyramid_report_classifies_existing_evidence_without_raw_values(
    tmp_path: Path,
) -> None:
    secret_marker = "secret-runtime-value"
    reports = tmp_path / "reports"
    _write_json(
        reports / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 2, "passed": 2, "failed": 0},
            "tests": [{"stdout": secret_marker}],
        },
    )
    _write_text(
        reports / "junit.xml",
        f"""<?xml version="1.0"?>
        <testsuite tests="2"><testcase name="{secret_marker}"/></testsuite>
        """,
    )
    _write_json(
        reports / "gate-coverage.json",
        {
            "schema_version": "entroping.gate-coverage-report.v1",
            "summary": {"total_gates": 2, "matched_gates": 2},
        },
    )
    _write_json(
        reports / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "summary": {"findings": 0, "drifted": 0},
        },
    )
    _write_json(
        reports / "entroping.sarif",
        {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": secret_marker}}}]},
    )
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {
                "status": "pass",
                "score": 98,
                "generated_tests": 4,
                "findings": 0,
            },
        },
    )
    _write_json(
        reports / "coverage.json",
        {
            "meta": {"version": "7.0"},
            "totals": {"percent_covered_display": "100", "covered_lines": 50},
            "files": {f"src/{secret_marker}.py": {"summary": {"covered_lines": 50}}},
        },
    )

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "test-pyramid.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-pyramid-report.v1"
    assert payload["summary"]["runtime_governance_status"] == "complete"
    assert payload["summary"]["findings"] == 0
    assert {layer["id"]: layer["status"] for layer in payload["layers"]} == {
        "code-coverage": "present",
        "runtime-api-proof": "present",
        "policy-governance": "present",
        "drift-contract": "present",
        "static-security": "present",
        "generated-test-quality": "present",
    }
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["artifacts"][0]["summary"] == "coverage 100%"
    assert secret_marker not in json.dumps(payload)

    markdown_result = test_pyramid_report.run_test_pyramid_report(
        project_root=tmp_path, output="md"
    )
    markdown = markdown_result.output_path.read_text(encoding="utf-8")
    assert "No missing runtime-governance proof detected from local artifacts." in markdown
    assert secret_marker not in markdown


def test_run_test_pyramid_report_omits_missing_external_test_evidence(
    tmp_path: Path,
) -> None:
    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    layer_ids = {layer.id for layer in result.report.layers}

    assert "external-test-evidence" not in layer_ids
    assert result.report.summary.total_layers == 6


def test_run_test_pyramid_report_includes_sanitized_external_test_evidence(
    tmp_path: Path,
) -> None:
    raw_marker = "raw_test_name_should_not_render"
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(marker=raw_marker),
    )

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in payload["layers"]}
    external_layer = layers["external-test-evidence"]
    assert external_layer["status"] == "present"
    assert external_layer["artifacts"][0] == {
        "id": "external-test-evidence-json",
        "label": "External Test Evidence JSON",
        "path": "reports/external-test-evidence.json",
        "state": "present",
        "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
        "summary": "partial, 5/5 layers, 10 tests, 0 failures, 0 errors, 1 skipped",
    }
    assert raw_marker not in json.dumps(payload)


def test_run_test_pyramid_report_marks_invalid_external_test_evidence_value_free(
    tmp_path: Path,
) -> None:
    raw_marker = "raw_external_test_name"
    payload = _external_test_evidence_payload(marker=raw_marker)
    payload["schema_version"] = "wrong.schema"
    _write_json(tmp_path / "reports" / "external-test-evidence.json", payload)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    rendered = result.output_path.read_text(encoding="utf-8")
    output = json.loads(rendered)
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == "schema mismatch"
    assert {(finding["artifact_id"], finding["state"]) for finding in output["findings"]} == {
        ("run-json", "missing"),
        ("junit-xml", "missing"),
        ("gate-coverage-json", "missing"),
    }
    assert raw_marker not in rendered


def test_run_test_pyramid_report_marks_symlinked_external_test_evidence_unsafe(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-external-test-evidence.json"
    outside.write_text(
        json.dumps(_external_test_evidence_payload(marker="outside-raw-name")),
        encoding="utf-8",
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "external-test-evidence.json").symlink_to(outside)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    rendered = result.output_path.read_text(encoding="utf-8")
    output = json.loads(rendered)
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "unsafe"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == (
        "symlinked path component"
    )
    assert "outside-raw-name" not in rendered


def test_run_test_pyramid_report_marks_external_test_evidence_directory_unsafe(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports" / "external-test-evidence.json").mkdir(parents=True)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "unsafe"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == "not a file"


def test_run_test_pyramid_report_rejects_secret_like_external_test_evidence(
    tmp_path: Path,
) -> None:
    payload = _external_test_evidence_payload(marker="sk-proj-" + ("a" * 24))
    _write_json(tmp_path / "reports" / "external-test-evidence.json", payload)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    rendered = result.output_path.read_text(encoding="utf-8")
    output = json.loads(rendered)
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "unsafe"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == ("secret-like content")
    assert "sk-proj" not in rendered


@pytest.mark.parametrize(
    ("raw_text", "expected_summary"),
    [
        ("{not-json", "invalid JSON"),
        ("[]", "invalid JSON"),
    ],
)
def test_run_test_pyramid_report_marks_malformed_external_test_evidence_invalid(
    tmp_path: Path,
    raw_text: str,
    expected_summary: str,
) -> None:
    _write_text(tmp_path / "reports" / "external-test-evidence.json", raw_text)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == (expected_summary)


def test_run_test_pyramid_report_marks_schema_invalid_external_test_evidence_invalid(
    tmp_path: Path,
) -> None:
    payload = _external_test_evidence_payload()
    payload.pop("summary")
    _write_json(tmp_path / "reports" / "external-test-evidence.json", payload)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == ("schema invalid")


def test_run_test_pyramid_report_marks_non_utf8_external_test_evidence_invalid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reports" / "external-test-evidence.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == ("invalid JSON")


def test_read_bounded_text_rejects_file_that_grows_after_fstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "reports" / "external-test-evidence.json"
    _write_text(path, '{"schema_version":"entroping.external-test-evidence.v1"}')

    class TinyStat:
        st_size = 0

    monkeypatch.setattr(os, "fstat", lambda _fd: TinyStat())

    assert test_pyramid_report._read_bounded_text(path, max_bytes=1) == (  # noqa: SLF001
        None,
        "artifact too large",
    )


def test_read_bounded_text_marks_open_error_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "reports" / "external-test-evidence.json"
    _write_text(path, '{"schema_version":"entroping.external-test-evidence.v1"}')

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise OSError("permission denied")

    monkeypatch.setattr(os, "open", fail_open)

    assert test_pyramid_report._read_bounded_text(path, max_bytes=1024) == (  # noqa: SLF001
        None,
        "unreadable",
    )


def test_run_test_pyramid_report_marks_unreadable_external_test_evidence_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(),
    )
    original_read_bounded_text = test_pyramid_report._read_bounded_text

    def fail_external_read(
        path: Path,
        *,
        max_bytes: int,
    ) -> tuple[str | None, str]:
        if path.name == "external-test-evidence.json":
            return None, "unreadable"
        return original_read_bounded_text(path, max_bytes=max_bytes)

    monkeypatch.setattr(test_pyramid_report, "_read_bounded_text", fail_external_read)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == "unreadable"


def test_run_test_pyramid_report_marks_oversized_external_test_evidence_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "external-test-evidence.json",
        _external_test_evidence_payload(),
    )
    monkeypatch.setattr(test_pyramid_report, "_MAX_EXTERNAL_EVIDENCE_ARTIFACT_BYTES", 1)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    output = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in output["layers"]}
    assert layers["external-test-evidence"]["status"] == "invalid"
    assert layers["external-test-evidence"]["artifacts"][0]["summary"] == ("artifact too large")


def test_run_test_pyramid_report_highlights_missing_runtime_governance_proof(
    tmp_path: Path,
) -> None:
    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "test-pyramid.md"
    assert result.report.summary.runtime_governance_status == "incomplete"
    assert {
        (finding.layer_id, finding.artifact_id, finding.state) for finding in result.report.findings
    } == {
        ("runtime-api-proof", "run-json", "missing"),
        ("runtime-api-proof", "junit-xml", "missing"),
        ("policy-governance", "gate-coverage-json", "missing"),
    }
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Test Pyramid Evidence" in markdown
    assert "## Missing Runtime Governance Proof" in markdown
    assert "`run-json`" in markdown
    assert "`junit-xml`" in markdown
    assert "`gate-coverage-json`" in markdown


def test_compile_test_pyramid_report_synthesizes_missing_required_artifacts() -> None:
    report = compile_test_pyramid_report(
        (
            PyramidArtifactEvidenceModel(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                summary="Run JSON present",
            ),
        ),
        project="checkout-api",
    )

    artifacts = {artifact.id: artifact for layer in report.layers for artifact in layer.artifacts}
    assert artifacts["run-json"].state == "present"
    assert artifacts["coverage-json"].state == "missing"
    assert artifacts["junit-xml"].state == "missing"
    assert {(finding.artifact_id, finding.state) for finding in report.findings} == {
        ("junit-xml", "missing"),
        ("gate-coverage-json", "missing"),
    }


def test_run_test_pyramid_report_handles_partial_evidence_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(test_pyramid_report, "build_local_evidence_index", lambda **_: ())

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["runtime_governance_status"] == "incomplete"
    assert {(finding["artifact_id"], finding["state"]) for finding in payload["findings"]} == {
        ("run-json", "missing"),
        ("junit-xml", "missing"),
        ("gate-coverage-json", "missing"),
    }


def test_render_test_pyramid_markdown_handles_markdown_sensitive_values() -> None:
    report = compile_test_pyramid_report(
        (
            PyramidArtifactEvidenceModel(
                id="coverage-json",
                label="Coverage | # JSON",
                path="reports/coverage.json",
                state="present",
                schema_version="coverage`schema",
                summary="coverage `100` | [source]\n# next & <img src=x>",
            ),
        ),
        project="`project`",
    )

    markdown = render_test_pyramid_markdown(report)

    assert "- Project: `` `project` ``" in markdown
    assert "coverage \\`100\\` \\| \\[source\\] \\# next &amp; &lt;img src=x&gt;" in markdown
    assert "schema ``coverage`schema``;" in markdown


def test_run_test_pyramid_report_marks_partial_runtime_proof_incomplete(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 1, "passed": 1, "failed": 0},
        },
    )
    _write_json(
        tmp_path / "reports" / "coverage.json",
        {
            "totals": {"percent_covered": 87.5},
            "files": {"src/hidden-value.py": {"summary": {"covered_lines": 1}}},
        },
    )

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in payload["layers"]}
    assert layers["runtime-api-proof"]["status"] == "incomplete"
    assert layers["code-coverage"]["artifacts"][0]["summary"] == "coverage 87.5%"
    assert "hidden-value.py" not in json.dumps(payload)


def test_run_test_pyramid_report_marks_unsafe_artifacts_without_following_them(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-run-latest.json"
    outside.write_text(
        '{"schema_version":"entroping.run-report.v1","summary":{"total":999},'
        '"value":"secret-outside-value"}\n',
        encoding="utf-8",
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "run-latest.json").symlink_to(outside)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    findings = payload["findings"]
    assert {
        (finding["artifact_id"], finding["state"], finding["message"]) for finding in findings
    } >= {
        (
            "run-json",
            "unsafe",
            "Runtime governance proof is unsafe for Run JSON evidence.",
        ),
    }
    assert "999" not in json.dumps(payload)
    assert "secret-outside-value" not in json.dumps(payload)


def test_run_test_pyramid_report_marks_symlinked_coverage_unsafe_without_reading(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside-coverage.json"
    outside.write_text('{"totals":{"percent_covered_display":"100"}}\n', encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "coverage.json").symlink_to(outside)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "unsafe"
    assert coverage_layer["artifacts"][0]["summary"] == "symlinked path component"


def test_run_test_pyramid_report_marks_coverage_directory_unsafe(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports" / "coverage.json").mkdir(parents=True)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "unsafe"
    assert coverage_layer["artifacts"][0]["summary"] == "not a file"


def test_run_test_pyramid_report_marks_invalid_coverage_without_raw_values(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "reports" / "coverage.json", '{"file":"secret-source.py"}')

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "coverage totals missing"
    assert "secret-source.py" not in json.dumps(payload)


def test_run_test_pyramid_report_preserves_unsafe_coverage_index_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "coverage.json",
        {"totals": {"percent_covered_display": "91%"}},
    )
    unsafe_coverage = LocalEvidenceArtifact(
        id="coverage-json",
        label="Coverage JSON",
        path="reports/coverage.json",
        state="unsafe",
        schema_version=None,
        summary="secret-like content",
    )

    monkeypatch.setattr(
        test_pyramid_report,
        "build_local_evidence_index",
        lambda *, project_root: (unsafe_coverage,),
    )

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "unsafe"
    assert coverage_layer["artifacts"][0] == {
        "id": "coverage-json",
        "label": "Coverage JSON",
        "path": "reports/coverage.json",
        "state": "unsafe",
        "schema_version": None,
        "summary": "secret-like content",
    }


def test_run_test_pyramid_report_marks_invalid_coverage_json(tmp_path: Path) -> None:
    _write_text(tmp_path / "reports" / "coverage.json", "{not-json")

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "invalid JSON"


def test_run_test_pyramid_report_marks_non_object_coverage_json_invalid(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "reports" / "coverage.json", "[]")

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "invalid JSON"


def test_run_test_pyramid_report_marks_coverage_without_percent_invalid(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "coverage.json",
        {"totals": {"percent_covered_display": "all", "percent_covered": -1}},
    )

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "coverage totals missing"


def test_run_test_pyramid_report_marks_oversized_coverage_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(tmp_path / "reports" / "coverage.json", "{}")
    monkeypatch.setattr(test_pyramid_report, "_MAX_COVERAGE_ARTIFACT_BYTES", 1)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "artifact too large"


def test_run_test_pyramid_report_marks_unreadable_coverage_without_value_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(tmp_path / "reports" / "coverage.json", '{"secret":"coverage-value"}')
    original_read_bounded_text = test_pyramid_report._read_bounded_text

    def fail_coverage_read(
        path: Path,
        *,
        max_bytes: int,
    ) -> tuple[str | None, str]:
        if path.name == "coverage.json":
            return None, "unreadable"
        return original_read_bounded_text(path, max_bytes=max_bytes)

    monkeypatch.setattr(test_pyramid_report, "_read_bounded_text", fail_coverage_read)

    result = test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    coverage_layer = next(layer for layer in payload["layers"] if layer["id"] == "code-coverage")
    assert coverage_layer["status"] == "invalid"
    assert coverage_layer["artifacts"][0]["summary"] == "unreadable"
    assert "coverage-value" not in json.dumps(payload)


def test_run_test_pyramid_report_wraps_evidence_index_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_index(*args: object, **kwargs: object) -> tuple[object, ...]:
        _ = (args, kwargs)
        raise OSError("index unavailable")

    monkeypatch.setattr(test_pyramid_report, "build_local_evidence_index", fail_index)

    with pytest.raises(test_pyramid_report.TestPyramidReportError, match="index unavailable"):
        test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")


def test_run_test_pyramid_report_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        _ = (args, kwargs)
        raise SafeWriteError("write blocked")

    monkeypatch.setattr(test_pyramid_report, "safe_write_text", fail_write)

    with pytest.raises(test_pyramid_report.TestPyramidReportError, match="write blocked"):
        test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="json")


def test_unsafe_coverage_summary_handles_path_safety_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_symlink_check(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise ValueError("outside")

    monkeypatch.setattr(test_pyramid_report, "first_symlink_path_component", fail_symlink_check)

    assert (
        test_pyramid_report._unsafe_artifact_summary(  # noqa: SLF001
            tmp_path / "reports" / "coverage.json",
            root=tmp_path,
        )
        == "path outside project"
    )


def test_unsafe_coverage_summary_rejects_resolved_path_outside_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        test_pyramid_report,
        "first_symlink_path_component",
        lambda *_, **__: None,
    )

    assert (
        test_pyramid_report._unsafe_artifact_summary(  # noqa: SLF001
            tmp_path.parent / "coverage.json",
            root=tmp_path,
        )
        == "path outside project"
    )


def test_run_test_pyramid_report_rejects_unknown_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported test-pyramid output"):
        test_pyramid_report.run_test_pyramid_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]
