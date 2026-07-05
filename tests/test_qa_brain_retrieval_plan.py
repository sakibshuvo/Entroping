"""Tests for deterministic QA brain retrieval-plan packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import entroping.core.plan.qa_brain_retrieval_plan as qa_brain_retrieval_plan
from entroping.core.plan.qa_brain_eval_plan import (
    QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION,
    QaBrainEvalCase,
    QaBrainEvalPlanError,
    QaBrainEvalPlanNextAction,
    QaBrainEvalPlanPacket,
    QaBrainEvalPlanSummary,
)

QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION = (
    qa_brain_retrieval_plan.QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION
)
QaBrainRetrievalPlanError = (
    qa_brain_retrieval_plan.QaBrainRetrievalPlanError
)
build_qa_brain_retrieval_plan = (
    qa_brain_retrieval_plan.build_qa_brain_retrieval_plan
)
render_qa_brain_retrieval_plan_markdown = (
    qa_brain_retrieval_plan.render_qa_brain_retrieval_plan_markdown
)
run_qa_brain_retrieval_plan_report = (
    qa_brain_retrieval_plan.run_qa_brain_retrieval_plan_report
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def test_qa_brain_retrieval_plan_writes_valid_json_without_prior_eval_plan(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_retrieval_plan_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-retrieval-plan.json"
    assert not (tmp_path / "reports" / "qa-brain-eval-plan.json").exists()
    assert payload["schema_version"] == QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION
    assert payload["eval_plan_schema_version"] == QA_BRAIN_EVAL_PLAN_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["plans_total"] == len(payload["retrieval_plans"])
    assert payload["summary"]["plans_ready"] == 0
    assert payload["summary"]["plans_missing"] == payload["summary"]["plans_total"]
    assert {plan["case_id"] for plan in payload["retrieval_plans"]} == {
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    }


def test_qa_brain_retrieval_plan_derives_ready_rows_without_raw_values(
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

    packet = build_qa_brain_retrieval_plan(project_root=tmp_path)
    plans = {plan.case_id: plan for plan in packet.retrieval_plans}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert plans["weak_test_detection"].readiness == "ready"
    assert "test-quality-json" in plans["weak_test_detection"].source_ids
    assert plans["weak_test_detection"].retrieval_category == "test_quality"
    assert "schema_version" in plans["weak_test_detection"].allowed_fields
    assert "request_body" in plans["weak_test_detection"].forbidden_fields
    assert "weak-test" in plans["weak_test_detection"].query_hints[0].lower()
    assert plans["api_drift_reasoning"].readiness == "ready"
    assert plans["mutation_fuzz_readiness"].readiness == "ready"
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_retrieval_plan_preserves_attention_sources_and_next_actions(
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

    packet = build_qa_brain_retrieval_plan(project_root=tmp_path)
    plans = {plan.case_id: plan for plan in packet.retrieval_plans}

    assert packet.summary.status == "partial"
    assert packet.summary.plans_attention == 2
    assert plans["bogus_evidence"].readiness == "attention"
    assert plans["bogus_evidence"].source_ids == (
        "artifact-manifest-json",
        "run-json",
        "drift-json",
    )
    assert next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    ).priority == "high"
    assert "999" not in packet.model_dump_json(exclude={"generated_at"})


def test_qa_brain_retrieval_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_retrieval_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Retrieval Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown
    assert "test_quality" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_retrieval_plan_markdown_escapes_table_cells_and_inline_code() -> None:
    packet = build_qa_brain_retrieval_plan(project_root=Path("."))
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "retrieval_plans": (
                packet.retrieval_plans[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "retrieval_intent": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_retrieval_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_retrieval_plan_reports_ready_when_all_plans_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

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

    def fake_eval_plan(*, project_root: Path) -> QaBrainEvalPlanPacket:
        _ = project_root
        cases = tuple(
            QaBrainEvalCase(
                id=cast(Any, eval_id),
                label=eval_id.replace("_", " ").title(),
                readiness="ready",
                source_ids=(f"{eval_id}-source",),
                source_paths=(f"reports/{eval_id}.json",),
                input_contract="Value-free rows.",
                output_contract="schema-valid critique.",
                acceptance_signal="Use local IDs only.",
                negative_controls=("Do not use raw values.",),
                next_action="Use evidence for retrieval design.",
            )
            for eval_id in eval_ids
        )
        return QaBrainEvalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="ready-project",
            seed_schema_version="entroping.qa-brain-seed.v1",
            summary=QaBrainEvalPlanSummary(
                status="ready",
                cases_total=len(eval_ids),
                cases_ready=len(eval_ids),
                cases_missing=0,
                cases_attention=0,
                next_actions_total=0,
            ),
            cases=cases,
            next_actions=(),
        )

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fake_eval_plan)

    packet = build_qa_brain_retrieval_plan(project_root=tmp_path)
    markdown = render_qa_brain_retrieval_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.plans_ready == packet.summary.plans_total
    assert packet.next_actions == ()
    assert "No QA brain retrieval-plan actions are currently needed." in markdown


def test_qa_brain_retrieval_plan_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(
        QaBrainRetrievalPlanError,
        match="Unsupported qa-brain-retrieval-plan output",
    ):
        run_qa_brain_retrieval_plan_report(project_root=tmp_path, output=cast(Any, "html"))


def test_qa_brain_retrieval_plan_wraps_eval_plan_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fail_eval_plan(*, project_root: Path) -> QaBrainEvalPlanPacket:
        _ = project_root
        raise QaBrainEvalPlanError("QA brain eval plan source is unsafe")

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fail_eval_plan)

    with pytest.raises(QaBrainRetrievalPlanError, match="eval plan source is unsafe"):
        build_qa_brain_retrieval_plan(project_root=tmp_path)


def test_qa_brain_retrieval_plan_rejects_unknown_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fake_eval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            cases=(
                QaBrainEvalCase.model_construct(
                    id="new_eval",
                    label="New eval",
                    readiness="ready",
                    source_ids=(),
                    source_paths=(),
                    input_contract="Value-free rows.",
                    output_contract="schema-valid critique.",
                    acceptance_signal="Use local IDs only.",
                    negative_controls=("Do not use raw values.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fake_eval_plan)

    with pytest.raises(
        QaBrainRetrievalPlanError,
        match="missing retrieval_category metadata for new_eval",
    ):
        build_qa_brain_retrieval_plan(project_root=tmp_path)


def test_qa_brain_retrieval_plan_rejects_missing_forbidden_field_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fake_eval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            cases=(
                QaBrainEvalCase(
                    id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    input_contract="Value-free rows.",
                    output_contract="schema-valid critique.",
                    acceptance_signal="Use local IDs only.",
                    negative_controls=("Do not use raw values.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fake_eval_plan)
    monkeypatch.setattr(qa_brain_retrieval_plan, "_FORBIDDEN_FIELDS", {})

    with pytest.raises(
        QaBrainRetrievalPlanError,
        match="missing forbidden_fields metadata for weak_test_detection",
    ):
        build_qa_brain_retrieval_plan(project_root=tmp_path)


def test_qa_brain_retrieval_plan_rejects_missing_intent_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fake_eval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            cases=(
                QaBrainEvalCase(
                    id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    input_contract="Value-free rows.",
                    output_contract="schema-valid critique.",
                    acceptance_signal="Use local IDs only.",
                    negative_controls=("Do not use raw values.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fake_eval_plan)
    monkeypatch.setattr(qa_brain_retrieval_plan, "_RETRIEVAL_INTENTS", {})

    with pytest.raises(
        QaBrainRetrievalPlanError,
        match="missing retrieval_intent metadata for weak_test_detection",
    ):
        build_qa_brain_retrieval_plan(project_root=tmp_path)


def test_qa_brain_retrieval_plan_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainRetrievalPlanError, match="path must stay under"):
        run_qa_brain_retrieval_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-retrieval-plan.json",
        )


def test_qa_brain_retrieval_plan_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-retrieval-plan.json"

    result = run_qa_brain_retrieval_plan_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION


@pytest.mark.parametrize("output", ("md", "json"))
def test_qa_brain_retrieval_plan_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:

    def fake_eval_plan(*, project_root: Path) -> QaBrainEvalPlanPacket:
        _ = project_root
        return QaBrainEvalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="secret-project",
            seed_schema_version="entroping.qa-brain-seed.v1",
            summary=QaBrainEvalPlanSummary(
                status="partial",
                cases_total=1,
                cases_ready=1,
                cases_missing=0,
                cases_attention=0,
                next_actions_total=0,
            ),
            cases=(
                QaBrainEvalCase(
                    id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=(f"test-quality-{_provider_token_fixture()}",),
                    source_paths=(f"reports/{_provider_token_fixture()}.json",),
                    input_contract="Value-free rows.",
                    output_contract="schema-valid critique.",
                    acceptance_signal="Use local IDs only.",
                    negative_controls=("Do not use raw values.",),
                    next_action="Use evidence.",
                ),
            ),
            next_actions=(
                QaBrainEvalPlanNextAction(
                    priority="low",
                    action="unused",
                    case_ids=("weak_test_detection",),
                ),
            ),
        )

    monkeypatch.setattr(qa_brain_retrieval_plan, "build_qa_brain_eval_plan", fake_eval_plan)

    with pytest.raises(QaBrainRetrievalPlanError, match="contains secret-like content"):
        run_qa_brain_retrieval_plan_report(
            project_root=tmp_path,
            output=cast(Any, output),
        )
