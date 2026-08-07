"""Experimental CLI report command tests."""

from cli_report_test_helpers import (
    _write_agent_bundle_manifest,
    _write_agent_bundle_qanstitution,
    _write_pilot_outcome_packet,
    _write_ready_evidence_bundle_inputs,
    _write_text,
)
from cli_test_support import (
    CliRunner,
    Path,
    app,
    json,
    pytest,
    report_cli,
)
from experimental_report_policy import (
    policy_entry,
    validate_experimental_report_growth_policy,
)
from typer.core import TyperCommand, TyperGroup
from typer.main import get_command

from entroping.core.design_partner_feedback import DesignPartnerFeedbackError
from entroping.core.evidence.api_inventory import ApiInventoryError
from entroping.core.evidence.connector_intent import ConnectorIntentError
from entroping.core.evidence.evidence_bundle import EvidenceBundleError
from entroping.core.evidence.evidence_cloud_dashboard import EvidenceCloudDashboardError
from entroping.core.evidence.evidence_index_report import EvidenceIndexError
from entroping.core.evidence.evidence_links import EvidenceLinksError
from entroping.core.evidence.evidence_portal import EvidencePortalError
from entroping.core.evidence.handoff_packet import HandoffError
from entroping.core.evidence.notification_packet import NotificationPacketError
from entroping.core.evidence.observability_packet import ObservabilityPacketError
from entroping.core.evidence.otel_mapping import OtelMappingError
from entroping.core.evidence.otlp_preview import OtlpPreviewError
from entroping.core.evidence.pilot_cohort import PilotCohortError
from entroping.core.evidence.pilot_metrics import PilotMetricsError
from entroping.core.evidence.pilot_outcome import PilotOutcomeError
from entroping.core.evidence.pr_evidence_card import (
    PrEvidenceCardError,
    PrEvidenceCardSummaryError,
    build_pr_evidence_card_packet,
    run_pr_evidence_card_report,
)
from entroping.core.export.evidence_cloud_export import EvidenceCloudExportError
from entroping.core.export.evidence_cloud_workspace import EvidenceCloudWorkspaceError
from entroping.core.export.work_item_draft import WorkItemDraftError
from entroping.core.export.work_item_import_bundle import WorkItemImportBundleError
from entroping.core.plan.evidence_action_plan import EvidenceActionPlanError
from entroping.core.plan.qa_brain_eval_plan import QaBrainEvalPlanError
from entroping.core.plan.qa_brain_fine_tune_readiness import (
    QaBrainFineTuneReadinessError,
)
from entroping.core.plan.qa_brain_model_packaging_plan import (
    QaBrainModelPackagingPlanError,
)
from entroping.core.plan.qa_brain_prompt_plan import QaBrainPromptPlanError
from entroping.core.plan.qa_brain_repair_plan import QaBrainRepairPlanError
from entroping.core.plan.qa_brain_retrieval_plan import QaBrainRetrievalPlanError
from entroping.core.plan.qa_brain_routing_plan import QaBrainRoutingPlanError
from entroping.core.plan.qa_brain_seed import QaBrainSeedError
from entroping.core.plan.team_access_control_plan import TeamAccessControlPlanError
from entroping.core.readiness.devex_readiness import DevexReadinessError
from entroping.core.readiness.evidence_cloud_readiness import EvidenceCloudReadinessError
from entroping.core.readiness.integration_readiness import IntegrationReadinessError
from entroping.core.readiness.mutation_readiness import (
    MutationReadinessError,
    MutationReadinessReplayValidationError,
    run_mutation_readiness_report,
)
from entroping.core.readiness.observability_adapter_readiness import (
    ObservabilityAdapterReadinessError,
)
from entroping.core.readiness.team_evidence_readiness import TeamEvidenceReadinessError

_EXPERIMENTAL_REPORT_PANEL = "Experimental Design-Partner Evidence"
_EXPERIMENTAL_REPORT_POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "meta"
    / "experimental-report-growth-policy.json"
)


def _assert_report_description(command_name: str, expected: str) -> None:
    root_command = get_command(app)
    assert isinstance(root_command, TyperGroup)
    report_command = root_command.commands["report"]
    assert isinstance(report_command, TyperGroup)
    command = report_command.commands[command_name]
    assert isinstance(command, TyperCommand)
    assert command.help == expected


def _live_experimental_report_commands() -> tuple[TyperGroup, tuple[str, ...]]:
    root_command = get_command(app)
    assert isinstance(root_command, TyperGroup)
    report_command = root_command.commands["report"]
    assert isinstance(report_command, TyperGroup)
    live_commands = tuple(
        command_name
        for command_name, command in report_command.commands.items()
        if isinstance(command, TyperCommand)
        and command.rich_help_panel == _EXPERIMENTAL_REPORT_PANEL
    )
    return report_command, live_commands


