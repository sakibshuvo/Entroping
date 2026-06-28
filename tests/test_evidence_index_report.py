"""Tests for schema-versioned local evidence index reports."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.evidence.evidence_index_report import (
    EVIDENCE_INDEX_SCHEMA_VERSION,
    EvidenceIndexError,
    build_evidence_index_packet,
    render_evidence_index_markdown,
    run_evidence_index_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def test_evidence_index_report_writes_valid_json_when_all_artifacts_are_missing(
    tmp_path: Path,
) -> None:
    result = run_evidence_index_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "evidence-index.json"
    assert payload["schema_version"] == EVIDENCE_INDEX_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["artifacts_total"] == len(payload["artifacts"])
    assert payload["summary"]["artifacts_present"] == 0
    assert payload["summary"]["artifacts_missing"] == payload["summary"]["artifacts_total"]
    assert payload["summary"]["artifacts_invalid"] == 0
    assert payload["summary"]["artifacts_unsafe"] == 0
    assert {artifact["state"] for artifact in payload["artifacts"]} == {"missing"}


def test_evidence_index_report_writes_value_free_markdown_from_existing_index(
    tmp_path: Path,
) -> None:
    secret_marker = _provider_token_fixture()
    _write_json(
        tmp_path / "reports" / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
            "tests": [{"stderr": f"Authorization: Bearer {secret_marker}"}],
        },
    )

    result = run_evidence_index_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert result.output_path == tmp_path / "reports" / "evidence-index.md"
    assert "# Entroping Evidence Index" in markdown
    assert "- Status: `partial`" in markdown
    assert "| run-json | Run JSON | present | reports/run-latest.json |" in markdown
    assert "2 total, 1 passed, 1 failed" in markdown
    assert secret_marker not in markdown


def test_evidence_index_report_preserves_invalid_and_unsafe_source_states(
    tmp_path: Path,
) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    outside = tmp_path.parent / "outside-run-latest.json"
    raw_target_marker = "raw-target-never-read"
    outside.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "summary": {"status": raw_target_marker},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "run-latest.json").symlink_to(outside)
    (reports_dir / "drift.json").write_text("{not-json\n", encoding="utf-8")

    packet = build_evidence_index_packet(project_root=tmp_path)
    by_id = {artifact.id: artifact for artifact in packet.artifacts}

    assert packet.summary.status == "partial"
    assert packet.summary.artifacts_invalid == 1
    assert packet.summary.artifacts_unsafe == 1
    assert by_id["run-json"].state == "unsafe"
    assert by_id["run-json"].summary == "symlinked path component"
    assert by_id["drift-json"].state == "invalid"
    assert by_id["drift-json"].summary == "invalid JSON"
    assert raw_target_marker not in packet.model_dump_json()


def test_evidence_index_markdown_escapes_table_cells() -> None:
    packet = build_evidence_index_packet(project_root=Path("."))
    escaped = packet.model_copy(
        update={
            "artifacts": (
                packet.artifacts[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "summary": "line one\nline two | `cell`",
                    }
                ),
            )
        }
    )

    markdown = render_evidence_index_markdown(escaped)

    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "&#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_evidence_index_markdown_escapes_project_inline_code() -> None:
    packet = build_evidence_index_packet(project_root=Path("."))
    escaped = packet.model_copy(update={"project": "project `tick`"})

    markdown = render_evidence_index_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown


def test_evidence_index_report_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "evidence-index.json"

    result = run_evidence_index_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EVIDENCE_INDEX_SCHEMA_VERSION


def test_evidence_index_report_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(EvidenceIndexError, match="Unsupported evidence-index output"):
        run_evidence_index_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )


def test_evidence_index_report_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceIndexError, match="path must stay under"):
        run_evidence_index_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "evidence-index.json",
        )


def test_evidence_index_report_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.evidence.evidence_index_report as evidence_index_report

    def fake_index(*, project_root: Path) -> tuple[LocalEvidenceArtifact, ...]:
        _ = project_root
        return (
            LocalEvidenceArtifact(
                id="run-json",
                label="Run JSON",
                path="reports/run-latest.json",
                state="present",
                schema_version="entroping.run-report.v1",
                summary=f"token {_provider_token_fixture()} leaked",
            ),
        )

    monkeypatch.setattr(evidence_index_report, "build_local_evidence_index", fake_index)

    with pytest.raises(EvidenceIndexError, match="contains secret-like content"):
        run_evidence_index_report(project_root=tmp_path, output="md")
