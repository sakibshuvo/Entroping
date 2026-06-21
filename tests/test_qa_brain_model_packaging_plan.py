"""Tests for deterministic QA brain model-packaging plan packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from entroping.core.qa_brain_fine_tune_readiness import (
    QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION,
    QaBrainFineTuneReadinessError,
    QaBrainFineTuneReadinessNextAction,
    QaBrainFineTuneReadinessPacket,
    QaBrainFineTuneReadinessRow,
    QaBrainFineTuneReadinessSummary,
)
from entroping.core.qa_brain_model_packaging_plan import (
    QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION,
    QaBrainModelPackagingPlanError,
    build_qa_brain_model_packaging_plan,
    render_qa_brain_model_packaging_plan_markdown,
    run_qa_brain_model_packaging_plan_report,
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


def _readiness_row(
    case_id: str,
    *,
    readiness: str = "ready",
    blockers: tuple[str, ...] = (),
    source_ids: tuple[str, ...] = ("test-quality-json",),
    source_paths: tuple[str, ...] = ("reports/test-quality.json",),
) -> QaBrainFineTuneReadinessRow:
    return QaBrainFineTuneReadinessRow(
        case_id=cast(Any, case_id),
        label=case_id.replace("_", " ").title(),
        readiness=cast(Any, readiness),
        source_ids=source_ids,
        source_paths=source_paths,
        readiness_stage=(
            "metadata_ready"
            if readiness == "ready"
            else "needs_repair"
            if readiness == "attention"
            else "needs_evidence"
        ),
        evidence_coverage="Stable evidence IDs are present.",
        prompt_plan_completeness="Prompt-plan metadata is complete.",
        safety_boundary="Provider-free metadata only.",
        eval_case_coverage="Covers the eval case.",
        redaction_boundary="No secrets, headers, cookies, tokens, or bodies.",
        deterministic_acceptance="Evidence IDs are present.",
        blockers=blockers,
        next_action="Use readiness metadata.",
    )


def _readiness_packet(
    rows: tuple[QaBrainFineTuneReadinessRow, ...],
    *,
    status: str = "ready",
) -> QaBrainFineTuneReadinessPacket:
    ready = sum(1 for row in rows if row.readiness == "ready")
    missing = sum(1 for row in rows if row.readiness == "missing")
    attention = sum(1 for row in rows if row.readiness == "attention")
    blockers_total = sum(len(row.blockers) for row in rows)
    actions = tuple(
        QaBrainFineTuneReadinessNextAction(
            priority="high" if row.readiness == "attention" else "medium",
            action=row.next_action,
            case_ids=(row.case_id,),
        )
        for row in rows
        if row.readiness != "ready" or row.blockers
    )
    return QaBrainFineTuneReadinessPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="readiness-project",
        prompt_plan_schema_version="entroping.qa-brain-prompt-plan.v1",
        summary=QaBrainFineTuneReadinessSummary(
            status=cast(Any, status),
            readiness_total=len(rows),
            readiness_ready=ready,
            readiness_missing=missing,
            readiness_attention=attention,
            blockers_total=blockers_total,
            next_actions_total=len(actions),
        ),
        readiness_rows=rows,
        next_actions=actions,
    )


def test_qa_brain_model_packaging_plan_writes_valid_json_without_prior_readiness_report(
    tmp_path: Path,
) -> None:
    # The real fine-tune readiness builder must provide one value-free missing
    # row per canonical QA Brain eval slice even without a prior JSON artifact.
    result = run_qa_brain_model_packaging_plan_report(
        project_root=tmp_path,
        output="json",
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == (
        tmp_path / "reports" / "qa-brain-model-packaging-plan.json"
    )
    assert not (tmp_path / "reports" / "qa-brain-fine-tune-readiness.json").exists()
    assert payload["schema_version"] == QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION
    assert payload["fine_tune_readiness_schema_version"] == (
        QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION
    )
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["plans_total"] == len(payload["packaging_plans"])
    assert payload["summary"]["plans_ready"] == 0
    assert payload["summary"]["plans_missing"] == payload["summary"]["plans_total"]
    assert {row["case_id"] for row in payload["packaging_plans"]} == set(_EVAL_IDS)


def test_qa_brain_model_packaging_plan_derives_ready_rows_without_raw_values(
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

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.packaging_plans}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert rows["weak_test_detection"].readiness == "ready"
    assert rows["weak_test_detection"].packaging_stage == "packaging_ready"
    assert rows["weak_test_detection"].deployment_modes == (
        "hosted",
        "local",
        "enterprise",
    )
    assert "LiteLLM" in rows["weak_test_detection"].litellm_routing_boundary
    assert rows["api_drift_reasoning"].readiness == "ready"
    assert rows["mutation_fuzz_readiness"].readiness == "ready"
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_model_packaging_plan_preserves_attention_and_blockers(
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

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.packaging_plans}

    assert packet.summary.status == "partial"
    assert packet.summary.plans_attention == 2
    assert packet.summary.blockers_total >= 2
    assert rows["bogus_evidence"].readiness == "attention"
    assert rows["bogus_evidence"].packaging_stage == "needs_boundary_repair"
    assert rows["bogus_evidence"].blockers
    assert next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    ).priority == "high"
    assert all("999" not in " ".join(row.source_paths) for row in packet.packaging_plans)
    assert all("999" not in " ".join(row.blockers) for row in packet.packaging_plans)


def test_qa_brain_model_packaging_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_model_packaging_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Model Packaging Plan" in markdown
    assert "- Schema: `entroping.qa-brain-model-packaging-plan.v1`" in markdown
    assert "- Fine-tune readiness schema: `entroping.qa-brain-fine-tune-readiness.v1`" in (
        markdown
    )
    assert "| weak_test_detection | Weak-test detection | ready | packaging_ready |" in (
        markdown
    )
    assert "reports/test-quality.json" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_model_packaging_plan_markdown_escapes_cells_and_inline_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet(
            (
                _readiness_row(
                    "weak_test_detection",
                    readiness="missing",
                    source_ids=(),
                    source_paths=(),
                ),
            ),
            status="insufficient",
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "packaging_plans": (
                packet.packaging_plans[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "artifact_boundary": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_model_packaging_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_model_packaging_plan_reports_insufficient_for_empty_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet((), status="insufficient")

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.plans_total == 0
    assert packet.next_actions == ()


def test_qa_brain_model_packaging_plan_reports_ready_when_all_rows_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet(tuple(_readiness_row(eval_id) for eval_id in _EVAL_IDS))

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)
    markdown = render_qa_brain_model_packaging_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.plans_ready == packet.summary.plans_total
    assert packet.next_actions == ()
    assert "No QA brain model-packaging plan actions are currently needed." in markdown


def test_qa_brain_model_packaging_plan_blocks_inherited_readiness_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet(
            (
                _readiness_row(
                    "weak_test_detection",
                    blockers=("Complete prompt-plan metadata before dataset design.",),
                ),
            ),
            status="partial",
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)
    row = packet.packaging_plans[0]

    assert packet.summary.status == "partial"
    assert packet.summary.blockers_total == 1
    assert packet.summary.next_actions_total == 1
    assert row.packaging_stage == "needs_boundary_repair"
    assert row.blockers == ("Complete prompt-plan metadata before dataset design.",)


def test_qa_brain_model_packaging_plan_deduplicates_next_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet(
            (
                _readiness_row("weak_test_detection", readiness="missing"),
                _readiness_row("weak_test_detection", readiness="attention"),
            ),
            status="partial",
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    packet = build_qa_brain_model_packaging_plan(project_root=tmp_path)

    assert len(packet.packaging_plans) == 2
    assert tuple(action.case_ids for action in packet.next_actions) == (
        ("weak_test_detection",),
    )


def test_qa_brain_model_packaging_plan_rejects_unsupported_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        QaBrainModelPackagingPlanError,
        match="Unsupported qa-brain-model-packaging-plan output",
    ):
        run_qa_brain_model_packaging_plan_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )


def test_qa_brain_model_packaging_plan_wraps_readiness_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fail_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        raise QaBrainFineTuneReadinessError("QA brain readiness source is unsafe")

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fail_readiness)

    with pytest.raises(QaBrainModelPackagingPlanError, match="source is unsafe"):
        build_qa_brain_model_packaging_plan(project_root=tmp_path)


def test_qa_brain_model_packaging_plan_rejects_unknown_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            readiness_rows=(
                QaBrainFineTuneReadinessRow.model_construct(
                    case_id="new_eval",
                    label="New eval",
                    readiness="ready",
                    source_ids=(),
                    source_paths=(),
                    readiness_stage="metadata_ready",
                    evidence_coverage="Stable evidence IDs are present.",
                    prompt_plan_completeness="Prompt-plan metadata is complete.",
                    safety_boundary="Provider-free metadata only.",
                    eval_case_coverage="Covers the eval case.",
                    redaction_boundary="No secrets.",
                    deterministic_acceptance="Evidence IDs are present.",
                    blockers=(),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    with pytest.raises(
        QaBrainModelPackagingPlanError,
        match="missing endpoint_boundary metadata for new_eval",
    ):
        build_qa_brain_model_packaging_plan(project_root=tmp_path)


def test_qa_brain_model_packaging_plan_rejects_missing_stage_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet((_readiness_row("weak_test_detection"),))

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)
    monkeypatch.setattr(packaging_plan, "_PACKAGING_STAGES", {})

    with pytest.raises(
        QaBrainModelPackagingPlanError,
        match="missing packaging_stage metadata for ready",
    ):
        build_qa_brain_model_packaging_plan(project_root=tmp_path)


def test_qa_brain_model_packaging_plan_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainModelPackagingPlanError, match="path must stay under"):
        run_qa_brain_model_packaging_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-model-packaging-plan.json",
        )


def test_qa_brain_model_packaging_plan_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-model-packaging-plan.json"

    result = run_qa_brain_model_packaging_plan_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert output_path.exists()


def test_qa_brain_model_packaging_plan_build_rejects_secret_like_packet_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    secret_marker = _provider_token_fixture()

    def fake_readiness(*, project_root: Path) -> QaBrainFineTuneReadinessPacket:
        _ = project_root
        return _readiness_packet(
            (
                _readiness_row(
                    "weak_test_detection",
                    source_ids=(secret_marker,),
                ),
            )
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_fine_tune_readiness", fake_readiness)

    with pytest.raises(
        QaBrainModelPackagingPlanError,
        match="contains secret-like content",
    ):
        build_qa_brain_model_packaging_plan(project_root=tmp_path)


def test_qa_brain_model_packaging_plan_writer_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_model_packaging_plan as packaging_plan

    secret_marker = _provider_token_fixture()

    def fake_build(*, project_root: Path) -> object:
        _ = project_root
        return packaging_plan.QaBrainModelPackagingPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="unsafe-project",
            fine_tune_readiness_schema_version=(
                QA_BRAIN_FINE_TUNE_READINESS_SCHEMA_VERSION
            ),
            summary=packaging_plan.QaBrainModelPackagingPlanSummary(
                status="ready",
                plans_total=1,
                plans_ready=1,
                plans_missing=0,
                plans_attention=0,
                blockers_total=0,
                next_actions_total=0,
            ),
            packaging_plans=(
                packaging_plan.QaBrainModelPackagingPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    source_ids=(secret_marker,),
                    source_paths=("reports/test-quality.json",),
                    packaging_stage="packaging_ready",
                    endpoint_boundary="OpenAI-compatible endpoint planning only.",
                    litellm_routing_boundary="Route through LiteLLM later.",
                    deployment_modes=("hosted", "local", "enterprise"),
                    artifact_boundary="No model artifacts are produced.",
                    access_control_audit="Access control design is required.",
                    blockers=(),
                    next_action="Use metadata only.",
                ),
            ),
            next_actions=(),
        )

    monkeypatch.setattr(packaging_plan, "build_qa_brain_model_packaging_plan", fake_build)

    with pytest.raises(
        QaBrainModelPackagingPlanError,
        match="contains secret-like content",
    ):
        run_qa_brain_model_packaging_plan_report(project_root=tmp_path, output="json")
