"""Tests for local work item import bundles."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import entroping.core.export.work_item_import_bundle as work_item_import_bundle
from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.safe_write import SafeWriteError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _count_as_int(value: object) -> int:
    assert isinstance(value, int | str)
    return int(value)


def _draft_item(
    *,
    item_id: str = "work-item-draft:001",
    priority: str = "high",
    title: str = "Review blocked evidence before merge.",
    summary: str = "Draft tracker row for review evidence action with blocked status.",
    target_systems: list[str] | None = None,
    source_action_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": item_id,
        "category": "draft",
        "priority": priority,
        "title": title,
        "summary": summary,
        "target_systems": target_systems or ["jira", "linear"],
        "source_ids": ["evidence-action-plan-json"],
        "source_action_ids": source_action_ids or ["evidence-action-plan:001"],
        "source_action_count": len(source_action_ids or ["evidence-action-plan:001"]),
        "forbidden_actions": [
            "call_external_api",
            "mutate_issue_tracker",
            "post_chat_message",
            "execute_chat_command",
            "upload_artifacts",
            "invoke_model_provider",
            "execute_hurl",
            "run_tests",
            "read_provider_keys",
            "parse_raw_traffic",
            "render_raw_artifact_contents",
        ],
        "status": "partial",
    }


def _draft_packet(
    *,
    items: list[dict[str, object]] | None = None,
    raw_marker: str = "raw work item draft detail must not render",
) -> dict[str, object]:
    item_rows = items if items is not None else [_draft_item()]
    return {
        "schema_version": "entroping.work-item-draft.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": "partial",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "items_total": len(item_rows),
            "items_high": sum(1 for item in item_rows if item["priority"] == "high"),
            "items_medium": sum(1 for item in item_rows if item["priority"] == "medium"),
            "items_low": sum(1 for item in item_rows if item["priority"] == "low"),
            "source_action_count": sum(
                _count_as_int(item["source_action_count"]) for item in item_rows
            ),
        },
        "sources": [],
        "items": item_rows,
        "raw_marker": raw_marker,
    }


def test_work_item_import_bundle_writes_json_rows_from_draft(
    tmp_path: Path,
) -> None:
    raw_marker = "raw tracker import payload must not render"
    _write_json(
        tmp_path / "reports" / "work-item-draft.json",
        _draft_packet(raw_marker=raw_marker),
    )

    result = work_item_import_bundle.run_work_item_import_bundle_report(
        project_root=tmp_path, output="json"
    )

    assert result.output_path == tmp_path / "reports" / "work-item-import-bundle.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert (
        payload["schema_version"] == work_item_import_bundle.WORK_ITEM_IMPORT_BUNDLE_SCHEMA_VERSION
    )
    assert (
        payload["csv_contract_version"]
        == work_item_import_bundle.WORK_ITEM_IMPORT_CSV_CONTRACT_VERSION
    )
    assert payload["csv_columns"] == list(work_item_import_bundle.WORK_ITEM_IMPORT_CSV_COLUMNS)
    assert payload["summary"]["status"] == "partial"
    assert payload["summary"]["sources_present"] == 1
    assert payload["summary"]["rows_total"] == 2
    assert payload["summary"]["actions_total"] == 0
    assert any(
        row["tracker_family"] == "jira"
        and row["external_id"] == "entroping-work-item-draft-001-jira"
        and row["title"] == "Review blocked evidence before merge."
        and row["priority"] == "high"
        and row["source_action_ids"] == ["evidence-action-plan:001"]
        and row["source_action_count"] == 1
        and "priority-high" in row["labels"]
        and "mutate_issue_tracker" in row["forbidden_actions"]
        for row in payload["rows"]
    )
    assert raw_marker not in json.dumps(payload)


def test_work_item_import_bundle_writes_spreadsheet_safe_csv(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "work-item-draft.json",
        _draft_packet(
            items=[
                _draft_item(
                    title='=HYPERLINK("https://example.test","open")',
                    summary="+cmd|' /C calc'!A0",
                    target_systems=["github_issues"],
                )
            ],
        ),
    )

    result = work_item_import_bundle.run_work_item_import_bundle_report(
        project_root=tmp_path, output="csv"
    )

    reader = csv.DictReader(result.output_path.read_text(encoding="utf-8").splitlines())
    rows = list(reader)
    assert result.output_path == tmp_path / "reports" / "work-item-import-bundle.csv"
    assert reader.fieldnames == list(work_item_import_bundle.WORK_ITEM_IMPORT_CSV_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["record_type"] == "import_row"
    assert rows[0]["tracker_family"] == "github_issues"
    assert rows[0]["title"].startswith("'=")
    assert rows[0]["body"].startswith("'+")
    assert rows[0]["forbidden_actions"].startswith("call_external_api")


def test_work_item_import_bundle_missing_source_yields_generation_action(
    tmp_path: Path,
) -> None:
    packet = work_item_import_bundle.build_work_item_import_bundle(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 1
    assert packet.summary.rows_total == 0
    assert packet.summary.actions_medium == 1
    assert packet.actions[0].category == "generate"
    assert packet.actions[0].action == (
        "Generate Work Item Draft before building tracker import bundle."
    )


def test_work_item_import_bundle_writes_missing_source_action_csv(tmp_path: Path) -> None:
    result = work_item_import_bundle.run_work_item_import_bundle_report(
        project_root=tmp_path, output="csv"
    )

    reader = csv.DictReader(result.output_path.read_text(encoding="utf-8").splitlines())
    rows = list(reader)
    assert reader.fieldnames == list(work_item_import_bundle.WORK_ITEM_IMPORT_CSV_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["record_type"] == "action"
    assert rows[0]["external_id"] == ""
    assert rows[0]["source_item_ids"] == ""
    assert rows[0]["source_action_ids"] == ""
    assert rows[0]["source_action_count"] == "0"
    assert rows[0]["priority"] == "medium"
    assert rows[0]["title"] == ("Generate Work Item Draft before building tracker import bundle.")


def test_work_item_import_bundle_marks_secret_like_source_unsafe(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "work-item-draft.json",
        _draft_packet(raw_marker="sk-proj-" + ("a" * 24)),
    )

    packet = work_item_import_bundle.build_work_item_import_bundle(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.sources[0].state == "unsafe"
    assert packet.actions[0].priority == "high"
    assert packet.actions[0].category == "repair"


def test_work_item_import_bundle_marks_invalid_json_invalid(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reports" / "work-item-draft.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    packet = work_item_import_bundle.build_work_item_import_bundle(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.sources[0].state == "invalid"
    assert packet.actions[0].priority == "high"
    assert packet.actions[0].status == "invalid"


def test_work_item_import_bundle_source_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_source, missing_document = work_item_import_bundle._source_from_index(
        None,
        root=tmp_path,
    )

    assert missing_source.path == "reports/work-item-draft.json"
    assert missing_source.summary == "not indexed"
    assert missing_document is None

    artifact = LocalEvidenceArtifact(
        id="work-item-draft-json",
        label="Work Item Draft JSON",
        path="reports/work-item-draft.json",
        state="present",
        schema_version="entroping.work-item-draft.v1",
        summary="partial",
    )
    monkeypatch.setattr(
        work_item_import_bundle,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "not a file"),
    )

    unsafe_source, document = work_item_import_bundle._source_from_index(
        artifact,
        root=tmp_path,
    )

    assert unsafe_source.state == "unsafe"
    assert unsafe_source.summary == "not a file"
    assert document is None


def test_work_item_import_bundle_marks_loaded_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = LocalEvidenceArtifact(
        id="work-item-draft-json",
        label="Work Item Draft JSON",
        path="reports/work-item-draft.json",
        state="present",
        schema_version="entroping.work-item-draft.v1",
        summary="partial",
    )
    monkeypatch.setattr(
        work_item_import_bundle,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{not json", ""),
    )

    source, document = work_item_import_bundle._source_from_index(artifact, root=tmp_path)

    assert source.state == "invalid"
    assert source.summary == "invalid JSON"
    assert source.sha256 is None
    assert document is None


def test_work_item_import_bundle_rows_ignore_malformed_or_secret_items() -> None:
    source = work_item_import_bundle.WorkItemImportSource(
        id="work-item-draft-json",
        label="Work Item Draft",
        path="reports/work-item-draft.json",
        state="present",
        schema_version="entroping.work-item-draft.v1",
        sha256="a" * 64,
        summary="partial",
        status="partial",
    )

    assert (
        work_item_import_bundle._rows_from_document(
            source=source,
            document={"items": {"not": "a list"}},
        )
        == ()
    )
    rows = work_item_import_bundle._rows_from_document(
        source=source,
        document={
            "items": [
                [],
                {"id": "missing-title"},
                {"id": "", "title": "empty id"},
                {"id": "sk-proj-" + ("a" * 24), "title": "secret id"},
                {"id": "safe", "title": "sk-proj-" + ("a" * 24)},
            ]
        },
    )

    assert rows == ()


def test_work_item_import_bundle_row_fallbacks_cover_low_and_default_priority() -> None:
    low_rows = work_item_import_bundle._rows_from_item(
        {
            "id": "work-item-draft:002",
            "title": "Low priority import row.",
            "summary": 42,
            "priority": "low",
            "source_action_ids": "not a list",
            "target_systems": "not a list",
        }
    )
    default_rows = work_item_import_bundle._rows_from_item(
        {
            "id": "work-item-draft:003",
            "title": "Default priority import row.",
            "priority": "urgent",
            "target_systems": ["not-supported", "linear"],
        }
    )

    assert len(low_rows) == 5
    assert low_rows[0].priority == "low"
    assert low_rows[0].source_action_ids == ()
    assert "Draft row from Entroping evidence." in low_rows[0].body
    assert len(default_rows) == 1
    assert default_rows[0].priority == "medium"
    assert default_rows[0].tracker_family == "linear"


def test_work_item_import_bundle_status_ready_and_partial_branches() -> None:
    ready_source = work_item_import_bundle.WorkItemImportSource(
        id="work-item-draft-json",
        label="Work Item Draft",
        path="reports/work-item-draft.json",
        state="present",
        schema_version="entroping.work-item-draft.v1",
        sha256="a" * 64,
        summary="ready",
        status="ready",
    )
    partial_source = ready_source.model_copy(update={"status": None})
    high_action = work_item_import_bundle.WorkItemImportAction(
        priority="high",
        category="repair",
        action="Repair Work Item Draft before building tracker import bundle.",
        source_ids=("work-item-draft-json",),
        status="invalid",
    )
    medium_action = high_action.model_copy(update={"priority": "medium"})

    assert work_item_import_bundle._status(source=ready_source, rows=(), actions=()) == "ready"
    assert work_item_import_bundle._status(source=partial_source, rows=(), actions=()) == "partial"
    assert (
        work_item_import_bundle._status(
            source=ready_source,
            rows=(),
            actions=(high_action,),
        )
        == "insufficient"
    )
    assert (
        work_item_import_bundle._status(
            source=ready_source,
            rows=(),
            actions=(medium_action,),
        )
        == "partial"
    )


def test_work_item_import_bundle_defensive_helpers(tmp_path: Path) -> None:
    assert work_item_import_bundle._parse_document("[]") is None
    assert work_item_import_bundle._document_status({"summary": {"status": ""}}) is None
    assert work_item_import_bundle._state_from_load_error("schema mismatch") == "invalid"
    assert work_item_import_bundle._state_from_load_error("unreadable") == "unsafe"
    assert (
        work_item_import_bundle._project_from_document(root=tmp_path, document={}) == tmp_path.name
    )


def test_work_item_import_bundle_rejects_output_outside_project(tmp_path: Path) -> None:
    with pytest.raises(
        work_item_import_bundle.WorkItemImportBundleError, match="must stay under the project root"
    ):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "work-item-import-bundle.json",
        )


def test_work_item_import_bundle_rejects_nested_forbidden_output_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        work_item_import_bundle.WorkItemImportBundleError, match="must not be written"
    ):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / ".entroping" / "work-item-import-bundle.json",
        )


def test_work_item_import_bundle_rejects_case_variant_forbidden_output_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        work_item_import_bundle.WorkItemImportBundleError, match="must not be written"
    ):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / ".Entroping" / "work-item-import-bundle.json",
        )


def test_work_item_import_bundle_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        work_item_import_bundle,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(
        work_item_import_bundle.WorkItemImportBundleError, match="secret-like content"
    ):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path, output="json"
        )


def test_work_item_import_bundle_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(work_item_import_bundle, "safe_write_text", fail_write)

    with pytest.raises(work_item_import_bundle.WorkItemImportBundleError, match="blocked write"):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path, output="json"
        )


def test_work_item_import_bundle_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(work_item_import_bundle.WorkItemImportBundleError, match="Unsupported"):
        work_item_import_bundle.run_work_item_import_bundle_report(
            project_root=tmp_path,
            output="md",  # type: ignore[arg-type]
        )