def test_experimental_report_growth_policy_covers_live_panel_in_order() -> None:
    report_command, live_commands = _live_experimental_report_commands()
    document = json.loads(_EXPERIMENTAL_REPORT_POLICY_PATH.read_text(encoding="utf-8"))

    entries = validate_experimental_report_growth_policy(document, live_commands)

    assert len(report_command.commands) == 62
    assert len(live_commands) == 41
    assert tuple(entry["command"] for entry in entries) == live_commands
    assert {entry["owner"] for entry in entries} == {
        "evidence-delivery",
        "observability",
        "product-evidence",
        "qa-brain",
        "workflow-integrations",
    }
    assert {entry["adoption_evidence"]["state"] for entry in entries} == {"missing"}
    assert {entry["adoption_evidence"]["pointer"] for entry in entries} == {
        "https://github.com/sakibshuvo/Entroping/issues/306",
    }
    assert {entry["disposition"] for entry in entries} == {"retain-experimental"}
    assert {entry["review_on"] for entry in entries} == {"2026-08-31"}


def test_experimental_report_growth_policy_is_not_shipped_with_cli() -> None:
    shipped_policy = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "entroping"
        / "cli"
        / "commands"
        / "report"
        / "_experimental_policy.py"
    )

    assert not shipped_policy.exists()


@pytest.mark.parametrize(
    ("policy_commands", "live_commands", "message"),
    (
        (("alpha",), ("alpha", "beta"), "missing live command.*beta"),
        (("alpha", "stale"), ("alpha",), "stale command.*stale"),
        (
            ("beta", "alpha"),
            ("alpha", "beta"),
            "order mismatch.*expected 'alpha'.*found 'beta'",
        ),
    ),
)
def test_experimental_report_growth_policy_reports_panel_drift(
    policy_commands: tuple[str, ...],
    live_commands: tuple[str, ...],
    message: str,
) -> None:
    document = {
        "schema_version": "entroping.experimental-report-growth-policy.v1",
        "entries": [policy_entry(command) for command in policy_commands],
    }

    with pytest.raises(ValueError, match=message):
        validate_experimental_report_growth_policy(document, live_commands)


def test_experimental_report_growth_policy_rejects_unvalidated_promotion() -> None:
    document = {
        "schema_version": "entroping.experimental-report-growth-policy.v1",
        "entries": [
            policy_entry(
                "synthetic-command",
                adoption_state="missing",
                disposition="promote",
            ),
        ],
    }

    with pytest.raises(
        ValueError,
        match=r"synthetic-command.*promote.*validated adoption evidence",
    ):
        validate_experimental_report_growth_policy(
            document,
            ("synthetic-command",),
        )


@pytest.mark.parametrize(
    ("command_name", "description"),
    (
        (
            "otlp-preview",
            "Write a local OTLP preview from sanitized telemetry evidence.",
        ),
        (
            "pr-evidence-card-summary",
            "Summarize a local PR evidence-card artifact for review.",
        ),
        (
            "mutation-readiness-replay",
            "Validate a local mutation-readiness manifest for deterministic replay.",
        ),
    ),
)
def test_experimental_report_command_descriptions_are_actionable(
    command_name: str,
    description: str,
) -> None:
    _assert_report_description(command_name, description)


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


def test_report_pr_evidence_card_summary_uses_default_artifact_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_pr_evidence_card_report(project_root=tmp_path, output="json")
    result = CliRunner().invoke(app, ["report", "pr-evidence-card-summary"])

    assert result.exit_code == 0, result.output
    assert "# Entroping PR Evidence Card Summary" in result.output
    assert "## Next Actions" in result.output


def test_report_pr_evidence_card_summary_supports_artifact_path_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    artifact_path = tmp_path / "artifacts" / "pr-evidence-card.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    packet = build_pr_evidence_card_packet(project_root=tmp_path)
    artifact_path.write_text(packet.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["report", "pr-evidence-card-summary", "--artifact-path", str(artifact_path)],
    )

    assert result.exit_code == 0, result.output
    assert "## Sources" in result.output


def test_report_pr_evidence_card_summary_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_pr_evidence_card_summary(*args: object, **kwargs: object) -> object:
        raise PrEvidenceCardSummaryError("PR evidence card summary is unavailable")

    monkeypatch.setattr(
        report_cli,
        "run_pr_evidence_card_summary_report",
        fail_pr_evidence_card_summary,
    )

    result = CliRunner().invoke(app, ["report", "pr-evidence-card-summary"])

    assert result.exit_code == 1
    assert "PR evidence card summary is unavailable" in result.output


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


