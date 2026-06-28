"""Tests for deterministic QA brain fine-tune readiness packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from entroping.core.plan.qa_brain_fine_tune_readiness import (
    QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
    QaBrainFineTuneReadinessError,
    build_qa_brain_fine_tune_readiness,
    render_qa_brain_fine_tune_readiness_markdown,
    run_qa_brain_fine_tune_readiness_report,
)
from entroping.core.plan.qa_brain_prompt_plan import (
    QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
    QaBrainPromptPlanError,
    QaBrainPromptPlanNextAction,
    QaBrainPromptPlanPacket,
    QaBrainPromptPlanRow,
    QaBrainPromptPlanSummary,
)

_EVAL_IDS = (
    "weak_test_detection",
    "missing_gate_discovery",
    "unsafe_generated_hurl",
    "bogus_evidence",
    "redaction_mistakes",
    "api_drift_reasoning",
    "mutation_fuzz_readiness",
    "cross_surface_handoff_quality",
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def _prompt_row(
    case_id: str,
    *,
    readiness: str = "ready",
    source_ids: tuple[str, ...] = ("test-quality-json",),
    source_paths: tuple[str, ...] = ("reports/test-quality.json",),
) -> QaBrainPromptPlanRow:
    return QaBrainPromptPlanRow(
        case_id=cast(Any, case_id),
        label=case_id.replace("_", " ").title(),
        readiness=cast(Any, readiness),
        source_ids=source_ids,
        source_paths=source_paths,
        retrieval_category="test_quality",
        prompt_objective="Critique local evidence with stable IDs only.",
        prompt_inputs_allowed=("case_id", "artifact_id", "readiness"),
        prompt_inputs_forbidden=("headers", "cookies", "tokens", "request_body"),
        expected_output_fields=("case_id", "risk_level", "evidence_ids"),
        deterministic_acceptance_signals=("Evidence IDs are present.",),
        negative_controls=("Do not reward generic confidence.",),
        safety_notes=("Use value-free local metadata only.",),
        next_action="Use evidence for prompt design.",
    )


def _prompt_packet(
    rows: tuple[QaBrainPromptPlanRow, ...],
    *,
    status: str = "ready",
) -> QaBrainPromptPlanPacket:
    ready = sum(1 for row in rows if row.readiness == "ready")
    missing = sum(1 for row in rows if row.readiness == "missing")
    attention = sum(1 for row in rows if row.readiness == "attention")
    actions = tuple(
        QaBrainPromptPlanNextAction(
            priority="high" if row.readiness == "attention" else "medium",
            action=row.next_action,
            case_ids=(row.case_id,),
        )
        for row in rows
        if row.readiness != "ready"
    )
    return QaBrainPromptPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="prompt-project",
        retrieval_plan_schema_version="entroping.qa-brain-retrieval-plan.v1",
        summary=QaBrainPromptPlanSummary(
            status=cast(Any, status),
            prompts_total=len(rows),
            prompts_ready=ready,
            prompts_missing=missing,
            prompts_attention=attention,
            next_actions_total=len(actions),
        ),
        prompt_plans=rows,
        next_actions=actions,
    )


def test_qa_brain_fine_tune_readiness_writes_valid_json_without_prior_prompt_plan(
    tmp_path: Path,
) -> None:
    # The real prompt-plan builder must provide one value-free missing row per
    # canonical QA Brain eval slice even when no prior prompt-plan artifact exists.
    result = run_qa_brain_fine_tune_readiness_report(
        project_root=tmp_path,
        output="json",
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == (
        tmp_path / "reports" / "qa-brain-fine-tune-readiness.json"
    )
    assert not (tmp_path / "reports" / "qa-brain-prompt-plan.json").exists()
    assert payload["schema_version"] == QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION
    assert payload["prompt_plan_schema_version"] == QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["readiness_total"] == len(payload["readiness_rows"])
    assert payload["summary"]["readiness_ready"] == 0
    assert payload["summary"]["readiness_missing"] == (
        payload["summary"]["readiness_total"]
    )
    assert {row["case_id"] for row in payload["readiness_rows"]} == set(_EVAL_IDS)


def test_qa_brain_fine_tune_readiness_derives_ready_rows_without_raw_values(
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

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.readiness_rows}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert rows["weak_test_detection"].readiness == "ready"
    assert rows["weak_test_detection"].readiness_stage == "metadata_ready"
    assert "test-quality-json" in rows["weak_test_detection"].source_ids
    assert rows["weak_test_detection"].blockers == ()
    assert "stable generated-test quality" in (
        rows["weak_test_detection"].deterministic_acceptance
    )
    assert rows["api_drift_reasoning"].readiness == "ready"
    assert rows["mutation_fuzz_readiness"].readiness == "ready"
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_fine_tune_readiness_preserves_attention_sources_and_actions(
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

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.readiness_rows}

    assert packet.summary.status == "partial"
    assert packet.summary.readiness_attention == 2
    assert packet.summary.blockers_total >= 2
    assert rows["bogus_evidence"].readiness == "attention"
    assert rows["bogus_evidence"].readiness_stage == "needs_repair"
    assert rows["bogus_evidence"].source_ids == (
        "artifact-manifest-json",
        "run-json",
        "drift-json",
    )
    assert rows["bogus_evidence"].blockers
    bogus_action = next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    )
    assert bogus_action.priority == "high"
    attention_payload = json.dumps(
        {
            "row": rows["bogus_evidence"].model_dump(mode="json"),
            "action": bogus_action.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    assert "999" not in attention_payload


def test_qa_brain_fine_tune_readiness_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_fine_tune_readiness_report(
        project_root=tmp_path,
        output="md",
    )
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Fine-Tune Readiness" in markdown
    assert "- Schema: `entroping.qa-brain-fine-tune-readiness.v1`" in markdown
    assert "- Prompt-plan schema: `entroping.qa-brain-prompt-plan.v1`" in markdown
    assert "| weak_test_detection | Weak-test detection | ready | metadata_ready |" in (
        markdown
    )
    assert "generated_tests" not in markdown


def test_qa_brain_fine_tune_readiness_markdown_escapes_table_cells_and_inline_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                _prompt_row(
                    "weak_test_detection",
                    readiness="missing",
                    source_ids=(),
                    source_paths=(),
                ),
            ),
            status="insufficient",
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "readiness_rows": (
                packet.readiness_rows[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "evidence_coverage": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_fine_tune_readiness_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_fine_tune_readiness_reports_insufficient_for_empty_prompt_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet((), status="insufficient")

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.readiness_total == 0
    assert packet.next_actions == ()


def test_qa_brain_fine_tune_readiness_reports_ready_when_all_rows_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(tuple(_prompt_row(eval_id) for eval_id in _EVAL_IDS))

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)
    markdown = render_qa_brain_fine_tune_readiness_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.readiness_ready == packet.summary.readiness_total
    assert packet.next_actions == ()
    assert "No QA brain fine-tune readiness actions are currently needed." in markdown


def test_qa_brain_fine_tune_readiness_blocks_incomplete_prompt_plan_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                _prompt_row("weak_test_detection").model_copy(
                    update={
                        "prompt_inputs_allowed": (),
                        "deterministic_acceptance_signals": (),
                    }
                ),
            )
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)
    row = packet.readiness_rows[0]

    assert packet.summary.status == "partial"
    assert packet.summary.blockers_total == 1
    assert packet.summary.next_actions_total == 1
    assert "allowed inputs" in row.prompt_plan_completeness
    assert row.deterministic_acceptance == (
        "No deterministic prompt-plan acceptance signals are available."
    )
    assert row.blockers == ("Complete prompt-plan metadata before future dataset design.",)


def test_qa_brain_fine_tune_readiness_summary_dedupes_duplicate_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def incomplete_prompt_row(case_id: str) -> QaBrainPromptPlanRow:
        return _prompt_row(case_id).model_copy(
            update={
                "prompt_inputs_allowed": (),
                "deterministic_acceptance_signals": (),
            }
        )

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                incomplete_prompt_row("weak_test_detection"),
                incomplete_prompt_row("api_drift_reasoning"),
            )
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.blockers_total == 1
    assert tuple(row.blockers for row in packet.readiness_rows) == (
        ("Complete prompt-plan metadata before future dataset design.",),
        ("Complete prompt-plan metadata before future dataset design.",),
    )


def test_qa_brain_fine_tune_readiness_deduplicates_next_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                _prompt_row(
                    "weak_test_detection",
                    readiness="missing",
                    source_ids=(),
                    source_paths=(),
                ),
                _prompt_row(
                    "weak_test_detection",
                    readiness="attention",
                    source_ids=("test-quality-json",),
                    source_paths=("reports/test-quality.json",),
                ),
                _prompt_row(
                    "weak_test_detection",
                    readiness="missing",
                    source_ids=(),
                    source_paths=(),
                ),
            ),
            status="partial",
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    packet = build_qa_brain_fine_tune_readiness(project_root=tmp_path)

    assert len(packet.readiness_rows) == 3
    assert tuple(action.case_ids for action in packet.next_actions) == (
        ("weak_test_detection",),
    )
    assert packet.next_actions[0].priority == "high"


def test_qa_brain_fine_tune_readiness_rejects_unsupported_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="Unsupported qa-brain-fine-tune-readiness output",
    ):
        run_qa_brain_fine_tune_readiness_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )


def test_qa_brain_fine_tune_readiness_wraps_prompt_plan_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fail_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        raise QaBrainPromptPlanError("QA brain prompt plan source is unsafe")

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fail_prompt_plan,
    )

    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="prompt plan source is unsafe",
    ):
        build_qa_brain_fine_tune_readiness(project_root=tmp_path)


def test_qa_brain_fine_tune_readiness_rejects_unknown_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            prompt_plans=(
                QaBrainPromptPlanRow.model_construct(
                    case_id="new_eval",
                    label="New eval",
                    readiness="ready",
                    source_ids=(),
                    source_paths=(),
                    retrieval_category="test_quality",
                    prompt_objective="Critique local evidence.",
                    prompt_inputs_allowed=("case_id",),
                    prompt_inputs_forbidden=("raw_url",),
                    expected_output_fields=("case_id",),
                    deterministic_acceptance_signals=("Evidence IDs are present.",),
                    negative_controls=("Do not reward generic confidence.",),
                    safety_notes=("Use metadata only.",),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="missing eval_case_coverage metadata for new_eval",
    ):
        build_qa_brain_fine_tune_readiness(project_root=tmp_path)


def test_qa_brain_fine_tune_readiness_rejects_missing_readiness_stage_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet((_prompt_row("weak_test_detection"),))

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )
    monkeypatch.setattr(fine_tune_readiness, "_READINESS_STAGES", {})

    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="missing readiness_stage metadata for ready",
    ):
        build_qa_brain_fine_tune_readiness(project_root=tmp_path)


def test_qa_brain_fine_tune_readiness_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainFineTuneReadinessError, match="path must stay under"):
        run_qa_brain_fine_tune_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-fine-tune-readiness.json",
        )


def test_qa_brain_fine_tune_readiness_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-fine-tune-readiness.json"

    result = run_qa_brain_fine_tune_readiness_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert output_path.exists()


def test_qa_brain_fine_tune_readiness_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    secret_marker = _provider_token_fixture()

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                _prompt_row(
                    "weak_test_detection",
                    source_ids=(secret_marker,),
                    source_paths=("reports/test-quality.json",),
                ),
            )
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    for output in ("json", "md"):
        with pytest.raises(
            QaBrainFineTuneReadinessError,
            match="contains secret-like content",
        ):
            run_qa_brain_fine_tune_readiness_report(
                project_root=tmp_path,
                output=cast(Any, output),
            )


def test_qa_brain_fine_tune_readiness_build_rejects_secret_like_packet_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    secret_marker = _provider_token_fixture()

    def fake_prompt_plan(*, project_root: Path) -> QaBrainPromptPlanPacket:
        _ = project_root
        return _prompt_packet(
            (
                _prompt_row(
                    "weak_test_detection",
                    source_ids=(secret_marker,),
                    source_paths=("reports/test-quality.json",),
                ),
            )
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_prompt_plan",
        fake_prompt_plan,
    )

    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="contains secret-like content",
    ):
        build_qa_brain_fine_tune_readiness(project_root=tmp_path)


def test_qa_brain_fine_tune_readiness_writer_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_fine_tune_readiness as fine_tune_readiness

    secret_marker = _provider_token_fixture()

    def fake_build(*, project_root: Path) -> object:
        _ = project_root
        return fine_tune_readiness.QaBrainFineTuneReadinessPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="unsafe-project",
            prompt_plan_schema_version=QA_BRAIN_PROMPT_PLAN_SCHEMA_VERSION,
            summary=fine_tune_readiness.QaBrainFineTuneReadinessSummary(
                status="ready",
                readiness_total=1,
                readiness_ready=1,
                readiness_missing=0,
                readiness_attention=0,
                blockers_total=0,
                next_actions_total=0,
            ),
            readiness_rows=(
                fine_tune_readiness.QaBrainFineTuneReadinessRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=(secret_marker,),
                    source_paths=("reports/test-quality.json",),
                    readiness_stage="metadata_ready",
                    evidence_coverage="Stable evidence IDs are present.",
                    prompt_plan_completeness="Prompt-plan metadata is complete.",
                    safety_boundary="Provider-free metadata only.",
                    eval_case_coverage="Covers weak-test detection.",
                    redaction_boundary="No secrets.",
                    deterministic_acceptance="Evidence IDs are present.",
                    blockers=(),
                    next_action="Use metadata only.",
                ),
            ),
            next_actions=(),
        )

    monkeypatch.setattr(
        fine_tune_readiness,
        "build_qa_brain_fine_tune_readiness",
        fake_build,
    )

    with pytest.raises(
        QaBrainFineTuneReadinessError,
        match="contains secret-like content",
    ):
        run_qa_brain_fine_tune_readiness_report(project_root=tmp_path, output="json")
