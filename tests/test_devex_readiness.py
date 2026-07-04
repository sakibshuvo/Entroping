"""Tests for developer experience readiness packets."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.readiness.devex_readiness as devex_readiness
from entroping.core.readiness.devex_readiness import (
    DEVEX_READINESS_SCHEMA_VERSION,
    DevexReadinessError,
    DevexReadinessPacket,
    build_devex_readiness,
    render_devex_readiness_markdown,
    run_devex_readiness_report,
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
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": 0, "evidence_links": 5},
            "run": {"project": "checkout-api", "failed_gate_ids": []},
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


def test_devex_readiness_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_devex_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "devex-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == DEVEX_READINESS_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
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
        "first_five_minutes_score": 100,
        "first_five_minutes_readiness_band": "ready",
        "missing_source_count": 0,
        "top_next_action": "No developer experience readiness actions are currently needed.",
    }
    families = {family["id"]: family for family in payload["families"]}
    assert families["cli"]["surface_ids"] == ["cli"]
    assert families["editor"]["surface_ids"] == ["vscode", "editor"]
    assert families["local_workbench"]["surface_ids"] == ["local_workbench"]
    assert families["pr_runtime_card"]["surface_ids"] == ["pr_runtime_card"]
    assert families["desktop"]["surface_ids"] == ["desktop"]
    assert families["cloud"]["surface_ids"] == ["cloud"]
    assert families["mobile"]["surface_ids"] == ["mobile"]
    assert "call_external_api" in families["cli"]["forbidden_actions"]
    assert "implement_app_surface" in families["editor"]["forbidden_actions"]
    assert "override_hurl_qanstitution_result" in families["mobile"]["forbidden_actions"]
    assert "explicit_user_action" in families["pr_runtime_card"]["action_requirements"]
    assert "source_sha256" in families["desktop"]["link_requirements"]
    assert "sk-proj" not in json.dumps(payload)


def test_devex_readiness_marks_missing_invalid_and_unsafe_sources(
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

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "invalid"
    assert sources["notification_packet"].state == "unsafe"
    assert sources["handoff"].state == "invalid"
    assert sources["evidence_index"].state == "missing"
    assert sources["integration_readiness"].state == "missing"
    assert sources["runtime_card"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.families_blocked == 7
    assert packet.summary.blockers_total == 4
    assert packet.summary.first_five_minutes_score == 0
    assert packet.summary.first_five_minutes_readiness_band == "blocked"
    assert packet.summary.missing_source_count == 2
    assert packet.summary.top_next_action == "Repair Runtime card local evidence."
    assert packet.next_actions
    assert "sk-proj" not in packet.model_dump_json()


def test_devex_readiness_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_devex_readiness(project_root=tmp_path).model_copy(
        update={"project": "checkout `api` | demo"}
    )

    markdown = render_devex_readiness_markdown(packet)

    assert "# Entroping Developer Experience Readiness" in markdown
    assert "- Project: `checkout &#96;api&#96; | demo`" in markdown
    assert "## First five minutes" in markdown
    assert "| editor | ready | vscode, editor |" in markdown
    assert "call_external_api" in markdown
    assert "No developer experience readiness actions are currently needed." in markdown
    assert "checkout `api`" not in markdown


def test_devex_readiness_handles_empty_sources(tmp_path: Path) -> None:
    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 6
    assert packet.summary.first_five_minutes_score == 40
    assert packet.summary.first_five_minutes_readiness_band == "blocked"
    assert packet.summary.missing_source_count == 6
    assert packet.summary.top_next_action == "Generate Runtime card local evidence."
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.summary.families_attention == 7
    assert packet.next_actions


def test_devex_readiness_json_output_preserves_required_null_source_fields(
    tmp_path: Path,
) -> None:
    result = run_devex_readiness_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert payload["sources"]
    for source in payload["sources"]:
        assert "schema_version" in source
        assert source["schema_version"] is None
        assert "sha256" in source
        assert source["sha256"] is None


def test_devex_readiness_markdown_output_renders_next_actions(
    tmp_path: Path,
) -> None:
    result = run_devex_readiness_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "devex-readiness.md"
    assert "| Priority | Action | Sources | Families |" in markdown
    assert "Generate Team access-control plan local evidence." in markdown


def test_devex_readiness_marks_malformed_sources_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "team-access-control-plan.json").write_text("[", encoding="utf-8")
    (reports / "notification-packet.json").write_text("[]", encoding="utf-8")
    _write_json(
        reports / "handoff.json",
        {"schema_version": "entroping.handoff.v1"},
    )
    _write_json(
        reports / "evidence-index.json",
        {"schema_version": "entroping.evidence-index.v1"},
    )
    _write_json(
        reports / "integration-readiness.json",
        {
            "schema_version": "entroping.integration-readiness.v1",
            "summary": {"status": "ready", "families_total": 1},
        },
    )

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "invalid"
    assert "Could not parse" in sources["team_access_control_plan"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "must be a JSON object" in sources["notification_packet"].summary
    assert sources["handoff"].state == "invalid"
    assert sources["handoff"].schema_version == "entroping.handoff.v1"
    assert "summary must be an object" in sources["handoff"].summary
    assert sources["evidence_index"].state == "invalid"
    assert sources["evidence_index"].schema_version == "entroping.evidence-index.v1"
    assert "summary must be an object" in sources["evidence_index"].summary
    assert sources["integration_readiness"].state == "invalid"
    assert sources["integration_readiness"].schema_version == (
        "entroping.integration-readiness.v1"
    )
    assert "families_ready must be a non-negative integer" in (
        sources["integration_readiness"].summary
    )


def test_devex_readiness_rejects_boolean_integer_fields(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "runtime-card.json",
        {
            "schema_version": "entroping.runtime-card.v1",
            "summary": {"status": "pass", "findings": True},
        },
    )

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert "findings must be a non-negative integer" in sources["runtime_card"].summary


def test_devex_readiness_rejects_blank_text_fields(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(
        reports / "notification-packet.json",
        {
            "schema_version": "entroping.notification-packet.v1",
            "summary": {"status": " ", "severity": "info"},
        },
    )

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["notification_packet"].state == "invalid"
    assert "status must be a non-empty string" in sources["notification_packet"].summary


def test_devex_readiness_marks_non_file_and_non_utf8_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    (reports / "team-access-control-plan.json").mkdir(parents=True)
    (reports / "notification-packet.json").write_bytes(b"\xff")

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "unsafe"
    assert "not a file" in sources["team_access_control_plan"].summary
    assert sources["notification_packet"].state == "invalid"
    assert "Could not decode" in sources["notification_packet"].summary


def test_devex_readiness_marks_symlinked_source_unsafe(tmp_path: Path) -> None:
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

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["team_access_control_plan"].state == "unsafe"
    assert "uses symlinked component" in sources["team_access_control_plan"].summary


def test_devex_readiness_marks_oversized_sources_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(devex_readiness, "_MAX_SOURCE_BYTES", 1)

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    first_source = sources["runtime_card"]

    assert first_source.state == "invalid"
    assert "exceeds" in first_source.summary


def test_devex_readiness_marks_read_errors_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def fail_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o600,
    ) -> int:
        if Path(os.fsdecode(path)).name == "team-access-control-plan.json":
            raise OSError("permission denied")
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", fail_open)

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    first_source = sources["team_access_control_plan"]

    assert first_source.state == "invalid"
    assert "Could not read team access-control plan" in first_source.summary


def test_devex_readiness_rejects_source_replaced_between_validation_and_read(
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
        mode: int = 0o600,
    ) -> int:
        candidate = Path(os.fsdecode(path))
        if candidate == target and not candidate.is_symlink():
            candidate.unlink()
            os.symlink(outside, candidate)
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", swap_before_open)

    packet = build_devex_readiness(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["runtime_card"].state == "invalid"
    assert sources["runtime_card"].sha256 is None


def test_devex_readiness_bounded_read_works_without_no_follow_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)

    assert devex_readiness._read_bounded_bytes(source, artifact="source") == b"{}"


def test_devex_readiness_bounded_read_rejects_non_regular_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "source-dir"
    source_dir.mkdir()

    with pytest.raises(DevexReadinessError, match="regular file|Could not read"):
        devex_readiness._read_bounded_bytes(source_dir, artifact="source")


def test_devex_readiness_falls_back_to_runtime_card_project(tmp_path: Path) -> None:
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

    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"
    assert packet.summary.families_attention == 7


def test_devex_readiness_ignores_blank_runtime_card_project(tmp_path: Path) -> None:
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

    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.project is None
    assert packet.summary.status == "partial"


def test_devex_readiness_uses_runtime_card_top_level_project(tmp_path: Path) -> None:
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

    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_devex_readiness_skips_blank_source_project_and_non_object_run(
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

    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.project == "checkout-api"
    assert packet.summary.status == "partial"


def test_devex_readiness_deduplicates_identical_actions() -> None:
    action = devex_readiness.DevexReadinessNextAction(
        priority="medium",
        action="Generate runtime evidence before enabling devex surfaces.",
        family_ids=("cli",),
    )

    assert devex_readiness._dedupe_actions([action, action]) == (action,)


def test_devex_readiness_packet_json_supports_pydantic_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    original_model_dump = cast(Any, DevexReadinessPacket.model_dump)

    def legacy_model_dump(
        self: DevexReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        return cast(dict[str, object], original_model_dump(self, *args, **kwargs))

    monkeypatch.setattr(
        devex_readiness.DevexReadinessPacket,
        "model_dump",
        legacy_model_dump,
    )

    packet = build_devex_readiness(project_root=tmp_path)

    assert packet.summary.status == "ready"


def test_devex_readiness_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def broken_model_dump(
        self: DevexReadinessPacket,
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        if "fallback" in kwargs:
            raise TypeError("fallback keyword is unsupported")
        raise ValueError("boom")

    monkeypatch.setattr(
        devex_readiness.DevexReadinessPacket,
        "model_dump",
        broken_model_dump,
    )

    with pytest.raises(
        DevexReadinessError,
        match="could not be serialized safely",
    ):
        build_devex_readiness(project_root=tmp_path)


def test_devex_readiness_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(DevexReadinessError, match="Unsupported devex-readiness"):
        run_devex_readiness_report(project_root=tmp_path, output=cast(Any, "html"))
    with pytest.raises(DevexReadinessError, match="must stay under"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "devex-readiness.json",
        )
    with pytest.raises(DevexReadinessError, match="must stay under"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("../escaped-devex-readiness.json"),
        )
    with pytest.raises(DevexReadinessError, match="must not be written into"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "devex-readiness.json",
        )
    with pytest.raises(DevexReadinessError, match="must not be written into"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("envs") / "devex-readiness.json",
        )

    monkeypatch.setattr(
        devex_readiness,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(DevexReadinessError, match="must stay under"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-devex-readiness.json",
        )


def test_devex_readiness_rejects_escaped_source_path(tmp_path: Path) -> None:
    with pytest.raises(DevexReadinessError, match="source path must stay under"):
        devex_readiness._resolve_source_path(Path("../outside.json"), root=tmp_path)


def test_devex_readiness_wraps_source_path_relative_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_relative_error(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("not relative")

    monkeypatch.setattr(
        devex_readiness,
        "first_symlink_path_component",
        raise_relative_error,
    )

    with pytest.raises(DevexReadinessError, match="source path must stay under"):
        devex_readiness._resolve_source_path(
            Path("reports") / "team-access-control-plan.json",
            root=tmp_path,
        )


def test_devex_readiness_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(DevexReadinessError, match="symlinked component"):
        run_devex_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "devex-readiness.json",
        )


def test_devex_readiness_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_devex_readiness(project_root=tmp_path)
    monkeypatch.setattr(
        devex_readiness,
        "build_devex_readiness",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(DevexReadinessError, match="contains secret-like content"):
        run_devex_readiness_report(project_root=tmp_path, output="json")


def test_devex_readiness_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(devex_readiness, "safe_write_text", fail_safe_write)

    with pytest.raises(DevexReadinessError, match="disk full"):
        run_devex_readiness_report(project_root=tmp_path, output="json")


def test_devex_readiness_defensively_rejects_secret_like_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = DevexReadinessPacket.model_construct(
        schema_version=DEVEX_READINESS_SCHEMA_VERSION,
        generated_at="2026-06-20T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        sources=(),
        families=(),
        next_actions=(),
    )
    monkeypatch.setattr(devex_readiness, "_build_packet", lambda **_: packet)

    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(DevexReadinessError, match="contains secret-like"),
    ):
        build_devex_readiness(project_root=tmp_path)
