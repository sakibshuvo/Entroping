"""Tests for PR runtime evidence card generation."""

import json
import os
from pathlib import Path

import pytest

import entroping.core.runtime_card as runtime_card
from entroping.core.runtime_card import (
    RUNTIME_CARD_SCHEMA_VERSION,
    RuntimeCardDriftEvidence,
    RuntimeCardError,
    RuntimeCardFinding,
    RuntimeCardRedactionEvidence,
    RuntimeCardRunEvidence,
    build_runtime_card,
    render_runtime_card_markdown,
    run_runtime_card_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_report(*, project: str = "checkout-api") -> dict[str, object]:
    return {
        "schema_version": "entroping.run-report.v1",
        "project": project,
        "environment": "ci",
        "generated_at": "2026-06-18T00:00:00+00:00",
        "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
        "tests": [
            {
                "path": "tests/checkout.hurl",
                "execution_path": ".entroping/run/checkout.hurl",
                "status": "failed",
                "exit_code": 1,
                "duration_ms": 12,
                "rule_ids": ["auth_required", "global_latency"],
                "stdout": "Authorization: Bearer sk-proj-secret-must-not-render",
                "stderr": "",
            },
            {
                "path": "tests/health.hurl",
                "execution_path": ".entroping/run/health.hurl",
                "status": "passed",
                "exit_code": 0,
                "duration_ms": 10,
                "rule_ids": [],
                "stdout": "",
                "stderr": "",
            },
        ],
    }


def _passing_run_report(*, project: str = "checkout-api") -> dict[str, object]:
    return {
        "schema_version": "entroping.run-report.v1",
        "project": project,
        "environment": "ci",
        "generated_at": "2026-06-18T00:00:00+00:00",
        "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
        "tests": [],
    }


def _write_runtime_card_inputs(root: Path, *, project: str = "checkout-api") -> None:
    _write_json(root / "reports" / "run-latest.json", _run_report(project=project))
    _write_json(
        root / "reports" / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "project": "checkout-api",
            "environment": "ci",
            "generated_at": "2026-06-18T00:00:00+00:00",
            "baseline_path": ".entroping/drift-baseline.json",
            "summary": {
                "baseline_tests": 2,
                "current_tests": 2,
                "findings": 2,
                "drifted": 2,
                "missing_baseline": False,
            },
            "findings": [],
        },
    )
    _write_json(
        root / "reports" / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 3,
                "total_sessions": 1,
                "redacted_records": 2,
                "unredacted_records": 1,
            },
            "sessions": [],
            "methods": [],
            "hosts": [],
            "dependency_targets": [],
            "status_families": [],
            "redaction_categories": [{"label": "low-confidence-body", "count": 1}],
        },
    )
    _write_json(
        root / "reports" / "evidence-bundle.json",
        _evidence_bundle_payload(status="ready"),
    )
    _write_json(
        root / "reports" / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {
                "status": "attention",
                "roles": 3,
                "configured_roles": 2,
                "manifests": 2,
                "findings": 1,
            },
        },
    )


def _write_verified_capture_summary(root: Path) -> None:
    _write_json(
        root / "reports" / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 1,
                "total_sessions": 1,
                "redacted_records": 1,
                "unredacted_records": 0,
            },
            "sessions": [],
            "methods": [],
            "hosts": [],
            "dependency_targets": [],
            "status_families": [],
            "redaction_categories": [],
        },
    )


def _write_verified_artifact_manifest(root: Path) -> None:
    _write_json(
        root / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "verified"}},
        },
    )


def test_run_runtime_card_report_summarizes_existing_evidence(tmp_path: Path) -> None:
    _write_runtime_card_inputs(tmp_path)

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "runtime-card.json"
    assert result.card.schema_version == RUNTIME_CARD_SCHEMA_VERSION
    assert result.card.summary.status == "fail"
    assert result.card.run is not None
    assert result.card.run.project == "checkout-api"
    assert result.card.run.failed_gate_ids == ("auth_required", "global_latency")
    assert result.card.drift.status == "drift"
    assert result.card.redaction.status == "attention"
    assert result.card.release.evidence_bundle_status == "ready"
    assert result.card.agent_provenance.status == "attention"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.runtime-card.v1"
    assert "sk-proj-secret-must-not-render" not in json.dumps(payload)


