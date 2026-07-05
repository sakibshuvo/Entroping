"""Tests for team evidence readiness packets."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.readiness.team_evidence_readiness as readiness
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path) -> None:
    reports = root / "reports"
    _write_json(
        reports / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
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
        },
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 4},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
        },
    )
    _write_json(
        reports / "pilot-metrics.json",
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "project": "checkout-api",
            "summary": {
                "status": "partial",
                "metrics_total": 6,
                "metrics_known": 2,
                "metrics_unknown": 1,
                "metrics_manual_input_required": 3,
                "sources_total": 5,
                "sources_present": 5,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
            },
        },
    )
    _write_json(
        reports / "design-partner-feedback.json",
        {
            "schema_version": "entroping.design-partner-feedback.v1",
            "evidence": {
                "evidence_bundle_status": "ready",
                "runtime_card_status": "pass",
                "pilot_metrics_status": "partial",
                "evidence_paths": [
                    "reports/evidence-bundle.json",
                    "reports/runtime-card.json",
                    "reports/pilot-metrics.json",
                ],
            },
            "monetization_signals": {
                "hosted_aggregation": {"answer": "unclear"},
                "premium_policy_packs": {"answer": "unclear"},
            },
        },
    )
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "artifacts_total": 5,
                "artifacts_present": 5,
                "artifacts_missing": 0,
                "artifacts_invalid": 0,
                "artifacts_unsafe": 0,
            },
        },
    )
    _write_json(
        reports / "notification-packet.json",
        {
            "schema_version": "entroping.notification-packet.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "severity": "info",
                "sources_total": 6,
                "sources_present": 6,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
            },
        },
    )


def test_team_evidence_readiness_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = readiness.run_team_evidence_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "team-evidence-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == readiness.TEAM_EVIDENCE_READINESS_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 6,
        "sources_present": 6,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "areas_total": 6,
        "areas_ready": 6,
        "areas_attention": 0,
        "areas_blocked": 0,
        "blockers_total": 0,
        "next_actions_total": 0,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["evidence_bundle"]["summary"] == "ready; 3/3 required present"
    assert sources["runtime_card"]["summary"] == "pass; 0 findings"
    assert sources["pilot_metrics"]["summary"] == "partial; 2/6 metrics known"
    assert {area["id"] for area in payload["readiness_areas"]} == {
        "upload_boundary",
        "runtime_visibility",
        "design_partner_pilot",
        "cross_surface_continuity",
        "notification_linkout",
        "cloud_boundary_controls",
    }
    assert all(area["status"] == "ready" for area in payload["readiness_areas"])
    assert payload["cloud_boundary"]["explicit_user_intent_required"] is True
    assert payload["cloud_boundary"]["upload_implemented"] is False
    assert "raw_traffic" in payload["cloud_boundary"]["forbidden_data_classes"]
    assert "provider_outputs" in payload["cloud_boundary"]["forbidden_data_classes"]
    assert "sk-proj" not in json.dumps(payload)


def test_team_evidence_readiness_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "evidence-bundle.json",
        {"schema_version": "entroping.evidence-bundle.v999"},
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_pilot = reports / "pilot-source.json"
    _write_json(
        real_pilot,
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "summary": {"status": "partial"},
        },
    )
    os.symlink(real_pilot, reports / "pilot-metrics.json")
    (reports / "handoff.json").write_text("not json\n", encoding="utf-8")
    (reports / "notification-packet.json").mkdir()

    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["evidence_bundle"].state == "invalid"
    assert sources["runtime_card"].state == "unsafe"
    assert sources["pilot_metrics"].state == "unsafe"
    assert sources["design_partner_feedback"].state == "missing"
    assert sources["handoff"].state == "invalid"
    assert sources["notification_packet"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.areas_blocked >= 3
    assert packet.summary.blockers_total >= 3
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_team_evidence_readiness_summary_dedupes_duplicate_blockers() -> None:
    areas = (
        readiness.TeamEvidenceReadinessArea(
            id="upload_boundary",
            label="Upload boundary",
            status="blocked",
            source_ids=("evidence_bundle",),
            boundary="local only",
            blockers=("Shared blocker.", "Area-specific blocker."),
            next_action="Repair local evidence.",
        ),
        readiness.TeamEvidenceReadinessArea(
            id="runtime_visibility",
            label="Runtime visibility",
            status="blocked",
            source_ids=("runtime_card",),
            boundary="local only",
            blockers=("Shared blocker.",),
            next_action="Repair runtime evidence.",
        ),
    )

    summary = readiness._summary(sources=(), areas=areas, next_actions=())

    assert summary.blockers_total == 2
    assert areas[0].blockers == ("Shared blocker.", "Area-specific blocker.")
    assert areas[1].blockers == ("Shared blocker.",)


def test_team_evidence_readiness_cloud_controls_reuse_source_blockers() -> None:
    source = readiness.TeamEvidenceSource(
        id="evidence_bundle",
        label="Evidence bundle",
        path="reports/evidence-bundle.json",
        state="invalid",
        schema_version=None,
        summary="schema mismatch",
    )
    by_id: dict[readiness.TeamEvidenceSourceId, readiness.TeamEvidenceSource] = {
        "evidence_bundle": source
    }
    source_area = readiness._area(
        "upload_boundary",
        label="Upload boundary",
        source_ids=("evidence_bundle",),
        by_id=by_id,
        boundary="local only",
    )
    cloud_area = readiness._cloud_controls_area(by_id=by_id)

    summary = readiness._summary(
        sources=(source,),
        areas=(source_area, cloud_area),
        next_actions=(),
    )

    assert cloud_area.blockers == source_area.blockers
    assert summary.blockers_total == 1


def test_team_evidence_readiness_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = readiness.build_team_evidence_readiness(project_root=tmp_path).model_copy(
        update={"project": "checkout `api` | demo"}
    )

    markdown = readiness.render_team_evidence_readiness_markdown(packet)

    assert "# Entroping Team Evidence Readiness" in markdown
    assert "- Project: `checkout &#96;api&#96; | demo`" in markdown
    assert "| evidence_bundle | present | reports/evidence-bundle.json |" in markdown
    assert "checkout `api`" not in markdown
    assert "raw_traffic" in markdown
    assert "No team evidence readiness actions are currently needed." in markdown


def test_team_evidence_readiness_handles_empty_sources(tmp_path: Path) -> None:
    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 6
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.next_actions


def test_team_evidence_readiness_markdown_output_renders_next_actions(
    tmp_path: Path,
) -> None:
    result = readiness.run_team_evidence_readiness_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "team-evidence-readiness.md"
    assert "| Priority | Action | Sources | Areas |" in markdown
    assert "Generate Evidence bundle local evidence." in markdown
    assert "No team evidence readiness actions are currently needed." not in markdown


def test_team_evidence_readiness_project_can_fall_back_to_runtime_card(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
            "run": {"project": "runtime-api"},
        },
    )

    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)

    assert packet.project == "runtime-api"
    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 1


def test_team_evidence_readiness_marks_malformed_source_contracts_invalid(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "evidence-bundle.json").write_bytes(b"\xff")
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": "pass",
        },
    )
    _write_json(
        reports / "pilot-metrics.json",
        {
            "schema_version": "entroping.pilot-metrics.v1",
            "summary": {
                "status": "",
                "metrics_known": 0,
                "metrics_total": 1,
            },
        },
    )
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "summary": {
                "status": "ready",
                "artifacts_present": -1,
                "artifacts_total": 1,
            },
        },
    )
    (reports / "notification-packet.json").write_text("[]", encoding="utf-8")

    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["evidence_bundle"].state == "invalid"
    assert "Could not decode" in sources["evidence_bundle"].summary
    assert sources["runtime_card"].summary == "Runtime card summary must be an object"
    assert sources["pilot_metrics"].summary == ("Pilot metrics status must be a non-empty string")
    assert sources["handoff"].summary == (
        "Cross-surface handoff artifacts_present must be a non-negative integer"
    )
    assert sources["notification_packet"].summary == ("Notification packet must be a JSON object")


def test_team_evidence_readiness_marks_oversized_source_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "summary": {
                "status": "ready",
                "required_total": 1,
                "required_present": 1,
            },
        },
    )
    monkeypatch.setattr(readiness, "_MAX_SOURCE_BYTES", 2)

    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)
    source = next(source for source in packet.sources if source.id == "evidence_bundle")

    assert source.state == "invalid"
    assert "exceeds 2 bytes" in source.summary


def test_team_evidence_readiness_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(readiness.TeamEvidenceReadinessError, match="Unsupported team-evidence"):
        readiness.run_team_evidence_readiness_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )
    with pytest.raises(readiness.TeamEvidenceReadinessError, match="must stay under"):
        readiness.run_team_evidence_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "team-evidence-readiness.json",
        )
    with pytest.raises(readiness.TeamEvidenceReadinessError, match="must not be written into"):
        readiness.run_team_evidence_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "team-evidence-readiness.json",
        )

    monkeypatch.setattr(
        readiness,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(readiness.TeamEvidenceReadinessError, match="must stay under"):
        readiness.run_team_evidence_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-team-evidence-readiness.json",
        )


def test_team_evidence_readiness_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(readiness.TeamEvidenceReadinessError, match="symlinked component"):
        readiness.run_team_evidence_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "team-evidence-readiness.json",
        )


def test_team_evidence_readiness_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = readiness.build_team_evidence_readiness(project_root=tmp_path)
    monkeypatch.setattr(
        readiness,
        "build_team_evidence_readiness",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(readiness.TeamEvidenceReadinessError, match="contains secret-like content"):
        readiness.run_team_evidence_readiness_report(project_root=tmp_path, output="json")


def test_team_evidence_readiness_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(readiness, "safe_write_text", fail_safe_write)

    with pytest.raises(readiness.TeamEvidenceReadinessError, match="disk full"):
        readiness.run_team_evidence_readiness_report(project_root=tmp_path, output="json")


def test_team_evidence_readiness_defensively_rejects_secret_like_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = readiness.TeamEvidenceReadinessPacket.model_construct(
        schema_version=readiness.TEAM_EVIDENCE_READINESS_SCHEMA_VERSION,
        generated_at="2026-06-20T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        cloud_boundary=object(),
        sources=(),
        readiness_areas=(),
        next_actions=(),
    )
    monkeypatch.setattr(
        readiness,
        "_build_packet",
        lambda **_: packet,
    )

    with pytest.raises(readiness.TeamEvidenceReadinessError, match="contains secret-like content"):
        readiness.build_team_evidence_readiness(project_root=tmp_path)


def test_team_evidence_readiness_helpers_handle_unreadable_and_duplicate_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.json"
    path.write_text("{}", encoding="utf-8")

    def fail_read_bytes(_path: Path) -> bytes:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    with pytest.raises(readiness.TeamEvidenceReadinessError, match="Could not read source"):
        readiness._read_bounded_bytes(path, artifact="source")

    action = readiness.TeamEvidenceNextAction(
        priority="medium",
        action="Generate Evidence bundle local evidence.",
        source_ids=("evidence_bundle",),
    )
    assert readiness._dedupe_actions([action, action]) == (action,)


def test_team_evidence_readiness_helpers_cover_project_and_action_fallbacks() -> None:
    project = readiness._project_from_documents(
        {
            "runtime_card": {"run": {"project": ""}},
            "pilot_metrics": {"project": "pilot-api"},
        }
    )
    later_project = readiness._project_from_documents(
        {
            "runtime_card": {"run": "not-an-object"},
            "pilot_metrics": {"project": ""},
            "handoff": {"project": "handoff-api"},
        }
    )
    next_action = readiness._area_next_action(
        label="Ad hoc",
        status="attention",
        source_ids=("evidence_bundle",),
        blockers=(),
    )

    assert project == "pilot-api"
    assert later_project == "handoff-api"
    assert next_action == "Generate Ad hoc evidence with: entroping report evidence-bundle."
