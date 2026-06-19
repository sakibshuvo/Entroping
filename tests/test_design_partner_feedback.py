"""Tests for sanitized design-partner feedback artifact generation."""

import json
from pathlib import Path
from typing import Any

import pytest

import entroping.core.design_partner_feedback as feedback
from entroping.core.design_partner_feedback import (
    DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION,
    run_design_partner_feedback_report,
)

_HASH = "a" * 64


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_evidence_bundle(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "generated_at": "2026-06-19T00:00:00+00:00",
            "purpose": "design-partner-upload-readiness",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "required_total": 3,
                "required_present": 3,
                "required_missing": 0,
                "required_invalid": 0,
                "artifacts_total": 3,
                "diagnostics_total": 0,
            },
            "artifacts": [
                {
                    "kind": "artifact_manifest",
                    "path": "reports/artifact-manifest.json",
                    "required": True,
                    "schema_version": "entroping.report-artifact-manifest.v1",
                    "size_bytes": 100,
                    "sha256": _HASH,
                }
            ],
            "missing_artifacts": [],
            "diagnostics": [],
            "manifest_audit": {
                "path": "reports/artifact-manifest.json",
                "status": "verified",
                "chain_path": "reports/audit-chain.jsonl",
                "checked_events": 1,
                "latest_event_hash": _HASH,
                "diagnostics": [],
            },
        },
    )


def _write_runtime_card(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "run": None,
            "drift": {
                "status": "none",
                "findings": 0,
                "drifted": 0,
                "missing_baseline": False,
            },
            "redaction": {
                "status": "missing",
                "total_records": 0,
                "redacted_records": 0,
                "unredacted_records": 0,
                "low_confidence_categories": [],
            },
            "release": {
                "artifact_manifest_audit_status": "verified",
                "evidence_bundle_status": "ready",
                "evidence_links": ["reports/evidence-bundle.json"],
            },
            "pilot_readiness": {
                "status": "ready",
                "path": "reports/evidence-bundle.json",
                "missing_artifacts": 0,
                "invalid_artifacts": 0,
                "checksum_mismatches": 0,
                "diagnostics": 0,
                "manifest_audit_status": "verified",
            },
            "agent_provenance": {
                "status": "missing",
                "configured_roles": 0,
                "manifests": 0,
                "findings": 0,
            },
            "artifacts": [],
            "findings": [],
        },
    )


def _write_pilot_metrics(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "generated_at": "2026-06-19T00:00:00+00:00",
            "project": "checkout-api",
            "summary": {
                "status": "insufficient",
                "metrics_total": 0,
                "metrics_known": 0,
                "metrics_unknown": 0,
                "metrics_manual_input_required": 0,
                "sources_total": 0,
                "sources_present": 0,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
            },
            "metrics": [],
            "sources": [],
        },
    )


def test_run_design_partner_feedback_report_writes_sanitized_template_with_local_statuses(
    tmp_path: Path,
) -> None:
    _write_ready_evidence_bundle(tmp_path / "reports" / "evidence-bundle.json")
    _write_runtime_card(tmp_path / "reports" / "runtime-card.json")
    _write_pilot_metrics(tmp_path / "reports" / "pilot-metrics.json")

    result = run_design_partner_feedback_report(project_root=tmp_path)

    assert result.output_path == tmp_path / "reports" / "design-partner-feedback.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload == result.feedback.model_dump(mode="json")
    assert payload["schema_version"] == DESIGN_PARTNER_FEEDBACK_SCHEMA_VERSION
    assert payload["evidence"]["evidence_bundle_status"] == "ready"
    assert payload["evidence"]["entroping_commands_run"] == ["manual input required"]
    assert payload["evidence"]["runtime_card_status"] == "pass"
    assert payload["evidence"]["pilot_metrics_status"] == "insufficient"
    assert payload["evidence"]["evidence_paths"] == [
        "reports/evidence-bundle.json",
        "reports/runtime-card.json",
        "reports/pilot-metrics.json",
    ]
    assert payload["feedback"] == {
        "blocked_regression_or_useful_failure": None,
        "false_positive_or_noisy_gate": None,
        "missing_evidence": None,
        "setup_friction": None,
        "security_privacy_concern": None,
    }
    assert payload["monetization_signals"]["hosted_aggregation"] == {
        "answer": "unclear",
        "reason": "manual input required",
    }
    assert "raw_traffic" not in json.dumps(payload)


