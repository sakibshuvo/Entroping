"""Tests for Evidence Cloud readiness packets."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.evidence_cloud_readiness as readiness
from entroping.core.evidence_cloud_readiness import (
    EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION,
    EvidenceCloudReadinessError,
    EvidenceCloudReadinessPacket,
    build_evidence_cloud_readiness,
    render_evidence_cloud_readiness_markdown,
    run_evidence_cloud_readiness_report,
)
from entroping.core.safe_write import SafeWriteError

_HASH = "a" * 64


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path, *, raw_marker: str = "raw-feedback-text") -> None:
    reports = root / "reports"
    _write_json(
        reports / "team-evidence-readiness.json",
        {
            "schema_version": "entroping.team-evidence-readiness.v1",
            "project": "checkout-api",
            "summary": {
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
            },
        },
    )
    for filename, schema_version, status in (
        ("evidence-bundle.json", "entroping.evidence-bundle.v1", "ready"),
        ("runtime-card.json", "entroping.runtime-card.v1", "pass"),
        ("artifact-manifest.json", "entroping.report-artifact-manifest.v1", "complete"),
        ("pilot-metrics.json", "entroping.pilot-metrics.v1", "partial"),
        ("integration-readiness.json", "entroping.integration-readiness.v1", "ready"),
        ("devex-readiness.json", "entroping.devex-readiness.v1", "ready"),
        ("connector-intent.json", "entroping.connector-intent.v1", "ready"),
        ("evidence-index.json", "entroping.evidence-index.v1", "ready"),
    ):
        _write_json(
            reports / filename,
            {
                "schema_version": schema_version,
                "project": "checkout-api",
                "summary": {
                    "status": status,
                    "sources_total": 3,
                    "sources_present": 3,
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
            "project": "checkout-api",
            "evidence": {
                "evidence_bundle_status": "ready",
                "runtime_card_status": "pass",
                "pilot_metrics_status": "partial",
                "notes": raw_marker,
            },
        },
    )


def test_evidence_cloud_readiness_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    raw_marker = "customer raw free-form feedback must not render"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    result = run_evidence_cloud_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "evidence-cloud-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 10,
        "sources_present": 10,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "areas_total": 6,
        "areas_ready": 6,
        "areas_attention": 0,
        "areas_blocked": 0,
        "upload_candidates_total": 4,
        "upload_candidates_ready": 4,
        "upload_candidates_blocked": 0,
        "blockers_total": 0,
        "next_actions_total": 0,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["team_evidence_readiness"]["summary"] == "ready; 6/6 sources present"
    assert sources["design_partner_feedback"]["summary"] == "bundle ready; runtime pass"
    assert {candidate["id"] for candidate in payload["upload_candidates"]} == {
        "team_evidence_bundle",
        "runtime_governance_card",
        "integration_surface_packet",
        "developer_experience_packet",
    }
    assert payload["cloud_boundary"]["upload_implemented"] is False
    assert payload["cloud_boundary"]["hosted_sync_implemented"] is False
    assert "raw_traffic" in payload["cloud_boundary"]["forbidden_data_classes"]
    assert raw_marker not in json.dumps(payload)


def test_evidence_cloud_readiness_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "team-evidence-readiness.json",
        {"schema_version": "entroping.team-evidence-readiness.v999"},
    )
    _write_json(
        reports / "evidence-bundle.json",
        {
            "schema_version": "entroping.evidence-bundle.v1",
            "summary": {"status": "ready"},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_runtime = reports / "runtime-source.json"
    _write_json(
        real_runtime,
        {"schema_version": "entroping.runtime-card.v1", "summary": {"status": "pass"}},
    )
    os.symlink(real_runtime, reports / "runtime-card.json")
    (reports / "artifact-manifest.json").write_text("not json\n", encoding="utf-8")
    (reports / "pilot-metrics.json").mkdir()

    packet = build_evidence_cloud_readiness(project_root=tmp_path)

    sources = {source.id: source for source in packet.sources}
    assert sources["team_evidence_readiness"].state == "invalid"
    assert sources["evidence_bundle"].state == "unsafe"
    assert sources["runtime_card"].state == "unsafe"
    assert sources["artifact_manifest"].state == "invalid"
    assert sources["design_partner_feedback"].state == "missing"
    assert sources["pilot_metrics"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.areas_blocked >= 2
    assert packet.summary.blockers_total >= 2
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_evidence_cloud_readiness_dedupes_same_invalid_source_across_areas(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    _write_json(
        tmp_path / "reports" / "team-evidence-readiness.json",
        {"schema_version": "entroping.team-evidence-readiness.v999"},
    )

    packet = build_evidence_cloud_readiness(project_root=tmp_path)
    team_blockers = tuple(
        blocker
        for area in packet.readiness_areas
        for blocker in area.blockers
        if blocker.startswith("Team evidence readiness is invalid")
    )

    assert len(team_blockers) == 2
    assert len(set(team_blockers)) == 1
    assert packet.summary.blockers_total == 1


def test_evidence_cloud_readiness_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_ready_sources(tmp_path, raw_marker=raw_marker)

    markdown = render_evidence_cloud_readiness_markdown(
        build_evidence_cloud_readiness(project_root=tmp_path)
    )

    assert "# Entroping Evidence Cloud Readiness" in markdown
    assert (
        "| team_evidence_readiness | present | reports/team-evidence-readiness.json |"
        in markdown
    )
    assert "upload_implemented" in markdown
    assert raw_marker not in markdown
    assert "<script>" not in markdown


def test_evidence_cloud_readiness_markdown_preserves_backslashes(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_evidence_cloud_readiness(project_root=tmp_path)
    source = packet.sources[0].model_copy(
        update={"path": r"reports\team|evidence-readiness.json"}
    )
    packet = packet.model_copy(update={"sources": (source, *packet.sources[1:])})

    markdown = render_evidence_cloud_readiness_markdown(packet)

    assert "reports&#92;team\\|evidence-readiness.json" in markdown
    assert "&amp;#92;" not in markdown


def test_evidence_cloud_readiness_rejects_unsafe_output_path(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudReadinessError, match="must not be written"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-cloud-readiness.json",
        )
    with pytest.raises(EvidenceCloudReadinessError, match="must not be written"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "evidence-cloud-readiness.json",
        )


def test_evidence_cloud_readiness_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudReadinessError, match="Unsupported"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_evidence_cloud_readiness_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def fail_safe_write_text(
        output_path: Path,
        content: str,
        *,
        artifact: str,
        root: Path,
    ) -> Path:
        raise SafeWriteError("outside root")

    monkeypatch.setattr(readiness, "safe_write_text", fail_safe_write_text)

    with pytest.raises(EvidenceCloudReadinessError, match="outside root"):
        run_evidence_cloud_readiness_report(project_root=tmp_path, output="json")


def test_evidence_cloud_readiness_uses_shared_report_output_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_output_path(
        path: Path,
        *,
        root: Path,
        artifact: str,
    ) -> Path:
        assert path == Path("reports") / "evidence-cloud-readiness.json"
        assert root == tmp_path
        assert artifact == "Evidence Cloud readiness packet"
        raise SafeWriteError("shared boundary rejection")

    monkeypatch.setattr(readiness, "safe_report_output_path", reject_output_path)

    with pytest.raises(EvidenceCloudReadinessError, match="shared boundary rejection"):
        run_evidence_cloud_readiness_report(project_root=tmp_path, output="json")


def test_evidence_cloud_readiness_rejects_secret_rendered_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(
        readiness,
        "_render_packet_content",
        lambda packet, *, output: "api_key = sk-proj-" + ("a" * 24),
    )

    with pytest.raises(EvidenceCloudReadinessError, match="secret-like content"):
        run_evidence_cloud_readiness_report(project_root=tmp_path, output="json")


def test_evidence_cloud_readiness_rejects_secret_packet_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(
        readiness,
        "_packet_json",
        lambda packet: "api_key = sk-proj-" + ("a" * 24),
    )

    with pytest.raises(EvidenceCloudReadinessError, match="secret-like content"):
        build_evidence_cloud_readiness(project_root=tmp_path)


def test_evidence_cloud_readiness_packet_json_supports_pydantic_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    original_model_dump = cast(Any, EvidenceCloudReadinessPacket.model_dump)

    def legacy_model_dump(
        self: EvidenceCloudReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        return cast(dict[str, object], original_model_dump(self, *args, **kwargs))

    monkeypatch.setattr(
        readiness.EvidenceCloudReadinessPacket,
        "model_dump",
        legacy_model_dump,
    )

    packet = build_evidence_cloud_readiness(project_root=tmp_path)

    assert packet.summary.status == "ready"


def test_evidence_cloud_readiness_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def broken_model_dump(
        self: EvidenceCloudReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        raise ValueError("boom")

    monkeypatch.setattr(
        readiness.EvidenceCloudReadinessPacket,
        "model_dump",
        broken_model_dump,
    )

    with pytest.raises(
        EvidenceCloudReadinessError,
        match="could not be serialized safely",
    ):
        build_evidence_cloud_readiness(project_root=tmp_path)


def test_evidence_cloud_readiness_rejects_output_path_outside_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceCloudReadinessError, match="under the project root"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-cloud-readiness.json",
        )

    with pytest.raises(EvidenceCloudReadinessError, match="under the project root"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("..") / "evidence-cloud-readiness.json",
        )


def test_evidence_cloud_readiness_rejects_symlinked_output_path(
    tmp_path: Path,
) -> None:
    linked = tmp_path / "linked-reports"
    linked.symlink_to(tmp_path / "reports")

    with pytest.raises(EvidenceCloudReadinessError, match="symlinked component"):
        run_evidence_cloud_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=linked / "evidence-cloud-readiness.json",
        )


def test_evidence_cloud_readiness_marks_oversized_and_unreadable_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(
        tmp_path / "reports" / "team-evidence-readiness.json",
        {
            "schema_version": "entroping.team-evidence-readiness.v1",
            "summary": {"status": "ready"},
        },
    )
    monkeypatch.setattr(readiness, "_MAX_SOURCE_BYTES", 1)

    packet = build_evidence_cloud_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_evidence_readiness"].state == "invalid"
    assert "exceeds" in sources["team_evidence_readiness"].summary


def test_evidence_cloud_readiness_rejects_escaped_source_path(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCloudReadinessError, match="source path must stay under"):
        readiness._resolve_source_path(Path("../outside.json"), root=tmp_path)


def test_evidence_cloud_readiness_wraps_source_path_relative_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_relative_error(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("not relative")

    monkeypatch.setattr(readiness, "first_symlink_path_component", raise_relative_error)

    with pytest.raises(EvidenceCloudReadinessError, match="source path must stay under"):
        readiness._resolve_source_path(
            Path("reports") / "team-evidence-readiness.json",
            root=tmp_path,
        )


def test_evidence_cloud_readiness_marks_invalid_utf8_and_non_object_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "team-evidence-readiness.json").write_bytes(b"\xff\xfe")
    (reports / "evidence-bundle.json").write_text("[]", encoding="utf-8")

    packet = build_evidence_cloud_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_evidence_readiness"].state == "invalid"
    assert "UTF-8" in sources["team_evidence_readiness"].summary
    assert sources["evidence_bundle"].state == "invalid"
    assert "JSON object" in sources["evidence_bundle"].summary


def test_evidence_cloud_readiness_partial_when_only_optional_evidence_exists(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "team-evidence-readiness.json",
        {
            "schema_version": "entroping.team-evidence-readiness.v1",
            "summary": {"status": "ready"},
        },
    )

    packet = build_evidence_cloud_readiness(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert any(action.action.startswith("Generate") for action in packet.next_actions)


def test_evidence_cloud_readiness_uses_runtime_card_run_project(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "run": {"project": "runtime-project"},
            "summary": {"status": "pass"},
        },
    )

    packet = build_evidence_cloud_readiness(project_root=tmp_path)

    assert packet.project == "runtime-project"


def test_evidence_cloud_readiness_artifact_manifest_summary_counts(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "summary": {"total_present": 2, "total_missing": 1},
        },
    )

    packet = build_evidence_cloud_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["artifact_manifest"].summary == "2 present; 1 missing"


def test_evidence_cloud_readiness_area_next_action_without_blockers() -> None:
    assert readiness._area_next_action(
        label="Synthetic area",
        status="attention",
        source_ids=("team_evidence_readiness",),
        blockers=(),
    ) == (
        "Generate Synthetic area evidence with: "
        "entroping report team-evidence-readiness --output json."
    )


def test_evidence_cloud_readiness_text_field_rejects_blank_values() -> None:
    assert readiness._text_field({"status": "   "}, "status") is None


def test_evidence_cloud_source_rejects_invalid_sha256() -> None:
    payload = {
        "id": "team_evidence_readiness",
        "label": "Team evidence readiness",
        "path": "reports/team-evidence-readiness.json",
        "state": "present",
        "schema_version": "entroping.team-evidence-readiness.v1",
        "sha256": "not-a-sha",
        "summary": "ready",
    }

    with pytest.raises(ValueError):
        readiness.EvidenceCloudSource.model_validate(payload)


def test_evidence_cloud_next_action_dedupe_preserves_priority_variants() -> None:
    actions = [
        readiness.EvidenceCloudNextAction(
            priority="high",
            action="Repair evidence.",
            source_ids=("team_evidence_readiness",),
            area_ids=("team_upload_boundary",),
        ),
        readiness.EvidenceCloudNextAction(
            priority="medium",
            action="Repair evidence.",
            source_ids=("team_evidence_readiness",),
            area_ids=("team_upload_boundary",),
        ),
        readiness.EvidenceCloudNextAction(
            priority="high",
            action="Repair evidence.",
            source_ids=("team_evidence_readiness",),
            area_ids=("team_upload_boundary",),
        ),
    ]

    deduped = readiness._dedupe_actions(actions)

    assert [action.priority for action in deduped] == ["high", "medium"]


def test_evidence_cloud_summary_dedupes_duplicate_area_blockers() -> None:
    areas = (
        readiness.EvidenceCloudReadinessArea(
            id="team_upload_boundary",
            label="Team upload boundary",
            status="blocked",
            source_ids=("team_evidence_readiness",),
            boundary="local only",
            upload_candidate=True,
            blockers=("Shared blocker.", "Team-specific blocker."),
            next_action="Repair local evidence.",
        ),
        readiness.EvidenceCloudReadinessArea(
            id="cloud_boundary_controls",
            label="Cloud boundary controls",
            status="blocked",
            source_ids=("team_evidence_readiness",),
            boundary="local only",
            upload_candidate=False,
            blockers=("Shared blocker.",),
            next_action="Repair local evidence.",
        ),
    )

    summary = readiness._summary(
        sources=(),
        areas=areas,
        upload_candidates=(),
        next_actions=(),
    )

    assert summary.blockers_total == 2
    assert areas[0].blockers == ("Shared blocker.", "Team-specific blocker.")
    assert areas[1].blockers == ("Shared blocker.",)


def test_evidence_cloud_readiness_packet_schema_rejects_extra_fields() -> None:
    payload = {
        "schema_version": EVIDENCE_CLOUD_READINESS_SCHEMA_VERSION,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "insufficient",
            "sources_total": 0,
            "sources_present": 0,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "areas_total": 0,
            "areas_ready": 0,
            "areas_attention": 0,
            "areas_blocked": 0,
            "upload_candidates_total": 0,
            "upload_candidates_ready": 0,
            "upload_candidates_blocked": 0,
            "blockers_total": 0,
            "next_actions_total": 0,
        },
        "cloud_boundary": {
            "explicit_user_intent_required": True,
            "upload_implemented": False,
            "hosted_sync_implemented": False,
            "access_control_audit_required": True,
            "forbidden_data_classes": [],
            "boundary_summary": "local only",
        },
        "sources": [],
        "readiness_areas": [],
        "upload_candidates": [],
        "next_actions": [],
        "extra": "not allowed",
    }

    with pytest.raises(ValueError):
        EvidenceCloudReadinessPacket.model_validate(payload)
