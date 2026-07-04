"""Tests for local PR evidence cards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entroping.core.evidence.pr_evidence_card as pr_evidence_card
from entroping.core.evidence.pr_evidence_card import (
    PR_EVIDENCE_CARD_SCHEMA_VERSION,
    PrEvidenceCardError,
    PrEvidenceCardSummaryError,
    build_pr_evidence_card_packet,
    render_pr_evidence_card_markdown,
    run_pr_evidence_card_report,
    run_pr_evidence_card_summary_report,
)
from entroping.core.safe_write import SafeWriteError

_SOURCE_SCHEMAS: dict[str, str] = {
    "runtime-card-json": "entroping.runtime-card.v1",
    "evidence-bundle-json": "entroping.evidence-bundle.v1",
    "test-pyramid-json": "entroping.test-pyramid-report.v1",
    "mutation-readiness-json": "entroping.mutation-readiness.v1",
    "observability-packet-json": "entroping.observability-packet.v1",
    "integration-readiness-json": "entroping.integration-readiness.v1",
    "devex-readiness-json": "entroping.devex-readiness.v1",
    "connector-intent-json": "entroping.connector-intent.v1",
    "handoff-json": "entroping.handoff.v1",
    "evidence-cloud-dashboard-json": "entroping.evidence-cloud-dashboard.v1",
    "evidence-index-json": "entroping.evidence-index.v1",
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _artifact(schema_version: str, status: str, raw_marker: str) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
        "summary": {
            "status": status,
            "targets_ready": 2,
            "targets_blocked": 0,
            "next_actions_total": 0,
        },
        "raw_marker": raw_marker,
    }


def _write_source_artifact(
    root: Path,
    source_id: str,
    *,
    status: str = "ready",
    include_summary: bool = True,
) -> None:
    payload: dict[str, object] = {
        "schema_version": _SOURCE_SCHEMAS[source_id],
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": "checkout-api",
    }
    if include_summary:
        payload["summary"] = {"status": status}
    report_name = source_id.removesuffix("-json")
    _write_json(root / "reports" / f"{report_name}.json", payload)


def test_pr_evidence_card_writes_value_free_json_from_local_artifacts(
    tmp_path: Path,
) -> None:
    raw_marker = "raw PR implementation detail must not render"
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        _artifact("entroping.runtime-card.v1", "pass", raw_marker),
    )
    _write_json(
        tmp_path / "reports" / "evidence-cloud-dashboard.json",
        _artifact("entroping.evidence-cloud-dashboard.v1", "ready", raw_marker),
    )

    result = run_pr_evidence_card_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "pr-evidence-card.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == PR_EVIDENCE_CARD_SCHEMA_VERSION
    assert payload["project"] == "checkout-api"
    assert payload["summary"]["status"] == "partial"
    assert payload["summary"]["sources_present"] == 2
    checklist = {item["id"]: item for item in payload["checklist"]}
    assert checklist["runtime-governance"]["state"] == "ready"
    assert checklist["evidence-cloud"]["state"] == "ready"
    assert checklist["test-pyramid"]["state"] == "blocked"
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["runtime-card-json"]["sha256"]
    assert raw_marker not in json.dumps(payload)


def test_pr_evidence_card_reports_ready_when_all_sources_are_ready(
    tmp_path: Path,
) -> None:
    for source_id in _SOURCE_SCHEMAS:
        _write_source_artifact(tmp_path, source_id)

    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    markdown = render_pr_evidence_card_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.sources_present == len(_SOURCE_SCHEMAS)
    assert packet.summary.checklist_ready == len(_SOURCE_SCHEMAS)
    assert packet.summary.next_actions_total == 0
    assert "- No PR evidence-card actions are currently needed." in markdown


def test_pr_evidence_card_surfaces_attention_checklist_actions(
    tmp_path: Path,
) -> None:
    _write_source_artifact(tmp_path, "runtime-card-json", include_summary=False)

    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    checklist = {item.id: item for item in packet.checklist}

    assert checklist["runtime-governance"].state == "attention"
    assert any(
        action.priority == "low"
        and action.action
        == "Review Runtime governance attention state before merge."
        for action in packet.next_actions
    )


def test_pr_evidence_card_markdown_is_review_ready_and_value_free(tmp_path: Path) -> None:
    raw_marker = "free-form <script>alert(1)</script>"
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        _artifact("entroping.runtime-card.v1", "fail", raw_marker),
    )

    markdown = render_pr_evidence_card_markdown(
        build_pr_evidence_card_packet(project_root=tmp_path)
    )

    assert markdown.startswith("# Entroping PR Evidence Card")
    assert "| Runtime governance | blocked |" in markdown
    assert "Deterministic local PR review card" in markdown
    assert raw_marker not in markdown
    assert "<script" not in markdown.lower()
    assert "https://" not in markdown


def test_pr_evidence_card_markdown_escapes_inline_code_breakouts(
    tmp_path: Path,
) -> None:
    payload = _artifact("entroping.runtime-card.v1", "pass", "value-free")
    payload["project"] = "checkout`api"
    _write_json(tmp_path / "reports" / "runtime-card.json", payload)

    markdown = render_pr_evidence_card_markdown(
        build_pr_evidence_card_packet(project_root=tmp_path)
    )

    assert "checkout`api" not in markdown
    assert "checkout&#96;api" in markdown


@pytest.mark.parametrize(
    "secret_like_value",
    (
        "ghp_" + "abcdefghijklmnopqrstuvwxyz123456",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "sk-proj-" + ("a" * 24),
    ),
)
def test_pr_evidence_card_marks_secret_like_sources_unsafe(
    tmp_path: Path,
    secret_like_value: str,
) -> None:
    _write_json(
        tmp_path / "reports" / "runtime-card.json",
        _artifact("entroping.runtime-card.v1", "pass", secret_like_value),
    )

    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    markdown = render_pr_evidence_card_markdown(packet)

    runtime_source = {source.id: source for source in packet.sources}["runtime-card-json"]
    assert runtime_source.state == "unsafe"
    assert runtime_source.summary == "secret-like content"
    assert secret_like_value not in packet.model_dump_json()
    assert secret_like_value not in markdown


def test_pr_evidence_card_marks_secondary_read_failures_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source_artifact(tmp_path, "runtime-card-json")
    monkeypatch.setattr(
        pr_evidence_card,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (None, "not a file"),
    )

    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    runtime_source = {source.id: source for source in packet.sources}["runtime-card-json"]

    assert runtime_source.state == "unsafe"
    assert runtime_source.summary == "not a file"


def test_pr_evidence_card_marks_secondary_invalid_json_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source_artifact(tmp_path, "runtime-card-json")
    monkeypatch.setattr(
        pr_evidence_card,
        "read_local_evidence_json_artifact_bytes",
        lambda *_args, **_kwargs: (b"{not json", ""),
    )

    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    runtime_source = {source.id: source for source in packet.sources}["runtime-card-json"]

    assert runtime_source.state == "invalid"
    assert runtime_source.summary == "invalid JSON"


def test_pr_evidence_card_writes_markdown_by_default(tmp_path: Path) -> None:
    result = run_pr_evidence_card_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "pr-evidence-card.md"
    assert result.output_path.read_text(encoding="utf-8").startswith(
        "# Entroping PR Evidence Card"
    )


def test_pr_evidence_card_rejects_output_outside_project(tmp_path: Path) -> None:
    with pytest.raises(PrEvidenceCardError, match="must stay under the project root"):
        run_pr_evidence_card_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "pr-evidence-card.json",
        )


def test_pr_evidence_card_rejects_output_under_forbidden_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(PrEvidenceCardError, match="must not be written"):
        run_pr_evidence_card_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "pr-evidence-card.json",
        )


def test_pr_evidence_card_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pr_evidence_card,
        "_render_packet_content",
        lambda *_args, **_kwargs: "sk-proj-" + ("a" * 24),
    )

    with pytest.raises(PrEvidenceCardError, match="contains secret-like content"):
        run_pr_evidence_card_report(project_root=tmp_path, output="json")


def test_pr_evidence_card_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(pr_evidence_card, "safe_write_text", fail_write)

    with pytest.raises(PrEvidenceCardError, match="blocked write"):
        run_pr_evidence_card_report(project_root=tmp_path, output="json")


def test_pr_evidence_card_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(PrEvidenceCardError, match="Unsupported"):
        run_pr_evidence_card_report(
            project_root=tmp_path,
            output="html",  # type: ignore[arg-type]
        )


def test_pr_evidence_card_summary_report_renders_markdown(tmp_path: Path) -> None:
    for source_id in _SOURCE_SCHEMAS:
        _write_source_artifact(tmp_path, source_id)
    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(packet.model_dump_json(), encoding="utf-8")

    result = run_pr_evidence_card_summary_report(project_root=tmp_path)

    assert result.artifact_path == artifact_path
    assert "# Entroping PR Evidence Card Summary" in result.summary_markdown
    assert "## Sources" in result.summary_markdown
    assert "## Checks" in result.summary_markdown
    assert "- No PR evidence-card actions are currently needed." in result.summary_markdown


def test_pr_evidence_card_summary_report_renders_actions(tmp_path: Path) -> None:
    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(packet.model_dump_json(), encoding="utf-8")

    result = run_pr_evidence_card_summary_report(project_root=tmp_path)

    assert "**medium**" in result.summary_markdown
    assert (
        "Generate Runtime Card JSON before using the PR evidence card."
        in result.summary_markdown
    )


def test_pr_evidence_card_summary_report_rejects_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(
        PrEvidenceCardSummaryError,
        match="Could not read PR evidence-card artifact",
    ):
        run_pr_evidence_card_summary_report(project_root=tmp_path)


def test_pr_evidence_card_summary_report_rejects_wrong_schema(tmp_path: Path) -> None:
    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.runtime-card.v1",
                "generated_at": "2026-01-01T00:00:00Z",
                "project": "checkout-api",
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(PrEvidenceCardSummaryError, match="unexpected schema"):
        run_pr_evidence_card_summary_report(project_root=tmp_path)


def test_pr_evidence_card_summary_report_rejects_non_utf8_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"\xff")

    with pytest.raises(PrEvidenceCardSummaryError, match="non-UTF-8 content"):
        run_pr_evidence_card_summary_report(project_root=tmp_path)


def test_pr_evidence_card_summary_report_rejects_invalid_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PrEvidenceCardSummaryError, match="does not contain valid JSON"):
        run_pr_evidence_card_summary_report(project_root=tmp_path)


def test_pr_evidence_card_summary_report_rejects_secret_like_content(tmp_path: Path) -> None:
    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    packet_payload = packet.model_dump()
    packet_payload["project"] = "ghp_" + ("a" * 24)

    artifact_path = tmp_path / "reports" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(packet_payload), encoding="utf-8")

    with pytest.raises(PrEvidenceCardSummaryError, match="secret-like"):
        run_pr_evidence_card_summary_report(project_root=tmp_path)


def test_pr_evidence_card_defensive_source_fallbacks(tmp_path: Path) -> None:
    source, document = pr_evidence_card._source_from_index(
        "runtime-card-json",
        None,
        root=tmp_path,
    )

    assert document is None
    assert source.label == "Runtime governance"
    assert source.path == "reports/runtime-card.json"
    assert pr_evidence_card._source_label("unknown-json") == "unknown-json"  # type: ignore[arg-type]
    assert pr_evidence_card._state_from_load_error("schema mismatch") == "invalid"
