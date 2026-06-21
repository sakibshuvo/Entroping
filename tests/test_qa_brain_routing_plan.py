"""Tests for deterministic QA brain routing-plan packets."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from entroping.core.qa_brain_model_packaging_plan import (
    QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION,
    QaBrainModelPackagingPlanError,
    QaBrainModelPackagingPlanNextAction,
    QaBrainModelPackagingPlanPacket,
    QaBrainModelPackagingPlanRow,
    QaBrainModelPackagingPlanSummary,
)
from entroping.core.qa_brain_routing_plan import (
    QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION,
    QaBrainRoutingPlanError,
    build_qa_brain_routing_plan,
    render_qa_brain_routing_plan_markdown,
    run_qa_brain_routing_plan_report,
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


def _packaging_row(
    case_id: str,
    *,
    readiness: str = "ready",
    packaging_stage: str = "packaging_ready",
    blockers: tuple[str, ...] = (),
    source_ids: tuple[str, ...] = ("test-quality-json",),
    source_paths: tuple[str, ...] = ("reports/test-quality.json",),
) -> QaBrainModelPackagingPlanRow:
    return QaBrainModelPackagingPlanRow(
        case_id=cast(Any, case_id),
        label=case_id.replace("_", " ").title(),
        readiness=cast(Any, readiness),
        source_ids=source_ids,
        source_paths=source_paths,
        packaging_stage=cast(Any, packaging_stage),
        endpoint_boundary="OpenAI-compatible endpoint planning only.",
        litellm_routing_boundary="Future routing must stay behind LiteLLM.",
        deployment_modes=("hosted", "local", "enterprise"),
        artifact_boundary="No model artifacts are produced.",
        access_control_audit="Access control and audit evidence is required.",
        blockers=blockers,
        next_action="Use model packaging metadata.",
    )


def _packaging_packet(
    rows: tuple[QaBrainModelPackagingPlanRow, ...],
    *,
    status: str = "ready",
) -> QaBrainModelPackagingPlanPacket:
    ready = sum(1 for row in rows if row.packaging_stage == "packaging_ready")
    missing = sum(
        1 for row in rows if row.packaging_stage == "needs_readiness_evidence"
    )
    attention = sum(1 for row in rows if row.packaging_stage == "needs_boundary_repair")
    blockers_total = sum(len(row.blockers) for row in rows)
    actions = tuple(
        QaBrainModelPackagingPlanNextAction(
            priority="high"
            if row.packaging_stage == "needs_boundary_repair"
            else "medium",
            action=row.next_action,
            case_ids=(row.case_id,),
        )
        for row in rows
        if row.packaging_stage != "packaging_ready" or row.blockers
    )
    return QaBrainModelPackagingPlanPacket(
        generated_at="2026-06-20T00:00:00+00:00",
        project="packaging-project",
        fine_tune_readiness_schema_version="entroping.qa-brain-fine-tune-readiness.v1",
        summary=QaBrainModelPackagingPlanSummary(
            status=cast(Any, status),
            plans_total=len(rows),
            plans_ready=ready,
            plans_missing=missing,
            plans_attention=attention,
            blockers_total=blockers_total,
            next_actions_total=len(actions),
        ),
        packaging_plans=rows,
        next_actions=actions,
    )


def test_qa_brain_routing_plan_writes_valid_json_without_prior_packaging_report(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_routing_plan_report(
        project_root=tmp_path,
        output="json",
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-routing-plan.json"
    assert not (tmp_path / "reports" / "qa-brain-model-packaging-plan.json").exists()
    assert payload["schema_version"] == QA_BRAIN_ROUTING_PLAN_SCHEMA_VERSION
    assert payload["model_packaging_plan_schema_version"] == (
        QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION
    )
    assert payload["project"] == tmp_path.name
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["routes_total"] == len(payload["routing_plans"])
    assert payload["summary"]["routes_ready"] == 0
    assert payload["summary"]["routes_missing"] == payload["summary"]["routes_total"]
    assert {row["case_id"] for row in payload["routing_plans"]} == set(_EVAL_IDS)


def test_qa_brain_routing_plan_derives_ready_rows_without_raw_values(
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

    packet = build_qa_brain_routing_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.routing_plans}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "partial"
    assert rows["weak_test_detection"].readiness == "ready"
    assert rows["weak_test_detection"].packaging_stage == "packaging_ready"
    assert rows["weak_test_detection"].routing_stage == "routing_design_ready"
    assert rows["weak_test_detection"].allowed_use_cases == (
        "critique",
        "generation",
        "prioritization",
        "repair_proposals",
    )
    assert tuple(
        gate.id for gate in rows["weak_test_detection"].repair_acceptance_gates
    ) == (
        "parser_validation",
        "hurl_execution",
        "qanstitution_governance",
        "deterministic_evidence",
        "secret_redaction",
        "codex_human_review",
    )
    assert all(gate.required for gate in rows["weak_test_detection"].repair_acceptance_gates)
    assert rows["weak_test_detection"].deployment_modes == (
        "hosted",
        "local",
        "enterprise",
    )
    assert "LiteLLM" in rows["weak_test_detection"].litellm_boundary
    assert "Hurl/QAnstitution" in rows["weak_test_detection"].forbidden_authority
    assert rows["api_drift_reasoning"].routing_stage == "routing_design_ready"
    assert rows["mutation_fuzz_readiness"].routing_stage == "routing_design_ready"
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_routing_plan_preserves_attention_and_blockers(
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

    packet = build_qa_brain_routing_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.routing_plans}

    assert packet.summary.status == "partial"
    assert packet.summary.routes_attention == 2
    assert packet.summary.blockers_total >= 2
    assert rows["bogus_evidence"].readiness == "attention"
    assert rows["bogus_evidence"].routing_stage == "needs_boundary_repair"
    assert rows["bogus_evidence"].blockers
    assert next(
        action for action in packet.next_actions if action.case_ids == ("bogus_evidence",)
    ).priority == "high"
    assert "999" not in packet.model_dump_json()


def test_qa_brain_routing_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80, "generated_tests": 2},
        },
    )

    result = run_qa_brain_routing_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Routing Plan" in markdown
    assert "- Schema: `entroping.qa-brain-routing-plan.v1`" in markdown
    assert (
        "- Model-packaging plan schema: "
        "`entroping.qa-brain-model-packaging-plan.v1`"
    ) in markdown
    assert (
        "| weak_test_detection | Weak-test detection | ready | packaging_ready | "
        "routing_design_ready |"
    ) in markdown
    assert "Repair Acceptance Gates" in markdown
    assert (
        "parser_validation, hurl_execution, qanstitution_governance, "
        "deterministic_evidence, secret_redaction, codex_human_review"
    ) in markdown
    assert "reports/test-quality.json" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_routing_plan_markdown_escapes_cells_and_inline_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            (
                _packaging_row(
                    "weak_test_detection",
                    readiness="missing",
                    packaging_stage="needs_readiness_evidence",
                    source_ids=(),
                    source_paths=(),
                ),
            ),
            status="insufficient",
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "routing_plans": (
                packet.routing_plans[0].model_copy(
                    update={
                        "label": "Label | with `tick`",
                        "litellm_boundary": "line one\nline two | `cell`",
                    }
                ),
            ),
        }
    )

    markdown = render_qa_brain_routing_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "line one line two \\| &#96;cell&#96;" in markdown
    assert "`cell`" not in markdown


def test_qa_brain_routing_plan_reports_insufficient_for_empty_packaging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet((), status="insufficient")

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.routes_total == 0
    assert packet.next_actions == ()


def test_qa_brain_routing_plan_reports_ready_when_all_rows_are_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            tuple(_packaging_row(eval_id) for eval_id in _EVAL_IDS)
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)
    markdown = render_qa_brain_routing_plan_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.routes_ready == packet.summary.routes_total
    assert packet.next_actions == ()
    assert "No QA brain routing-plan actions are currently needed." in markdown


def test_qa_brain_routing_plan_blocks_inherited_packaging_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            (
                _packaging_row(
                    "weak_test_detection",
                    blockers=("Complete packaging metadata before routing design.",),
                ),
            ),
            status="partial",
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)
    row = packet.routing_plans[0]

    assert packet.summary.status == "partial"
    assert packet.summary.blockers_total == 1
    assert packet.summary.next_actions_total == 1
    assert row.routing_stage == "needs_boundary_repair"
    assert row.blockers == ("Complete packaging metadata before routing design.",)


def test_qa_brain_routing_plan_omits_repair_gates_without_repair_use_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet((_packaging_row("weak_test_detection"),))

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )
    monkeypatch.setattr(
        routing_plan,
        "_ALLOWED_USE_CASES",
        {"weak_test_detection": ("critique",)},
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)

    assert packet.routing_plans[0].allowed_use_cases == ("critique",)
    assert packet.routing_plans[0].repair_acceptance_gates == ()


def test_qa_brain_routing_plan_deduplicates_next_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            (
                _packaging_row(
                    "weak_test_detection",
                    readiness="missing",
                    packaging_stage="needs_readiness_evidence",
                ),
                _packaging_row(
                    "weak_test_detection",
                    readiness="attention",
                    packaging_stage="needs_boundary_repair",
                ),
            ),
            status="partial",
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    packet = build_qa_brain_routing_plan(project_root=tmp_path)

    assert len(packet.routing_plans) == 2
    assert tuple(action.case_ids for action in packet.next_actions) == (
        ("weak_test_detection",),
    )
    assert tuple(action.priority for action in packet.next_actions) == ("high",)
    assert "Repair Weak Test Detection" in packet.next_actions[0].action

    def fake_packaging_high_first(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            (
                _packaging_row(
                    "weak_test_detection",
                    readiness="attention",
                    packaging_stage="needs_boundary_repair",
                ),
                _packaging_row(
                    "weak_test_detection",
                    readiness="missing",
                    packaging_stage="needs_readiness_evidence",
                ),
            ),
            status="partial",
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging_high_first,
    )

    high_first_packet = build_qa_brain_routing_plan(project_root=tmp_path)

    assert tuple(action.case_ids for action in high_first_packet.next_actions) == (
        ("weak_test_detection",),
    )
    assert tuple(action.priority for action in high_first_packet.next_actions) == ("high",)
    assert "Repair Weak Test Detection" in high_first_packet.next_actions[0].action


def test_qa_brain_routing_plan_defensive_next_action_fallback() -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    assert routing_plan._plan_next_action(
        row=_packaging_row("weak_test_detection"),
        routing_stage=cast(Any, "unexpected_internal_stage"),
    ) == "Resolve Weak Test Detection blockers before future routing design."


def test_qa_brain_routing_plan_rejects_unsupported_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        QaBrainRoutingPlanError,
        match="Unsupported qa-brain-routing-plan output",
    ):
        run_qa_brain_routing_plan_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )


def test_qa_brain_routing_plan_wraps_packaging_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fail_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        raise QaBrainModelPackagingPlanError("QA brain packaging source is unsafe")

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fail_packaging,
    )

    with pytest.raises(QaBrainRoutingPlanError, match="source is unsafe"):
        build_qa_brain_routing_plan(project_root=tmp_path)


def test_qa_brain_routing_plan_rejects_unknown_case_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> SimpleNamespace:
        _ = project_root
        return SimpleNamespace(
            packaging_plans=(
                QaBrainModelPackagingPlanRow.model_construct(
                    case_id="new_eval",
                    label="New eval",
                    readiness="ready",
                    source_ids=(),
                    source_paths=(),
                    packaging_stage="packaging_ready",
                    endpoint_boundary="OpenAI-compatible endpoint planning only.",
                    litellm_routing_boundary="Route through LiteLLM later.",
                    deployment_modes=("hosted", "local", "enterprise"),
                    artifact_boundary="No model artifacts are produced.",
                    access_control_audit="Access control design is required.",
                    blockers=(),
                    next_action="Use evidence.",
                ),
            )
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    with pytest.raises(
        QaBrainRoutingPlanError,
        match="missing allowed_use_cases metadata for new_eval",
    ):
        build_qa_brain_routing_plan(project_root=tmp_path)


def test_qa_brain_routing_plan_rejects_missing_stage_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet((_packaging_row("weak_test_detection"),))

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )
    monkeypatch.setattr(routing_plan, "_ROUTING_STAGES", {})

    with pytest.raises(
        QaBrainRoutingPlanError,
        match="missing routing_stage metadata for packaging_ready",
    ):
        build_qa_brain_routing_plan(project_root=tmp_path)


def test_qa_brain_routing_plan_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainRoutingPlanError, match="path must stay under"):
        run_qa_brain_routing_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-routing-plan.json",
        )


def test_qa_brain_routing_plan_writes_custom_output_path_inside_project(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "custom" / "qa-brain-routing-plan.json"

    result = run_qa_brain_routing_plan_report(
        project_root=tmp_path,
        output="json",
        output_path=output_path,
    )

    assert result.output_path == output_path
    assert output_path.exists()


def test_qa_brain_routing_plan_build_rejects_secret_like_packet_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    secret_marker = _provider_token_fixture()

    def fake_packaging(*, project_root: Path) -> QaBrainModelPackagingPlanPacket:
        _ = project_root
        return _packaging_packet(
            (
                _packaging_row(
                    "weak_test_detection",
                    source_ids=(secret_marker,),
                ),
            )
        )

    monkeypatch.setattr(
        routing_plan,
        "build_qa_brain_model_packaging_plan",
        fake_packaging,
    )

    with pytest.raises(
        QaBrainRoutingPlanError,
        match="contains secret-like content",
    ):
        build_qa_brain_routing_plan(project_root=tmp_path)


def test_qa_brain_routing_plan_writer_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.qa_brain_routing_plan as routing_plan

    secret_marker = _provider_token_fixture()

    def fake_build(*, project_root: Path) -> object:
        _ = project_root
        return routing_plan.QaBrainRoutingPlanPacket(
            generated_at="2026-06-20T00:00:00+00:00",
            project="unsafe-project",
            model_packaging_plan_schema_version=(
                QA_BRAIN_MODEL_PACKAGING_PLAN_SCHEMA_VERSION
            ),
            summary=routing_plan.QaBrainRoutingPlanSummary(
                status="ready",
                routes_total=1,
                routes_ready=1,
                routes_missing=0,
                routes_attention=0,
                blockers_total=0,
                next_actions_total=0,
            ),
            routing_plans=(
                routing_plan.QaBrainRoutingPlanRow(
                    case_id="weak_test_detection",
                    label="Weak-test detection",
                    readiness="ready",
                    packaging_stage="packaging_ready",
                    source_ids=(secret_marker,),
                    source_paths=("reports/test-quality.json",),
                    routing_stage="routing_design_ready",
                    litellm_boundary="Route through LiteLLM later.",
                    endpoint_boundary="OpenAI-compatible endpoint planning only.",
                    deployment_modes=("hosted", "local", "enterprise"),
                    allowed_use_cases=(
                        "critique",
                        "generation",
                        "prioritization",
                        "repair_proposals",
                    ),
                    repair_acceptance_gates=(
                        routing_plan.QaBrainRepairAcceptanceGate(
                            id="parser_validation",
                            label="Parser validation",
                            required=True,
                            summary=(
                                "Parse proposed Hurl and policy changes before "
                                "review."
                            ),
                        ),
                    ),
                    forbidden_authority="Hurl/QAnstitution remains authority.",
                    access_control_audit="Access control design is required.",
                    blockers=(),
                    next_action="Use metadata only.",
                ),
            ),
            next_actions=(),
        )

    monkeypatch.setattr(routing_plan, "build_qa_brain_routing_plan", fake_build)

    with pytest.raises(
        QaBrainRoutingPlanError,
        match="contains secret-like content",
    ):
        run_qa_brain_routing_plan_report(project_root=tmp_path, output="json")
