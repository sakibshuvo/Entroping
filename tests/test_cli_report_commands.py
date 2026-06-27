"""CLI adapter tests for report commands."""

from cli_test_support import (
    BinaryIO,
    CliRunner,
    Path,
    ReportWriterError,
    RunReport,
    RunReportSummary,
    RunTestReport,
    _record_freeze_exchange,
    _record_mock_exchange,
    app,
    json,
    pytest,
    report_cli,
    subprocess,
    write_json_report,
)

from entroping.bridge.capture_summary import (
    CaptureSummaryReport,
    CaptureSummaryTotals,
    capture_summary_report_to_dict,
    render_capture_summary_markdown,
)
from entroping.bridge.redaction_review import (
    RedactionReviewReport,
    render_redaction_review_html,
    render_redaction_review_markdown,
)
from entroping.core.api_inventory import ApiInventoryError
from entroping.core.capture_summary_report import CaptureSummaryResult
from entroping.core.connector_intent import ConnectorIntentError
from entroping.core.design_partner_feedback import DesignPartnerFeedbackError
from entroping.core.devex_readiness import DevexReadinessError
from entroping.core.evidence_action_plan import EvidenceActionPlanError
from entroping.core.evidence_bundle import EvidenceBundleError
from entroping.core.evidence_cloud_dashboard import EvidenceCloudDashboardError
from entroping.core.evidence_cloud_export import EvidenceCloudExportError
from entroping.core.evidence_cloud_readiness import EvidenceCloudReadinessError
from entroping.core.evidence_cloud_workspace import EvidenceCloudWorkspaceError
from entroping.core.evidence_index_report import EvidenceIndexError
from entroping.core.evidence_links import EvidenceLinksError
from entroping.core.evidence_portal import EvidencePortalError
from entroping.core.handoff_packet import HandoffError
from entroping.core.integration_readiness import IntegrationReadinessError
from entroping.core.mutation_readiness import MutationReadinessError
from entroping.core.notification_packet import NotificationPacketError
from entroping.core.observability_adapter_readiness import (
    ObservabilityAdapterReadinessError,
)
from entroping.core.observability_packet import ObservabilityPacketError
from entroping.core.otel_mapping import OtelMappingError
from entroping.core.pilot_cohort import PilotCohortError
from entroping.core.pilot_metrics import PilotMetricsError
from entroping.core.pilot_outcome import PilotOutcomeError
from entroping.core.pr_evidence_card import PrEvidenceCardError
from entroping.core.qa_brain_eval_plan import QaBrainEvalPlanError
from entroping.core.qa_brain_fine_tune_readiness import (
    QaBrainFineTuneReadinessError,
)
from entroping.core.qa_brain_model_packaging_plan import (
    QaBrainModelPackagingPlanError,
)
from entroping.core.qa_brain_prompt_plan import QaBrainPromptPlanError
from entroping.core.qa_brain_repair_plan import QaBrainRepairPlanError
from entroping.core.qa_brain_retrieval_plan import QaBrainRetrievalPlanError
from entroping.core.qa_brain_routing_plan import QaBrainRoutingPlanError
from entroping.core.qa_brain_seed import QaBrainSeedError
from entroping.core.redaction_review_report import RedactionReviewResult
from entroping.core.report_artifact_manifest import write_report_artifact_manifest
from entroping.core.runtime_card import RuntimeCardError
from entroping.core.team_access_control_plan import TeamAccessControlPlanError
from entroping.core.team_evidence_readiness import TeamEvidenceReadinessError
from entroping.core.work_item_draft import WorkItemDraftError
from entroping.core.work_item_import_bundle import WorkItemImportBundleError


def _write_effective_policy_report(
    path: Path,
    *,
    imports: tuple[str, ...] = (),
    gates: tuple[dict[str, object], ...] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": list(imports),
                "gates": list(gates),
            }
        ),
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_pilot_outcome_packet(
    path: Path,
    *,
    project: str = "checkout-api",
    status: str = "ready",
    hosted: str = "yes",
    policy: str = "no",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.pilot-outcome.v1",
                "generated_at": "2026-06-21T00:00:00+00:00",
                "project": project,
                "summary": {
                    "status": status,
                    "sources_total": 5,
                    "sources_present": 5,
                    "sources_missing": 0,
                    "sources_invalid": 0,
                    "sources_unsafe": 0,
                    "manual_input_gaps": 0,
                    "monetization_yes": 1 if hosted == "yes" else 0,
                    "monetization_no": 1 if hosted == "no" else 0,
                    "monetization_unclear": 1 if hosted == "unclear" else 0,
                    "actions_total": 0,
                    "actions_high": 0,
                    "actions_medium": 0,
                    "actions_low": 0,
                },
                "sources": [],
                "pilot_evidence_readiness": {
                    "design_partner_feedback_status": "ready",
                    "pilot_metrics_status": "ready",
                    "runtime_card_status": "pass",
                    "evidence_cloud_status": "ready",
                    "work_item_import_status": status,
                },
                "manual_input_gaps": [],
                "monetization_signals": [
                    {
                        "id": "hosted_aggregation",
                        "answer": hosted,
                        "manual_reason_required": False,
                    },
                    {
                        "id": "premium_policy_packs",
                        "answer": policy,
                        "manual_reason_required": False,
                    },
                ],
                "actions": [],
            }
        ),
        encoding="utf-8",
    )


def _write_ready_evidence_bundle_inputs(root: Path) -> None:
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-18T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        root / "reports" / "run-latest.json",
    )
    _write_effective_policy_report(root / "reports" / "effective-policy.json")
    write_report_artifact_manifest(project_root=root)


def _write_complete_artifact_manifest_inputs(root: Path) -> None:
    artifacts = {
        "reports/agent-bundle.json": '{"schema_version":"entroping.agent-review-bundle.v1"}\n',
        "reports/run-latest.json": '{"schema_version":"entroping.run-report.v1"}\n',
        "reports/run-plan.json": '{"schema_version":"entroping.run-plan.v1"}\n',
        "reports/junit.xml": '<testsuite tests="1"></testsuite>\n',
        "reports/run-latest.html": (
            "<!doctype html><html><body><h1>Entroping Run Report</h1></body></html>\n"
        ),
        "reports/drift.json": '{"schema_version":"entroping.drift-report.v1"}\n',
        "reports/entroping.sarif": '{"version":"2.1.0","runs":[]}\n',
        "reports/review-summary.md": "# Entroping Review Summary\n\n- Status: `pass`\n",
        "reports/test-quality.json": '{"schema_version":"entroping.test-quality-report.v1"}\n',
        "reports/test-quality.md": "# Entroping Generated-Test Quality Score\n",
    }
    for path, content in artifacts.items():
        _write_text(root / path, content)


def _capture_summary_with_unredacted_records(record_count: int = 1) -> CaptureSummaryReport:
    return CaptureSummaryReport(
        summary=CaptureSummaryTotals(
            total_records=record_count,
            total_sessions=1,
            redacted_records=0,
            unredacted_records=record_count,
        ),
        sessions=(),
        methods=(),
        hosts=(),
        dependency_targets=(),
        status_families=(),
        redaction_categories=(),
    )


def _redaction_review_with_unsafe_records(
    *,
    unredacted_records: int,
    low_confidence_records: int,
) -> RedactionReviewReport:
    return RedactionReviewReport(
        total_records=max(unredacted_records, low_confidence_records, 1),
        redacted_records=0 if unredacted_records else 1,
        unredacted_records=unredacted_records,
        low_confidence_records=low_confidence_records,
        request_count=max(unredacted_records, low_confidence_records, 1),
        response_count=0,
    )


def test_report_help_classifies_launch_stable_experimental_and_maintainer_commands() -> None:
    result = CliRunner().invoke(app, ["report", "--help"])

    assert result.exit_code == 0
    panels = (
        "Launch-Critical Reports",
        "Stable Public Reports",
        "Maintainer And Baseline Tools",
        "Experimental Design-Partner Evidence",
    )
    for panel in panels:
        assert panel in result.output
    panel_offsets = [result.output.index(panel) for panel in panels]
    assert panel_offsets == sorted(panel_offsets)

    launch_panel = result.output.split("Launch-Critical Reports", maxsplit=1)[1].split(
        "Stable Public Reports",
        maxsplit=1,
    )[0]
    for command in (
        "bug",
        "failure-bundle",
        "runtime-card",
        "review-summary",
    ):
        assert command in launch_panel

    stable_panel = result.output.split("Stable Public Reports", maxsplit=1)[1].split(
        "Maintainer And Baseline Tools",
        maxsplit=1,
    )[0]
    for command in (
        "delta",
        "policy",
        "policy-diff",
        "gate-coverage",
        "traceability",
        "github-annotations",
        "sarif",
    ):
        assert command in stable_panel

    maintainer_panel = result.output.split("Maintainer And Baseline Tools", maxsplit=1)[1].split(
        "Experimental Design-Partner Evidence",
        maxsplit=1,
    )[0]
    for command in (
        "badges",
        "gate-injection",
        "test-quality",
        "artifact-manifest",
        "promote-drift-baseline",
    ):
        assert command in maintainer_panel

    experimental_panel = result.output.split(
        "Experimental Design-Partner Evidence",
        maxsplit=1,
    )[1]
    for command in (
        "evidence-bundle",
        "design-partner-feedback",
        "handoff",
        "notification-packet",
        "integration-readiness",
        "devex-readiness",
        "evidence-cloud-readiness",
        "evidence-cloud-export",
        "evidence-cloud-workspace",
        "evidence-links",
        "evidence-portal",
        "connector-intent",
        "evidence-action-plan",
        "work-item-draft",
        "work-item-import-bundle",
        "external-test-evidence",
        "team-access-control-plan",
        "team-evidence-readiness",
        "observability-packet",
        "otel-mapping",
        "observability-adapter-readiness",
        "api-inventory",
        "mutation-readiness",
        "pilot-metrics",
        "pilot-outcome",
        "pilot-cohort",
        "agent-bundle",
    ):
        assert command in experimental_panel


