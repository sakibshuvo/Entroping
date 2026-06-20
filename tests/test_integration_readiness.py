"""Tests for integration readiness packets."""

import json
import os
from pathlib import Path
from typing import IO, Any, cast

import pytest

import entroping.core.integration_readiness as integration_readiness
from entroping.core.integration_readiness import (
    INTEGRATION_READINESS_SCHEMA_VERSION,
    IntegrationReadinessError,
    IntegrationReadinessPacket,
    build_integration_readiness,
    render_integration_readiness_markdown,
    run_integration_readiness_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path) -> None:
    reports = root / "reports"
    _write_json(
        reports / "team-access-control-plan.json",
        {
            "schema_version": "entroping.team-access-control-plan.v1",
            "project": "checkout-api",
            "summary": {
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
        reports / "observability-packet.json",
        {
            "schema_version": "entroping.observability-packet.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "severity": "info",
                "sources_total": 2,
                "sources_present": 2,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
                "events_total": 4,
                "debug_events": 0,
                "info_events": 4,
                "warning_events": 0,
                "error_events": 0,
            },
        },
    )
    _write_json(
        reports / "api-inventory.json",
        {
            "schema_version": "entroping.api-inventory.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "sources_total": 4,
                "sources_present": 4,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
                "styles_total": 4,
                "hurl_tests_total": 12,
                "operations_total": 18,
            },
        },
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 5},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
        },
    )


def test_integration_readiness_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_integration_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "integration-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == INTEGRATION_READINESS_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 6,
        "sources_present": 6,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "families_total": 6,
        "families_ready": 6,
        "families_attention": 0,
        "families_blocked": 0,
        "blockers_total": 0,
        "next_actions_total": 0,
    }
    families = {family["id"]: family for family in payload["families"]}
    assert families["issue_trackers"]["surface_ids"] == ["jira", "linear", "monday"]
    assert families["chat"]["surface_ids"] == ["slack", "discord"]
    assert families["enterprise_automation"]["surface_ids"] == [
        "workato",
        "claude",
        "codex",
    ]
    assert families["observability"]["surface_ids"] == [
        "opentelemetry",
        "datadog",
        "splunk",
    ]
    assert "call_external_api" in families["issue_trackers"]["forbidden_actions"]
    assert "override_hurl_qanstitution_result" in families["chat"]["forbidden_actions"]
    assert "artifact_id" in families["chat"]["event_requirements"]
    assert "source_sha256" in families["cross_surface_continuity"]["link_requirements"]
    assert "sk-proj" not in json.dumps(payload)


def test_integration_readiness_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "team-access-control-plan.json",
        {"schema_version": "entroping.team-access-control-plan.v999"},
    )
    _write_json(
        reports / "notification-packet.json",
        {
            "schema_version": "entroping.notification-packet.v1",
            "summary": {"status": "ready", "severity": "info"},
            "token": "sk-proj-" + ("a" * 24),
        },
    )
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "summary": {"status": "ready", "artifacts_total": 1},
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

    packet = build_integration_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "invalid"
    assert sources["notification_packet"].state == "unsafe"
    assert sources["handoff"].state == "invalid"
    assert sources["observability_packet"].state == "missing"
    assert sources["api_inventory"].state == "missing"
    assert sources["runtime_card"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.families_blocked == 6
    assert packet.summary.blockers_total == 4
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_integration_readiness_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_integration_readiness(project_root=tmp_path).model_copy(
        update={"project": "checkout `api` | demo"}
    )

    markdown = render_integration_readiness_markdown(packet)

    assert "# Entroping Integration Readiness" in markdown
    assert "- Project: `checkout &#96;api&#96; | demo`" in markdown
    assert "| issue_trackers | ready | jira, linear, monday |" in markdown
    assert "call_external_api" in markdown
    assert "No integration readiness actions are currently needed." in markdown
    assert "checkout `api`" not in markdown


def test_integration_readiness_handles_empty_sources(tmp_path: Path) -> None:
    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 6
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.summary.families_attention == 6
    assert packet.next_actions


def test_integration_readiness_markdown_output_renders_next_actions(
    tmp_path: Path,
) -> None:
    result = run_integration_readiness_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "integration-readiness.md"
    assert "| Priority | Action | Sources | Families |" in markdown
    assert "Generate Team access-control plan local evidence." in markdown


def test_integration_readiness_marks_malformed_sources_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "team-access-control-plan.json").write_text("[", encoding="utf-8")
    (reports / "notification-packet.json").write_text("[]", encoding="utf-8")
    _write_json(
        reports / "handoff.json",
        {"schema_version": "entroping.handoff.v1"},
    )
    _write_json(
        reports / "observability-packet.json",
        {
            "schema_version": "entroping.observability-packet.v1",
            "summary": {"status": "", "severity": "info"},
        },
    )

    packet = build_integration_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "invalid"
    assert "Could not parse" in sources["team_access_control_plan"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "must be a JSON object" in sources["notification_packet"].summary
    assert sources["handoff"].state == "invalid"
    assert sources["handoff"].schema_version == "entroping.handoff.v1"
    assert "summary must be an object" in sources["handoff"].summary
    assert sources["observability_packet"].state == "invalid"
    assert sources["observability_packet"].schema_version == "entroping.observability-packet.v1"
    assert "status must be a non-empty string" in sources["observability_packet"].summary


def test_integration_readiness_rejects_boolean_integer_fields(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": True},
        },
    )

    packet = build_integration_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert "findings must be a non-negative integer" in sources["runtime_card"].summary


