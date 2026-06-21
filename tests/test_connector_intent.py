"""Tests for connector intent packets."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.connector_intent as connector_intent
from entroping.core.connector_intent import (
    CONNECTOR_INTENT_SCHEMA_VERSION,
    ConnectorIntentError,
    ConnectorIntentPacket,
    build_connector_intent,
    render_connector_intent_markdown,
    run_connector_intent_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_sources(root: Path) -> None:
    reports = root / "reports"
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 5},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
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
        reports / "integration-readiness.json",
        {
            "schema_version": "entroping.integration-readiness.v1",
            "project": "checkout-api",
            "summary": {
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
            },
        },
    )
    _write_json(
        reports / "devex-readiness.json",
        {
            "schema_version": "entroping.devex-readiness.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "sources_total": 6,
                "sources_present": 6,
                "sources_missing": 0,
                "sources_invalid": 0,
                "sources_unsafe": 0,
                "families_total": 7,
                "families_ready": 7,
                "families_attention": 0,
                "families_blocked": 0,
                "blockers_total": 0,
                "next_actions_total": 0,
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
        reports / "evidence-index.json",
        {
            "schema_version": "entroping.evidence-index.v1",
            "project": "checkout-api",
            "summary": {
                "status": "ready",
                "artifacts_total": 6,
                "artifacts_present": 6,
                "artifacts_missing": 0,
                "artifacts_invalid": 0,
                "artifacts_unsafe": 0,
            },
        },
    )


def test_connector_intent_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_connector_intent_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "connector-intent.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == CONNECTOR_INTENT_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 7,
        "sources_present": 7,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "intents_total": 6,
        "intents_ready": 6,
        "intents_attention": 0,
        "intents_blocked": 0,
        "blockers_total": 0,
        "next_actions_total": 0,
    }
    intents = {intent["id"]: intent for intent in payload["intents"]}
    assert intents["issue_tracker"]["target_systems"] == [
        "jira",
        "linear",
        "monday",
        "github_issues",
        "generic_tracker",
    ]
    assert intents["chat"]["target_systems"] == [
        "slack",
        "discord",
        "teams",
        "generic_chat",
    ]
    assert intents["enterprise_automation"]["target_systems"] == [
        "workato",
        "zapier",
        "generic_workflow",
    ]
    assert intents["enterprise_ai"]["target_systems"] == [
        "claude",
        "codex",
        "openai_compatible_agent",
        "generic_ai_assistant",
    ]
    assert intents["observability"]["target_systems"] == [
        "opentelemetry",
        "datadog",
        "splunk",
        "grafana",
        "generic_observability",
    ]
    assert intents["devex_surface"]["target_systems"] == [
        "vscode",
        "editor",
        "local_workbench",
        "desktop",
        "cloud",
        "mobile",
        "pr_card",
    ]
    assert intents["issue_tracker"]["required_user_action"] == "explicit_user_approval"
    assert "artifact_id" in intents["chat"]["minimum_payload_fields"]
    assert "approval_id" in intents["enterprise_automation"]["audit_fields"]
    assert "invoke_model_provider" in intents["enterprise_ai"]["forbidden_actions"]
    assert "mutate_dashboard_or_monitor" in intents["observability"]["forbidden_actions"]
    assert "implement_app_surface" in intents["devex_surface"]["forbidden_actions"]
    assert "sk-proj" not in json.dumps(payload)


def test_connector_intent_marks_missing_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "integration-readiness.json",
        {"schema_version": "entroping.integration-readiness.v999"},
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

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "unsafe"
    assert sources["handoff"].state == "invalid"
    assert sources["notification_packet"].state == "unsafe"
    assert sources["integration_readiness"].state == "invalid"
    assert sources["devex_readiness"].state == "missing"
    assert sources["observability_packet"].state == "missing"
    assert sources["evidence_index"].state == "missing"
    assert packet.summary.status == "insufficient"
    assert packet.summary.intents_blocked == 4
    assert packet.summary.intents_attention == 2
    assert packet.summary.blockers_total == 4
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_connector_intent_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_connector_intent(project_root=tmp_path).model_copy(
        update={"project": "checkout `api` | demo"}
    )

    markdown = render_connector_intent_markdown(packet)

    assert "# Entroping Connector Intent" in markdown
    assert "- Project: `checkout &#96;api&#96; | demo`" in markdown
    assert (
        "| issue_tracker | ready | jira, linear, monday, github_issues, generic_tracker |"
        in markdown
    )
    assert "call_external_api" in markdown
    assert "No connector intent actions are currently needed." in markdown
    assert "checkout `api`" not in markdown


def test_connector_intent_handles_empty_sources(tmp_path: Path) -> None:
    packet = build_connector_intent(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 7
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.summary.intents_attention == 6
    assert packet.next_actions


def test_connector_intent_json_output_preserves_required_null_source_fields(
    tmp_path: Path,
) -> None:
    result = run_connector_intent_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert payload["sources"]
    for source in payload["sources"]:
        assert "schema_version" in source
        assert source["schema_version"] is None
        assert "sha256" in source
        assert source["sha256"] is None


def test_connector_intent_markdown_output_renders_next_actions(
    tmp_path: Path,
) -> None:
    result = run_connector_intent_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "connector-intent.md"
    assert "| Priority | Action | Sources | Intents |" in markdown
    assert "Generate Runtime card local evidence." in markdown


def test_connector_intent_marks_malformed_sources_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "runtime-card.json").write_text("[", encoding="utf-8")
    (reports / "handoff.json").write_text("[]", encoding="utf-8")
    _write_json(
        reports / "notification-packet.json",
        {"schema_version": "entroping.notification-packet.v1"},
    )
    _write_json(
        reports / "devex-readiness.json",
        {"schema_version": "entroping.devex-readiness.v1"},
    )
    _write_json(
        reports / "observability-packet.json",
        {
            "schema_version": "entroping.observability-packet.v1",
            "summary": {"status": "ready", "severity": "info"},
        },
    )

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert "Could not parse" in sources["runtime_card"].summary
    assert sources["handoff"].state == "invalid"
    assert "must be a JSON object" in sources["handoff"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "summary must be an object" in sources["notification_packet"].summary
    assert sources["devex_readiness"].state == "invalid"
    assert "summary must be an object" in sources["devex_readiness"].summary
    assert sources["observability_packet"].state == "invalid"
    assert "events_total must be a non-negative integer" in (
        sources["observability_packet"].summary
    )


def test_connector_intent_rejects_boolean_integer_fields(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": True},
        },
    )

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert "findings must be a non-negative integer" in sources["runtime_card"].summary


def test_connector_intent_rejects_blank_text_fields(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "notification-packet.json",
        {
            "schema_version": "entroping.notification-packet.v1",
            "summary": {"status": " ", "severity": "info"},
        },
    )

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["notification_packet"].state == "invalid"
    assert "status must be a non-empty string" in sources["notification_packet"].summary


def test_connector_intent_marks_non_file_and_non_utf8_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    (reports / "runtime-card.json").mkdir(parents=True)
    (reports / "notification-packet.json").write_bytes(b"\xff")

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "unsafe"
    assert "not a file" in sources["runtime_card"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "Could not decode" in sources["notification_packet"].summary


def test_connector_intent_marks_symlinked_source_unsafe(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    real_source = reports / "runtime-source.json"
    _write_json(
        real_source,
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
        },
    )
    os.symlink(real_source, reports / "runtime-card.json")

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "unsafe"
    assert "uses symlinked component" in sources["runtime_card"].summary


def test_connector_intent_marks_oversized_sources_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(connector_intent, "_MAX_SOURCE_BYTES", 1)

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    first_source = sources["runtime_card"]

    assert first_source.state == "invalid"
    assert "exceeds" in first_source.summary


def test_connector_intent_marks_read_errors_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def fail_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
    ) -> int:
        if Path(os.fsdecode(path)).name == "runtime-card.json":
            raise OSError("permission denied")
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", fail_open)

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    first_source = sources["runtime_card"]

    assert first_source.state == "invalid"
    assert "Could not read runtime card" in first_source.summary


def test_connector_intent_rejects_source_replaced_between_validation_and_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    outside = tmp_path.parent / "outside-runtime-card.json"
    _write_json(
        outside,
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0},
        },
    )
    target = tmp_path / "reports" / "runtime-card.json"

    def swap_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
    ) -> int:
        candidate = Path(os.fsdecode(path))
        if candidate == target and not candidate.is_symlink():
            candidate.unlink()
            os.symlink(outside, candidate)
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", swap_before_open)

    packet = build_connector_intent(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert sources["runtime_card"].sha256 is None


def test_connector_intent_bounded_read_works_without_no_follow_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)

    assert connector_intent._read_bounded_bytes(source, artifact="source") == b"{}"


def test_connector_intent_bounded_read_rejects_non_regular_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "source-dir"
    source_dir.mkdir()

    with pytest.raises(ConnectorIntentError, match="regular file|Could not read"):
        connector_intent._read_bounded_bytes(source_dir, artifact="source")


def test_connector_intent_falls_back_to_runtime_card_project(tmp_path: Path) -> None:
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

    packet = build_connector_intent(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"
    assert packet.summary.intents_attention == 6


def test_connector_intent_ignores_blank_runtime_card_project(tmp_path: Path) -> None:
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

    packet = build_connector_intent(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "partial"


def test_connector_intent_uses_runtime_card_top_level_project(tmp_path: Path) -> None:
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

    packet = build_connector_intent(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_connector_intent_skips_blank_source_project_and_non_object_run(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "handoff.json",
        {
            "schema_version": "entroping.handoff.v1",
            "project": " ",
            "summary": {
                "status": "ready",
                "artifacts_present": 1,
                "artifacts_total": 1,
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

    packet = build_connector_intent(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_connector_intent_deduplicates_identical_actions() -> None:
    action = connector_intent.ConnectorIntentNextAction(
        priority="medium",
        action="Generate runtime evidence before enabling connector intents.",
        intent_ids=("issue_tracker",),
    )

    assert connector_intent._dedupe_actions([action, action]) == (action,)


def test_connector_intent_packet_json_supports_pydantic_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    original_model_dump = cast(Any, ConnectorIntentPacket.model_dump)

    def legacy_model_dump(
        self: ConnectorIntentPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        return cast(dict[str, object], original_model_dump(self, *args, **kwargs))

    monkeypatch.setattr(
        connector_intent.ConnectorIntentPacket,
        "model_dump",
        legacy_model_dump,
    )

    packet = build_connector_intent(project_root=tmp_path)

    assert packet.summary.status == "ready"


def test_connector_intent_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def broken_model_dump(
        self: ConnectorIntentPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        raise ValueError("boom")

    monkeypatch.setattr(
        connector_intent.ConnectorIntentPacket,
        "model_dump",
        broken_model_dump,
    )

    with pytest.raises(
        ConnectorIntentError,
        match="could not be serialized safely",
    ):
        build_connector_intent(project_root=tmp_path)


def test_connector_intent_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ConnectorIntentError, match="Unsupported connector-intent"):
        run_connector_intent_report(project_root=tmp_path, output=cast(Any, "html"))
    with pytest.raises(ConnectorIntentError, match="must stay under"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "connector-intent.json",
        )
    with pytest.raises(ConnectorIntentError, match="must stay under"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("../escaped-connector-intent.json"),
        )
    with pytest.raises(ConnectorIntentError, match="must not be written into"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "connector-intent.json",
        )
    with pytest.raises(ConnectorIntentError, match="must not be written into"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "connector-intent.json",
        )

    monkeypatch.setattr(
        connector_intent,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ConnectorIntentError, match="must stay under"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-connector-intent.json",
        )


def test_connector_intent_rejects_escaped_source_path(tmp_path: Path) -> None:
    with pytest.raises(ConnectorIntentError, match="source path must stay under"):
        connector_intent._resolve_source_path(Path("../outside.json"), root=tmp_path)


def test_connector_intent_wraps_source_path_relative_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_relative_error(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("not relative")

    monkeypatch.setattr(
        connector_intent,
        "first_symlink_path_component",
        raise_relative_error,
    )

    with pytest.raises(ConnectorIntentError, match="source path must stay under"):
        connector_intent._resolve_source_path(
            Path("reports") / "runtime-card.json",
            root=tmp_path,
        )


def test_connector_intent_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(ConnectorIntentError, match="symlinked component"):
        run_connector_intent_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "connector-intent.json",
        )


def test_connector_intent_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_connector_intent(project_root=tmp_path)
    monkeypatch.setattr(
        connector_intent,
        "build_connector_intent",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(ConnectorIntentError, match="contains secret-like content"):
        run_connector_intent_report(project_root=tmp_path, output="json")


def test_connector_intent_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(connector_intent, "safe_write_text", fail_safe_write)

    with pytest.raises(ConnectorIntentError, match="disk full"):
        run_connector_intent_report(project_root=tmp_path, output="json")


def test_connector_intent_defensively_rejects_secret_like_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = ConnectorIntentPacket.model_construct(
        schema_version=CONNECTOR_INTENT_SCHEMA_VERSION,
        generated_at="2026-06-20T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        sources=(),
        intents=(),
        next_actions=(),
    )
    monkeypatch.setattr(connector_intent, "_build_packet", lambda **_: packet)

    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(ConnectorIntentError, match="contains secret-like"),
    ):
        build_connector_intent(project_root=tmp_path)