def test_run_runtime_card_report_writes_fail_card_when_run_report_is_missing(
    tmp_path: Path,
) -> None:
    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.run is None
    assert result.card.artifacts[0].state == "missing"
    assert ("missing_required_artifact", "reports/run-latest.json") in {
        (finding.code, finding.path) for finding in result.card.findings
    }
    assert result.output_path.exists()


def test_run_runtime_card_report_writes_markdown_without_evidence_links(
    tmp_path: Path,
) -> None:
    result = run_runtime_card_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.card.summary.status == "fail"
    assert "No sanitized evidence links were found." in markdown
    assert "missing_required_artifact" in markdown


def test_run_runtime_card_report_marks_missing_release_evidence_attention(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "attention"
    assert result.card.summary.findings == 2
    assert result.card.release.evidence_links == (
        "reports/run-latest.json",
        "reports/capture-summary.json",
    )
    assert result.card.drift.status == "unknown"
    assert result.card.redaction.status == "verified"
    assert {
        ("missing_artifact_manifest", "reports/artifact-manifest.json"),
        ("missing_evidence_bundle", "reports/evidence-bundle.json"),
    } <= {(finding.code, finding.path) for finding in result.card.findings}


def test_runtime_card_marks_missing_redaction_attention(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "attention"
    assert card.redaction.status == "missing"


def test_run_runtime_card_report_rejects_malformed_present_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "run-latest.json").write_text("{", encoding="utf-8")

    with pytest.raises(RuntimeCardError, match="Could not parse run report"):
        run_runtime_card_report(project_root=tmp_path, output="json")

    assert not (tmp_path / "reports" / "runtime-card.json").exists()


def test_run_runtime_card_report_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(RuntimeCardError, match="Unsupported runtime card output"):
        run_runtime_card_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_run_runtime_card_report_rejects_unsafe_output_path(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())

    with pytest.raises(RuntimeCardError, match="runtime card path must stay under"):
        run_runtime_card_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "runtime-card.json",
        )


def test_run_runtime_card_report_rejects_secret_like_rendered_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    monkeypatch.setattr(
        runtime_card,
        "render_runtime_card_markdown",
        lambda _card: "token=live-secret\n",
    )

    with pytest.raises(RuntimeCardError, match="contains secret-like content"):
        run_runtime_card_report(project_root=tmp_path, output="md")