def test_integration_readiness_marks_non_file_and_non_utf8_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    (reports / "team-access-control-plan.json").mkdir(parents=True)
    (reports / "notification-packet.json").write_bytes(b"\xff")

    packet = build_integration_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "unsafe"
    assert "not a file" in sources["team_access_control_plan"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "Could not decode" in sources["notification_packet"].summary


def test_integration_readiness_marks_symlinked_source_unsafe(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    real_source = reports / "team-access-control-source.json"
    _write_json(
        real_source,
        {
            "schema_version": "entroping.team-access-control-plan.v1",
            "summary": {
                "status": "ready",
                "roles_ready": 1,
                "roles_total": 1,
                "blockers_total": 0,
            },
        },
    )
    os.symlink(real_source, reports / "team-access-control-plan.json")

    packet = build_integration_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "unsafe"
    assert "uses symlinked component" in sources["team_access_control_plan"].summary


def test_integration_readiness_marks_oversized_sources_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(integration_readiness, "_MAX_SOURCE_BYTES", 1)

    packet = build_integration_readiness(project_root=tmp_path)
    first_source = packet.sources[0]

    assert first_source.id == "team_access_control_plan"
    assert first_source.state == "invalid"
    assert "exceeds" in first_source.summary


def test_integration_readiness_marks_read_errors_invalid(
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
        if self.name == "team-access-control-plan.json":
            raise OSError("permission denied")
        return original_open(self, mode, buffering, encoding, errors, newline)

    original_open = Path.open
    monkeypatch.setattr(Path, "open", fail_open)

    packet = build_integration_readiness(project_root=tmp_path)
    first_source = packet.sources[0]

    assert first_source.id == "team_access_control_plan"
    assert first_source.state == "invalid"
    assert "Could not read team access-control plan" in first_source.summary


def test_integration_readiness_falls_back_to_runtime_card_project(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
            "run": {"project": "checkout-api"},
        },
    )

    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"
    assert packet.summary.families_attention == 6


def test_integration_readiness_ignores_blank_runtime_card_project(tmp_path: Path) -> None:
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

    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "partial"


def test_integration_readiness_uses_runtime_card_top_level_project(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "project": "checkout-api",
            "summary": {"status": "pass", "findings": 0},
            "run": {"project": None},
        },
    )

    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_integration_readiness_skips_blank_source_project_and_non_object_run(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "team-access-control-plan.json",
        {
            "schema_version": "entroping.team-access-control-plan.v1",
            "project": " ",
            "summary": {
                "status": "ready",
                "roles_ready": 1,
                "roles_total": 1,
                "blockers_total": 0,
            },
        },
    )
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "project": "checkout-api",
            "summary": {"status": "pass", "findings": 0},
            "run": "not-object",
        },
    )

    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_integration_readiness_deduplicates_identical_actions() -> None:
    action = integration_readiness.IntegrationReadinessNextAction(
        priority="medium",
        action="Generate team access-control evidence before enabling integrations.",
        family_ids=("issue_trackers",),
    )

    assert integration_readiness._dedupe_actions([action, action]) == (action,)


