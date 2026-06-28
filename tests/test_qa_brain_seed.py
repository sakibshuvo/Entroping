"""Tests for deterministic QA brain seed packets."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from entroping.core.evidence.evidence_index import LocalEvidenceArtifact
from entroping.core.plan.qa_brain_seed import (
    QA_BRAIN_SEED_SCHEMA_VERSION,
    QaBrainSeedError,
    build_qa_brain_seed,
    render_qa_brain_seed_markdown,
    run_qa_brain_seed_report,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def test_qa_brain_seed_writes_valid_json_when_all_evidence_is_missing(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_seed_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-seed.json"
    assert payload["schema_version"] == QA_BRAIN_SEED_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["sources_total"] == len(payload["sources"])
    assert payload["summary"]["sources_present"] == 0
    assert payload["summary"]["sources_missing"] == payload["summary"]["sources_total"]
    assert payload["summary"]["eval_slices_total"] == len(payload["eval_slices"])
    assert payload["summary"]["eval_slices_ready"] == 0
    assert {source["state"] for source in payload["sources"]} == {"missing"}
    assert {slice_["id"] for slice_ in payload["eval_slices"]} == {
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    }


def test_qa_brain_seed_classifies_value_free_evidence_without_raw_values(
    tmp_path: Path,
) -> None:
    secret_marker = _provider_token_fixture()
    reports = tmp_path / "reports"
    _write_json(
        reports / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
            "tests": [{"stderr": f"Authorization: Bearer {secret_marker}"}],
        },
    )
    _write_json(
        reports / "gate-coverage.json",
        {"schema_version": "entroping.gate-coverage-report.v1", "summary": {}},
    )
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1},
        },
    )
    _write_json(
        reports / "capture-summary.json",
        {
            "schema_version": "entroping.capture-summary.v1",
            "summary": {
                "total_records": 3,
                "redacted_records": 3,
                "unredacted_records": 0,
            },
        },
    )
    _write_json(
        reports / "api-inventory.json",
        {"schema_version": "entroping.api-inventory.v1", "summary": {}},
    )
    _write_json(
        reports / "mutation-readiness.json",
        {"schema_version": "entroping.mutation-readiness.v1", "summary": {}},
    )

    packet = build_qa_brain_seed(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    slices = {slice_.id: slice_ for slice_ in packet.eval_slices}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert sources["run-json"].category == "runtime_governance"
    assert sources["test-quality-json"].category == "generated_test_quality"
    assert sources["api-inventory-json"].category == "api_inventory"
    assert sources["mutation-readiness-json"].category == "mutation_fuzz"
    assert sources["capture-summary-json"].category == "redaction_safety"
    assert slices["weak_test_detection"].status == "ready"
    assert "test-quality-json" in slices["weak_test_detection"].source_ids
    assert slices["api_drift_reasoning"].status == "ready"
    assert "api-inventory-json" in slices["api_drift_reasoning"].source_ids
    assert slices["mutation_fuzz_readiness"].status == "ready"
    assert secret_marker not in rendered


def test_qa_brain_seed_preserves_invalid_and_unsafe_evidence_states(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    outside = tmp_path.parent / "outside-run-latest.json"
    outside.write_text(
        '{"schema_version":"entroping.run-report.v1","summary":{"total":999}}\n',
        encoding="utf-8",
    )
    (reports / "run-latest.json").symlink_to(outside)
    (reports / "drift.json").write_text("{not-json\n", encoding="utf-8")
    _write_json(
        reports / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "summary": {"status": "incomplete"},
        },
    )

    packet = build_qa_brain_seed(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}
    slices = {slice_.id: slice_ for slice_ in packet.eval_slices}

    assert packet.summary.status == "partial"
    assert packet.summary.sources_invalid == 1
    assert packet.summary.sources_unsafe == 1
    assert sources["run-json"].state == "unsafe"
    assert sources["run-json"].summary == "symlinked path component"
    assert sources["drift-json"].state == "invalid"
    assert sources["artifact-manifest-json"].category == "cross_surface_handoff"
    assert slices["bogus_evidence"].status == "attention"
    assert slices["bogus_evidence"].source_ids == (
        "artifact-manifest-json",
        "run-json",
        "drift-json",
    )
    assert next(
        action for action in packet.next_actions if action.action.endswith("Bogus evidence.")
    ).source_ids == slices["bogus_evidence"].source_ids
    assert "999" not in packet.model_dump_json()


def test_qa_brain_seed_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1},
        },
    )

    result = run_qa_brain_seed_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Seed" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown
    assert (
        "| test-quality-json | Generated-Test Quality JSON | generated_test_quality | "
        "present |"
    ) in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_seed_markdown_escapes_table_cells_and_inline_code() -> None:
    packet = build_qa_brain_seed(project_root=Path("."))
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "sources": (
                packet.sources[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "summary": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_seed_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_seed_reports_ready_when_all_eval_slices_have_present_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_seed as qa_brain_seed

    source_ids = (
        "test-quality-json",
        "gate-coverage-json",
        "artifact-manifest-json",
        "capture-summary-json",
        "api-inventory-json",
        "mutation-readiness-json",
        "handoff-json",
    )

    def fake_index(*, project_root: Path) -> tuple[LocalEvidenceArtifact, ...]:
        _ = project_root
        return tuple(
            LocalEvidenceArtifact(
                id=source_id,
                label=source_id.replace("-", " ").title(),
                path=f"reports/{source_id}.json",
                state="present",
                schema_version="entroping.fixture.v1",
                summary="fixture present",
            )
            for source_id in source_ids
        )

    monkeypatch.setattr(qa_brain_seed, "build_local_evidence_index", fake_index)

    packet = build_qa_brain_seed(project_root=tmp_path)
    markdown = render_qa_brain_seed_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.eval_slices_ready == packet.summary.eval_slices_total
    assert packet.next_actions == ()
    assert "No QA brain seed actions are currently needed." in markdown


def test_qa_brain_seed_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(QaBrainSeedError, match="Unsupported qa-brain-seed output"):
        run_qa_brain_seed_report(project_root=tmp_path, output=cast(Any, "html"))


def test_qa_brain_seed_rejects_output_paths_outside_project(tmp_path: Path) -> None:
    with pytest.raises(QaBrainSeedError, match="path must stay under"):
        run_qa_brain_seed_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-seed.json",
        )


def test_qa_brain_seed_writes_custom_output_path_inside_project(tmp_path: Path) -> None:
    output_path = tmp_path / "custom" / "qa-brain-seed.json"

    result = run_qa_brain_seed_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == QA_BRAIN_SEED_SCHEMA_VERSION


@pytest.mark.parametrize("output", ("md", "json"))
def test_qa_brain_seed_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    import entroping.core.plan.qa_brain_seed as qa_brain_seed

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

    monkeypatch.setattr(qa_brain_seed, "build_local_evidence_index", fake_index)

    with pytest.raises(QaBrainSeedError, match="contains secret-like content"):
        run_qa_brain_seed_report(project_root=tmp_path, output=cast(Any, output))
