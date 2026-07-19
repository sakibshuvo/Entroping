"""Shared fixtures and writers for CLI report command tests."""

from cli_test_support import (
    Path,
    RunReport,
    RunReportSummary,
    RunTestReport,
    json,
    write_json_report,
)

from entroping.bridge.capture_summary import (
    CaptureSummaryReport,
    CaptureSummaryTotals,
)
from entroping.bridge.redaction_review import (
    RedactionReviewReport,
)
from entroping.core.report_artifact_manifest import write_report_artifact_manifest


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
