"""Tests for local work item draft packets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entroping.core.export.work_item_draft as work_item_draft
from entroping.core.safe_write import SafeWriteError

_SOURCE_SCHEMAS: dict[str, str] = {
    "evidence-action-plan-json": "entroping.evidence-action-plan.v1",
    "connector-intent-json": "entroping.connector-intent.v1",
    "integration-readiness-json": "entroping.integration-readiness.v1",
    "evidence-links-json": "entroping.evidence-links.v1",
    "notification-packet-json": "entroping.notification-packet.v1",
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_artifact(
    schema_version: str,
    *,
    status: str = "ready",
    raw_marker: str = "raw implementation detail must not render",
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {"status": status},
        "raw_marker": raw_marker,
    }


def _action_plan_artifact(
    *,
    status: str = "partial",
    raw_marker: str = "raw action-plan detail must not render",
    actions: list[object] | None = None,
) -> dict[str, object]:
    payload = _source_artifact(
        "entroping.evidence-action-plan.v1",
        status=status,
        raw_marker=raw_marker,
    )
    payload["actions"] = actions or []
    return payload


def _write_source(root: Path, source_id: str, *, status: str = "ready") -> None:
    _write_json(
        root / "reports" / f"{source_id.removesuffix('-json')}.json",
        _source_artifact(_SOURCE_SCHEMAS[source_id], status=status),
    )


def test_work_item_draft_writes_value_free_json_from_action_plan(
    tmp_path: Path,
) -> None:
    raw_marker = "raw tracker payload must not render"
    _write_json(
        tmp_path / "reports" / "evidence-action-plan.json",
        _action_plan_artifact(
            raw_marker=raw_marker,
            actions=[
                {
                    "priority": "high",
                    "category": "review",
                    "action": "Review PR Evidence Card blocked status before merge.",
                    "source_ids": ["pr-evidence-card-json"],
                    "status": "blocked",
                },
                {
                    "priority": "low",
                    "category": "review",
                    "action": "Review local evidence plan after merge.",
                    "source_ids": ["evidence-action-plan-json"],
                },
            ],
        ),
    )
    _write_source(tmp_path, "connector-intent-json")

    result = work_item_draft.run_work_item_draft_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "work-item-draft.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == work_item_draft.WORK_ITEM_DRAFT_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["sources_present"] == 2
    assert payload["summary"]["items_high"] >= 1
    assert any(
        item["title"] == "Review PR Evidence Card blocked status before merge."
        and item["source_action_count"] == 1
        and item["target_systems"]
        == [
            "jira",
            "linear",
            "monday",
            "github_issues",
            "generic_tracker",
        ]
        for item in payload["items"]
    )
    assert raw_marker not in json.dumps(payload)


def test_work_item_draft_reports_ready_when_all_sources_are_ready(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-action-plan.json",
        _action_plan_artifact(status="ready"),
    )
    for source_id in _SOURCE_SCHEMAS:
        if source_id != "evidence-action-plan-json":
            _write_source(tmp_path, source_id)

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    markdown = work_item_draft.render_work_item_draft_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.sources_present == len(_SOURCE_SCHEMAS)
    assert packet.summary.items_total == 0
    assert "- No work item draft rows are currently needed." in markdown


def test_work_item_draft_reports_partial_when_sources_have_no_status(
    tmp_path: Path,
) -> None:
    for source_id, schema_version in _SOURCE_SCHEMAS.items():
        _write_json(
            tmp_path / "reports" / f"{source_id.removesuffix('-json')}.json",
            {
                "schema_version": schema_version,
                "project": "checkout-api",
            },
        )

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.items_total == 0


def test_work_item_draft_missing_sources_create_generation_items(tmp_path: Path) -> None:
    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == len(_SOURCE_SCHEMAS)
    assert packet.summary.items_medium == len(_SOURCE_SCHEMAS)
    assert all(item.category == "generate" for item in packet.items)


def test_work_item_draft_marks_secret_like_sources_unsafe(tmp_path: Path) -> None:
    secret_like_value = "sk-proj-" + ("a" * 24)
    _write_json(
        tmp_path / "reports" / "evidence-action-plan.json",
        _action_plan_artifact(status="ready", raw_marker=secret_like_value),
    )

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    markdown = work_item_draft.render_work_item_draft_markdown(packet)
    source = {item.id: item for item in packet.sources}["evidence-action-plan-json"]

    assert source.state == "unsafe"
    assert source.summary == "secret-like content"
    assert any(item.priority == "high" and item.category == "repair" for item in packet.items)
    assert secret_like_value not in packet.model_dump_json()
    assert secret_like_value not in markdown


def test_work_item_draft_marks_secondary_read_failures_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "evidence-action-plan.json", _action_plan_artifact())
    monkeypatch.setattr(
        work_item_draft,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "not a file"),
    )

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    source = {item.id: item for item in packet.sources}["evidence-action-plan-json"]

    assert source.state == "unsafe"
    assert source.summary == "not a file"


def test_work_item_draft_marks_secondary_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_json(tmp_path / "reports" / "evidence-action-plan.json", _action_plan_artifact())
    monkeypatch.setattr(
        work_item_draft,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{not json", ""),
    )

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    source = {item.id: item for item in packet.sources}["evidence-action-plan-json"]

    assert source.state == "invalid"
    assert source.summary == "invalid JSON"


def test_work_item_draft_filters_malformed_or_secret_source_actions(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-action-plan.json",
        _action_plan_artifact(
            actions=[
                [],
                {"action": ""},
                {"action": "Prepare safe tracker draft.", "priority": "urgent"},
            ],
        ),
    )

    packet = work_item_draft.build_work_item_draft_packet(project_root=tmp_path)

    assert any(
        item.priority == "medium"
        and item.title == "Prepare safe tracker draft."
        and item.source_action_ids == ("evidence-action-plan:001",)
        for item in packet.items
    )


def test_work_item_draft_filters_secret_like_extracted_action() -> None:
    secret_like_value = "sk-proj-" + ("a" * 24)
    source = work_item_draft.WorkItemDraftSource(
        id="evidence-action-plan-json",
        label="Evidence Action Plan",
        path="reports/evidence-action-plan.json",
        state="present",
        schema_version="entroping.evidence-action-plan.v1",
        sha256="a" * 64,
        summary="ready",
        status="ready",
    )

    items = work_item_draft._draft_items_from_action_plan(
        source=source,
        document={"actions": [{"action": secret_like_value}]},
    )

    assert items == ()


def test_work_item_draft_ignores_non_list_action_plan_actions() -> None:
    source = work_item_draft.WorkItemDraftSource(
        id="evidence-action-plan-json",
        label="Evidence Action Plan",
        path="reports/evidence-action-plan.json",
        state="present",
        schema_version="entroping.evidence-action-plan.v1",
        sha256="a" * 64,
        summary="ready",
        status="ready",
    )

    items = work_item_draft._draft_items_from_action_plan(
        source=source,
        document={"actions": {"action": "not a list"}},
    )

    assert items == ()


def test_work_item_draft_markdown_escapes_inline_code_and_html_breakouts(
    tmp_path: Path,
) -> None:
    payload = _action_plan_artifact(status="ready")
    payload["project"] = "checkout`api<unsafe>|line\nbreak"
    _write_json(tmp_path / "reports" / "evidence-action-plan.json", payload)

    markdown = work_item_draft.render_work_item_draft_markdown(
        work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    )

    assert "checkout`api<unsafe>|line\nbreak" not in markdown
    assert "checkout&#96;api&lt;unsafe&gt;\\|line break" in markdown


def test_work_item_draft_markdown_neutralizes_link_and_formatting_syntax(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "evidence-action-plan.json",
        _action_plan_artifact(
            status="partial",
            actions=[
                {
                    "action": "Review [tracker](https://example.test) ![x](y) *now* _soon_",
                    "priority": "high",
                }
            ],
        ),
    )

    markdown = work_item_draft.render_work_item_draft_markdown(
        work_item_draft.build_work_item_draft_packet(project_root=tmp_path)
    )

    assert "[tracker](https://example.test)" not in markdown
    assert "![x](y)" not in markdown
    assert "*now*" not in markdown
    assert "_soon_" not in markdown
    assert (
        "Review &#91;tracker&#93;&#40;https://example.test&#41; "
        "&#33;&#91;x&#93;&#40;y&#41; &#42;now&#42; &#95;soon&#95;"
    ) in markdown


def test_work_item_draft_writes_markdown_by_default(tmp_path: Path) -> None:
    result = work_item_draft.run_work_item_draft_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "work-item-draft.md"
    assert result.output_path.read_text(encoding="utf-8").startswith("# Entroping Work Item Draft")


def test_work_item_draft_rejects_output_outside_project(tmp_path: Path) -> None:
    with pytest.raises(
        work_item_draft.WorkItemDraftError, match="must stay under the project root"
    ):
        work_item_draft.run_work_item_draft_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "work-item-draft.json",
        )


def test_work_item_draft_rejects_output_under_forbidden_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(work_item_draft.WorkItemDraftError, match="must not be written"):
        work_item_draft.run_work_item_draft_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "work-item-draft.json",
        )


def test_work_item_draft_rejects_nested_forbidden_output_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(work_item_draft.WorkItemDraftError, match="must not be written"):
        work_item_draft.run_work_item_draft_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / ".entroping" / "work-item-draft.json",
        )


def test_work_item_draft_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        work_item_draft,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(work_item_draft.WorkItemDraftError, match="contains secret-like content"):
        work_item_draft.run_work_item_draft_report(project_root=tmp_path, output="json")


def test_work_item_draft_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(work_item_draft, "safe_write_text", fail_write)

    with pytest.raises(work_item_draft.WorkItemDraftError, match="blocked write"):
        work_item_draft.run_work_item_draft_report(project_root=tmp_path, output="json")


def test_work_item_draft_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(work_item_draft.WorkItemDraftError, match="Unsupported"):
        work_item_draft.run_work_item_draft_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_work_item_draft_defensive_source_fallbacks(tmp_path: Path) -> None:
    source, document = work_item_draft._source_from_index(
        "evidence-action-plan-json",
        None,
        root=tmp_path,
    )

    assert document is None
    assert source.label == "Evidence Action Plan"
    assert source.path == "reports/evidence-action-plan.json"
    assert work_item_draft._source_label("unknown-json") == "unknown-json"  # type: ignore[arg-type]
    assert work_item_draft._state_from_load_error("schema mismatch") == "invalid"


@pytest.mark.parametrize(
    "load_error",
    [
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    ],
)
def test_work_item_draft_unsafe_load_errors_remain_unsafe(load_error: str) -> None:
    assert work_item_draft._state_from_load_error(load_error) == "unsafe"
