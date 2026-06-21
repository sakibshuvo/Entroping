"""Tests for local evidence action plans."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entroping.core.evidence_action_plan as evidence_action_plan
from entroping.core.evidence_action_plan import (
    EVIDENCE_ACTION_PLAN_SCHEMA_VERSION,
    EvidenceActionPlanError,
    build_evidence_action_plan_packet,
    render_evidence_action_plan_markdown,
    run_evidence_action_plan_report,
)
from entroping.core.safe_write import SafeWriteError

_SOURCE_SCHEMAS: dict[str, str] = {
    "pr-evidence-card-json": "entroping.pr-evidence-card.v1",
    "evidence-portal-json": "entroping.evidence-portal.v1",
    "evidence-links-json": "entroping.evidence-links.v1",
    "evidence-cloud-dashboard-json": "entroping.evidence-cloud-dashboard.v1",
    "devex-readiness-json": "entroping.devex-readiness.v1",
    "integration-readiness-json": "entroping.integration-readiness.v1",
    "connector-intent-json": "entroping.connector-intent.v1",
    "observability-packet-json": "entroping.observability-packet.v1",
    "mutation-readiness-json": "entroping.mutation-readiness.v1",
    "test-pyramid-json": "entroping.test-pyramid-report.v1",
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_artifact(
    schema_version: str,
    *,
    status: str = "ready",
    raw_marker: str = "raw implementation detail must not render",
    next_actions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": status,
            "next_actions_total": len(next_actions or ()),
        },
        "next_actions": next_actions or [],
        "raw_marker": raw_marker,
    }


def _write_source(
    root: Path,
    source_id: str,
    *,
    status: str = "ready",
    include_summary: bool = True,
    next_actions: list[dict[str, object]] | None = None,
) -> None:
    payload = _source_artifact(
        _SOURCE_SCHEMAS[source_id],
        status=status,
        next_actions=next_actions,
    )
    if not include_summary:
        payload.pop("summary")
    _write_json(
        root / "reports" / f"{source_id.removesuffix('-json')}.json",
        payload,
    )


def test_evidence_action_plan_writes_value_free_json_from_local_sources(
    tmp_path: Path,
) -> None:
    raw_marker = "raw PR body text must not render"
    _write_json(
        tmp_path / "reports" / "pr-evidence-card.json",
        _source_artifact(
            "entroping.pr-evidence-card.v1",
            status="partial",
            raw_marker=raw_marker,
            next_actions=[
                {
                    "priority": "high",
                    "action": "Repair Runtime Card JSON before merge.",
                    "source_ids": ["runtime-card-json"],
                },
                {
                    "priority": "low",
                    "action": "Review local evidence plan after merge.",
                },
            ],
        ),
    )
    _write_source(tmp_path, "evidence-portal-json")

    result = run_evidence_action_plan_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "evidence-action-plan.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_ACTION_PLAN_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["sources_present"] == 2
    assert payload["summary"]["actions_high"] >= 1
    assert any(
        action["action"] == "Repair Runtime Card JSON before merge."
        for action in payload["actions"]
    )
    assert any(
        action["priority"] == "low"
        and action["action"] == "Review local evidence plan after merge."
        for action in payload["actions"]
    )
    assert raw_marker not in json.dumps(payload)


def test_evidence_action_plan_reports_ready_when_all_sources_are_ready(
    tmp_path: Path,
) -> None:
    for source_id in _SOURCE_SCHEMAS:
        _write_source(tmp_path, source_id)

    packet = build_evidence_action_plan_packet(project_root=tmp_path)
    markdown = render_evidence_action_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.sources_present == len(_SOURCE_SCHEMAS)
    assert packet.summary.actions_total == 0
    assert "- No evidence action-plan actions are currently needed." in markdown


def test_evidence_action_plan_reports_partial_when_sources_have_no_status(
    tmp_path: Path,
) -> None:
    for source_id in _SOURCE_SCHEMAS:
        _write_source(tmp_path, source_id, include_summary=False)

    packet = build_evidence_action_plan_packet(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.actions_total == 0


def test_evidence_action_plan_missing_sources_create_generation_actions(
    tmp_path: Path,
) -> None:
    packet = build_evidence_action_plan_packet(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == len(_SOURCE_SCHEMAS)
    assert packet.summary.actions_medium == len(_SOURCE_SCHEMAS)
    assert all(action.category == "generate" for action in packet.actions)


def test_evidence_action_plan_marks_secret_like_sources_unsafe(
    tmp_path: Path,
) -> None:
    secret_like_value = "sk-proj-" + ("a" * 24)
    _write_json(
        tmp_path / "reports" / "pr-evidence-card.json",
        _source_artifact(
            "entroping.pr-evidence-card.v1",
            status="ready",
            raw_marker=secret_like_value,
        ),
    )

    packet = build_evidence_action_plan_packet(project_root=tmp_path)
    markdown = render_evidence_action_plan_markdown(packet)
    source = {item.id: item for item in packet.sources}["pr-evidence-card-json"]

    assert source.state == "unsafe"
    assert source.summary == "secret-like content"
    assert any(
        action.priority == "high" and action.category == "repair"
        for action in packet.actions
    )
    assert secret_like_value not in packet.model_dump_json()
    assert secret_like_value not in markdown


def test_evidence_action_plan_marks_secondary_read_failures_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path, "pr-evidence-card-json")
    monkeypatch.setattr(
        evidence_action_plan,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "not a file"),
    )

    packet = build_evidence_action_plan_packet(project_root=tmp_path)
    source = {item.id: item for item in packet.sources}["pr-evidence-card-json"]

    assert source.state == "unsafe"
    assert source.summary == "not a file"


def test_evidence_action_plan_marks_secondary_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path, "pr-evidence-card-json")
    monkeypatch.setattr(
        evidence_action_plan,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{not json", ""),
    )

    packet = build_evidence_action_plan_packet(project_root=tmp_path)
    source = {item.id: item for item in packet.sources}["pr-evidence-card-json"]

    assert source.state == "invalid"
    assert source.summary == "invalid JSON"


def test_evidence_action_plan_present_blocked_status_creates_review_action(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path, "pr-evidence-card-json", status="blocked")

    packet = build_evidence_action_plan_packet(project_root=tmp_path)

    assert any(
        action.priority == "high"
        and action.category == "review"
        and action.action == "Review PR Evidence Card blocked status before merge."
        for action in packet.actions
    )


def test_evidence_action_plan_next_action_count_creates_value_free_review_action(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-portal.json",
        {
            "schema_version": "entroping.evidence-portal.v1",
            "generated_at": "2026-06-21T00:00:00+00:00",
            "project": "checkout-api",
            "summary": {"status": "ready", "next_actions_total": 2},
        },
    )

    packet = build_evidence_action_plan_packet(project_root=tmp_path)

    assert any(
        action.priority == "low"
        and action.category == "review"
        and action.action == "Review Evidence Portal 2 source next actions."
        for action in packet.actions
    )


def test_evidence_action_plan_filters_malformed_or_secret_next_actions(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "pr-evidence-card.json",
        _source_artifact(
            "entroping.pr-evidence-card.v1",
            status="ready",
            next_actions=[
                {"action": ""},
                {"action": "Review safe local evidence before merge.", "priority": "urgent"},
            ],
        )
        | {
            "next_actions": [
                [],
                {"action": ""},
                {
                    "action": "Review safe local evidence before merge.",
                    "priority": "urgent",
                },
            ]
        },
    )

    packet = build_evidence_action_plan_packet(project_root=tmp_path)

    assert any(
        action.priority == "medium"
        and action.action == "Review safe local evidence before merge."
        for action in packet.actions
    )


def test_evidence_action_plan_filters_secret_like_extracted_action() -> None:
    secret_like_value = "sk-proj-" + ("a" * 24)
    source = evidence_action_plan.EvidenceActionPlanSource(
        id="pr-evidence-card-json",
        label="PR Evidence Card",
        path="reports/pr-evidence-card.json",
        state="present",
        schema_version="entroping.pr-evidence-card.v1",
        sha256="a" * 64,
        summary="ready",
        status="ready",
    )

    actions = evidence_action_plan._extract_next_actions(
        source=source,
        document={"next_actions": [{"action": secret_like_value}]},
    )

    assert actions == ()


def test_evidence_action_plan_markdown_escapes_inline_code_and_html_breakouts(
    tmp_path: Path,
) -> None:
    payload = _source_artifact("entroping.pr-evidence-card.v1", status="ready")
    payload["project"] = "checkout`api<unsafe>|line\nbreak"
    _write_json(tmp_path / "reports" / "pr-evidence-card.json", payload)

    markdown = render_evidence_action_plan_markdown(
        build_evidence_action_plan_packet(project_root=tmp_path)
    )

    assert "checkout`api<unsafe>|line\nbreak" not in markdown
    assert "checkout&#96;api&lt;unsafe&gt;\\|line break" in markdown


def test_evidence_action_plan_writes_markdown_by_default(tmp_path: Path) -> None:
    result = run_evidence_action_plan_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "evidence-action-plan.md"
    assert result.output_path.read_text(encoding="utf-8").startswith(
        "# Entroping Evidence Action Plan"
    )


def test_evidence_action_plan_rejects_output_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EvidenceActionPlanError, match="must stay under the project root"):
        run_evidence_action_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-action-plan.json",
        )


def test_evidence_action_plan_rejects_output_under_forbidden_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceActionPlanError, match="must not be written"):
        run_evidence_action_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "evidence-action-plan.json",
        )


def test_evidence_action_plan_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evidence_action_plan,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(EvidenceActionPlanError, match="contains secret-like content"):
        run_evidence_action_plan_report(project_root=tmp_path, output="json")


def test_evidence_action_plan_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(evidence_action_plan, "safe_write_text", fail_write)

    with pytest.raises(EvidenceActionPlanError, match="blocked write"):
        run_evidence_action_plan_report(project_root=tmp_path, output="json")


def test_evidence_action_plan_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceActionPlanError, match="Unsupported"):
        run_evidence_action_plan_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_evidence_action_plan_defensive_source_fallbacks(tmp_path: Path) -> None:
    source, document = evidence_action_plan._source_from_index(
        "pr-evidence-card-json",
        None,
        root=tmp_path,
    )

    assert document is None
    assert source.label == "PR Evidence Card"
    assert source.path == "reports/pr-evidence-card.json"
    assert evidence_action_plan._source_label("unknown-json") == "unknown-json"  # type: ignore[arg-type]
    assert evidence_action_plan._state_from_load_error("schema mismatch") == "invalid"
