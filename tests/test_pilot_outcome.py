"""Tests for local design-partner pilot outcome packets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entroping.core.evidence.pilot_outcome as pilot_outcome
from entroping.core.evidence.evidence_index import (
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.safe_write import SafeWriteError

PILOT_OUTCOME_SCHEMA_VERSION = (
    pilot_outcome.PILOT_OUTCOME_SCHEMA_VERSION
)
PilotOutcomeError = (
    pilot_outcome.PilotOutcomeError
)
build_pilot_outcome_packet = (
    pilot_outcome.build_pilot_outcome_packet
)
run_pilot_outcome_report = (
    pilot_outcome.run_pilot_outcome_report
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _design_partner_feedback(*, hosted: str = "yes", policy: str = "unclear") -> dict[str, object]:
    return {
        "schema_version": "entroping.design-partner-feedback.v1",
        "recorded_at": "2026-06-21T00:00:00+00:00",
        "pilot": {
            "repo_or_service": "manual input required",
            "ai_assisted_change_type": "backend-api-change",
        },
        "evidence": {
            "entroping_commands_run": ["entroping report runtime-card"],
            "evidence_bundle_status": "ready",
            "runtime_card_status": "pass",
            "pilot_metrics_status": "partial",
            "evidence_paths": ["reports/runtime-card.json"],
        },
        "feedback": {
            "blocked_regression_or_useful_failure": None,
            "false_positive_or_noisy_gate": None,
            "missing_evidence": "manual input required",
            "setup_friction": None,
            "security_privacy_concern": None,
        },
        "monetization_signals": {
            "hosted_aggregation": {
                "answer": hosted,
                "reason": "manual input required",
            },
            "premium_policy_packs": {
                "answer": policy,
                "reason": "manual input required",
            },
        },
        "follow_up": {
            "github_issue": "#1089",
            "summary": "manual input required",
        },
        "raw_private_note": "this private partner note must not render",
    }


def _pilot_metrics() -> dict[str, object]:
    return {
        "schema_version": "entroping.pilot-metrics.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "metrics_total": 2,
            "metrics_known": 1,
            "metrics_unknown": 0,
            "metrics_manual_input_required": 1,
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
        },
        "metrics": [
            {
                "id": "setup_time_minutes",
                "label": "Setup time",
                "state": "manual_input_required",
                "value": None,
                "unit": "minutes",
                "numerator": None,
                "denominator": None,
                "summary": "Requires design-partner timing input.",
                "source_paths": [],
            }
        ],
        "sources": [],
    }


def _status_packet(
    schema_version: str,
    status: str,
    project: str = "checkout-api",
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": project,
        "summary": {"status": status},
    }


def _write_all_sources(root: Path) -> None:
    reports = root / "reports"
    _write_json(reports / "design-partner-feedback.json", _design_partner_feedback())
    _write_json(reports / "pilot-metrics.json", _pilot_metrics())
    _write_json(
        reports / "runtime-card.json",
        _status_packet("entroping.runtime-card.v1", "pass"),
    )
    _write_json(
        reports / "evidence-cloud-dashboard.json",
        _status_packet("entroping.evidence-cloud-dashboard.v1", "ready"),
    )
    _write_json(
        reports / "work-item-import-bundle.json",
        _status_packet("entroping.work-item-import-bundle.v1", "partial"),
    )


def test_pilot_outcome_public_feedback_without_status_is_present(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)
    feedback = _design_partner_feedback()
    evidence = feedback["evidence"]
    assert isinstance(evidence, dict)
    evidence["pilot_metrics_status"] = 1
    _write_json(tmp_path / "reports" / "design-partner-feedback.json", feedback)

    packet = build_pilot_outcome_packet(project_root=tmp_path)

    source = next(
        source for source in packet.sources if source.id == "design-partner-feedback-json"
    )
    assert source.status == "present"

    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {"schema_version": "entroping.runtime-card.v1"},
    )
    packet = build_pilot_outcome_packet(project_root=tmp_path)
    runtime_source = next(
        source for source in packet.sources if source.id == "runtime-card-json"
    )
    assert runtime_source.status == "present"


def test_pilot_outcome_public_loader_classifies_unknown_read_error_as_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_all_sources(tmp_path)
    target = tmp_path / "reports" / "runtime-card.json"
    original_reader = read_local_evidence_json_artifact_bytes

    def fail_runtime(path: Path, *, root: Path) -> tuple[bytes | None, str]:
        if path == target:
            return None, "unexpected read error"
        return original_reader(path, root=root)

    monkeypatch.setattr(
        pilot_outcome,
        "read_local_evidence_json_artifact_bytes",
        fail_runtime,
    )

    packet = build_pilot_outcome_packet(project_root=tmp_path)

    source = next(source for source in packet.sources if source.id == "runtime-card-json")
    assert source.state == "invalid"
    assert source.summary == "unexpected read error"


def _complete_feedback() -> dict[str, object]:
    payload = _design_partner_feedback(hosted="yes", policy="no")
    payload["pilot"] = {
        "repo_or_service": "partner-api",
        "ai_assisted_change_type": "backend-api-change",
    }
    payload["feedback"] = {
        "blocked_regression_or_useful_failure": None,
        "false_positive_or_noisy_gate": None,
        "missing_evidence": None,
        "setup_friction": None,
        "security_privacy_concern": None,
    }
    payload["monetization_signals"] = {
        "hosted_aggregation": {
            "answer": "yes",
            "reason": "runtime governance visibility is useful",
        },
        "premium_policy_packs": {
            "answer": "no",
            "reason": "policy pack budget not validated",
        },
    }
    payload["follow_up"] = {
        "github_issue": "#1089",
        "summary": "follow-up captured elsewhere",
    }
    return payload


def test_pilot_outcome_writes_json_from_sanitized_sources(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)

    result = run_pilot_outcome_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert result.output_path == tmp_path / "reports" / "pilot-outcome.json"
    assert payload["schema_version"] == PILOT_OUTCOME_SCHEMA_VERSION
    assert payload["summary"]["status"] == "partial"
    assert payload["summary"]["sources_present"] == 5
    assert payload["summary"]["manual_input_gaps"] == 5
    assert payload["summary"]["monetization_yes"] == 1
    assert payload["summary"]["monetization_unclear"] == 1
    assert payload["pilot_evidence_readiness"]["runtime_card_status"] == "pass"
    assert payload["pilot_evidence_readiness"]["evidence_cloud_status"] == "ready"
    assert "pilot.repo_or_service" in payload["manual_input_gaps"]
    assert any(signal["id"] == "hosted_aggregation" for signal in payload["monetization_signals"])
    assert any(action["category"] == "collect" for action in payload["actions"])
    assert "raw_private_note" not in json.dumps(payload)
    assert "this private partner note must not render" not in json.dumps(payload)


def test_pilot_outcome_ready_markdown_has_no_action_or_gap_rows(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(reports / "design-partner-feedback.json", _complete_feedback())
    _write_json(reports / "pilot-metrics.json", _pilot_metrics())
    _write_json(
        reports / "runtime-card.json",
        _status_packet("entroping.runtime-card.v1", "pass"),
    )
    _write_json(
        reports / "evidence-cloud-dashboard.json",
        _status_packet("entroping.evidence-cloud-dashboard.v1", "ready"),
    )
    _write_json(
        reports / "work-item-import-bundle.json",
        _status_packet("entroping.work-item-import-bundle.v1", "ready"),
    )

    result = run_pilot_outcome_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.packet.summary.status == "ready"
    assert result.packet.summary.monetization_no == 1
    assert result.packet.project == "partner-api"
    assert "- `none`" in markdown
    assert "No local pilot outcome action required." in markdown


def test_pilot_outcome_writes_value_free_markdown(tmp_path: Path) -> None:
    _write_all_sources(tmp_path)

    result = run_pilot_outcome_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "pilot-outcome.md"
    assert "# Entroping Pilot Outcome" in markdown
    assert "hosted_aggregation" in markdown
    assert "pilot.repo_or_service" in markdown
    assert "this private partner note must not render" not in markdown


def test_pilot_outcome_missing_sources_generate_actions(tmp_path: Path) -> None:
    packet = build_pilot_outcome_packet(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 5
    assert packet.summary.actions_medium == 5
    assert {action.category for action in packet.actions} == {"generate"}


def test_pilot_outcome_marks_invalid_and_secret_sources_repairable(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "design-partner-feedback.json",
        {"schema_version": "wrong.v1", "secret": "sk-proj-" + ("a" * 24)},
    )
    _write_json(reports / "pilot-metrics.json", {"schema_version": "wrong.v1"})

    packet = build_pilot_outcome_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["design-partner-feedback-json"].state == "unsafe"
    assert sources["pilot-metrics-json"].state == "invalid"
    assert packet.summary.status == "insufficient"
    assert packet.summary.actions_high == 2
    assert any(action.category == "repair" for action in packet.actions)


def test_pilot_outcome_marks_invalid_json_and_load_errors(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "pilot-metrics.json").write_text("{not json", encoding="utf-8")
    (reports / "runtime-card.json").mkdir()

    packet = build_pilot_outcome_packet(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["pilot-metrics-json"].state == "invalid"
    assert sources["runtime-card-json"].state == "unsafe"
def test_pilot_outcome_records_command_manual_input_gap(tmp_path: Path) -> None:
    feedback = _complete_feedback()
    feedback["evidence"] = {
        "entroping_commands_run": ["manual input required"],
        "evidence_bundle_status": "ready",
        "runtime_card_status": "pass",
        "pilot_metrics_status": "partial",
        "evidence_paths": [],
    }
    _write_json(tmp_path / "reports" / "design-partner-feedback.json", feedback)

    packet = build_pilot_outcome_packet(project_root=tmp_path)

    assert "evidence.entroping_commands_run" in packet.manual_input_gaps


def test_pilot_outcome_rejects_output_outside_project(tmp_path: Path) -> None:
    with pytest.raises(PilotOutcomeError, match="must stay under the project root"):
        run_pilot_outcome_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "pilot-outcome.json",
        )


def test_pilot_outcome_rejects_case_variant_forbidden_output_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(PilotOutcomeError, match="must not be written"):
        run_pilot_outcome_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / ".Entroping" / "pilot-outcome.json",
        )


def test_pilot_outcome_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_pilot_outcome_packet(project_root=tmp_path).model_copy(
        update={"project": "sk-proj-" + ("a" * 24)}
    )
    monkeypatch.setattr(
        pilot_outcome,
        "build_pilot_outcome_packet",
        lambda **_: packet,
    )

    with pytest.raises(PilotOutcomeError, match="secret-like content"):
        run_pilot_outcome_report(project_root=tmp_path, output="json")


def test_pilot_outcome_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(pilot_outcome, "safe_write_text", fail_write)

    with pytest.raises(PilotOutcomeError, match="blocked write"):
        run_pilot_outcome_report(project_root=tmp_path, output="json")


def test_pilot_outcome_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(PilotOutcomeError, match="Unsupported"):
        run_pilot_outcome_report(
            project_root=tmp_path,
            output="csv",  # type: ignore[arg-type]
        )