def test_integration_readiness_packet_json_supports_pydantic_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    original_model_dump = cast(Any, IntegrationReadinessPacket.model_dump)

    def legacy_model_dump(
        self: IntegrationReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        return cast(dict[str, object], original_model_dump(self, *args, **kwargs))

    monkeypatch.setattr(
        integration_readiness.IntegrationReadinessPacket,
        "model_dump",
        legacy_model_dump,
    )

    packet = build_integration_readiness(project_root=tmp_path)

    assert packet.summary.status == "ready"


def test_integration_readiness_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def broken_model_dump(
        self: IntegrationReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        raise ValueError("boom")

    monkeypatch.setattr(
        integration_readiness.IntegrationReadinessPacket,
        "model_dump",
        broken_model_dump,
    )

    with pytest.raises(
        IntegrationReadinessError,
        match="could not be serialized safely",
    ):
        build_integration_readiness(project_root=tmp_path)


def test_integration_readiness_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(IntegrationReadinessError, match="Unsupported integration-readiness"):
        run_integration_readiness_report(project_root=tmp_path, output=cast(Any, "html"))
    with pytest.raises(IntegrationReadinessError, match="must stay under"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "integration-readiness.json",
        )
    with pytest.raises(IntegrationReadinessError, match="must stay under"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("../escaped-integration-readiness.json"),
        )
    with pytest.raises(IntegrationReadinessError, match="must not be written into"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "integration-readiness.json",
        )
    with pytest.raises(IntegrationReadinessError, match="must not be written into"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "integration-readiness.json",
        )

    monkeypatch.setattr(
        integration_readiness,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(IntegrationReadinessError, match="must stay under"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-integration-readiness.json",
        )


def test_integration_readiness_rejects_escaped_source_path(tmp_path: Path) -> None:
    with pytest.raises(IntegrationReadinessError, match="source path must stay under"):
        integration_readiness._resolve_source_path(Path("../outside.json"), root=tmp_path)


def test_integration_readiness_wraps_source_path_relative_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_relative_error(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("not relative")

    monkeypatch.setattr(
        integration_readiness,
        "first_symlink_path_component",
        raise_relative_error,
    )

    with pytest.raises(IntegrationReadinessError, match="source path must stay under"):
        integration_readiness._resolve_source_path(
            Path("reports") / "team-access-control-plan.json",
            root=tmp_path,
        )


def test_integration_readiness_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(IntegrationReadinessError, match="symlinked component"):
        run_integration_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "integration-readiness.json",
        )


def test_integration_readiness_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_integration_readiness(project_root=tmp_path)
    monkeypatch.setattr(
        integration_readiness,
        "build_integration_readiness",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(IntegrationReadinessError, match="contains secret-like content"):
        run_integration_readiness_report(project_root=tmp_path, output="json")


def test_integration_readiness_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(integration_readiness, "safe_write_text", fail_safe_write)

    with pytest.raises(IntegrationReadinessError, match="disk full"):
        run_integration_readiness_report(project_root=tmp_path, output="json")


def test_integration_readiness_defensively_rejects_secret_like_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = IntegrationReadinessPacket.model_construct(
        schema_version=INTEGRATION_READINESS_SCHEMA_VERSION,
        generated_at="2026-06-20T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        sources=(),
        families=(),
        next_actions=(),
    )
    monkeypatch.setattr(integration_readiness, "_build_packet", lambda **_: packet)

    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(IntegrationReadinessError, match="contains secret-like"),
    ):
        build_integration_readiness(project_root=tmp_path)
