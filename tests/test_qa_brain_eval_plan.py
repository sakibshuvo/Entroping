"""Tests for deterministic QA brain eval-plan packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from entroping.core.plan.qa_brain_eval_plan import (
    QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
    QaBrainEvalPlanError,
    build_qa_brain_eval_plan,
    render_qa_brain_eval_plan_markdown,
    run_qa_brain_eval_plan_report,
)
from entroping.core.plan.qa_brain_seed import (
    QA_BRAIN_SEED_SCHEMA_VERSION,
    QaBrainEvalSlice,
    QaBrainNextAction,
    QaBrainSeedError,
    QaBrainSeedPacket,
    QaBrainSeedSummary,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def test_qa_brain_eval_plan_writes_valid_json_without_prior_seed_report(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_eval_plan_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-eval-plan.json"
    assert not (tmp_path / "reports" / "qa-brain-seed.json").exists()
    assert payload["schema_version"] == QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION
    assert payload["seed_schema_version"] == QA_BRAIN_SEED_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["cases_total"] == len(payload["cases"])
    assert payload["summary"]["cases_ready"] == 0
    assert payload["summary"]["cases_missing"] == payload["summary"]["cases_total"]
    assert {case["id"] for case in payload["cases"]} == {
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    }


def test_qa_brain_eval_plan_derives_ready_cases_without_raw_values(
    tmp_path: Path,
) -> None:
    secret_marker = _provider_token_fixture()
    reports = tmp_path / "reports"
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
            "tests": [{"stderr": f"Authorization: Bearer {secret_marker}"}],
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

    packet = build_qa_brain_eval_plan(project_root=tmp_path)
    cases = {case.id: case for case in packet.cases}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert cases["weak_test_detection"].readiness == "ready"
    assert "test-quality-json" in cases["weak_test_detection"].source_ids
    assert cases["api_drift_reasoning"].readiness == "ready"
    assert "api-inventory-json" in cases["api_drift_reasoning"].source_ids
    assert cases["mutation_fuzz_readiness"].readiness == "ready"
    assert cases["weak_test_detection"].input_contract.startswith("Value-free")
    assert "schema-valid" in cases["weak_test_detection"].output_contract
    assert "secret" in cases["redaction_mistakes"].negative_controls[0].lower()
    assert secret_marker not in rendered


def test_qa_brain_eval_plan_preserves_attention_sources_and_next_actions(
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

    packet = build_qa_brain_eval_plan(project_root=tmp_path)
    cases = {case.id: case for case in packet.cases}

    assert packet.summary.status == "partial"
    assert packet.summary.cases_attention == 2
    assert cases["bogus_evidence"].readiness == "attention"
    assert cases["bogus_evidence"].source_ids == (
        "artifact-manifest-json",
        "run-json",
        "drift-json",
    )
    assert next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    ).priority == "high"
    assert "999" not in packet.model_dump_json()


def test_qa_brain_eval_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_eval_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Eval Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown
    assert "schema-valid" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_eval_plan_markdown_escapes_table_cells_and_inline_code() -> None:
    packet = build_qa_brain_eval_plan(project_root=Path("."))
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "cases": (
                packet.cases[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "input_contract": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_eval_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_eval_plan_reports_ready_when_all_cases_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_eval_plan as qa_brain_eval_plan

    eval_ids = (
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    )

    def fake_seed(*, project_root: Path) -> QaBrainSeedPacket:
        _ = project_root
        slices = tuple(
            QaBrainEvalSlice(
                id=cast(Any, eval_id),
                label=eval_id.replace("_", " ").title(),
                status="ready",
                source_ids=(f"{eval_id}-source",),
                source_paths=(f"reports/{eval_id}.json",),
                next_action="Use evidence for eval design.",
            )
            for eval_id in eval_ids
        )
        return QaBrainSeedPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="ready-project",
            summary=QaBrainSeedSummary(
                status="ready",
                sources_total=len(eval_ids),
                sources_present=len(eval_ids),
                sources_missing=0,
                sources_invalid=0,
                sources_unsafe=0,
                eval_slices_total=len(eval_ids),
                eval_slices_ready=len(eval_ids),
                next_actions_total=0,
            ),
            sources=(),
            eval_slices=slices,
            next_actions=(),
        )

    monkeypatch.setattr(qa_brain_eval_plan, "build_qa_brain_seed", fake_seed)

    packet = build_qa_brain_eval_plan(project_root=tmp_path)
    markdown = render_qa_brain_eval_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.cases_ready == packet.summary.cases_total
    assert packet.next_actions == ()
    assert "No QA brain eval-plan actions are currently needed." in markdown


def test_qa_brain_eval_plan_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(QaBrainEvalPlanError, match="Unsupported qa-brain-eval-plan output"):
        run_qa_brain_eval_plan_report(project_root=tmp_path, output=cast(Any, "html"))


def test_qa_brain_eval_plan_wraps_seed_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_eval_plan as qa_brain_eval_plan

    def fail_seed(*, project_root: Path) -> QaBrainSeedPacket:
        _ = project_root
        raise QaBrainSeedError("QA brain seed source is unsafe")

    monkeypatch.setattr(qa_brain_eval_plan, "build_qa_brain_seed", fail_seed)

    with pytest.raises(QaBrainEvalPlanError, match="QA brain seed source is unsafe"):
        build_qa_brain_eval_plan(project_root=tmp_path)


def test_qa_brain_eval_plan_rejects_unknown_seed_slice_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_eval_plan as qa_brain_eval_plan

    def fake_seed(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            eval_slices=(
                QaBrainEvalSlice.model_construct(
                    id="new_eval",
                    label="New eval",
                    status="ready",
                    source_ids=(),
                    source_paths=(),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(qa_brain_eval_plan, "build_qa_brain_seed", fake_seed)

    with pytest.raises(
        QaBrainEvalPlanError,
        match="missing input_contract metadata for new_eval",
    ):
        build_qa_brain_eval_plan(project_root=tmp_path)


def test_qa_brain_eval_plan_rejects_missing_negative_control_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_eval_plan as qa_brain_eval_plan

    def fake_seed(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            eval_slices=(
                QaBrainEvalSlice(
                    id="weak_test_detection",
                    label="Weak-test detection",
                    status="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(qa_brain_eval_plan, "build_qa_brain_seed", fake_seed)
    monkeypatch.setattr(qa_brain_eval_plan, "_NEGATIVE_CONTROLS", {})

    with pytest.raises(
        QaBrainEvalPlanError,
        match="missing negative_controls metadata for weak_test_detection",
    ):
        build_qa_brain_eval_plan(project_root=tmp_path)


def test_qa_brain_eval_plan_rejects_output_paths_outside_project(tmp_path: Path) -> None:
    with pytest.raises(QaBrainEvalPlanError, match="path must stay under"):
        run_qa_brain_eval_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-eval-plan.json",
        )


def test_qa_brain_eval_plan_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-eval-plan.json"

    result = run_qa_brain_eval_plan_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION


@pytest.mark.parametrize("output", ("md", "json"))
def test_qa_brain_eval_plan_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    import entroping.core.plan.qa_brain_eval_plan as qa_brain_eval_plan

    def fake_seed(*, project_root: Path) -> QaBrainSeedPacket:
        _ = project_root
        return QaBrainSeedPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="secret-project",
            summary=QaBrainSeedSummary(
                status="partial",
                sources_total=1,
                sources_present=1,
                sources_missing=0,
                sources_invalid=0,
                sources_unsafe=0,
                eval_slices_total=1,
                eval_slices_ready=1,
                next_actions_total=0,
            ),
            sources=(),
            eval_slices=(
                QaBrainEvalSlice(
                    id="weak_test_detection",
                    label="Weak-test detection",
                    status="ready",
                    source_ids=(f"test-quality-{_provider_token_fixture()}",),
                    source_paths=(f"reports/{_provider_token_fixture()}.json",),
                    next_action="Use evidence for eval design.",
                ),
            ),
            next_actions=(
                QaBrainNextAction(
                    priority="low",
                    action="unused",
                    source_ids=(f"test-quality-{_provider_token_fixture()}",),
                ),
            ),
        )

    monkeypatch.setattr(qa_brain_eval_plan, "build_qa_brain_seed", fake_seed)

    with pytest.raises(QaBrainEvalPlanError, match="contains secret-like content"):
        run_qa_brain_eval_plan_report(project_root=tmp_path, output=cast(Any, output))