def test_run_design_partner_feedback_report_fails_closed_for_unsafe_output(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "design-partner-feedback.json"

    try:
        run_design_partner_feedback_report(project_root=tmp_path, output_path=outside)
    except ValueError as exc:
        assert "design-partner feedback artifact path must stay under" in str(exc)
    else:  # pragma: no cover - failure clarity
        raise AssertionError("expected unsafe output path to fail")


def test_run_design_partner_feedback_report_marks_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "evidence-bundle.json").write_text("not json\n", encoding="utf-8")
    (reports / "runtime-card.json").write_text(
        json.dumps({"schema_version": "entroping.runtime-card.v1"}),
        encoding="utf-8",
    )
    (reports / "pilot-metrics.json").mkdir()

    result = run_design_partner_feedback_report(project_root=tmp_path)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert payload["evidence"]["evidence_bundle_status"] == "invalid"
    assert payload["evidence"]["runtime_card_status"] == "not_collected"
    assert payload["evidence"]["pilot_metrics_status"] == "unsafe"
    assert payload["evidence"]["evidence_paths"] == []

    (reports / "runtime-card.json").unlink()
    (reports / "runtime-card.json").mkdir()
    unsafe_runtime = run_design_partner_feedback_report(project_root=tmp_path)
    unsafe_payload = json.loads(unsafe_runtime.output_path.read_text(encoding="utf-8"))
    assert unsafe_payload["evidence"]["runtime_card_status"] == "not_collected"


def test_design_partner_feedback_rejects_invalid_source_contracts(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "evidence-bundle.json",
        {"schema_version": "entroping.evidence-bundle.v1"},
    )
    _write_json(
        reports / "pilot-metrics.json",
        {"schema_version": "entroping.pilot-metrics.v1"},
    )

    result = run_design_partner_feedback_report(project_root=tmp_path)
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert payload["evidence"]["evidence_bundle_status"] == "invalid"
    assert payload["evidence"]["pilot_metrics_status"] == "invalid"
    assert payload["evidence"]["evidence_paths"] == []


def test_design_partner_feedback_source_reader_defends_races_and_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "reports" / "evidence-bundle.json"
    source.parent.mkdir()

    def raise_outside(path: Path, *, root: Path) -> Path | None:
        _ = path, root
        raise ValueError("outside")

    monkeypatch.setattr(feedback, "first_symlink_path_component", raise_outside)
    assert feedback._load_json_document(source, root=tmp_path) == (None, "unsafe")

    monkeypatch.setattr(
        feedback,
        "first_symlink_path_component",
        lambda path, *, root: path,
    )
    assert feedback._load_json_document(source, root=tmp_path) == (None, "unsafe")

    monkeypatch.setattr(
        feedback,
        "first_symlink_path_component",
        lambda path, *, root: None,
    )
    source.write_text("[]\n", encoding="utf-8")
    assert feedback._load_json_document(source, root=tmp_path) == (None, "invalid")

    original_open = Path.open

    def fail_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == source:
            raise OSError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)
    assert feedback._load_json_document(source, root=tmp_path) == (None, "invalid")

    monkeypatch.setattr(Path, "open", original_open)
    monkeypatch.setattr(feedback, "_MAX_FEEDBACK_SOURCE_BYTES", 2)
    source.write_text("{}\n", encoding="utf-8")
    assert feedback._load_json_document(source, root=tmp_path) == (None, "invalid")