def test_report_otlp_preview_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        """
{
  "schema_version": "entroping.run-report.v1",
  "project": "private-checkout-service",
  "environment": "local",
  "generated_at": "2026-07-04T00:00:00+00:00",
  "summary": {"total": 2, "passed": 1, "failed": 1, "exit_code": 1},
  "tests": [
    {
      "path": "tests/private-flow.hurl",
      "execution_path": ".entroping/run/private-flow.hurl",
      "status": "failed",
      "exit_code": 1,
      "duration_ms": 10,
      "rule_ids": [],
      "stdout": "raw-output-should-not-render",
      "stderr": ""
    }
  ]
}
""",
    )

    result = CliRunner().invoke(app, ["report", "otlp-preview"])

    assert result.exit_code == 0
    assert "Wrote OTLP preview: reports/otlp-preview.md" in result.output
    markdown = Path("reports/otlp-preview.md").read_text(encoding="utf-8")
    assert "# Entroping OTLP Preview" in markdown
    assert "| entroping.tests.total | 1 | sum | 2 |" in markdown
    assert "local-only-no-export" in markdown
    assert "private-checkout-service" not in markdown
    assert "private-flow" not in markdown
    assert "raw-output-should-not-render" not in markdown


def test_report_otlp_preview_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "otlp-preview", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote OTLP preview: reports/otlp-preview.json" in result.output
    payload = json.loads(Path("reports/otlp-preview.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.otlp-preview.v1"
    assert payload["summary"]["status"] == "insufficient"
    assert payload["fixture"]["network_policy"] == "local-only-no-export"


def test_report_otlp_preview_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(app, ["report", "otlp-preview", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported otlp-preview output" in result.output
    assert not Path("reports/otlp-preview.html").exists()


def test_report_otlp_preview_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_otlp_preview(*args: object, **kwargs: object) -> object:
        raise OtlpPreviewError("otlp preview path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_otlp_preview_report",
        fail_otlp_preview,
    )

    result = CliRunner().invoke(app, ["report", "otlp-preview"])

    assert result.exit_code == 1
    assert "otlp preview path is unsafe" in result.output


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


def test_report_mutation_readiness_replay_validates_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("tests") / "generated" / "security" / "auth.hurl",
        "\n".join(
            (
                "# entroping: tags=generated,negative",
                "# entroping: source=openapi",
                "# entroping: operation_id=getOrders",
                "# entroping: negative_category=invalid-auth",
                "# entroping: mutation_seed=auth-seed",
                "GET http://127.0.0.1:18080/orders",
                "HTTP 401",
                "[Asserts]",
                'header "WWW-Authenticate" exists',
            )
        )
        + "\n",
    )
    run_mutation_readiness_report(project_root=tmp_path, output="json")

    result = CliRunner().invoke(app, ["report", "mutation-readiness-replay"])

    assert result.exit_code == 0
    assert "mutation-readiness replay manifest valid" in result.output


def test_report_mutation_readiness_replay_prints_manifest_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_mutation_readiness_report(project_root=tmp_path, output="json")

    result = CliRunner().invoke(app, ["report", "mutation-readiness-replay"])

    assert result.exit_code == 0
    assert "warn: no seeded fuzz candidates were present for replay" in result.output
    assert "mutation-readiness replay manifest valid" in result.output


def test_report_mutation_readiness_replay_reports_validation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("tests") / "generated" / "security" / "auth.hurl",
        "\n".join(
            (
                "# entroping: tags=generated,negative",
                "# entroping: source=openapi",
                "# entroping: operation_id=getOrders",
                "# entroping: negative_category=invalid-auth",
                "# entroping: mutation_seed=auth-seed",
                "GET http://127.0.0.1:18080/orders",
                "HTTP 401",
                "[Asserts]",
                'header "WWW-Authenticate" exists',
            )
        )
        + "\n",
    )
    result_report = run_mutation_readiness_report(project_root=tmp_path, output="json")
    payload = json.loads(result_report.output_path.read_text(encoding="utf-8"))
    payload["seeded_fuzz_candidates"][0]["seed_metadata"] = False
    result_report.output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "mutation-readiness-replay"])
    assert result.exit_code == 1
    assert "missing seed" in result.output


def test_report_mutation_readiness_replay_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_mutation_readiness_replay(*args: object, **kwargs: object) -> object:
        raise MutationReadinessReplayValidationError(
            "mutation readiness replay path is unsafe"
        )

    monkeypatch.setattr(
        report_cli,
        "run_mutation_readiness_replay_validation",
        fail_mutation_readiness_replay,
    )

    result = CliRunner().invoke(app, ["report", "mutation-readiness-replay"])
    assert result.exit_code == 1
    assert "mutation readiness replay path is unsafe" in result.output


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