def test_run_runtime_card_report_rejects_schema_mismatch(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_json(
        tmp_path / "reports" / "drift.json",
        {"schema_version": "entroping.drift-report.v999"},
    )

    with pytest.raises(RuntimeCardError, match="must use schema_version"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_run_runtime_card_report_rejects_non_object_json(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeCardError, match="must be a JSON object"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_run_runtime_card_report_rejects_unreadable_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    original_read_text = Path.read_text

    def fail_run_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.name == "run-latest.json":
            raise OSError("permission denied")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_run_read)

    with pytest.raises(RuntimeCardError, match="Could not read run report"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_run_runtime_card_report_rejects_directory_artifact(tmp_path: Path) -> None:
    (tmp_path / "reports" / "run-latest.json").mkdir(parents=True)

    with pytest.raises(RuntimeCardError, match="path is not a file"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_run_runtime_card_report_rejects_symlinked_artifact_component(tmp_path: Path) -> None:
    actual = tmp_path / "actual-reports"
    actual.mkdir()
    (tmp_path / "reports").symlink_to(actual, target_is_directory=True)
    _write_json(actual / "run-latest.json", _passing_run_report())

    with pytest.raises(RuntimeCardError, match="uses symlinked component"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_run_runtime_card_report_wraps_artifact_boundary_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())

    def fail_symlink_check(_candidate: Path, *, root: Path) -> Path:
        _ = root
        raise ValueError("outside")

    monkeypatch.setattr(runtime_card, "first_symlink_path_component", fail_symlink_check)

    with pytest.raises(RuntimeCardError, match="must stay inside the project"):
        run_runtime_card_report(project_root=tmp_path, output="json")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": [],
                "tests": [],
            },
            "Run report field summary must be an object",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": {},
            },
            "Run report field tests must be a list",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": -1, "passed": 0, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            "summary.total must be a non-negative integer",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": True, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": [],
            },
            "summary.total must be a non-negative integer",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": "0"},
                "tests": [],
            },
            "summary.exit_code must be an integer",
        ),
        (
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": False},
                "tests": [],
            },
            "summary.exit_code must be an integer",
        ),
    ],
)
def test_run_runtime_card_report_rejects_malformed_run_fields(
    tmp_path: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", payload)

    with pytest.raises(RuntimeCardError, match=message):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_runtime_card_summarizes_optional_attention_and_verified_paths(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "run-latest.json",
        {
            **_passing_run_report(project=""),
            "tests": [
                "ignored",
                {
                    "status": "timeout",
                    "exit_code": 0,
                    "rule_ids": ["timeout_gate"],
                },
            ],
        },
    )
    _write_json(
        tmp_path / "reports" / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "summary": {"findings": 0, "drifted": 0, "missing_baseline": True},
        },
    )
    _write_json(
        tmp_path / "reports" / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 2,
                "redacted_records": 2,
                "unredacted_records": 0,
            },
            "redaction_categories": [
                "ignored",
                {"label": "high-confidence-body", "count": 1},
            ],
        },
    )
    _write_json(
        tmp_path / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "verified"}},
        },
    )
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        _evidence_bundle_payload(
            status="not_ready",
            required_present=2,
            required_missing=1,
            required_invalid=1,
            diagnostics=[
                {
                    "severity": "error",
                    "code": "checksum_mismatch",
                    "path": "reports/run-latest.json",
                    "message": "Evidence artifact checksum does not match artifact manifest.",
                }
            ],
            manifest_audit_status="broken",
        ),
    )
    _write_json(
        tmp_path / "reports" / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {
                "status": "pass",
                "configured_roles": 1,
                "manifests": 1,
                "findings": 0,
            },
        },
    )

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "fail"
    assert card.run is not None
    assert card.run.project == "unknown"
    assert card.run.failed_gate_ids == ("timeout_gate",)
    assert card.drift.status == "missing_baseline"
    assert card.redaction.status == "verified"
    assert card.release.artifact_manifest_audit_status == "verified"
    assert card.release.evidence_bundle_status == "not_ready"
    assert card.pilot_readiness.status == "not_ready"
    assert card.pilot_readiness.missing_artifacts == 1
    assert card.pilot_readiness.invalid_artifacts == 1
    assert card.pilot_readiness.checksum_mismatches == 1
    assert card.pilot_readiness.manifest_audit_status == "broken"
    assert card.agent_provenance.status == "pass"
    assert "evidence_bundle_attention" in {finding.code for finding in card.findings}


def test_runtime_card_summarizes_clean_optional_evidence(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_verified_artifact_manifest(tmp_path)
    _write_json(
        tmp_path / "reports" / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "summary": {"findings": 0, "drifted": 0, "missing_baseline": False},
        },
    )
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        _evidence_bundle_payload(status="ready"),
    )

    result = run_runtime_card_report(project_root=tmp_path, output="md")

    assert result.card.summary.status == "pass"
    assert result.card.drift.status == "none"
    assert "No runtime-card findings were found." in result.output_path.read_text(
        encoding="utf-8"
    )


