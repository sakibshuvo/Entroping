"""Tests for team access-control plan packets."""

import json
import os
from pathlib import Path
from typing import IO, Any, cast

import pytest

import entroping.core.team_access_control_plan as access_plan
from entroping.core.safe_write import SafeWriteError
from entroping.core.team_access_control_plan import (
    TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
    TeamAccessControlPlanError,
    TeamAccessControlPlanPacket,
    build_team_access_control_plan,
    render_team_access_control_plan_markdown,
    run_team_access_control_plan_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path) -> None:
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
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 4},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
        },
    )


def test_team_access_control_plan_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_team_access_control_plan_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "team-access-control-plan.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 4,
        "sources_present": 4,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "roles_total": 5,
        "roles_ready": 5,
        "roles_attention": 0,
        "roles_blocked": 0,
        "audit_events_total": 6,
        "blockers_total": 0,
        "next_actions_total": 0,
    }
    roles = {role["id"]: role for role in payload["roles"]}
    assert roles["owner"]["status"] == "ready"
    assert roles["external_design_partner"]["allowed_actions"] == [
        "view_value_free_evidence",
        "acknowledge_status",
    ]
    assert "override_hurl_qanstitution_result" in roles["owner"]["forbidden_actions"]
    assert "view_raw_traffic" in roles["owner"]["forbidden_actions"]
    assert "raw_traffic" in payload["boundary"]["forbidden_data_classes"]
    assert payload["boundary"]["upload_implemented"] is False
    assert payload["boundary"]["access_control_enforced"] is False
    assert "sk-proj" not in json.dumps(payload)


