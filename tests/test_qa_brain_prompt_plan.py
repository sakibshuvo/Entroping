"""Tests for deterministic QA brain prompt-plan packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from entroping.core.qa_brain_prompt_plan import (
    QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
    QaBrainPromptPlanError,
    build_qa_brain_prompt_plan,
    render_qa_brain_prompt_plan_markdown,
    run_qa_brain_prompt_plan_report,
)
from entroping.core.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanNextAction,
    QaBrainRetrievalPlanPacket,
    QaBrainRetrievalPlanRow,
    QaBrainRetrievalPlanSummary,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def test_qa_brain_prompt_plan_writes_valid_json_without_prior_retrieval_plan(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_prompt_plan_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-prompt-plan.json"
    assert not (tmp_path / "reports" / "qa-brain-retrieval-plan.json").exists()
    assert payload["schema_version"] == QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION
    assert payload["retrieval_plan_schema_version"] == (
        QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION
    )
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["prompts_total"] == len(payload["prompt_plans"])
    assert payload["summary"]["prompts_ready"] == 0
    assert payload["summary"]["prompts_missing"] == payload["summary"]["prompts_total"]
    assert {plan["case_id"] for plan in payload["prompt_plans"]} == {
        "weak_test_detection",
        "missing_gate_discovery",
        "unsafe_generated_hurl",
        "bogus_evidence",
        "redaction_mistakes",
        "api_drift_reasoning",
        "mutation_fuzz_readiness",
        "cross_surface_handoff_quality",
    }


def test_qa_brain_prompt_plan_derives_ready_rows_without_raw_values(
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

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)
    plans = {plan.case_id: plan for plan in packet.prompt_plans}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert plans["weak_test_detection"].readiness == "ready"
    assert "test-quality-json" in plans["weak_test_detection"].source_ids
    assert plans["weak_test_detection"].retrieval_category == "test_quality"
    assert "case_id" in plans["weak_test_detection"].prompt_inputs_allowed
    assert "provider_output" in plans["weak_test_detection"].prompt_inputs_forbidden
    assert "risk_level" in plans["weak_test_detection"].expected_output_fields
    assert plans["api_drift_reasoning"].readiness == "ready"
    assert plans["mutation_fuzz_readiness"].readiness == "ready"
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_prompt_plan_preserves_attention_sources_and_next_actions(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    outside_value = "outside-run-summary-should-not-leak"
    outside = tmp_path.parent / "outside-run-latest.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "summary": {"total": 999, "raw_value": outside_value},
            }
        )
        + "\n",
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

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)
    plans = {plan.case_id: plan for plan in packet.prompt_plans}

    assert packet.summary.status == "partial"
    assert packet.summary.prompts_attention == 2
    assert plans["bogus_evidence"].readiness == "attention"
    assert plans["bogus_evidence"].source_ids == (
        "artifact-manifest-json",
        "run-json",
        "drift-json",
    )
    assert next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    ).priority == "high"
    assert outside_value not in packet.model_dump_json()


def test_qa_brain_prompt_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_prompt_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Prompt Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown
    assert "test_quality" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_prompt_plan_markdown_escapes_table_cells_and_inline_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        return QaBrainRetrievalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="escape-project",
            eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
            summary=QaBrainRetrievalPlanSummary(
                status="partial",
                plans_total=1,
                plans_ready=0,
                plans_missing=1,
                plans_attention=0,
                next_actions_total=1,
            ),
            retrieval_plans=(
                QaBrainRetrievalPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="missing",
                    source_ids=(),
                    source_paths=(),
                    retrieval_category="test_quality",
                    retrieval_intent="Find local value-free evidence.",
                    allowed_fields=("schema_version", "artifact_id"),
                    forbidden_fields=("request_body", "response_body"),
                    query_hints=("Find evidence using stable IDs.",),
                    safety_notes=("Use value-free local metadata only.",),
                    next_action="Add evidence for prompt design.",
                ),
            ),
            next_actions=(
                QaBrainRetrievalPlanNextAction(
                    priority="medium",
                    action="Add evidence for prompt design.",
                    case_ids=("weak_test_detection",),
                ),
            ),
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "prompt_plans": (
                packet.prompt_plans[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "prompt_objective": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_prompt_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_prompt_plan_deduplicates_allowed_prompt_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        return QaBrainRetrievalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="dedupe-project",
            eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
            summary=QaBrainRetrievalPlanSummary(
                status="ready",
                plans_total=1,
                plans_ready=1,
                plans_missing=0,
                plans_attention=0,
                next_actions_total=0,
            ),
            retrieval_plans=(
                QaBrainRetrievalPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    retrieval_category="test_quality",
                    retrieval_intent="Find local value-free evidence.",
                    allowed_fields=("case_id", "artifact_id", "readiness"),
                    forbidden_fields=("request_body", "response_body"),
                    query_hints=("Find evidence using stable IDs.",),
                    safety_notes=("Use value-free local metadata only.",),
                    next_action="Use evidence for prompt design.",
                ),
            ),
            next_actions=(),
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)
    inputs = packet.prompt_plans[0].prompt_inputs_allowed

    assert inputs[:7] == (
        "case_id",
        "label",
        "readiness",
        "source_ids",
        "source_paths",
        "retrieval_category",
        "retrieval_intent",
    )
    assert inputs.count("case_id") == 1
    assert inputs.count("readiness") == 1
    assert "artifact_id" in inputs


def test_qa_brain_prompt_plan_reports_insufficient_for_empty_retrieval_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        return QaBrainRetrievalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="empty-project",
            eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
            summary=QaBrainRetrievalPlanSummary(
                status="insufficient",
                plans_total=0,
                plans_ready=0,
                plans_missing=0,
                plans_attention=0,
                next_actions_total=0,
            ),
            retrieval_plans=(),
            next_actions=(),
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.prompts_total == 0
    assert packet.next_actions == ()


def test_qa_brain_prompt_plan_reports_ready_when_all_prompts_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

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

    def fake_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        rows = tuple(
            QaBrainRetrievalPlanRow(
                case_id=cast(Any, eval_id),
                label=eval_id.replace("_", " ").title(),
                readiness="ready",
                source_ids=(f"{eval_id}-source",),
                source_paths=(f"reports/{eval_id}.json",),
                retrieval_category="test_quality",
                retrieval_intent="Find local value-free evidence.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body"),
                query_hints=("Find evidence using stable IDs.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Use evidence for prompt design.",
            )
            for eval_id in eval_ids
        )
        return QaBrainRetrievalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="ready-project",
            eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
            summary=QaBrainRetrievalPlanSummary(
                status="ready",
                plans_total=len(eval_ids),
                plans_ready=len(eval_ids),
                plans_missing=0,
                plans_attention=0,
                next_actions_total=0,
            ),
            retrieval_plans=rows,
            next_actions=(),
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    packet = build_qa_brain_prompt_plan(project_root=tmp_path)
    markdown = render_qa_brain_prompt_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.prompts_ready == packet.summary.prompts_total
    assert packet.next_actions == ()
    assert "No QA brain prompt-plan actions are currently needed." in markdown


def test_qa_brain_prompt_plan_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(
        QaBrainPromptPlanError,
        match="Unsupported qa-brain-prompt-plan output",
    ):
        run_qa_brain_prompt_plan_report(project_root=tmp_path, output=cast(Any, "html"))


def test_qa_brain_prompt_plan_wraps_retrieval_plan_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fail_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        raise QaBrainRetrievalPlanError("QA brain retrieval plan source is unsafe")

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fail_retrieval_plan,
    )

    with pytest.raises(QaBrainPromptPlanError, match="retrieval plan source is unsafe"):
        build_qa_brain_prompt_plan(project_root=tmp_path)


def test_qa_brain_prompt_plan_rejects_unknown_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            retrieval_plans=(
                QaBrainRetrievalPlanRow.model_construct(
                    case_id="new_eval",
                    label="New eval",
                    readiness="ready",
                    source_ids=(),
                    source_paths=(),
                    retrieval_category="test_quality",
                    retrieval_intent="Find value-free evidence.",
                    allowed_fields=("schema_version",),
                    forbidden_fields=("raw_url",),
                    query_hints=("Find by stable IDs.",),
                    safety_notes=("Use metadata only.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    with pytest.raises(
        QaBrainPromptPlanError,
        match="missing prompt_objective metadata for new_eval",
    ):
        build_qa_brain_prompt_plan(project_root=tmp_path)


def test_qa_brain_prompt_plan_rejects_missing_forbidden_input_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            retrieval_plans=(
                QaBrainRetrievalPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    retrieval_category="test_quality",
                    retrieval_intent="Find value-free evidence.",
                    allowed_fields=("schema_version",),
                    forbidden_fields=("raw_url",),
                    query_hints=("Find by stable IDs.",),
                    safety_notes=("Use metadata only.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )
    monkeypatch.setattr(qa_brain_prompt_plan, "_PROMPT_INPUTS_FORBIDDEN", {})

    with pytest.raises(
        QaBrainPromptPlanError,
        match="missing prompt_inputs_forbidden metadata for weak_test_detection",
    ):
        build_qa_brain_prompt_plan(project_root=tmp_path)


def test_qa_brain_prompt_plan_rejects_missing_output_field_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            retrieval_plans=(
                QaBrainRetrievalPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                    retrieval_category="test_quality",
                    retrieval_intent="Find value-free evidence.",
                    allowed_fields=("schema_version",),
                    forbidden_fields=("raw_url",),
                    query_hints=("Find by stable IDs.",),
                    safety_notes=("Use metadata only.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )
    monkeypatch.setattr(qa_brain_prompt_plan, "_EXPECTED_OUTPUT_FIELDS", {})

    with pytest.raises(
        QaBrainPromptPlanError,
        match="missing expected_output_fields metadata for weak_test_detection",
    ):
        build_qa_brain_prompt_plan(project_root=tmp_path)


def test_qa_brain_prompt_plan_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainPromptPlanError, match="path must stay under"):
        run_qa_brain_prompt_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-prompt-plan.json",
        )


def test_qa_brain_prompt_plan_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-prompt-plan.json"

    result = run_qa_brain_prompt_plan_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION


@pytest.mark.parametrize("output", ("md", "json"))
def test_qa_brain_prompt_plan_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    import entroping.core.qa_brain_prompt_plan as qa_brain_prompt_plan

    def fake_retrieval_plan(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        _ = project_root
        return QaBrainRetrievalPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="secret-project",
            eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
            summary=QaBrainRetrievalPlanSummary(
                status="partial",
                plans_total=1,
                plans_ready=1,
                plans_missing=0,
                plans_attention=0,
                next_actions_total=0,
            ),
            retrieval_plans=(
                QaBrainRetrievalPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=(f"test-quality-{_provider_token_fixture()}",),
                    source_paths=(f"reports/{_provider_token_fixture()}.json",),
                    retrieval_category="test_quality",
                    retrieval_intent="Find value-free evidence.",
                    allowed_fields=("schema_version",),
                    forbidden_fields=("request_body", "response_body"),
                    query_hints=("Find using stable IDs.",),
                    safety_notes=("Use metadata only.",),
                    next_action="Use evidence.",
                ),
            ),
            next_actions=(
                QaBrainRetrievalPlanNextAction(
                    priority="low",
                    action="unused",
                    case_ids=("weak_test_detection",),
                ),
            ),
        )

    monkeypatch.setattr(
        qa_brain_prompt_plan,
        "build_qa_brain_retrieval_plan",
        fake_retrieval_plan,
    )

    with pytest.raises(QaBrainPromptPlanError, match="contains secret-like content"):
        run_qa_brain_prompt_plan_report(
            project_root=tmp_path,
            output=cast(Any, output),
        )