def test_report_evidence_bundle_writes_ready_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_ready_evidence_bundle_inputs(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-bundle"])

    assert result.exit_code == 0
    assert "Wrote evidence bundle: reports/evidence-bundle.json" in result.output
    payload = json.loads(Path("reports/evidence-bundle.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-bundle.v1"
    assert payload["summary"]["status"] == "ready"


def test_report_evidence_bundle_writes_markdown_when_output_path_is_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_ready_evidence_bundle_inputs(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-bundle", "--output", "reports/evidence-bundle.md"],
    )

    assert result.exit_code == 0
    assert "Wrote evidence bundle: reports/evidence-bundle.md" in result.output
    markdown = Path("reports/evidence-bundle.md").read_text(encoding="utf-8")
    assert "# Evidence Bundle" in markdown
    assert "- Status: `ready`" in markdown
    assert "reports/run-latest.json" in markdown


def test_report_evidence_bundle_exits_nonzero_when_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-bundle"])

    assert result.exit_code == 1
    assert "not_ready" in result.output
    assert Path("reports/evidence-bundle.json").exists()


def test_report_evidence_bundle_wraps_core_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_evidence_bundle(*args: object, **kwargs: object) -> object:
        raise EvidenceBundleError("evidence bundle path is unsafe")

    monkeypatch.setattr(report_cli, "run_evidence_bundle_report", fail_evidence_bundle)

    result = CliRunner().invoke(app, ["report", "evidence-bundle"])

    assert result.exit_code == 1
    assert "evidence bundle path is unsafe" in result.output


def test_report_design_partner_feedback_writes_sanitized_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "design-partner-feedback"])

    assert result.exit_code == 0
    assert (
        "Wrote design-partner feedback artifact: reports/design-partner-feedback.json"
    ) in result.output
    payload = json.loads(Path("reports/design-partner-feedback.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.design-partner-feedback.v1"
    assert payload["evidence"]["evidence_bundle_status"] == "missing"
    assert payload["evidence"]["runtime_card_status"] == "missing"
    assert payload["feedback"]["setup_friction"] is None
    assert "provider_output" not in json.dumps(payload)


def test_report_design_partner_feedback_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_design_partner_feedback(*args: object, **kwargs: object) -> object:
        raise DesignPartnerFeedbackError("design-partner feedback path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_design_partner_feedback_report",
        fail_design_partner_feedback,
    )

    result = CliRunner().invoke(app, ["report", "design-partner-feedback"])

    assert result.exit_code == 1
    assert "design-partner feedback path is unsafe" in result.output


def test_report_runtime_card_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
  "tests": []
}
""",
    )
    _write_text(
        Path("reports") / "capture-summary.json",
        """
{
  "schema_version": "entroping.capture-summary.v1",
  "summary": {
    "total_records": 1,
    "total_sessions": 1,
    "redacted_records": 1,
    "unredacted_records": 0
  },
  "redaction_categories": []
}
""",
    )
    _write_text(
        Path("reports") / "artifact-manifest.json",
        """
{
  "schema_version": "entroping.report-artifact-manifest.v1",
  "audit": {"verification": {"status": "verified"}}
}
""",
    )
    _write_text(
        Path("reports") / "evidence-bundle.json",
        """
{
  "schema_version": "entroping.evidence-bundle.v1",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "purpose": "design-partner-upload-readiness",
  "project": "checkout-api",
  "summary": {
    "status": "ready",
    "required_total": 2,
    "required_present": 2,
    "required_missing": 0,
    "required_invalid": 0,
    "artifacts_total": 2,
    "diagnostics_total": 0
  },
  "artifacts": [],
  "missing_artifacts": [],
  "diagnostics": [],
  "manifest_audit": {
    "path": "reports/artifact-manifest.json",
    "status": "verified",
    "chain_path": ".entroping/report-audit-chain.jsonl",
    "checked_events": 1,
    "latest_event_hash": "0",
    "diagnostics": []
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card"])

    assert result.exit_code == 0
    assert "Wrote runtime evidence card: reports/runtime-card.md" in result.output
    card = Path("reports/runtime-card.md").read_text(encoding="utf-8")
    assert "# Entroping Runtime Evidence Card" in card
    assert "- Status: `pass`" in card


def test_report_runtime_card_exits_nonzero_without_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
  "tests": []
}
""",
    )
    _write_text(
        Path("reports") / "capture-summary.json",
        """
{
  "schema_version": "entroping.capture-summary.v1",
  "summary": {
    "total_records": 1,
    "total_sessions": 1,
    "redacted_records": 1,
    "unredacted_records": 0
  },
  "redaction_categories": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(Path("reports/runtime-card.json").read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "attention"
    assert {
        ("missing_artifact_manifest", "reports/artifact-manifest.json"),
        ("missing_evidence_bundle", "reports/evidence-bundle.json"),
    } <= {(finding["code"], finding["path"]) for finding in payload["findings"]}


def test_report_runtime_card_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-18T00:00:00+00:00",
  "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
  "tests": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "json"])

    assert result.exit_code == 1
    assert "Wrote runtime evidence card: reports/runtime-card.json" in result.output
    payload = json.loads(Path("reports/runtime-card.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.runtime-card.v1"
    assert payload["summary"]["status"] == "fail"


def test_report_runtime_card_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "runtime-card", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported runtime card output" in result.output


def test_report_runtime_card_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_runtime_card(*args: object, **kwargs: object) -> object:
        raise RuntimeCardError("runtime card source evidence is unsafe")

    monkeypatch.setattr(report_cli, "run_runtime_card_report", fail_runtime_card)

    result = CliRunner().invoke(app, ["report", "runtime-card"])

    assert result.exit_code == 1
    assert "runtime card source evidence is unsafe" in result.output


def test_report_pilot_metrics_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "checkout-api",
  "environment": "ci",
  "generated_at": "2026-06-19T00:00:00+00:00",
  "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
  "tests": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "pilot-metrics"])

    assert result.exit_code == 0
    assert "Wrote pilot metrics report: reports/pilot-metrics.md" in result.output
    markdown = Path("reports/pilot-metrics.md").read_text(encoding="utf-8")
    assert "# Entroping Pilot Metrics" in markdown
    assert "manual_input_required" in markdown


def test_report_pilot_metrics_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "pilot-metrics", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote pilot metrics report: reports/pilot-metrics.json" in result.output
    payload = json.loads(Path("reports/pilot-metrics.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pilot-metrics.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_pilot_metrics_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "pilot-metrics", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported pilot metrics output" in result.output
    assert not Path("reports/pilot-metrics.html").exists()


def test_report_pilot_metrics_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_pilot_metrics(*args: object, **kwargs: object) -> object:
        raise PilotMetricsError("pilot metrics path is unsafe")

    monkeypatch.setattr(report_cli, "run_pilot_metrics_report", fail_pilot_metrics)

    result = CliRunner().invoke(app, ["report", "pilot-metrics"])

    assert result.exit_code == 1
    assert "pilot metrics path is unsafe" in result.output


def test_report_pilot_outcome_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "pilot-outcome"])

    assert result.exit_code == 0, result.output
    assert "Wrote pilot outcome packet: reports/pilot-outcome.md" in result.output
    markdown = Path("reports/pilot-outcome.md").read_text(encoding="utf-8")
    assert "# Entroping Pilot Outcome" in markdown
    assert "Generate Design-partner feedback" in markdown


def test_report_pilot_outcome_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "pilot-outcome", "--output", "json"])

    assert result.exit_code == 0, result.output
    assert "Wrote pilot outcome packet: reports/pilot-outcome.json" in result.output
    payload = json.loads(Path("reports/pilot-outcome.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pilot-outcome.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_pilot_outcome_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "pilot-outcome", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported pilot-outcome output" in result.output
    assert not Path("reports/pilot-outcome.html").exists()


def test_report_pilot_outcome_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_pilot_outcome(*args: object, **kwargs: object) -> object:
        raise PilotOutcomeError("pilot outcome path is unsafe")

    monkeypatch.setattr(report_cli, "run_pilot_outcome_report", fail_pilot_outcome)

    result = CliRunner().invoke(app, ["report", "pilot-outcome"])

    assert result.exit_code == 1
    assert "pilot outcome path is unsafe" in result.output


def test_report_pilot_cohort_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pilot_outcome_packet(Path("reports") / "pilot-a.json")
    _write_text(
        Path("reports") / "pilot-cohort-manifest.json",
        """
{
  "schema_version": "entroping.pilot-cohort-manifest.v1",
  "outcomes": [{"id": "pilot-a", "path": "reports/pilot-a.json"}]
}
""",
    )

    result = CliRunner().invoke(
        app,
        ["report", "pilot-cohort", "--manifest", "reports/pilot-cohort-manifest.json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote pilot cohort packet: reports/pilot-cohort.md" in result.output
    markdown = Path("reports/pilot-cohort.md").read_text(encoding="utf-8")
    assert "# Entroping Pilot Cohort" in markdown
    assert "checkout-api" in markdown


def test_report_pilot_cohort_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pilot_outcome_packet(Path("reports") / "pilot-a.json")
    _write_text(
        Path("reports") / "pilot-cohort-manifest.json",
        """
{
  "schema_version": "entroping.pilot-cohort-manifest.v1",
  "outcomes": [{"id": "pilot-a", "path": "reports/pilot-a.json"}]
}
""",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "pilot-cohort",
            "--manifest",
            "reports/pilot-cohort-manifest.json",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote pilot cohort packet: reports/pilot-cohort.json" in result.output
    payload = json.loads(Path("reports/pilot-cohort.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pilot-cohort.v1"
    assert payload["summary"]["outcomes_present"] == 1


def test_report_pilot_cohort_requires_manifest() -> None:
    result = CliRunner().invoke(app, ["report", "pilot-cohort"])

    assert result.exit_code == 2
    assert "Usage:" in result.output
    assert "pilot-cohort" in result.output


def test_report_pilot_cohort_rejects_unsupported_output(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_text(
        manifest,
        """
{
  "schema_version": "entroping.pilot-cohort-manifest.v1",
  "outcomes": [{"id": "pilot-a", "path": "reports/pilot-a.json"}]
}
""",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "pilot-cohort",
            "--manifest",
            str(manifest),
            "--output",
            "html",
        ],
    )

    assert result.exit_code == 2
    assert "Unsupported pilot-cohort output" in result.output
    assert not Path("reports/pilot-cohort.html").exists()


def test_report_pilot_cohort_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_pilot_cohort(*args: object, **kwargs: object) -> object:
        raise PilotCohortError("pilot cohort path is unsafe")

    monkeypatch.setattr(report_cli, "run_pilot_cohort_report", fail_pilot_cohort)

    result = CliRunner().invoke(
        app,
        ["report", "pilot-cohort", "--manifest", "reports/pilot-cohort-manifest.json"],
    )

    assert result.exit_code == 1
    assert "pilot cohort path is unsafe" in result.output


def test_report_handoff_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "runtime-card.json",
        """
{
  "schema_version": "entroping.runtime-card.v1",
  "summary": {"status": "pass", "findings": 0, "evidence_links": 1},
  "run": {"project": "checkout-api", "failed_gate_ids": []},
  "pilot_readiness": {"status": "ready"},
  "test_pyramid": {"status": "complete"}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "handoff"])

    assert result.exit_code == 0
    assert "Wrote evidence handoff packet: reports/handoff.md" in result.output
    markdown = Path("reports/handoff.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Handoff" in markdown
    assert "| runtime_card | present | reports/runtime-card.json |" in markdown


def test_report_handoff_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "handoff", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote evidence handoff packet: reports/handoff.json" in result.output
    payload = json.loads(Path("reports/handoff.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.handoff.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_handoff_fail_on_insufficient_fails_after_writing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "handoff", "--fail-on-insufficient"])

    assert result.exit_code == 1
    assert "Handoff packet has no present evidence artifacts." in result.output
    assert Path("reports/handoff.md").exists()


def test_report_handoff_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "handoff", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported handoff output" in result.output
    assert not Path("reports/handoff.html").exists()


def test_report_handoff_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_handoff(*args: object, **kwargs: object) -> object:
        raise HandoffError("handoff source evidence is unsafe")

    monkeypatch.setattr(report_cli, "run_handoff_report", fail_handoff)

    result = CliRunner().invoke(app, ["report", "handoff"])

    assert result.exit_code == 1
    assert "handoff source evidence is unsafe" in result.output


def test_report_notification_packet_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "handoff.json",
        """
{
  "schema_version": "entroping.handoff.v1",
  "generated_at": "2026-06-20T00:00:00+00:00",
  "project": "checkout-api",
  "git": {"branch": "main", "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
  "summary": {
    "status": "ready",
    "artifacts_total": 0,
    "artifacts_present": 0,
    "artifacts_missing": 0,
    "artifacts_invalid": 0,
    "artifacts_unsafe": 0
  },
  "runtime": null,
  "artifacts": [],
  "targets": []
}
""",
    )

    result = CliRunner().invoke(app, ["report", "notification-packet"])

    assert result.exit_code == 0
    assert "Wrote notification packet: reports/notification-packet.md" in result.output
    markdown = Path("reports/notification-packet.md").read_text(encoding="utf-8")
    assert "# Entroping Notification Packet" in markdown
    assert "| jira |" in markdown


def test_report_notification_packet_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "notification-packet", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote notification packet: reports/notification-packet.json" in result.output
    payload = json.loads(Path("reports/notification-packet.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.notification-packet.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_notification_packet_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "notification-packet", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported notification-packet output" in result.output
    assert not Path("reports/notification-packet.html").exists()


def test_report_notification_packet_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_notification_packet(*args: object, **kwargs: object) -> object:
        raise NotificationPacketError("notification packet path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_notification_packet_report",
        fail_notification_packet,
    )

    result = CliRunner().invoke(app, ["report", "notification-packet"])

    assert result.exit_code == 1
    assert "notification packet path is unsafe" in result.output


def test_report_team_evidence_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "evidence-bundle.json",
        """
{
  "schema_version": "entroping.evidence-bundle.v1",
  "project": "checkout-api",
  "summary": {
    "status": "ready",
    "required_total": 3,
    "required_present": 3,
    "required_missing": 0,
    "required_invalid": 0,
    "artifacts_total": 3,
    "diagnostics_total": 0
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "team-evidence-readiness"])

    assert result.exit_code == 0
    assert ("Wrote team evidence readiness: reports/team-evidence-readiness.md") in result.output
    markdown = Path("reports/team-evidence-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping Team Evidence Readiness" in markdown
    assert "| evidence_bundle | present | reports/evidence-bundle.json |" in markdown


def test_report_team_evidence_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "team-evidence-readiness", "--output", "json"],
    )

    assert result.exit_code == 0
    assert ("Wrote team evidence readiness: reports/team-evidence-readiness.json") in result.output
    payload = json.loads(Path("reports/team-evidence-readiness.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.team-evidence-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_team_evidence_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "team-evidence-readiness", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported team-evidence-readiness output" in result.output
    assert not Path("reports/team-evidence-readiness.html").exists()


def test_report_team_evidence_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_team_evidence_readiness(*args: object, **kwargs: object) -> object:
        raise TeamEvidenceReadinessError("team evidence readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_team_evidence_readiness_report",
        fail_team_evidence_readiness,
    )

    result = CliRunner().invoke(app, ["report", "team-evidence-readiness"])

    assert result.exit_code == 1
    assert "team evidence readiness path is unsafe" in result.output


def test_report_evidence_cloud_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-cloud-readiness"])

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud readiness: reports/evidence-cloud-readiness.md" in (result.output)
    markdown = Path("reports/evidence-cloud-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Cloud Readiness" in markdown
    assert "| team_evidence_readiness | missing | reports/team-evidence-readiness.json |" in (
        markdown
    )


def test_report_evidence_cloud_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-readiness", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud readiness: reports/evidence-cloud-readiness.json" in (
        result.output
    )
    payload = json.loads(Path("reports/evidence-cloud-readiness.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-cloud-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_cloud_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-readiness", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-cloud-readiness output" in result.output
    assert not Path("reports/evidence-cloud-readiness.html").exists()


def test_report_evidence_cloud_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_cloud_readiness(*args: object, **kwargs: object) -> object:
        raise EvidenceCloudReadinessError("evidence cloud readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_cloud_readiness_report",
        fail_evidence_cloud_readiness,
    )

    result = CliRunner().invoke(app, ["report", "evidence-cloud-readiness"])

    assert result.exit_code == 1
    assert "evidence cloud readiness path is unsafe" in result.output


def test_report_evidence_cloud_export_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-cloud-export"])

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud export: reports/evidence-cloud-export.md" in result.output
    markdown = Path("reports/evidence-cloud-export.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Cloud Export" in markdown
    assert "| evidence-portal-json | missing | reports/evidence-portal.json |" in markdown


def test_report_evidence_cloud_export_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-export", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud export: reports/evidence-cloud-export.json" in result.output
    payload = json.loads(Path("reports/evidence-cloud-export.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-cloud-export.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_cloud_export_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-export", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-cloud-export output" in result.output
    assert not Path("reports/evidence-cloud-export.html").exists()


def test_report_evidence_cloud_export_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_cloud_export(*args: object, **kwargs: object) -> object:
        raise EvidenceCloudExportError("evidence cloud export path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_cloud_export_report",
        fail_evidence_cloud_export,
    )

    result = CliRunner().invoke(app, ["report", "evidence-cloud-export"])

    assert result.exit_code == 1
    assert "evidence cloud export path is unsafe" in result.output


def test_report_evidence_cloud_workspace_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = Path("reports") / "evidence-cloud-export.json"
    _write_text(
        manifest,
        """
        {
          "schema_version": "entroping.evidence-cloud-export.v1",
          "generated_at": "2026-06-21T00:00:00+00:00",
          "project": "checkout-api",
          "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "export_items_total": 1,
            "export_items_ready": 1,
            "export_items_blocked": 0,
            "boundary_controls_total": 1,
            "next_actions_total": 0
          },
          "sources": [],
          "export_items": [],
          "boundary_controls": [
            {
              "id": "explicit_upload_only",
              "label": "Explicit upload only",
              "enforced": true,
              "summary": "This manifest never uploads artifacts."
            }
          ],
          "next_actions": []
        }
        """,
    )

    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-workspace", "--manifest", str(manifest)],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud workspace: reports/evidence-cloud-workspace.md" in result.output
    markdown = Path("reports/evidence-cloud-workspace.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Cloud Workspace" in markdown
    assert "| checkout-api | ready | 1/1 | 1/1 |" in markdown


def test_report_evidence_cloud_workspace_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = Path("reports") / "evidence-cloud-export.json"
    _write_text(
        manifest,
        """
        {
          "schema_version": "entroping.evidence-cloud-export.v1",
          "generated_at": "2026-06-21T00:00:00+00:00",
          "project": "checkout-api",
          "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "export_items_total": 1,
            "export_items_ready": 1,
            "export_items_blocked": 0,
            "boundary_controls_total": 1,
            "next_actions_total": 0
          },
          "sources": [],
          "export_items": [],
          "boundary_controls": [],
          "next_actions": []
        }
        """,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-workspace",
            "--manifest",
            str(manifest),
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud workspace: reports/evidence-cloud-workspace.json" in result.output
    payload = json.loads(Path("reports/evidence-cloud-workspace.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-cloud-workspace.v1"
    assert payload["summary"]["status"] == "ready"


def test_report_evidence_cloud_workspace_requires_manifest() -> None:
    result = CliRunner().invoke(app, ["report", "evidence-cloud-workspace"])

    assert result.exit_code == 2
    assert "Missing option" in result.output


def test_report_evidence_cloud_workspace_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-workspace",
            "--manifest",
            "reports/evidence-cloud-export.json",
            "--output",
            "html",
        ],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-cloud-workspace output" in result.output
    assert not Path("reports/evidence-cloud-workspace.html").exists()


def test_report_evidence_cloud_workspace_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_cloud_workspace(*args: object, **kwargs: object) -> object:
        raise EvidenceCloudWorkspaceError("workspace manifest path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_cloud_workspace_report",
        fail_evidence_cloud_workspace,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-workspace",
            "--manifest",
            "reports/evidence-cloud-export.json",
        ],
    )

    assert result.exit_code == 1
    assert "workspace manifest path is unsafe" in result.output


def test_report_evidence_cloud_dashboard_writes_static_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = Path("reports") / "evidence-cloud-export.json"
    _write_text(
        manifest,
        """
        {
          "schema_version": "entroping.evidence-cloud-export.v1",
          "generated_at": "2026-06-21T00:00:00+00:00",
          "project": "checkout-api",
          "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "export_items_total": 1,
            "export_items_ready": 1,
            "export_items_blocked": 0,
            "boundary_controls_total": 1,
            "next_actions_total": 0
          },
          "sources": [],
          "export_items": [],
          "boundary_controls": [
            {
              "id": "explicit_upload_only",
              "label": "Explicit upload only",
              "enforced": true,
              "summary": "This manifest never uploads artifacts."
            }
          ],
          "next_actions": []
        }
        """,
    )

    result = CliRunner().invoke(
        app,
        ["report", "evidence-cloud-dashboard", "--manifest", str(manifest)],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud dashboard: reports/evidence-cloud-dashboard.html" in (
        result.output
    )
    html = Path("reports/evidence-cloud-dashboard.html").read_text(encoding="utf-8")
    assert "<h1>Entroping Evidence Cloud Dashboard</h1>" in html
    assert "checkout-api" in html


def test_report_evidence_cloud_dashboard_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = Path("reports") / "evidence-cloud-export.json"
    _write_text(
        manifest,
        """
        {
          "schema_version": "entroping.evidence-cloud-export.v1",
          "generated_at": "2026-06-21T00:00:00+00:00",
          "project": "checkout-api",
          "summary": {
            "status": "ready",
            "sources_total": 1,
            "sources_present": 1,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "export_items_total": 1,
            "export_items_ready": 1,
            "export_items_blocked": 0,
            "boundary_controls_total": 1,
            "next_actions_total": 0
          },
          "sources": [],
          "export_items": [],
          "boundary_controls": [],
          "next_actions": []
        }
        """,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-dashboard",
            "--manifest",
            str(manifest),
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote Evidence Cloud dashboard: reports/evidence-cloud-dashboard.json" in (
        result.output
    )
    payload = json.loads(Path("reports/evidence-cloud-dashboard.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-cloud-dashboard.v1"
    assert payload["workspace_schema_version"] == "entroping.evidence-cloud-workspace.v1"


def test_report_evidence_cloud_dashboard_requires_manifest() -> None:
    result = CliRunner().invoke(app, ["report", "evidence-cloud-dashboard"])

    assert result.exit_code == 2
    assert "Missing option" in result.output


def test_report_evidence_cloud_dashboard_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-dashboard",
            "--manifest",
            "reports/evidence-cloud-export.json",
            "--output",
            "md",
        ],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-cloud-dashboard output" in result.output
    assert not Path("reports/evidence-cloud-dashboard.md").exists()


def test_report_evidence_cloud_dashboard_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_cloud_dashboard(*args: object, **kwargs: object) -> object:
        raise EvidenceCloudDashboardError("dashboard manifest path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_cloud_dashboard_report",
        fail_evidence_cloud_dashboard,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "evidence-cloud-dashboard",
            "--manifest",
            "reports/evidence-cloud-export.json",
        ],
    )

    assert result.exit_code == 1
    assert "dashboard manifest path is unsafe" in result.output


def test_report_evidence_links_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-links"])

    assert result.exit_code == 0, result.output
    assert "Wrote evidence links: reports/evidence-links.md" in result.output
    markdown = Path("reports/evidence-links.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Links" in markdown
    assert "| evidence-index-json | missing | reports/evidence-index.json |" in markdown


def test_report_evidence_links_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-links", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote evidence links: reports/evidence-links.json" in result.output
    payload = json.loads(Path("reports/evidence-links.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-links.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_links_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "evidence-links", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-links output" in result.output
    assert not Path("reports/evidence-links.html").exists()


def test_report_evidence_links_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_links(*args: object, **kwargs: object) -> object:
        raise EvidenceLinksError("evidence links path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_links_report",
        fail_evidence_links,
    )

    result = CliRunner().invoke(app, ["report", "evidence-links"])

    assert result.exit_code == 1
    assert "evidence links path is unsafe" in result.output


def test_report_evidence_portal_writes_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-portal"])

    assert result.exit_code == 0, result.output
    assert "Wrote evidence portal: reports/evidence-portal.html" in result.output
    html = Path("reports/evidence-portal.html").read_text(encoding="utf-8")
    assert "<h1>Entroping Evidence Portal</h1>" in html
    assert "Evidence Links JSON" in html


def test_report_evidence_portal_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-portal", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote evidence portal: reports/evidence-portal.json" in result.output
    payload = json.loads(Path("reports/evidence-portal.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-portal.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_portal_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "evidence-portal", "--output", "md"],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-portal output" in result.output
    assert not Path("reports/evidence-portal.md").exists()


def test_report_evidence_portal_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_portal(*args: object, **kwargs: object) -> object:
        raise EvidencePortalError("evidence portal path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_portal_report",
        fail_evidence_portal,
    )

    result = CliRunner().invoke(app, ["report", "evidence-portal"])

    assert result.exit_code == 1
    assert "evidence portal path is unsafe" in result.output


def test_report_pr_evidence_card_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "pr-evidence-card"])

    assert result.exit_code == 0, result.output
    assert "Wrote PR evidence card: reports/pr-evidence-card.md" in result.output
    markdown = Path("reports/pr-evidence-card.md").read_text(encoding="utf-8")
    assert "# Entroping PR Evidence Card" in markdown
    assert "Runtime governance" in markdown


def test_report_pr_evidence_card_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "pr-evidence-card", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote PR evidence card: reports/pr-evidence-card.json" in result.output
    payload = json.loads(Path("reports/pr-evidence-card.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.pr-evidence-card.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_pr_evidence_card_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "pr-evidence-card", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported pr-evidence-card output" in result.output
    assert not Path("reports/pr-evidence-card.html").exists()


def test_report_pr_evidence_card_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_pr_evidence_card(*args: object, **kwargs: object) -> object:
        raise PrEvidenceCardError("PR evidence card path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_pr_evidence_card_report",
        fail_pr_evidence_card,
    )

    result = CliRunner().invoke(app, ["report", "pr-evidence-card"])

    assert result.exit_code == 1
    assert "PR evidence card path is unsafe" in result.output


def test_report_evidence_action_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-action-plan"])

    assert result.exit_code == 0, result.output
    assert "Wrote evidence action plan: reports/evidence-action-plan.md" in result.output
    markdown = Path("reports/evidence-action-plan.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Action Plan" in markdown
    assert "Generate PR Evidence Card before using the evidence action plan." in markdown


def test_report_evidence_action_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "evidence-action-plan", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote evidence action plan: reports/evidence-action-plan.json" in result.output
    payload = json.loads(Path("reports/evidence-action-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-action-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_action_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "evidence-action-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported evidence-action-plan output" in result.output
    assert not Path("reports/evidence-action-plan.html").exists()


def test_report_evidence_action_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_action_plan(*args: object, **kwargs: object) -> object:
        raise EvidenceActionPlanError("evidence action plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_action_plan_report",
        fail_evidence_action_plan,
    )

    result = CliRunner().invoke(app, ["report", "evidence-action-plan"])

    assert result.exit_code == 1
    assert "evidence action plan path is unsafe" in result.output


def test_report_work_item_draft_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "work-item-draft"])

    assert result.exit_code == 0, result.output
    assert "Wrote work item draft: reports/work-item-draft.md" in result.output
    markdown = Path("reports/work-item-draft.md").read_text(encoding="utf-8")
    assert "# Entroping Work Item Draft" in markdown
    assert "Generate Evidence Action Plan before drafting tracker work items." in markdown


def test_report_work_item_draft_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "work-item-draft", "--output", "json"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote work item draft: reports/work-item-draft.json" in result.output
    payload = json.loads(Path("reports/work-item-draft.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.work-item-draft.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_work_item_draft_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "work-item-draft", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported work-item-draft output" in result.output
    assert not Path("reports/work-item-draft.html").exists()


def test_report_work_item_draft_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_work_item_draft(*args: object, **kwargs: object) -> object:
        raise WorkItemDraftError("work item draft path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_work_item_draft_report",
        fail_work_item_draft,
    )

    result = CliRunner().invoke(app, ["report", "work-item-draft"])

    assert result.exit_code == 1
    assert "work item draft path is unsafe" in result.output


def test_report_work_item_import_bundle_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "work-item-import-bundle"])

    assert result.exit_code == 0, result.output
    assert (
        "Wrote work item import bundle: reports/work-item-import-bundle.json"
        in result.output
    )
    payload = json.loads(
        Path("reports/work-item-import-bundle.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "entroping.work-item-import-bundle.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_work_item_import_bundle_writes_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "work-item-import-bundle", "--output", "csv"],
    )

    assert result.exit_code == 0, result.output
    assert (
        "Wrote work item import bundle: reports/work-item-import-bundle.csv"
        in result.output
    )
    csv_text = Path("reports/work-item-import-bundle.csv").read_text(encoding="utf-8")
    assert csv_text.startswith("record_type,tracker_family,external_id")


def test_report_work_item_import_bundle_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "work-item-import-bundle", "--output", "md"],
    )

    assert result.exit_code == 2
    assert "Unsupported work-item-import-bundle output" in result.output
    assert not Path("reports/work-item-import-bundle.md").exists()


def test_report_work_item_import_bundle_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_work_item_import_bundle(*args: object, **kwargs: object) -> object:
        raise WorkItemImportBundleError("work item import bundle path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_work_item_import_bundle_report",
        fail_work_item_import_bundle,
    )

    result = CliRunner().invoke(app, ["report", "work-item-import-bundle"])

    assert result.exit_code == 1
    assert "work item import bundle path is unsafe" in result.output


def test_report_team_access_control_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "team-evidence-readiness.json",
        """
{
  "schema_version": "entroping.team-evidence-readiness.v1",
  "project": "checkout-api",
  "summary": {
    "status": "ready",
    "sources_total": 1,
    "sources_present": 1,
    "sources_missing": 0,
    "sources_invalid": 0,
    "sources_unsafe": 0,
    "areas_total": 1,
    "areas_ready": 1,
    "areas_attention": 0,
    "areas_blocked": 0,
    "blockers_total": 0,
    "next_actions_total": 0
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "team-access-control-plan"])

    assert result.exit_code == 0
    assert ("Wrote team access-control plan: reports/team-access-control-plan.md") in result.output
    markdown = Path("reports/team-access-control-plan.md").read_text(encoding="utf-8")
    assert "# Entroping Team Access-Control Plan" in markdown
    assert (
        "| team_evidence_readiness | present | reports/team-evidence-readiness.json |"
    ) in markdown


def test_report_team_access_control_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "team-access-control-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert (
        "Wrote team access-control plan: reports/team-access-control-plan.json"
    ) in result.output
    payload = json.loads(Path("reports/team-access-control-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.team-access-control-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_team_access_control_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "team-access-control-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported team-access-control-plan output" in result.output
    assert not Path("reports/team-access-control-plan.html").exists()


def test_report_team_access_control_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_team_access_control_plan(*args: object, **kwargs: object) -> object:
        raise TeamAccessControlPlanError("team access-control plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_team_access_control_plan_report",
        fail_team_access_control_plan,
    )

    result = CliRunner().invoke(app, ["report", "team-access-control-plan"])

    assert result.exit_code == 1
    assert "team access-control plan path is unsafe" in result.output


def test_report_integration_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "team-access-control-plan.json",
        """
{
  "schema_version": "entroping.team-access-control-plan.v1",
  "project": "checkout-api",
  "summary": {
    "status": "ready",
    "sources_total": 4,
    "sources_present": 4,
    "sources_missing": 0,
    "sources_invalid": 0,
    "sources_unsafe": 0,
    "roles_total": 5,
    "roles_ready": 5,
    "roles_attention": 0,
    "roles_blocked": 0,
    "audit_events_total": 6,
    "blockers_total": 0,
    "next_actions_total": 0
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "integration-readiness"])

    assert result.exit_code == 0
    assert "Wrote integration readiness: reports/integration-readiness.md" in result.output
    markdown = Path("reports/integration-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping Integration Readiness" in markdown
    assert "| issue_trackers |" in markdown


def test_report_integration_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "integration-readiness", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote integration readiness: reports/integration-readiness.json" in result.output
    payload = json.loads(Path("reports/integration-readiness.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.integration-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_integration_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "integration-readiness", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported integration-readiness output" in result.output
    assert not Path("reports/integration-readiness.html").exists()


def test_report_integration_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_integration_readiness(*args: object, **kwargs: object) -> object:
        raise IntegrationReadinessError("integration readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_integration_readiness_report",
        fail_integration_readiness,
    )

    result = CliRunner().invoke(app, ["report", "integration-readiness"])

    assert result.exit_code == 1
    assert "integration readiness path is unsafe" in result.output


def test_report_devex_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "runtime-card.json",
        """
{
  "schema_version": "entroping.runtime-card.v1",
  "project": "checkout-api",
  "summary": {
    "status": "pass",
    "findings": 0
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "devex-readiness"])

    assert result.exit_code == 0
    assert "Wrote developer experience readiness: reports/devex-readiness.md" in result.output
    markdown = Path("reports/devex-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping Developer Experience Readiness" in markdown
    assert "| cli |" in markdown


def test_report_devex_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "devex-readiness", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote developer experience readiness: reports/devex-readiness.json" in result.output
    payload = json.loads(Path("reports/devex-readiness.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.devex-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_devex_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "devex-readiness", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported devex-readiness output" in result.output
    assert not Path("reports/devex-readiness.html").exists()


def test_report_devex_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_devex_readiness(*args: object, **kwargs: object) -> object:
        raise DevexReadinessError("developer experience readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_devex_readiness_report",
        fail_devex_readiness,
    )

    result = CliRunner().invoke(app, ["report", "devex-readiness"])

    assert result.exit_code == 1
    assert "developer experience readiness path is unsafe" in result.output


def test_report_connector_intent_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "runtime-card.json",
        """
{
  "schema_version": "entroping.runtime-card.v1",
  "project": "checkout-api",
  "summary": {
    "status": "pass",
    "findings": 0
  }
}
""",
    )

    result = CliRunner().invoke(app, ["report", "connector-intent"])

    assert result.exit_code == 0
    assert "Wrote connector intent: reports/connector-intent.md" in result.output
    markdown = Path("reports/connector-intent.md").read_text(encoding="utf-8")
    assert "# Entroping Connector Intent" in markdown
    assert "| issue_tracker |" in markdown


def test_report_connector_intent_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "connector-intent", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote connector intent: reports/connector-intent.json" in result.output
    payload = json.loads(Path("reports/connector-intent.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.connector-intent.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_connector_intent_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "connector-intent", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported connector-intent output" in result.output
    assert not Path("reports/connector-intent.html").exists()


def test_report_connector_intent_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_connector_intent(*args: object, **kwargs: object) -> object:
        raise ConnectorIntentError("connector intent path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_connector_intent_report",
        fail_connector_intent,
    )

    result = CliRunner().invoke(app, ["report", "connector-intent"])

    assert result.exit_code == 1
    assert "connector intent path is unsafe" in result.output


def test_report_observability_packet_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path(".entroping") / "latest-diagnostics.jsonl",
        json.dumps(
            {
                "schema_version": "entroping.diagnostics.v1",
                "timestamp": "2026-06-20T00:00:00+00:00",
                "component": "doctor",
                "operation": "ci",
                "severity": "info",
                "code": "doctor.ready",
                "summary": "Doctor readiness is available.",
                "attributes": [],
            },
            sort_keys=True,
        )
        + "\n",
    )

    result = CliRunner().invoke(app, ["report", "observability-packet"])

    assert result.exit_code == 0
    assert "Wrote observability packet: reports/observability-packet.md" in result.output
    markdown = Path("reports/observability-packet.md").read_text(encoding="utf-8")
    assert "# Entroping Observability Packet" in markdown
    assert "| opentelemetry |" in markdown


def test_report_observability_packet_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "observability-packet", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote observability packet: reports/observability-packet.json" in result.output
    payload = json.loads(Path("reports/observability-packet.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.observability-packet.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_observability_packet_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "observability-packet", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported observability-packet output" in result.output
    assert not Path("reports/observability-packet.html").exists()


def test_report_observability_packet_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_observability_packet(*args: object, **kwargs: object) -> object:
        raise ObservabilityPacketError("observability packet path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_observability_packet_report",
        fail_observability_packet,
    )

    result = CliRunner().invoke(app, ["report", "observability-packet"])

    assert result.exit_code == 1
    assert "observability packet path is unsafe" in result.output


def test_report_otel_mapping_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "otel-mapping"])

    assert result.exit_code == 0
    assert "Wrote OpenTelemetry mapping packet: reports/otel-mapping.md" in result.output
    markdown = Path("reports/otel-mapping.md").read_text(encoding="utf-8")
    assert "# Entroping OpenTelemetry Mapping" in markdown
    assert "| metric | entroping.test.total | optional | count |" in markdown


def test_report_otel_mapping_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "otel-mapping", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote OpenTelemetry mapping packet: reports/otel-mapping.json" in result.output
    payload = json.loads(Path("reports/otel-mapping.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.otel-mapping.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_otel_mapping_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "otel-mapping", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported otel-mapping output" in result.output
    assert not Path("reports/otel-mapping.html").exists()


def test_report_otel_mapping_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_otel_mapping(*args: object, **kwargs: object) -> object:
        raise OtelMappingError("otel mapping path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_otel_mapping_report",
        fail_otel_mapping,
    )

    result = CliRunner().invoke(app, ["report", "otel-mapping"])

    assert result.exit_code == 1
    assert "otel mapping path is unsafe" in result.output


def test_report_observability_adapter_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "observability-adapter-readiness"])

    assert result.exit_code == 0
    assert "Wrote observability adapter readiness" in result.output
    assert "reports/observability-adapter-readiness.md" in result.output
    markdown = Path("reports/observability-adapter-readiness.md").read_text(
        encoding="utf-8"
    )
    assert "# Entroping Observability Adapter Readiness" in markdown
    assert "| opentelemetry | OpenTelemetry | attention |" in markdown


def test_report_observability_adapter_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "observability-adapter-readiness", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "reports/observability-adapter-readiness.json" in result.output
    payload = json.loads(
        Path("reports/observability-adapter-readiness.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "entroping.observability-adapter-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_observability_adapter_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "observability-adapter-readiness", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported observability-adapter-readiness output" in result.output
    assert not Path("reports/observability-adapter-readiness.html").exists()


def test_report_observability_adapter_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_adapter_readiness(*args: object, **kwargs: object) -> object:
        raise ObservabilityAdapterReadinessError("adapter readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_observability_adapter_readiness_report",
        fail_adapter_readiness,
    )

    result = CliRunner().invoke(app, ["report", "observability-adapter-readiness"])

    assert result.exit_code == 1
    assert "adapter readiness path is unsafe" in result.output


def test_report_api_inventory_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("tests") / "graphql.hurl",
        "# entroping: tags=graphql\nPOST http://127.0.0.1:18082/graphql\n",
    )

    result = CliRunner().invoke(app, ["report", "api-inventory"])

    assert result.exit_code == 0
    assert "Wrote API inventory: reports/api-inventory.md" in result.output
    markdown = Path("reports/api-inventory.md").read_text(encoding="utf-8")
    assert "# Entroping API Inventory" in markdown
    assert "| GraphQL |" in markdown


def test_report_api_inventory_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "api-inventory", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote API inventory: reports/api-inventory.json" in result.output
    payload = json.loads(Path("reports/api-inventory.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.api-inventory.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_api_inventory_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "api-inventory", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported api-inventory output" in result.output
    assert not Path("reports/api-inventory.html").exists()


def test_report_api_inventory_wraps_core_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_api_inventory(*args: object, **kwargs: object) -> object:
        raise ApiInventoryError("API inventory path is unsafe")

    monkeypatch.setattr(report_cli, "run_api_inventory_report", fail_api_inventory)

    result = CliRunner().invoke(app, ["report", "api-inventory"])

    assert result.exit_code == 1
    assert "API inventory path is unsafe" in result.output


def test_report_mutation_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("tests") / "generated" / "negative" / "schema.hurl",
        """
# entroping: tags=generated,negative
# entroping: source=openapi
# entroping: negative_category=schema-violations
# entroping: fuzz_seed=schema-seed
POST http://127.0.0.1:18080/orders
HTTP 422
[Asserts]
jsonpath "$.code" isString
""".strip()
        + "\n",
    )

    result = CliRunner().invoke(app, ["report", "mutation-readiness"])

    assert result.exit_code == 0
    assert "Wrote mutation readiness: reports/mutation-readiness.md" in result.output
    markdown = Path("reports/mutation-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping Mutation Readiness" in markdown
    assert "schema" in markdown


def test_report_mutation_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "mutation-readiness", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote mutation readiness: reports/mutation-readiness.json" in result.output
    payload = json.loads(Path("reports/mutation-readiness.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.mutation-readiness.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_mutation_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "mutation-readiness", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported mutation-readiness output" in result.output
    assert not Path("reports/mutation-readiness.html").exists()


def test_report_mutation_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_mutation_readiness(*args: object, **kwargs: object) -> object:
        raise MutationReadinessError("mutation readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_mutation_readiness_report",
        fail_mutation_readiness,
    )

    result = CliRunner().invoke(app, ["report", "mutation-readiness"])

    assert result.exit_code == 1
    assert "mutation readiness path is unsafe" in result.output


def test_report_evidence_index_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
  "tests": [{"stderr": "raw-output-should-not-render"}]
}
""",
    )

    result = CliRunner().invoke(app, ["report", "evidence-index"])

    assert result.exit_code == 0
    assert "Wrote evidence index: reports/evidence-index.md" in result.output
    markdown = Path("reports/evidence-index.md").read_text(encoding="utf-8")
    assert "# Entroping Evidence Index" in markdown
    assert "| run-json | Run JSON | present | reports/run-latest.json |" in markdown
    assert "raw-output-should-not-render" not in markdown


def test_report_evidence_index_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "evidence-index", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote evidence index: reports/evidence-index.json" in result.output
    payload = json.loads(Path("reports/evidence-index.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.evidence-index.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_evidence_index_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "evidence-index", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported evidence-index output" in result.output
    assert not Path("reports/evidence-index.html").exists()


def test_report_evidence_index_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_evidence_index(*args: object, **kwargs: object) -> object:
        raise EvidenceIndexError("evidence index path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_evidence_index_report",
        fail_evidence_index,
    )

    result = CliRunner().invoke(app, ["report", "evidence-index"])

    assert result.exit_code == 1
    assert "evidence index path is unsafe" in result.output


def test_report_qa_brain_seed_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-seed"])

    assert result.exit_code == 0
    assert "Wrote QA brain seed: reports/qa-brain-seed.md" in result.output
    markdown = Path("reports/qa-brain-seed.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Seed" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown


def test_report_qa_brain_seed_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "qa-brain-seed", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote QA brain seed: reports/qa-brain-seed.json" in result.output
    payload = json.loads(Path("reports/qa-brain-seed.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-seed.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_seed_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "qa-brain-seed", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported qa-brain-seed output" in result.output
    assert not Path("reports/qa-brain-seed.html").exists()


def test_report_qa_brain_seed_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_seed(*args: object, **kwargs: object) -> object:
        raise QaBrainSeedError("QA brain seed path is unsafe")

    monkeypatch.setattr(report_cli, "run_qa_brain_seed_report", fail_qa_brain_seed)

    result = CliRunner().invoke(app, ["report", "qa-brain-seed"])

    assert result.exit_code == 1
    assert "QA brain seed path is unsafe" in result.output


def test_report_qa_brain_eval_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-eval-plan"])

    assert result.exit_code == 0
    assert "Wrote QA brain eval plan: reports/qa-brain-eval-plan.md" in result.output
    markdown = Path("reports/qa-brain-eval-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Eval Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown


def test_report_qa_brain_eval_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-eval-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote QA brain eval plan: reports/qa-brain-eval-plan.json" in result.output
    payload = json.loads(Path("reports/qa-brain-eval-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-eval-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_eval_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-eval-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-eval-plan output" in result.output
    assert not Path("reports/qa-brain-eval-plan.html").exists()


def test_report_qa_brain_eval_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_eval_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainEvalPlanError("QA brain eval plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_eval_plan_report",
        fail_qa_brain_eval_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-eval-plan"])

    assert result.exit_code == 1
    assert "QA brain eval plan path is unsafe" in result.output


def test_report_qa_brain_retrieval_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-retrieval-plan"])

    assert result.exit_code == 0
    assert "Wrote QA brain retrieval plan: reports/qa-brain-retrieval-plan.md" in result.output
    markdown = Path("reports/qa-brain-retrieval-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Retrieval Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown


def test_report_qa_brain_retrieval_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-retrieval-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote QA brain retrieval plan: reports/qa-brain-retrieval-plan.json" in result.output
    payload = json.loads(Path("reports/qa-brain-retrieval-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-retrieval-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_retrieval_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-retrieval-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-retrieval-plan output" in result.output
    assert not Path("reports/qa-brain-retrieval-plan.html").exists()


def test_report_qa_brain_retrieval_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_retrieval_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainRetrievalPlanError("QA brain retrieval plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_retrieval_plan_report",
        fail_qa_brain_retrieval_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-retrieval-plan"])

    assert result.exit_code == 1
    assert "QA brain retrieval plan path is unsafe" in result.output


def test_report_qa_brain_prompt_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-prompt-plan"])

    assert result.exit_code == 0
    assert "Wrote QA brain prompt plan: reports/qa-brain-prompt-plan.md" in result.output
    markdown = Path("reports/qa-brain-prompt-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Prompt Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready |" in markdown


def test_report_qa_brain_prompt_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-prompt-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote QA brain prompt plan: reports/qa-brain-prompt-plan.json" in result.output
    payload = json.loads(Path("reports/qa-brain-prompt-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-prompt-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_prompt_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-prompt-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-prompt-plan output" in result.output
    assert not Path("reports/qa-brain-prompt-plan.html").exists()


def test_report_qa_brain_prompt_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_prompt_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainPromptPlanError("QA brain prompt plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_prompt_plan_report",
        fail_qa_brain_prompt_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-prompt-plan"])

    assert result.exit_code == 1
    assert "QA brain prompt plan path is unsafe" in result.output


def test_report_qa_brain_fine_tune_readiness_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-fine-tune-readiness"])

    assert result.exit_code == 0
    assert (
        "Wrote QA brain fine-tune readiness: reports/qa-brain-fine-tune-readiness.md"
    ) in result.output
    markdown = Path("reports/qa-brain-fine-tune-readiness.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Fine-Tune Readiness" in markdown
    assert "| weak_test_detection | Weak-test detection | ready | metadata_ready |" in (markdown)


def test_report_qa_brain_fine_tune_readiness_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-fine-tune-readiness", "--output", "json"],
    )

    assert result.exit_code == 0
    assert (
        "Wrote QA brain fine-tune readiness: reports/qa-brain-fine-tune-readiness.json"
    ) in result.output
    payload = json.loads(
        Path("reports/qa-brain-fine-tune-readiness.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == ("entroping.qa-brain-fine-tune-readiness.v1")
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_fine_tune_readiness_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-fine-tune-readiness", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-fine-tune-readiness output" in result.output
    assert not Path("reports/qa-brain-fine-tune-readiness.html").exists()


def test_report_qa_brain_fine_tune_readiness_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_fine_tune_readiness(*args: object, **kwargs: object) -> object:
        raise QaBrainFineTuneReadinessError("QA brain fine-tune readiness path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_fine_tune_readiness_report",
        fail_qa_brain_fine_tune_readiness,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-fine-tune-readiness"])

    assert result.exit_code == 1
    assert "QA brain fine-tune readiness path is unsafe" in result.output


def test_report_qa_brain_model_packaging_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-model-packaging-plan"])

    assert result.exit_code == 0
    assert (
        "Wrote QA brain model packaging plan: reports/qa-brain-model-packaging-plan.md"
    ) in result.output
    markdown = Path("reports/qa-brain-model-packaging-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Model Packaging Plan" in markdown
    assert "| weak_test_detection | Weak-test detection | ready | packaging_ready |" in (markdown)


def test_report_qa_brain_model_packaging_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-model-packaging-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert (
        "Wrote QA brain model packaging plan: reports/qa-brain-model-packaging-plan.json"
    ) in result.output
    payload = json.loads(
        Path("reports/qa-brain-model-packaging-plan.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "entroping.qa-brain-model-packaging-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_model_packaging_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-model-packaging-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-model-packaging-plan output" in result.output
    assert not Path("reports/qa-brain-model-packaging-plan.html").exists()


def test_report_qa_brain_model_packaging_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_model_packaging_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainModelPackagingPlanError("QA brain model packaging plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_model_packaging_plan_report",
        fail_qa_brain_model_packaging_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-model-packaging-plan"])

    assert result.exit_code == 1
    assert "QA brain model packaging plan path is unsafe" in result.output


def test_report_qa_brain_routing_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "test-quality.json",
        """
{
  "schema_version": "entroping.test-quality-report.v1",
  "summary": {"status": "warn", "score": 80, "generated_tests": 2, "findings": 1}
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-routing-plan"])

    assert result.exit_code == 0
    assert ("Wrote QA brain routing plan: reports/qa-brain-routing-plan.md") in result.output
    markdown = Path("reports/qa-brain-routing-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Routing Plan" in markdown
    assert (
        "| weak_test_detection | Weak-test detection | ready | packaging_ready | "
        "routing_design_ready |"
    ) in markdown


def test_report_qa_brain_routing_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-routing-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert ("Wrote QA brain routing plan: reports/qa-brain-routing-plan.json") in result.output
    payload = json.loads(Path("reports/qa-brain-routing-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-routing-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_routing_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-routing-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-routing-plan output" in result.output
    assert not Path("reports/qa-brain-routing-plan.html").exists()


def test_report_qa_brain_routing_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_routing_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainRoutingPlanError("QA brain routing plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_routing_plan_report",
        fail_qa_brain_routing_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-routing-plan"])

    assert result.exit_code == 1
    assert "QA brain routing plan path is unsafe" in result.output


def test_report_qa_brain_repair_plan_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "qa-brain-routing-plan.json",
        """
{
  "schema_version": "entroping.qa-brain-routing-plan.v1",
  "summary": {"status": "ready", "routes_total": 1, "routes_ready": 1},
  "routing_plans": [
    {
      "case_id": "weak_test_detection",
      "repair_acceptance_gates": [{"id": "parser_validation"}]
    }
  ]
}
""",
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-repair-plan"])

    assert result.exit_code == 0
    assert ("Wrote QA brain repair plan: reports/qa-brain-repair-plan.md") in result.output
    markdown = Path("reports/qa-brain-repair-plan.md").read_text(encoding="utf-8")
    assert "# Entroping QA Brain Repair Plan" in markdown
    assert "weak_test_detection" in markdown


def test_report_qa_brain_repair_plan_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-repair-plan", "--output", "json"],
    )

    assert result.exit_code == 0
    assert ("Wrote QA brain repair plan: reports/qa-brain-repair-plan.json") in result.output
    payload = json.loads(Path("reports/qa-brain-repair-plan.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.qa-brain-repair-plan.v1"
    assert payload["summary"]["status"] == "insufficient"


def test_report_qa_brain_repair_plan_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "qa-brain-repair-plan", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported qa-brain-repair-plan output" in result.output
    assert not Path("reports/qa-brain-repair-plan.html").exists()


def test_report_qa_brain_repair_plan_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_qa_brain_repair_plan(*args: object, **kwargs: object) -> object:
        raise QaBrainRepairPlanError("QA brain repair plan path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_qa_brain_repair_plan_report",
        fail_qa_brain_repair_plan,
    )

    result = CliRunner().invoke(app, ["report", "qa-brain-repair-plan"])

    assert result.exit_code == 1
    assert "QA brain repair plan path is unsafe" in result.output


def test_report_bug_generates_markdown_from_latest_failing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--minimal"])
    (Path("tests") / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HURL_VARIABLE_base_url", "http://localhost:18080")

    def fake_run(
        args: list[str],
        *,
        stdout: BinaryIO,
        stderr: BinaryIO,
        timeout: float,
        check: bool,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        _ = (args, stdout, timeout, check, shell)
        stderr.write(b"token=live-secret\nassert failed\n")
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr("entroping.core.hurl_runner.shutil.which", lambda binary: "/bin/hurl")
    monkeypatch.setattr("entroping.core.hurl_runner.subprocess.run", fake_run)
    run_result = runner.invoke(app, ["run", "--tag", "smoke"])
    assert run_result.exit_code == 1

    bug_result = runner.invoke(app, ["report", "bug"])

    assert bug_result.exit_code == 0
    assert "reports/bug.md" in bug_result.output
    bug = Path("reports/bug.md").read_text(encoding="utf-8")
    assert "tests/health.hurl" in bug
    assert "global_latency" in bug
    assert "live-secret" not in bug
    assert "token=[REDACTED]" in bug


def test_report_bug_returns_actionable_message_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "Run entroping run before report bug" in result.output
    assert not (tmp_path / "reports" / "bug.md").exists()


def test_report_bug_returns_actionable_message_without_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-05-30T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="",
                stderr="",
            ),
        ),
    )
    write_json_report(report, latest_state)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "no failures to report" in result.output


def test_report_bug_rejects_unsupported_latest_run_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    latest_state.parent.mkdir()
    latest_state.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v999",
                "project": "checkout-api",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "Could not load latest run report" in normalized_output
    assert "must use schema_version entroping.run-report.v1" in normalized_output
    assert "entroping.run-report.v999" not in result.output


def test_report_bug_rejects_versioned_latest_run_missing_required_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    latest_state.parent.mkdir()
    latest_state.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    normalized_output = " ".join(result.output.split())
    assert "Could not load latest run report" in normalized_output
    assert "required field summary.total" in normalized_output
    assert "private-runtime-value" not in result.output


def test_report_failure_bundle_writes_sanitized_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="failed",
                exit_code=1,
                duration_ms=10,
                rule_ids=("global_latency",),
                stdout="Authorization: Bearer bundle-secret\n",
                stderr="token=bundle-secret\nassert failed",
            ),
        ),
    )
    write_json_report(report, latest_state)

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 0
    assert "reports/failure-bundle/manifest.json" in result.output
    manifest = json.loads(Path("reports/failure-bundle/manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "entroping.failure-bundle.v1"
    assert "bundle-secret" not in (Path("reports/failure-bundle") / "run-latest.json").read_text(
        encoding="utf-8"
    )


def test_report_failure_bundle_returns_actionable_message_without_latest_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 1
    assert "Run entroping run before report failure-bundle" in result.output
    assert not (tmp_path / "reports" / "failure-bundle").exists()


def test_report_failure_bundle_returns_actionable_message_without_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="",
                stderr="",
            ),
        ),
    )
    write_json_report(report, latest_state)

    result = CliRunner().invoke(app, ["report", "failure-bundle"])

    assert result.exit_code == 1
    assert "no failures to bundle" in result.output


def test_report_bug_wraps_writer_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    latest_state = Path(".entroping") / "latest-run.json"
    report = RunReport(
        project="checkout-api",
        environment="default",
        generated_at="2026-05-30T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/health.hurl",
                execution_path=".entroping/run/health.hurl",
                status="failed",
                exit_code=1,
                duration_ms=10,
                rule_ids=("global_latency",),
                stdout="",
                stderr="assert failed",
            ),
        ),
    )
    write_json_report(report, latest_state)

    def fail_write_bug_report(report: RunReport, path: Path) -> Path:
        _ = report, path
        raise ReportWriterError("could not write bug")

    monkeypatch.setattr(report_cli, "write_bug_report", fail_write_bug_report)

    result = CliRunner().invoke(app, ["report", "bug"])

    assert result.exit_code == 1
    assert "could not write bug" in result.output


def test_report_delta_outputs_json_and_fails_on_added_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="Authorization: Bearer delta-secret",
                    stderr="token=delta-secret",
                ),
            ),
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="Authorization: Bearer delta-secret",
                    stderr="token=delta-secret",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.run-delta-report.v1"
    assert payload["status"] == "fail"
    assert payload["added_failures"][0]["path"] == "tests/health.hurl"
    assert payload["latency_deltas"][0]["delta_ms"] == 10
    assert "delta-secret" not in result.output
    assert "token=" not in result.output


def test_report_delta_outputs_markdown_and_passes_when_failures_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/refund.hurl",
                    execution_path=".entroping/run/refund.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=10,
                    rule_ids=("old_gate",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/refund.hurl",
                    execution_path=".entroping/run/refund.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        ["report", "delta", "--base", str(base_path), "--current", str(current_path)],
    )

    assert result.exit_code == 0
    assert "# Entroping Run Delta" in result.output
    assert "Status: **pass**" in result.output
    assert "tests/refund.hurl" in result.output


def test_report_delta_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "delta", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported delta output" in result.output


def test_report_delta_wraps_report_load_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            "reports/missing-base.json",
            "--current",
            "reports/current.json",
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output


def test_report_delta_rejects_unsafe_test_paths_without_echoing_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        base_path,
    )
    unsafe_path = "/private/tmp/customer-secret.hurl"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path=unsafe_path,
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output
    assert "unsafe test path" in result.output
    assert unsafe_path not in result.output


def test_report_delta_rejects_project_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    base_path = reports_dir / "base.json"
    current_path = reports_dir / "current.json"
    write_json_report(
        RunReport(
            project="checkout-api",
            environment="ci",
            generated_at="2026-06-04T00:00:00+00:00",
            summary=RunReportSummary(total=1, passed=1, failed=0, exit_code=0),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="passed",
                    exit_code=0,
                    duration_ms=10,
                    rule_ids=(),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        base_path,
    )
    write_json_report(
        RunReport(
            project="billing-api",
            environment="ci",
            generated_at="2026-06-04T00:01:00+00:00",
            summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
            tests=(
                RunTestReport(
                    path="tests/health.hurl",
                    execution_path=".entroping/run/health.hurl",
                    status="failed",
                    exit_code=1,
                    duration_ms=20,
                    rule_ids=("global_latency",),
                    stdout="",
                    stderr="",
                ),
            ),
        ),
        current_path,
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "delta",
            "--base",
            str(base_path),
            "--current",
            str(current_path),
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare run reports" in result.output
    assert "project mismatch" in result.output


def test_report_badges_writes_shields_endpoint_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "tests": [{"path": "tests/health.hurl", "rule_ids": ["latency"]}],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "gates": [{"id": "latency"}, {"id": "auth_required"}],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 2, "covered_operations": 2},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [{"story_id": "CHK-001", "test_paths": ["tests/health.hurl"]}],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "badges"])

    assert result.exit_code == 0
    assert "reports/badges/policy-gates.json" in result.output
    policy_badge = json.loads((reports_dir / "badges" / "policy-gates.json").read_text())
    assert policy_badge == {
        "schemaVersion": 1,
        "label": "policy gates",
        "message": "1/2 (50%)",
        "color": "yellow",
    }


def test_report_badges_reports_missing_source_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "badges"])

    assert result.exit_code == 1
    assert "Missing run report" in result.output
    assert not (tmp_path / "reports" / "badges").exists()


@pytest.mark.security
@pytest.mark.regression
def test_report_badges_rejects_outside_project_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True)
    monkeypatch.chdir(project_root)
    (reports_dir / "run-latest.json").write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "tests": []}),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps({"schema_version": "entroping.effective-policy-report.v1", "gates": []}),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 0, "covered_operations": 0},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "outside-badges"

    result = CliRunner().invoke(
        app,
        ["report", "badges", "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "coverage badge path must stay under" in result.output
    assert not output_dir.exists()


def test_report_redaction_writes_markdown_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-secret")

    result = runner.invoke(app, ["report", "redaction"])

    assert result.exit_code == 0
    assert "reports/redaction-review.md" in result.output
    content = Path("reports/redaction-review.md").read_text(encoding="utf-8")
    assert "# Entroping Redaction Review" in content
    assert "request authorization header" in content
    assert "request password body field" in content
    assert "redaction-secret" not in content
    assert "[REDACTED]" not in content


def test_report_redaction_writes_html_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-html-secret")

    result = runner.invoke(app, ["report", "redaction", "--output", "html"])

    assert result.exit_code == 0
    assert "reports/redaction-review.html" in result.output
    content = Path("reports/redaction-review.html").read_text(encoding="utf-8")
    assert "<h1>Entroping Redaction Review</h1>" in content
    assert "request authorization header" in content
    assert "redaction-html-secret" not in content
    assert "[REDACTED]" not in content


def test_report_redaction_fail_on_unsafe_passes_for_redacted_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="redaction-safe-secret")

    result = CliRunner().invoke(app, ["report", "redaction", "--fail-on-unsafe"])

    assert result.exit_code == 0
    content = Path("reports/redaction-review.md").read_text(encoding="utf-8")
    assert "- Unredacted records: 0" in content
    assert "- Low-confidence records: 0" in content
    assert "redaction-safe-secret" not in content


def test_report_redaction_without_fail_on_unsafe_preserves_default_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unsafe_redaction_review(
        *,
        project_root: Path,
        output: str,
    ) -> RedactionReviewResult:
        report = _redaction_review_with_unsafe_records(
            unredacted_records=1,
            low_confidence_records=1,
        )
        output_path = project_root / "reports" / f"redaction-review.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_redaction_review_markdown(report), encoding="utf-8")
        return RedactionReviewResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_redaction_review", write_unsafe_redaction_review)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 0
    assert Path("reports/redaction-review.md").exists()
    assert "unsafe records" not in result.output


@pytest.mark.parametrize(
    ("output", "unredacted_records", "low_confidence_records"),
    [
        ("md", 1, 0),
        ("html", 0, 2),
    ],
)
def test_report_redaction_fail_on_unsafe_fails_after_writing_report(
    output: str,
    unredacted_records: int,
    low_confidence_records: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unsafe_redaction_review(
        *,
        project_root: Path,
        output: str,
    ) -> RedactionReviewResult:
        report = _redaction_review_with_unsafe_records(
            unredacted_records=unredacted_records,
            low_confidence_records=low_confidence_records,
        )
        output_path = project_root / "reports" / f"redaction-review.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output == "html":
            output_path.write_text(render_redaction_review_html(report), encoding="utf-8")
        else:
            output_path.write_text(render_redaction_review_markdown(report), encoding="utf-8")
        return RedactionReviewResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_redaction_review", write_unsafe_redaction_review)

    result = CliRunner().invoke(
        app,
        ["report", "redaction", "--output", output, "--fail-on-unsafe"],
    )

    assert result.exit_code == 1
    assert (
        "Redaction review found unsafe records: "
        f"unredacted={unredacted_records}, "
        f"low_confidence={low_confidence_records}."
    ) in result.output
    assert Path("reports", f"redaction-review.{output}").exists()


def test_report_redaction_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not (tmp_path / "reports" / "redaction-review.md").exists()


def test_report_redaction_reports_empty_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStore

    monkeypatch.chdir(tmp_path)
    TrafficStore.open_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "redaction"])

    assert result.exit_code == 1
    assert "contains no traffic records" in result.output
    assert not (tmp_path / "reports" / "redaction-review.md").exists()


def test_report_redaction_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "redaction", "--output", "json"])

    assert result.exit_code == 2
    assert "Unsupported redaction output" in result.output


def test_report_redaction_fail_on_unsafe_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "redaction", "--output", "json", "--fail-on-unsafe"],
    )

    assert result.exit_code == 2
    assert "Unsupported redaction output" in result.output


def test_report_artifact_manifest_preserves_default_success_with_missing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        '{"schema_version":"password=manifest-secret"}\n',
    )

    result = CliRunner().invoke(app, ["report", "artifact-manifest"])

    assert result.exit_code == 0
    assert "9 missing" in result.output
    assert "manifest-secret" not in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 9
    assert "manifest-secret" not in json.dumps(payload)


def test_report_artifact_manifest_fail_on_incomplete_passes_when_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_complete_artifact_manifest_inputs(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 0
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 0
    assert payload["audit"]["verification"]["status"] == "verified"


def test_report_artifact_manifest_fail_on_incomplete_fails_after_writing_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        '{"schema_version":"password=manifest-secret"}\n',
    )

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 1
    assert "Artifact manifest incomplete: missing=9, audit=verified." in result.output
    assert "manifest-secret" not in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 9
    assert "manifest-secret" not in json.dumps(payload)


def test_report_artifact_manifest_fail_on_incomplete_writes_custom_output_before_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = Path("reports") / "custom-artifact-manifest.json"

    result = CliRunner().invoke(
        app,
        [
            "report",
            "artifact-manifest",
            "--output",
            str(output_path),
            "--fail-on-incomplete",
        ],
    )

    assert result.exit_code == 1
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 10


def test_report_artifact_manifest_fail_on_incomplete_fails_on_broken_audit_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_complete_artifact_manifest_inputs(tmp_path)
    first = CliRunner().invoke(app, ["report", "artifact-manifest"])
    assert first.exit_code == 0
    chain_path = Path(".entroping") / "report-audit-chain.jsonl"
    chain_path.write_text(
        chain_path.read_text(encoding="utf-8").replace(
            "entroping.run-report.v1",
            "entroping.run-report.v9",
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 1
    assert "Artifact manifest incomplete: missing=0, audit=broken." in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 0
    assert payload["audit"]["verification"]["status"] == "broken"


def test_report_capture_summary_writes_json_without_raw_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")
    _record_mock_exchange(tmp_path, secret="capture-dependency-secret")

    result = runner.invoke(app, ["report", "capture-summary", "--output", "json"])

    assert result.exit_code == 0
    assert "reports/capture-summary.json" in result.output
    payload = json.loads(Path("reports/capture-summary.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.capture-summary.v1"
    assert payload["summary"]["total_records"] == 2
    assert payload["dependency_targets"][0] == {
        "label": "payments.example.test",
        "count": 1,
    }
    assert "capture-cli-secret" not in result.output
    assert "capture-dependency-secret" not in json.dumps(payload)
    assert "[REDACTED]" not in json.dumps(payload)


def test_report_capture_summary_fail_on_unredacted_passes_for_redacted_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")

    result = CliRunner().invoke(
        app,
        ["report", "capture-summary", "--output", "json", "--fail-on-unredacted"],
    )

    assert result.exit_code == 0
    payload = json.loads(Path("reports/capture-summary.json").read_text(encoding="utf-8"))
    assert payload["summary"]["unredacted_records"] == 0
    assert "capture-cli-secret" not in json.dumps(payload)


def test_report_capture_summary_fail_on_unredacted_passes_for_default_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_freeze_exchange(tmp_path, secret="capture-cli-secret")

    result = CliRunner().invoke(app, ["report", "capture-summary", "--fail-on-unredacted"])

    assert result.exit_code == 0
    markdown = Path("reports/capture-summary.md").read_text(encoding="utf-8")
    assert "| Unredacted records | 0 |" in markdown
    assert "capture-cli-secret" not in markdown


@pytest.mark.parametrize(
    ("output", "unredacted_records", "record_word"),
    [
        ("md", 1, "record"),
        ("json", 2, "records"),
    ],
)
def test_report_capture_summary_fail_on_unredacted_fails_after_writing_report(
    output: str,
    unredacted_records: int,
    record_word: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def write_unredacted_summary(*, project_root: Path, output: str) -> CaptureSummaryResult:
        report = _capture_summary_with_unredacted_records(unredacted_records)
        output_path = project_root / "reports" / f"capture-summary.{output}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output == "json":
            output_path.write_text(
                json.dumps(capture_summary_report_to_dict(report), indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            output_path.write_text(render_capture_summary_markdown(report), encoding="utf-8")
        return CaptureSummaryResult(output_path=output_path, report=report)

    monkeypatch.setattr(report_cli, "run_capture_summary_report", write_unredacted_summary)

    result = CliRunner().invoke(
        app,
        ["report", "capture-summary", "--output", output, "--fail-on-unredacted"],
    )

    assert result.exit_code == 1
    assert (
        f"Capture summary found {unredacted_records} unredacted traffic {record_word}."
        in result.output
    )
    assert Path("reports", f"capture-summary.{output}").exists()


def test_report_capture_summary_writes_empty_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from entroping.core.traffic_store import TrafficStore

    monkeypatch.chdir(tmp_path)
    TrafficStore.open_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "capture-summary"])

    assert result.exit_code == 0
    assert "0 traffic records" in result.output
    content = Path("reports/capture-summary.md").read_text(encoding="utf-8")
    assert "No captured traffic records found." in content


def test_report_capture_summary_reports_missing_traffic_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "capture-summary"])

    assert result.exit_code == 1
    assert "No traffic state found" in result.output
    assert not (tmp_path / "reports" / "capture-summary.md").exists()
    assert not (tmp_path / ".entroping").exists()


def test_report_capture_summary_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "capture-summary", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported capture-summary output" in result.output


def test_report_traceability_outputs_empty_suite_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 0
    assert "# Story Traceability" in result.output
    assert "No story-linked tests found." in result.output
    assert "No traceability findings." in result.output


def test_report_traceability_renders_story_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke,checkout",
                "# entroping: story_id=CHK-001",
                "# entroping: owner=payments",
                "# entroping: doc_url=https://jira.example.test/browse/CHK-001",
                "",
                "GET {{base_url}}/checkout",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 0
    assert "CHK-001" in result.output
    assert "payments" in result.output
    assert "https://jira.example.test/browse/CHK-001" in result.output
    assert "tests/checkout.hurl" in result.output
    assert "checkout, smoke" in result.output


def test_report_traceability_outputs_json_for_badge_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke,checkout",
                "# entroping: story_id=CHK-001",
                "# entroping: owner=payments",
                "",
                "GET {{base_url}}/checkout",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "entroping.traceability-report.v1"
    assert payload["summary"] == {"stories": 1, "findings": 0, "passed": True}
    assert payload["stories"][0]["story_id"] == "CHK-001"


def test_report_traceability_links_markdown_story_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "# entroping: story_id=CHK-001\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    stories_dir = Path("docs") / "stories"
    stories_dir.mkdir(parents=True)
    (stories_dir / "checkout.md").write_text(
        "---\nstory_id: CHK-001\ntitle: Checkout accepts payment\n---\n",
        encoding="utf-8",
    )

    md_result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])
    json_result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert md_result.exit_code == 0
    assert "docs/stories/checkout.md" in md_result.output
    assert "Checkout accepts payment" in md_result.output
    assert json_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["stories"][0]["story_paths"] == ["docs/stories/checkout.md"]
    assert payload["stories"][0]["titles"] == ["Checkout accepts payment"]


def test_report_traceability_reports_malformed_story_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    stories_dir = Path("docs") / "stories"
    stories_dir.mkdir(parents=True)
    (stories_dir / "broken.md").write_text("# Broken story\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["findings"][0]["kind"] == "malformed_story_metadata"
    assert payload["findings"][0]["story_path"] == "docs/stories/broken.md"


def test_report_traceability_reports_missing_story_when_story_directory_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "# entroping: story_id=CHK-001\n\nGET {{base_url}}/checkout\nHTTP 200\n",
        encoding="utf-8",
    )
    (Path("docs") / "stories").mkdir(parents=True)

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["findings"][0]["kind"] == "missing_story"
    assert payload["findings"][0]["story_ids"] == ["CHK-001"]


def test_report_traceability_reports_missing_story_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "missing_story_id" in result.output
    assert "tests/missing.hurl" in result.output


def test_report_traceability_reports_duplicate_doc_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    for file_name, story_id in (("checkout.hurl", "CHK-001"), ("refund.hurl", "PAY-002")):
        (tests_dir / file_name).write_text(
            "\n".join(
                [
                    f"# entroping: story_id={story_id}",
                    "# entroping: doc_url=https://jira.example.test/browse/shared",
                    "",
                    "GET {{base_url}}/health",
                    "HTTP 200",
                ],
            ),
            encoding="utf-8",
        )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "duplicate_doc_url" in result.output
    assert "CHK-001" in result.output
    assert "PAY-002" in result.output
    assert "https://jira.example.test/browse/shared" in result.output


def test_report_traceability_wraps_metadata_syntax_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "broken.hurl").write_text(
        "# entroping: story_id\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "traceability", "--output", "md"])

    assert result.exit_code == 1
    assert "tests/broken.hurl" in result.output
    assert "line 1" in result.output
    assert "expected" in result.output
    assert "'key=value'" in result.output


def test_report_traceability_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "traceability", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported traceability output" in result.output


def test_report_policy_writes_effective_policy_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("qanstitution.yaml").write_text(
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "policy", "--output", "md"])

    assert result.exit_code == 0
    assert "Wrote effective policy report: reports/effective-policy.md" in result.output
    assert "global_latency" in Path("reports/effective-policy.md").read_text(encoding="utf-8")


def test_report_policy_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "policy", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported policy output" in result.output


def test_report_policy_wraps_effective_policy_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "policy"])

    assert result.exit_code == 1
    assert "QAnstitution file not found" in result.output


def test_report_policy_diff_emits_json_from_effective_policy_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    (reports / "base-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": ["rules/base.yaml"],
                "gates": [
                    {
                        "id": "latency",
                        "source_path": "qanstitution.yaml",
                        "condition": "true",
                        "gate": "duration < 2000",
                        "enforcement": "block",
                        "final": False,
                        "group": None,
                        "description": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (reports / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": ["rules/current.yaml"],
                "gates": [
                    {
                        "id": "latency",
                        "source_path": "qanstitution.yaml",
                        "condition": "true",
                        "gate": "duration < 1000",
                        "enforcement": "block",
                        "final": False,
                        "group": None,
                        "description": None,
                    },
                    {
                        "id": "auth",
                        "source_path": "rules/current.yaml",
                        "condition": "true",
                        "gate": 'header "Authorization" exists',
                        "enforcement": "warn",
                        "final": True,
                        "group": None,
                        "description": "Auth evidence",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.effective-policy-diff.v1"
    assert payload["status"] == "changed"
    assert payload["summary"]["added_imports"] == 1
    assert payload["summary"]["removed_imports"] == 1
    assert payload["summary"]["added_gates"] == 1
    assert payload["summary"]["changed_gates"] == 1


def test_report_policy_diff_emits_markdown_no_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    policy = {
        "schema_version": "entroping.effective-policy-report.v1",
        "project": "checkout-api",
        "config_path": "qanstitution.yaml",
        "imports": [],
        "gates": [],
    }
    (reports / "base-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    (reports / "effective-policy.json").write_text(json.dumps(policy), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
        ],
    )

    assert result.exit_code == 0
    assert "# Entroping Effective Policy Diff" in result.stdout
    assert "No effective policy differences found." in result.stdout


def test_report_policy_diff_fail_on_change_exits_nonzero_for_changed_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    _write_effective_policy_report(
        reports / "base-policy.json",
        gates=(
            {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 1000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
        ),
    )
    _write_effective_policy_report(
        reports / "effective-policy.json",
        gates=(
            {
                "id": "latency",
                "source_path": "qanstitution.yaml",
                "condition": "true",
                "gate": "duration < 1000",
                "enforcement": "block",
                "final": False,
                "group": None,
                "description": None,
            },
            {
                "id": "auth",
                "source_path": "rules/current.yaml",
                "condition": "true",
                "gate": 'header "Authorization" exists',
                "enforcement": "warn",
                "final": False,
                "group": None,
                "description": None,
            },
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--output",
            "json",
            "--fail-on-change",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "changed"
    assert payload["summary"]["added_gates"] == 1


def test_report_policy_diff_fail_on_change_allows_unchanged_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    policy = {
        "id": "latency",
        "source_path": "qanstitution.yaml",
        "condition": "true",
        "gate": "duration < 1000",
        "enforcement": "block",
        "final": False,
        "group": None,
        "description": None,
    }
    _write_effective_policy_report(reports / "base-policy.json", gates=(policy,))
    _write_effective_policy_report(reports / "effective-policy.json", gates=(policy,))

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
            "--fail-on-change",
        ],
    )

    assert result.exit_code == 0
    assert "Status: **unchanged**" in result.stdout


def test_report_policy_diff_rejects_bad_output() -> None:
    result = CliRunner().invoke(app, ["report", "policy-diff", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported policy-diff output" in result.output


def test_report_policy_diff_wraps_malformed_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports = Path("reports")
    reports.mkdir()
    (reports / "base-policy.json").write_text("{not json}\n", encoding="utf-8")
    (reports / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "project": "checkout-api",
                "config_path": "qanstitution.yaml",
                "imports": [],
                "gates": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "report",
            "policy-diff",
            "--base",
            "reports/base-policy.json",
            "--current",
            "reports/effective-policy.json",
        ],
    )

    assert result.exit_code == 1
    assert "Could not compare effective policy reports" in result.output


def test_report_github_annotations_emits_report_and_traceability_annotations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
status: failed
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/health.hurl",
                        "message": "Response status changed.",
                        "baseline": {},
                        "current": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "github-annotations", "--traceability"])

    assert result.exit_code == 0
    assert "::error file=tests/health.hurl" in result.output
    assert "Entroping Hurl failure" in result.output
    assert "Entroping drift%3A response_status_changed" in result.output
    assert "Entroping traceability%3A missing_story_id" in result.output
    assert "live-secret" not in result.output
    assert "token=[REDACTED]" in result.output


def test_report_github_annotations_truncates_annotations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="2" failures="2" errors="0">
  <testcase classname="tests" name="one.hurl" time="0.001">
    <failure message="first" type="entroping.hurl" />
  </testcase>
  <testcase classname="tests" name="two.hurl" time="0.001">
    <failure message="second" type="entroping.hurl" />
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "github-annotations", "--max-annotations", "1"],
    )

    assert result.exit_code == 0
    assert "Entroping Hurl failure" in result.output
    assert "first" in result.output
    assert "second" not in result.output
    assert "Entroping annotations truncated" in result.output
    assert "1 annotation(s) omitted" in result.output


@pytest.mark.security
@pytest.mark.regression
def test_report_github_annotations_drops_unsafe_file_properties(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping unsafe paths" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="unsafe.hurl" time="0.001">
    <failure message="failed" type="entroping.hurl">path: ../outside.hurl
status: failed</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "unsafe_annotation_path",
                        "severity": "error",
                        "path": "https://evil.example/finding.hurl",
                        "message": "Unsafe annotation path.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "github-annotations"])

    assert result.exit_code == 0
    assert "::error title=Entroping Hurl failure::" in result.output
    assert "::error title=Entroping drift%3A unsafe_annotation_path::" in result.output
    assert "file=../outside.hurl" not in result.output
    assert "file=https%3A//evil.example/finding.hurl" not in result.output


def test_report_review_summary_writes_provider_neutral_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "generated_at": "2026-06-01T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
secret=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 0
    assert "Wrote review summary: reports/review-summary.md" in result.output
    summary = (reports_dir / "review-summary.md").read_text(encoding="utf-8")
    assert "# Entroping Review Summary" in summary
    assert "| JUnit | error | tests/health.hurl |" in summary
    assert "live-secret" not in summary
    assert "secret=[REDACTED]" in summary


def test_report_review_summary_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "review-summary", "--output", "json"])

    assert result.exit_code == 2
    assert "Unsupported review summary output" in result.output


def test_report_review_summary_wraps_report_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output


def test_report_review_summary_rejects_malformed_tests_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "checkout-api",
                "environment": "ci",
                "summary": {"total": 1, "passed": 1, "failed": 0, "exit_code": 0},
                "tests": {},
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "review-summary"])

    assert result.exit_code == 1
    assert "must contain a tests list" in result.output
    assert not (reports_dir / "review-summary.md").exists()


def test_report_agent_bundle_writes_selected_role_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_agent_bundle_qanstitution(("builder", "breaker"))
    _write_agent_bundle_manifest(
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
    )
    _write_agent_bundle_manifest(
        "20260604T010100Z-architect-build-breaker-b.json",
        agent="breaker",
    )

    result = CliRunner().invoke(
        app,
        ["report", "agent-bundle", "--output", "json", "--role", "builder"],
    )

    assert result.exit_code == 0
    assert "Wrote agent review bundle: reports/agent-bundle.json" in result.output
    payload = json.loads(Path("reports/agent-bundle.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.agent-review-bundle.v1"
    assert payload["summary"]["status"] == "pass"
    assert [role["role"] for role in payload["roles"]] == ["builder"]
    assert payload["roles"][0]["manifests"][0]["agent"] == "builder"


def test_report_agent_bundle_writes_markdown_and_exits_nonzero_for_failed_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_agent_bundle_qanstitution(("builder", "breaker"))
    _write_agent_bundle_manifest(
        "20260604T010000Z-architect-build-builder-a.json",
        agent="builder",
        output_paths=("tests/generated/checkout.hurl",),
    )
    _write_agent_bundle_manifest(
        "20260604T010100Z-architect-build-breaker-b.json",
        agent="breaker",
        output_paths=("tests/generated/checkout.hurl",),
    )

    result = CliRunner().invoke(app, ["report", "agent-bundle"])

    assert result.exit_code == 1
    assert "Wrote agent review bundle: reports/agent-bundle.md" in result.output
    markdown = Path("reports/agent-bundle.md").read_text(encoding="utf-8")
    assert "# Entroping Agent Review Bundle" in markdown
    assert "output_path_conflict" in markdown
    assert "tests/generated/checkout.hurl" in markdown


def test_report_agent_bundle_rejects_invalid_role_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_agent_bundle_qanstitution(("builder",))

    result = CliRunner().invoke(app, ["report", "agent-bundle", "--role", "planner"])

    assert result.exit_code == 2
    assert "Unsupported agent-bundle role" in result.output
    assert not Path("reports/agent-bundle.md").exists()


def test_report_agent_bundle_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "agent-bundle", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported agent-bundle output" in result.output


def test_report_agent_bundle_wraps_bundle_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "agent-bundle"])

    assert result.exit_code == 1
    assert "QAnstitution file not found" in result.output
    assert not Path("reports/agent-bundle.md").exists()


def test_report_github_annotations_rejects_malformed_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "github-annotations"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output


def test_report_sarif_writes_code_scanning_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="Entroping checkout-api" tests="1" failures="1" errors="0">
  <testcase classname="tests" name="health.hurl" time="0.010">
    <failure message="failed" type="entroping.hurl">path: tests/health.hurl
status: failed
token=live-secret</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )
    (reports_dir / "drift.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-report.v1",
                "findings": [
                    {
                        "kind": "response_status_changed",
                        "severity": "error",
                        "path": "tests/health.hurl",
                        "message": "Response status changed.",
                        "baseline": {},
                        "current": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "sarif"])

    assert result.exit_code == 0
    assert "Wrote SARIF report: reports/entroping.sarif" in result.output
    sarif = json.loads((reports_dir / "entroping.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 2
    assert "live-secret" not in json.dumps(sarif)
    assert "token=[REDACTED]" in json.dumps(sarif)


def test_report_sarif_accepts_custom_output_and_traceability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    tests_dir = Path("tests")
    tests_dir.mkdir()
    (tests_dir / "missing.hurl").write_text(
        "# entroping: tags=smoke\n\nGET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "sarif", "--traceability", "--output", "reports/security.sarif"],
    )

    assert result.exit_code == 0
    assert "reports/security.sarif" in result.output
    sarif = json.loads(Path("reports/security.sarif").read_text(encoding="utf-8"))
    assert sarif["runs"][0]["results"] == [
        {
            "ruleId": "entroping.traceability.missing_story_id",
            "level": "error",
            "message": {"text": "tests/missing.hurl has no # entroping: story_id metadata."},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "tests/missing.hurl"},
                        "region": {"startLine": 1},
                    }
                }
            ],
        }
    ]


@pytest.mark.security
@pytest.mark.regression
def test_report_sarif_rejects_outside_project_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    output = tmp_path / "outside.sarif"

    result = CliRunner().invoke(
        app,
        ["report", "sarif", "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "SARIF report path must stay under" in result.output
    assert not output.exists()


def test_report_sarif_wraps_report_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "sarif"])

    assert result.exit_code == 1
    assert "Could not parse drift report" in result.output


def test_report_promote_drift_baseline_writes_active_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    candidate = reports_dir / "drift-baseline.candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-baseline.v1",
                "project": "checkout-api",
                "environment": "staging",
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 25,
                        "rule_ids": ["global_latency"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "promote-drift-baseline"])

    assert result.exit_code == 0
    assert "Promoted drift baseline: .entroping/drift-baseline.json" in result.output
    assert "1 test" in result.output
    active = json.loads((Path(".entroping") / "drift-baseline.json").read_text(encoding="utf-8"))
    assert active == json.loads(candidate.read_text(encoding="utf-8"))


def test_report_promote_drift_baseline_wraps_candidate_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift-baseline.candidate.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "promote-drift-baseline"])

    assert result.exit_code == 1
    assert "Could not parse drift baseline candidate" in result.output
    assert not (Path(".entroping") / "drift-baseline.json").exists()


def _write_agent_bundle_qanstitution(roles: tuple[str, ...]) -> None:
    agent_lines: list[str] = []
    for role in roles:
        agent_lines.extend(
            [
                f"  {role}:",
                f"    source: agents/{role}.md",
                f"    model: openai/{role}",
            ]
        )
    Path("qanstitution.yaml").write_text(
        f"""
project: checkout-api
agents:
{chr(10).join(agent_lines)}
gates: []
""".lstrip(),
        encoding="utf-8",
    )


def _write_agent_bundle_manifest(
    name: str,
    *,
    agent: str,
    output_paths: tuple[str, ...] = ("tests/generated/checkout.hurl",),
) -> None:
    manifest_dir = Path(".entroping") / "agent-runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "entroping.agent-run-manifest.v1",
        "generated_at": "2026-06-04T01:00:00+00:00",
        "command": "architect build",
        "mode": "create",
        "agent": agent,
        "model": f"openai/{agent}",
        "provider": None,
        "persona": {
            "source_path": f"agents/{agent}.md",
            "sha256": "persona-sha",
        },
        "prompt": {
            "intent_sha256": "prompt-hash",
            "package_sha256": "package-hash",
        },
        "output_paths": list(output_paths),
        "tags": [],
        "validation": {
            "status": "passed",
            "structured_output_validated": True,
            "hurl_validated": True,
        },
        "latency_ms": 42,
        "cost": {
            "estimated_usd": None,
            "input_cost_per_1m_tokens_usd": None,
            "output_cost_per_1m_tokens_usd": None,
        },
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }
    (manifest_dir / name).write_text(json.dumps(payload), encoding="utf-8")