def test_team_access_control_plan_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "team-evidence-readiness.json",
        {"schema_version": "entroping.team-evidence-readiness.v999"},
    )
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "summary": {"status": "ready", "artifacts_total": 1},
        },
    )
    _write_json(
        reports / "notification-packet.json",
        {
            "schema_version": "entroping.notification-packet.v1",
            "summary": {"status": "ready", "severity": "info"},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    real_runtime = reports / "runtime-source.json"
    _write_json(
        real_runtime,
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
        },
    )
    os.symlink(real_runtime, reports / "runtime-card.json")

    packet = build_team_access_control_plan(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_evidence_readiness"].state == "invalid"
    assert sources["handoff"].state == "invalid"
    assert sources["notification_packet"].state == "unsafe"
    assert sources["runtime_card"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.roles_blocked == 5
    assert packet.summary.blockers_total == 4
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_team_access_control_plan_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_team_access_control_plan(project_root=tmp_path).model_copy(
        update={"project": "checkout `api` | demo"}
    )

    markdown = render_team_access_control_plan_markdown(packet)

    assert "# Entroping Team Access-Control Plan" in markdown
    assert "- Project: `checkout &#96;api&#96; | demo`" in markdown
    assert "| owner | ready |" in markdown
    assert "override_hurl_qanstitution_result" in markdown
    assert "No team access-control actions are currently needed." in markdown
    assert "checkout `api`" not in markdown


def test_team_access_control_plan_handles_empty_sources(tmp_path: Path) -> None:
    packet = build_team_access_control_plan(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 4
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.summary.roles_attention == 5
    assert packet.next_actions


def test_team_access_control_plan_markdown_output_renders_next_actions(
    tmp_path: Path,
) -> None:
    result = run_team_access_control_plan_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "team-access-control-plan.md"
    assert "| Priority | Action | Sources | Roles | Audit Events |" in markdown
    assert "Generate Team evidence readiness local evidence." in markdown


def test_team_access_control_plan_marks_malformed_sources_invalid(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "team-evidence-readiness.json").write_text("[", encoding="utf-8")
    (reports / "handoff.json").write_text("[]", encoding="utf-8")
    _write_json(
        reports / "notification-packet.json",
        {"schema_version": "entroping.notification-packet.v1"},
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "", "findings": 0},
        },
    )

    packet = build_team_access_control_plan(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_evidence_readiness"].state == "invalid"
    assert "Could not parse" in sources["team_evidence_readiness"].summary
    assert sources["handoff"].state == "invalid"
    assert "must be a JSON object" in sources["handoff"].summary
    assert sources["notification_packet"].state == "invalid"
    assert sources["notification_packet"].schema_version == "entroping.notification-packet.v1"
    assert "summary must be an object" in sources["notification_packet"].summary
    assert sources["runtime_card"].state == "invalid"
    assert sources["runtime_card"].schema_version == "entroping.runtime-card.v1"
    assert "status must be a non-empty string" in sources["runtime_card"].summary


def test_team_access_control_plan_marks_non_file_and_non_utf8_sources_unsafe_or_invalid(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    (reports / "team-evidence-readiness.json").mkdir(parents=True)
    (reports / "handoff.json").write_bytes(b"\xff")

    packet = build_team_access_control_plan(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_evidence_readiness"].state == "unsafe"
    assert "not a file" in sources["team_evidence_readiness"].summary
    assert sources["handoff"].state == "invalid"
    assert "Could not decode" in sources["handoff"].summary


def test_team_access_control_plan_marks_oversized_sources_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(access_plan, "_MAX_SOURCE_BYTES", 1)

    packet = build_team_access_control_plan(project_root=tmp_path)
    first_source = packet.sources[0]

    assert first_source.id == "team_evidence_readiness"
    assert first_source.state == "invalid"
    assert "exceeds" in first_source.summary


def test_team_access_control_plan_marks_read_errors_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def fail_open(
        self: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        if self.name == "team-evidence-readiness.json":
            raise OSError("permission denied")
        return original_open(self, mode, buffering, encoding, errors, newline)

    original_open = Path.open
    monkeypatch.setattr(Path, "open", fail_open)

    packet = build_team_access_control_plan(project_root=tmp_path)
    first_source = packet.sources[0]

    assert first_source.id == "team_evidence_readiness"
    assert first_source.state == "invalid"
    assert "Could not read team evidence readiness" in first_source.summary


def test_team_access_control_plan_falls_back_to_runtime_card_project(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "summary": {
                "status": "ready",
                "artifacts_total": 1,
                "artifacts_present": 1,
            },
        },
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
            "run": {"project": "checkout-api"},
        },
    )

    packet = build_team_access_control_plan(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"
    assert packet.summary.roles_attention == 5


def test_team_access_control_plan_keeps_project_unknown_when_runtime_card_has_none(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
        },
    )

    packet = build_team_access_control_plan(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "partial"


def test_team_access_control_plan_ignores_blank_runtime_card_project(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
            "run": {"project": "  "},
        },
    )

    packet = build_team_access_control_plan(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "partial"


def test_team_access_control_plan_deduplicates_identical_actions() -> None:
    action = access_plan.TeamAccessControlNextAction(
        priority="medium",
        action="Generate team evidence readiness before planning team access.",
        role_ids=("owner",),
        audit_event_ids=("evidence_viewed",),
    )

    assert access_plan._dedupe_actions([action, action]) == (action,)


def test_team_access_control_plan_attention_next_action_without_blockers() -> None:
    assert (
        access_plan._role_next_action(
            role_label="Owner",
            status="attention",
            blockers=(),
        )
        == "Generate team evidence readiness before planning team access."
    )


def test_team_access_control_plan_packet_json_supports_pydantic_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    original_model_dump = cast(Any, TeamAccessControlPlanPacket.model_dump)

    def legacy_model_dump(
        self: TeamAccessControlPlanPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        return cast(dict[str, object], original_model_dump(self, *args, **kwargs))

    monkeypatch.setattr(
        access_plan.TeamAccessControlPlanPacket,
        "model_dump",
        legacy_model_dump,
    )

    packet = build_team_access_control_plan(project_root=tmp_path)

    assert packet.summary.status == "ready"


def test_team_access_control_plan_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def broken_model_dump(
        self: TeamAccessControlPlanPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        raise ValueError("boom")

    monkeypatch.setattr(
        access_plan.TeamAccessControlPlanPacket,
        "model_dump",
        broken_model_dump,
    )

    with pytest.raises(
        TeamAccessControlPlanError,
        match="could not be serialized safely",
    ):
        build_team_access_control_plan(project_root=tmp_path)


def test_team_access_control_plan_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TeamAccessControlPlanError, match="Unsupported team-access"):
        run_team_access_control_plan_report(project_root=tmp_path, output=cast(Any, "html"))
    with pytest.raises(TeamAccessControlPlanError, match="must stay under"):
        run_team_access_control_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "team-access-control-plan.json",
        )
    with pytest.raises(TeamAccessControlPlanError, match="must not be written into"):
        run_team_access_control_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "team-access-control-plan.json",
        )

    monkeypatch.setattr(
        access_plan,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(TeamAccessControlPlanError, match="must stay under"):
        run_team_access_control_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-team-access-control-plan.json",
        )


def test_team_access_control_plan_rejects_symlinked_output_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(TeamAccessControlPlanError, match="symlinked component"):
        run_team_access_control_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "team-access-control-plan.json",
        )


def test_team_access_control_plan_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_team_access_control_plan(project_root=tmp_path)
    monkeypatch.setattr(
        access_plan,
        "build_team_access_control_plan",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(TeamAccessControlPlanError, match="contains secret-like content"):
        run_team_access_control_plan_report(project_root=tmp_path, output="json")


def test_team_access_control_plan_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(access_plan, "safe_write_text", fail_safe_write)

    with pytest.raises(TeamAccessControlPlanError, match="disk full"):
        run_team_access_control_plan_report(project_root=tmp_path, output="json")


def test_team_access_control_plan_defensively_rejects_secret_like_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = TeamAccessControlPlanPacket.model_construct(
        schema_version=TEAM_ACCESS_CONTROL_PLAN_SCHEMA_VERSION,
        generated_at="2026-06-20T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        boundary=object(),
        sources=(),
        roles=(),
        audit_events=(),
        next_actions=(),
    )
    monkeypatch.setattr(access_plan, "_build_packet", lambda **_: packet)

    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(TeamAccessControlPlanError, match="contains secret-like"),
    ):
        build_team_access_control_plan(project_root=tmp_path)