def test_runtime_card_marks_present_drift_attention(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_json(
        tmp_path / "reports" / "drift.json",
        {
            "schema_version": "entroping.drift-report.v1",
            "summary": {"findings": 0, "drifted": 0, "missing_baseline": True},
        },
    )

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "attention"
    assert card.drift.status == "missing_baseline"


def test_runtime_card_error_findings_force_failure() -> None:
    status = runtime_card._card_status(
        run=RuntimeCardRunEvidence(
            project="checkout-api",
            environment="ci",
            total=1,
            passed=1,
            failed=0,
            exit_code=0,
            failed_tests=0,
        ),
        drift=RuntimeCardDriftEvidence(
            status="none",
            findings=0,
            drifted=0,
            missing_baseline=False,
        ),
        redaction=RuntimeCardRedactionEvidence(
            status="verified",
            total_records=1,
            redacted_records=1,
            unredacted_records=0,
        ),
        findings=(
            [
                RuntimeCardFinding(
                    severity="error",
                    code="unsafe",
                    path=None,
                    message="Unsafe evidence.",
                )
            ]
        ),
    )

    assert status == "fail"


def test_runtime_card_summarizes_audit_and_agent_attention(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_json(
        tmp_path / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "audit": {"verification": {"status": "broken"}},
        },
    )
    _write_json(
        tmp_path / "reports" / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {
                "status": "fail",
                "configured_roles": 2,
                "manifests": 2,
                "findings": 1,
            },
        },
    )

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "attention"
    assert card.release.artifact_manifest_audit_status == "broken"
    assert card.agent_provenance.status == "fail"
    assert {"artifact_manifest_audit_attention", "agent_provenance_attention"} <= {
        finding.code for finding in card.findings
    }


def test_runtime_card_rejects_invalid_capture_categories(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_json(
        tmp_path / "reports" / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 1,
                "redacted_records": 1,
                "unredacted_records": 0,
            },
            "redaction_categories": {},
        },
    )

    with pytest.raises(RuntimeCardError, match="redaction_categories must be a list"):
        run_runtime_card_report(project_root=tmp_path, output="json")


