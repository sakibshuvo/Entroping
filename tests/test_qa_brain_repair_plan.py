"""Tests for deterministic QA brain repair-plan packets."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from entroping.core.plan.qa_brain_repair_plan import (
    QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION,
    QaBrainRepairPlanError,
    QaBrainRepairPlanNextAction,
    QaBrainRepairPlanPacket,
    QaBrainRepairPlanRow,
    QaBrainRepairPlanSource,
    QaBrainRepairPlanSummary,
    build_qa_brain_repair_plan,
    render_qa_brain_repair_plan_markdown,
    run_qa_brain_repair_plan_report,
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

_GATE_IDS = (
    "parser_validation",
    "hurl_execution",
    "qanstitution_governance",
    "deterministic_evidence",
    "secret_redaction",
    "codex_human_review",
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _provider_token_fixture() -> str:
    return "sk-" + "proj-" + "secretmarker0123456789"


def _routing_plan_payload() -> dict[str, object]:
    return {
        "schema_version": "entroping.qa-brain-routing-plan.v1",
        "summary": {
            "status": "ready",
            "routes_total": len(_EVAL_IDS),
            "routes_ready": len(_EVAL_IDS),
        },
        "routing_plans": [
            {
                "case_id": eval_id,
                "repair_acceptance_gates": [
                    {"id": gate_id, "required": True} for gate_id in _GATE_IDS
                ],
            }
            for eval_id in _EVAL_IDS
        ],
    }


def _write_ready_sources(tmp_path: Path, *, secret_marker: str | None = None) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 82, "generated_tests": 3},
            "tests": [{"stderr": f"Authorization: Bearer {secret_marker}"}]
            if secret_marker
            else [],
        },
    )
    _write_json(
        reports / "mutation-readiness.json",
        {
            "schema_version": "entroping.mutation-readiness.v1",
            "summary": {"status": "partial", "candidate_categories_total": 2},
        },
    )
    _write_json(
        reports / "evidence-action-plan.json",
        {
            "schema_version": "entroping.evidence-action-plan.v1",
            "summary": {"status": "partial", "actions_total": 2},
        },
    )
    _write_json(
        reports / "evidence-index.json",
        {
            "schema_version": "entroping.evidence-index.v1",
            "summary": {"status": "partial", "artifacts_present": 4},
        },
    )
    _write_json(reports / "qa-brain-routing-plan.json", _routing_plan_payload())


def test_qa_brain_repair_plan_writes_valid_json_without_prior_reports(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_repair_plan_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))

    assert result.output_path == tmp_path / "reports" / "qa-brain-repair-plan.json"
    assert not (tmp_path / "reports" / "qa-brain-routing-plan.json").exists()
    assert payload["schema_version"] == QA_BRAIN_REPAIR_PLAN_SCHEMA_VERSION
    assert payload["summary"]["status"] == "insufficient"
    assert payload["summary"]["repair_plans_total"] == len(_EVAL_IDS)
    assert payload["summary"]["repair_plans_ready"] == 0
    assert {row["case_id"] for row in payload["repair_plans"]} == set(_EVAL_IDS)
    assert all(source["state"] == "missing" for source in payload["sources"])


def test_qa_brain_repair_plan_markdown_lists_missing_next_actions(
    tmp_path: Path,
) -> None:
    result = run_qa_brain_repair_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "## Next Actions" in markdown
    assert "| Priority | Action | Cases |" in markdown
    assert "Add value-free evidence and routing acceptance gates" in markdown


def test_qa_brain_repair_plan_derives_ready_rows_without_raw_values(
    tmp_path: Path,
) -> None:
    secret_marker = _provider_token_fixture()
    _write_ready_sources(tmp_path, secret_marker=secret_marker)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.repair_plans}
    rendered = packet.model_dump_json()

    assert packet.summary.status == "ready"
    assert rows["unsafe_generated_hurl"].readiness == "ready"
    assert rows["unsafe_generated_hurl"].repair_intent == "repair"
    assert rows["unsafe_generated_hurl"].acceptance_gate_ids == _GATE_IDS
    assert rows["weak_test_detection"].source_ids
    assert secret_marker not in rendered
    assert "generated_tests" not in rendered


def test_qa_brain_repair_plan_adds_ready_repair_proposal_dry_run_checklist(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    checklist = {item.case_id: item for item in packet.repair_proposal_dry_run_checklist}
    item = checklist["unsafe_generated_hurl"]

    assert item.prerequisite_status == "ready"
    assert item.readiness == "ready"
    assert item.acceptance_gate_status == "ready"
    assert item.next_action_label == "repair-proposal-dry-run"
    assert tuple(
        (artifact.source_id, artifact.status) for artifact in item.artifact_statuses
    ) == (
        ("test-quality-json", "present"),
        ("mutation-readiness-json", "present"),
        ("qa-brain-routing-plan-json", "present"),
    )


def test_qa_brain_repair_plan_marks_partial_repair_proposal_dry_run_checklist(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80},
        },
    )
    _write_json(reports / "qa-brain-routing-plan.json", _routing_plan_payload())

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    checklist = {item.case_id: item for item in packet.repair_proposal_dry_run_checklist}
    item = checklist["weak_test_detection"]

    assert item.prerequisite_status == "partial"
    assert item.readiness == "ready"
    assert item.acceptance_gate_status == "ready"
    assert item.next_action_label == "add-value-free-evidence"
    assert tuple(
        (artifact.source_id, artifact.status) for artifact in item.artifact_statuses
    ) == (
        ("test-quality-json", "present"),
        ("evidence-action-plan-json", "missing"),
        ("qa-brain-routing-plan-json", "present"),
    )


def test_qa_brain_repair_plan_marks_missing_repair_proposal_dry_run_checklist(
    tmp_path: Path,
) -> None:
    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    checklist = {item.case_id: item for item in packet.repair_proposal_dry_run_checklist}
    item = checklist["weak_test_detection"]

    assert item.prerequisite_status == "missing"
    assert item.readiness == "missing"
    assert item.acceptance_gate_status == "missing"
    assert item.next_action_label == "add-value-free-evidence"
    assert tuple(
        (artifact.source_id, artifact.status) for artifact in item.artifact_statuses
    ) == (
        ("test-quality-json", "missing"),
        ("evidence-action-plan-json", "missing"),
        ("qa-brain-routing-plan-json", "missing"),
    )


def test_qa_brain_repair_plan_reports_partial_when_some_rows_are_ready(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80},
        },
    )
    routing = _routing_plan_payload()
    routing_plans = cast(list[dict[str, object]], routing["routing_plans"])
    routing["routing_plans"] = [routing_plans[0]]
    _write_json(reports / "qa-brain-routing-plan.json", routing)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.repair_plans}

    assert packet.summary.status == "partial"
    assert rows["weak_test_detection"].readiness == "ready"
    assert rows["missing_gate_discovery"].readiness == "missing"


def test_qa_brain_repair_plan_markdown_is_human_readable_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_qa_brain_repair_plan_report(project_root=tmp_path, output="md")
    markdown = result.output_path.read_text(encoding="utf-8")

    assert "# Entroping QA Brain Repair Plan" in markdown
    assert "- Schema: `entroping.qa-brain-repair-plan.v1`" in markdown
    assert "Repair Proposal Dry-Run Checklist" in markdown
    assert "repair-proposal-dry-run" in markdown
    assert "Repair Plans" in markdown
    assert "parser_validation, hurl_execution, qanstitution_governance" in markdown
    assert "reports/qa-brain-routing-plan.json" in markdown
    assert "generated_tests" not in markdown


def test_qa_brain_repair_plan_marks_symlinked_routing_source_unsafe(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(reports / "test-quality.json", _routing_plan_payload())
    outside = tmp_path.parent / "qa-routing-outside.json"
    outside.write_text(
        json.dumps({**_routing_plan_payload(), "raw": "outside-999"}),
        encoding="utf-8",
    )
    (reports / "qa-brain-routing-plan.json").symlink_to(outside)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    routing_source = next(
        source for source in packet.sources if source.id == "qa-brain-routing-plan-json"
    )

    assert routing_source.state == "unsafe"
    assert packet.summary.status == "partial"
    assert all(row.readiness == "attention" for row in packet.repair_plans)
    assert "outside-999" not in packet.model_dump_json()


def test_qa_brain_repair_plan_marks_secret_like_routing_source_unsafe(
    tmp_path: Path,
) -> None:
    secret_marker = _provider_token_fixture()
    payload = {**_routing_plan_payload(), "raw": secret_marker}
    _write_json(tmp_path / "reports" / "qa-brain-routing-plan.json", payload)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    routing_source = next(
        source for source in packet.sources if source.id == "qa-brain-routing-plan-json"
    )

    assert routing_source.state == "unsafe"
    assert secret_marker not in packet.model_dump_json()


@pytest.mark.parametrize(
    ("raw_bytes", "expected_summary"),
    (
        (b"\xff", "invalid JSON"),
        (b"{not-json", "invalid JSON"),
        (b"[]", "invalid JSON"),
        (
            json.dumps({"schema_version": "entroping.other.v1"}).encode("utf-8"),
            "schema mismatch",
        ),
    ),
)
def test_qa_brain_repair_plan_marks_malformed_routing_source_invalid(
    tmp_path: Path,
    raw_bytes: bytes,
    expected_summary: str,
) -> None:
    path = tmp_path / "reports" / "qa-brain-routing-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw_bytes)

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    routing_source = next(
        source for source in packet.sources if source.id == "qa-brain-routing-plan-json"
    )

    assert routing_source.state == "invalid"
    assert routing_source.summary == expected_summary


def test_qa_brain_repair_plan_handles_value_free_routing_edge_shapes(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "qa-brain-routing-plan.json",
        {
            "schema_version": "entroping.qa-brain-routing-plan.v1",
            "routing_plans": [
                [],
                {"case_id": "unknown_case"},
                {
                    "case_id": "weak_test_detection",
                    "repair_acceptance_gates": [
                        [],
                        {"id": "bad_gate"},
                        {"id": "parser_validation"},
                        {"id": "parser_validation"},
                    ],
                },
            ],
        },
    )

    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    rows = {row.case_id: row for row in packet.repair_plans}
    routing_source = next(
        source for source in packet.sources if source.id == "qa-brain-routing-plan-json"
    )

    assert routing_source.summary == "QA brain routing plan present"
    assert rows["weak_test_detection"].acceptance_gate_ids == ("parser_validation",)
    assert rows["missing_gate_discovery"].acceptance_gate_ids == ()


def test_qa_brain_repair_plan_rejects_unsupported_output(tmp_path: Path) -> None:
    with pytest.raises(
        QaBrainRepairPlanError,
        match="Unsupported qa-brain-repair-plan output",
    ):
        run_qa_brain_repair_plan_report(
            project_root=tmp_path,
            output=cast(Any, "html"),
        )


def test_qa_brain_repair_plan_rejects_output_paths_outside_project(
    tmp_path: Path,
) -> None:
    with pytest.raises(QaBrainRepairPlanError, match="path must stay under"):
        run_qa_brain_repair_plan_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "qa-brain-repair-plan.json",
        )


def test_qa_brain_repair_plan_build_rejects_secret_like_packet_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_repair_plan as repair_plan

    secret_marker = _provider_token_fixture()

    def fake_sources_and_gates(
        *,
        root: Path,
    ) -> tuple[
        tuple[QaBrainRepairPlanSource, ...],
        dict[str, tuple[str, ...]],
    ]:
        _ = root
        return (
            (
                QaBrainRepairPlanSource(
                    id="test-quality-json",
                    label="Generated-Test Quality JSON",
                    path="reports/test-quality.json",
                    state="present",
                    schema_version="entroping.test-quality-report.v1",
                    summary=secret_marker,
                ),
            ),
            {},
        )

    monkeypatch.setattr(repair_plan, "_sources_and_routing_gates", fake_sources_and_gates)

    with pytest.raises(QaBrainRepairPlanError, match="contains secret-like content"):
        build_qa_brain_repair_plan(project_root=tmp_path)


def test_qa_brain_repair_plan_writer_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_repair_plan as repair_plan

    secret_marker = _provider_token_fixture()
    packet = QaBrainRepairPlanPacket(
        generated_at="2026-06-21T00:00:00+00:00",
        project="unsafe-project",
        routing_plan_schema_version="entroping.qa-brain-routing-plan.v1",
        summary=QaBrainRepairPlanSummary(
            status="ready",
            sources_total=1,
            sources_present=1,
            sources_missing=0,
            sources_invalid=0,
            sources_unsafe=0,
            repair_plans_total=1,
            repair_plans_ready=1,
            repair_plans_missing=0,
            repair_plans_attention=0,
            blockers_total=0,
            next_actions_total=0,
        ),
        sources=(
            QaBrainRepairPlanSource(
                id="test-quality-json",
                label="Generated-Test Quality JSON",
                path="reports/test-quality.json",
                state="present",
                schema_version="entroping.test-quality-report.v1",
                summary=secret_marker,
            ),
        ),
        repair_plans=(
            QaBrainRepairPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="ready",
                repair_intent="review",
                source_ids=("test-quality-json",),
                source_paths=("reports/test-quality.json",),
                acceptance_gate_ids=("parser_validation",),
                blockers=(),
                next_action="Use metadata.",
            ),
        ),
        next_actions=(),
    )

    def fake_build(*, project_root: Path) -> QaBrainRepairPlanPacket:
        _ = project_root
        return packet

    monkeypatch.setattr(repair_plan, "build_qa_brain_repair_plan", fake_build)

    with pytest.raises(QaBrainRepairPlanError, match="contains secret-like content"):
        run_qa_brain_repair_plan_report(project_root=tmp_path, output="json")


def test_qa_brain_repair_plan_handles_missing_index_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_repair_plan as repair_plan

    monkeypatch.setattr(repair_plan, "build_local_evidence_index", lambda *, project_root: ())

    packet = build_qa_brain_repair_plan(project_root=tmp_path)

    assert all(source.state == "missing" for source in packet.sources)


def test_qa_brain_repair_plan_summary_dedupes_duplicate_blockers() -> None:
    import entroping.core.plan.qa_brain_repair_plan as repair_plan

    rows = (
        QaBrainRepairPlanRow(
            case_id="weak_test_detection",
            label="Weak-test detection",
            readiness="missing",
            repair_intent="review",
            blockers=("Shared blocker.", "Row-specific blocker."),
            next_action="Add evidence.",
        ),
        QaBrainRepairPlanRow(
            case_id="missing_gate_discovery",
            label="Missing-gate discovery",
            readiness="missing",
            repair_intent="generate",
            blockers=("Shared blocker.",),
            next_action="Add gates.",
        ),
    )

    summary = repair_plan._summary(sources=(), repair_plans=rows, next_actions=())

    assert summary.blockers_total == 2
    assert rows[0].blockers == ("Shared blocker.", "Row-specific blocker.")
    assert rows[1].blockers == ("Shared blocker.",)


def test_qa_brain_repair_plan_defensive_helpers() -> None:
    import entroping.core.plan.qa_brain_repair_plan as repair_plan

    low = QaBrainRepairPlanRow(
        case_id="weak_test_detection",
        label="Weak-test detection",
        readiness="missing",
        repair_intent="review",
        next_action="Add evidence.",
    )
    actions = repair_plan._next_actions((low,))

    assert repair_plan._load_failure_state("artifact too large") == "invalid"
    assert repair_plan._routing_summary({"summary": {"status": "partial"}}) == (
        "partial routing plan"
    )
    assert repair_plan._routing_gates_by_case({"routing_plans": {}}) == {}
    assert repair_plan._repair_gate_ids({}) == ()
    assert actions == (
        QaBrainRepairPlanNextAction(
            priority="medium",
            action="Add evidence.",
            case_ids=("weak_test_detection",),
        ),
    )
    assert not repair_plan._contains_unredacted_packet_secret_like_value(
        json.dumps({"sha256": "a" * 64})
    )
    assert repair_plan._contains_unredacted_packet_secret_like_value(
        json.dumps({"api_key": _provider_token_fixture()})
    )


def test_qa_brain_repair_plan_markdown_escapes_cells(tmp_path: Path) -> None:
    _write_ready_sources(tmp_path)
    packet = build_qa_brain_repair_plan(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "project": "project `tick`",
            "repair_plans": (
                packet.repair_plans[0].model_copy(
                    update={"label": "Label | with `tick`"}
                ),
            ),
        }
    )

    markdown = render_qa_brain_repair_plan_markdown(escaped)

    assert "- Project: `project &#96;tick&#96;`" in markdown
    assert "Label \\| with &#96;tick&#96;" in markdown
    assert "`tick`" not in markdown