def test_runtime_card_agent_unknown_status_requires_attention(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_json(
        tmp_path / "reports" / "agent-bundle.json",
        {
            "schema_version": "entroping.agent-review-bundle.v1",
            "summary": {
                "status": "unknown",
                "configured_roles": 1,
                "manifests": 1,
                "findings": 0,
            },
        },
    )

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "attention"
    assert card.agent_provenance.status == "attention"
    assert "agent_status_unrecognized" in {finding.code for finding in card.findings}


def test_runtime_card_markdown_redacts_and_escapes_unsafe_fields(tmp_path: Path) -> None:
    _write_runtime_card_inputs(
        tmp_path,
        project="checkout|api` token=live-secret\x1b[31m",
    )

    result = run_runtime_card_report(project_root=tmp_path, output="md")
    markdown = render_runtime_card_markdown(result.card)

    assert result.output_path == tmp_path / "reports" / "runtime-card.md"
    assert "live-secret" not in markdown
    assert "\x1b" not in markdown
    assert "token=[REDACTED]" in markdown
    assert "checkout\\|api'" in markdown
    assert "| Run JSON | present | reports/run-latest.json |" in markdown


def _evidence_bundle_payload(
    *,
    status: str,
    required_present: int = 3,
    required_missing: int = 0,
    required_invalid: int = 0,
    diagnostics: list[dict[str, object]] | None = None,
    manifest_audit_status: str = "verified",
) -> dict[str, object]:
    diagnostics = diagnostics or []
    return {
        "schema_version": "entroping.evidence-bundle.v1",
        "generated_at": "2026-06-18T00:00:00+00:00",
        "purpose": "design-partner-upload-readiness",
        "project": "checkout-api",
        "summary": {
            "status": status,
            "required_total": 3,
            "required_present": required_present,
            "required_missing": required_missing,
            "required_invalid": required_invalid,
            "artifacts_total": required_present,
            "diagnostics_total": len(diagnostics),
        },
        "artifacts": [],
        "missing_artifacts": [],
        "diagnostics": diagnostics,
        "manifest_audit": {
            "path": "reports/artifact-manifest.json",
            "status": manifest_audit_status,
            "chain_path": ".entroping/report-audit-chain.jsonl",
            "checked_events": 1,
            "latest_event_hash": "0" * 64,
            "diagnostics": [],
        },
    }


def test_runtime_card_includes_ready_pilot_readiness(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_verified_artifact_manifest(tmp_path)
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        _evidence_bundle_payload(status="ready"),
    )

    result = run_runtime_card_report(project_root=tmp_path, output="md")

    assert result.card.summary.status == "pass"
    assert result.card.pilot_readiness.status == "ready"
    assert result.card.pilot_readiness.path == "reports/evidence-bundle.json"
    assert result.card.pilot_readiness.missing_artifacts == 0
    assert result.card.pilot_readiness.invalid_artifacts == 0
    assert result.card.pilot_readiness.checksum_mismatches == 0
    assert result.card.pilot_readiness.manifest_audit_status == "verified"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "## Pilot Readiness" in markdown
    assert "- Status: `ready`" in markdown
    assert "- Missing artifacts: `0`" in markdown


def test_runtime_card_marks_missing_pilot_readiness(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_verified_artifact_manifest(tmp_path)

    card = build_runtime_card(project_root=tmp_path)

    assert card.summary.status == "attention"
    assert card.pilot_readiness.status == "missing"
    assert card.pilot_readiness.path == "reports/evidence-bundle.json"
    assert card.release.evidence_bundle_status == "missing"
    assert ("missing_evidence_bundle", "reports/evidence-bundle.json") in {
        (finding.code, finding.path) for finding in card.findings
    }


def test_runtime_card_marks_malformed_evidence_bundle_invalid(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    (tmp_path / "reports" / "evidence-bundle.json").write_text("{", encoding="utf-8")

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_marks_non_utf8_evidence_bundle_invalid(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    (tmp_path / "reports" / "evidence-bundle.json").write_bytes(b"\xff")

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_marks_oversized_evidence_bundle_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        _evidence_bundle_payload(status="ready"),
    )
    original_stat = Path.stat

    def fake_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = original_stat(path, follow_symlinks=follow_symlinks)
        if path.name != "evidence-bundle.json":
            return result
        values = list(result)
        values[6] = runtime_card._MAX_RUNTIME_CARD_ARTIFACT_BYTES + 1
        return type(result)(values)

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_marks_unsupported_evidence_bundle_schema_invalid(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        {"schema_version": "entroping.evidence-bundle.v999"},
    )

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.pilot_readiness.diagnostics == 1
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_marks_malformed_evidence_bundle_readiness_invalid(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        {
            **_evidence_bundle_payload(status="ready"),
            "summary": {"status": "unknown"},
        },
    )

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_rejects_boolean_evidence_bundle_readiness_count(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    payload = _evidence_bundle_payload(status="ready")
    summary = payload["summary"]
    assert isinstance(summary, dict)
    summary["required_missing"] = True
    _write_json(tmp_path / "reports" / "evidence-bundle.json", payload)

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "invalid"
    assert result.card.release.evidence_bundle_status == "invalid"
    assert "pilot_readiness_invalid" in {finding.code for finding in result.card.findings}


def test_runtime_card_accepts_pilot_readiness_without_manifest_audit(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    _write_verified_artifact_manifest(tmp_path)
    payload = _evidence_bundle_payload(status="ready")
    payload["manifest_audit"] = None
    _write_json(tmp_path / "reports" / "evidence-bundle.json", payload)

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "pass"
    assert result.card.pilot_readiness.status == "ready"
    assert result.card.pilot_readiness.manifest_audit_status == "missing"


def test_runtime_card_marks_unsafe_evidence_bundle_path(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "run-latest.json", _passing_run_report())
    _write_verified_capture_summary(tmp_path)
    (tmp_path / "reports" / "evidence-bundle.json").mkdir()

    result = run_runtime_card_report(project_root=tmp_path, output="json")

    assert result.card.summary.status == "fail"
    assert result.card.pilot_readiness.status == "unsafe"
    assert result.card.release.evidence_bundle_status == "unsafe"
    assert "pilot_readiness_unsafe" in {finding.code for finding in result.card.findings}
