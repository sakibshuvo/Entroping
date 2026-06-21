"""Compatibility guardrails for the locked v4.1 CLI surface."""

import re
from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from entroping.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
HELP_ENV = {"COLUMNS": "120", "NO_COLOR": "1"}
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True, slots=True)
class CliContract:
    signature: str
    help_args: tuple[str, ...]
    flags: tuple[str, ...]


LOCKED_CLI_CONTRACTS = (
    CliContract(
        "entroping init [--minimal] [--github-actions]",
        ("init", "--help"),
        ("--minimal", "--github-actions"),
    ),
    CliContract(
        "entroping doctor [--ci] [--output <text|json>]",
        ("doctor", "--help"),
        ("--ci", "--output"),
    ),
    CliContract("entroping config list", ("config", "list", "--help"), ()),
    CliContract(
        "entroping config set --agent <builder|auditor|breaker> --model <model-id>",
        ("config", "set", "--help"),
        ("--agent", "--model"),
    ),
    CliContract(
        "entroping config vendor-policy-pack --pack <path> [--name <dir>]",
        ("config", "vendor-policy-pack", "--help"),
        ("--pack", "--name"),
    ),
    CliContract(
        "entroping config test-policy-pack --pack <path> [--output <text|json>]",
        ("config", "test-policy-pack", "--help"),
        ("--pack", "--output"),
    ),
    CliContract(
        (
            "entroping architect build [--new] [--changed-from <ref>] [--prompt <text>] "
            "[--strategy merge] [--tag <tag>] [--agent <builder|breaker>]"
        ),
        ("architect", "build", "--help"),
        ("--new", "--changed-from", "--prompt", "--strategy", "--tag", "--agent"),
    ),
    CliContract(
        "entroping architect refactor --target <glob> --prompt <text> [--preview]",
        ("architect", "refactor", "--help"),
        ("--target", "--prompt", "--preview"),
    ),
    CliContract(
        (
            "entroping architect audit "
            "[--focus <logic|auditor>] [--output <json|md>] [--changed-from <ref>]"
        ),
        ("architect", "audit", "--help"),
        ("--focus", "--output", "--changed-from"),
    ),
    CliContract(
        (
            "entroping watch [--port <port>] [--target <url>] "
            "[--scope-host <host> ...] [--scope-url-prefix <url> ...]"
        ),
        ("watch", "--help"),
        ("--port", "--target", "--scope-host", "--scope-url-prefix"),
    ),
    CliContract(
        (
            "entroping freeze --name <flow> [--golden] [--mock <service>] [--dry-run] "
            "[capture filters]"
        ),
        ("freeze", "--help"),
        (
            "--name",
            "--golden",
            "--mock",
            "--dry-run",
            "--include-host",
            "--exclude-host",
            "--include-method",
            "--exclude-method",
            "--include-path",
            "--exclude-path",
        ),
    ),
    CliContract(
        "entroping map [--export <mermaid|dot|md|png>] [capture filters]",
        ("map", "--help"),
        (
            "--export",
            "--include-host",
            "--exclude-host",
            "--include-method",
            "--exclude-method",
            "--include-path",
            "--exclude-path",
        ),
    ),
    CliContract("entroping studio [--env <name>]", ("studio", "--help"), ("--env",)),
    CliContract(
        "entroping run [--env <name>] [--suite <name>] [--tag <tag>] "
        "[--tag-expression <expr>] [--operation-id <id>] [--ci] [--parallel] "
        "[--fail-fast] [--dry-run] [--report <html|junit|json|drift> ...] "
        "[--drift-check] [--changed-from <ref>] [--rerun-failures]",
        ("run", "--help"),
        (
            "--env",
            "--suite",
            "--tag",
            "--tag-expression",
            "--operation-id",
            "--ci",
            "--parallel",
            "--fail-fast",
            "--dry-run",
            "--report",
            "--drift-check",
            "--changed-from",
            "--rerun-failures",
        ),
    ),
    CliContract("entroping report bug", ("report", "bug", "--help"), ()),
    CliContract(
        "entroping report delta [--base <path>] [--current <path>] [--output <md|json>]",
        ("report", "delta", "--help"),
        ("--base", "--current", "--output"),
    ),
    CliContract(
        (
            "entroping report badges [--output <directory>] [--run-json <path>] "
            "[--policy-json <path>] [--openapi-json <path>] [--traceability-json <path>]"
        ),
        ("report", "badges", "--help"),
        ("--output", "--run-json", "--policy-json", "--openapi-json", "--traceability-json"),
    ),
    CliContract(
        "entroping report redaction [--output <md|html>]",
        ("report", "redaction", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report capture-summary [--output <md|json>]",
        ("report", "capture-summary", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report policy [--output <md|json>]",
        ("report", "policy", "--help"),
        ("--output",),
    ),
    CliContract(
        (
            "entroping report policy-diff [--base <path>] [--current <path>] "
            "[--output <md|json>] [--fail-on-change]"
        ),
        ("report", "policy-diff", "--help"),
        ("--base", "--current", "--output", "--fail-on-change"),
    ),
    CliContract(
        "entroping report gate-coverage [--output <md|json>]",
        ("report", "gate-coverage", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report gate-injection --target <path> [--output <md|json>]",
        ("report", "gate-injection", "--help"),
        ("--target", "--output"),
    ),
    CliContract(
        "entroping report test-quality [--output <md|json>]",
        ("report", "test-quality", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report test-pyramid [--output <md|json>]",
        ("report", "test-pyramid", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report artifact-manifest [--output <path>] [--fail-on-incomplete]",
        ("report", "artifact-manifest", "--help"),
        ("--output", "--fail-on-incomplete"),
    ),
    CliContract(
        "entroping report evidence-bundle [--output <path>]",
        ("report", "evidence-bundle", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report design-partner-feedback [--output <path>]",
        ("report", "design-partner-feedback", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report runtime-card [--output <md|json>]",
        ("report", "runtime-card", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report handoff [--output <md|json>] [--fail-on-insufficient]",
        ("report", "handoff", "--help"),
        ("--output", "--fail-on-insufficient"),
    ),
    CliContract(
        "entroping report notification-packet [--output <md|json>]",
        ("report", "notification-packet", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report team-evidence-readiness [--output <md|json>]",
        ("report", "team-evidence-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report team-access-control-plan [--output <md|json>]",
        ("report", "team-access-control-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report integration-readiness [--output <md|json>]",
        ("report", "integration-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report devex-readiness [--output <md|json>]",
        ("report", "devex-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-cloud-readiness [--output <md|json>]",
        ("report", "evidence-cloud-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-cloud-export [--output <md|json>]",
        ("report", "evidence-cloud-export", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-cloud-workspace --manifest <path> [--output <md|json>]",
        ("report", "evidence-cloud-workspace", "--help"),
        ("--manifest", "--output"),
    ),
    CliContract(
        "entroping report evidence-cloud-dashboard --manifest <path> [--output <html|json>]",
        ("report", "evidence-cloud-dashboard", "--help"),
        ("--manifest", "--output"),
    ),
    CliContract(
        "entroping report evidence-links [--output <md|json>]",
        ("report", "evidence-links", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-portal [--output <html|json>]",
        ("report", "evidence-portal", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report pr-evidence-card [--output <md|json>]",
        ("report", "pr-evidence-card", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-action-plan [--output <md|json>]",
        ("report", "evidence-action-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report connector-intent [--output <md|json>]",
        ("report", "connector-intent", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report external-test-evidence [--output <md|json>]",
        ("report", "external-test-evidence", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report observability-packet [--output <md|json>]",
        ("report", "observability-packet", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report api-inventory [--output <md|json>]",
        ("report", "api-inventory", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report mutation-readiness [--output <md|json>]",
        ("report", "mutation-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report evidence-index [--output <md|json>]",
        ("report", "evidence-index", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-seed [--output <md|json>]",
        ("report", "qa-brain-seed", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-eval-plan [--output <md|json>]",
        ("report", "qa-brain-eval-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-retrieval-plan [--output <md|json>]",
        ("report", "qa-brain-retrieval-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-prompt-plan [--output <md|json>]",
        ("report", "qa-brain-prompt-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-fine-tune-readiness [--output <md|json>]",
        ("report", "qa-brain-fine-tune-readiness", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-model-packaging-plan [--output <md|json>]",
        ("report", "qa-brain-model-packaging-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report qa-brain-routing-plan [--output <md|json>]",
        ("report", "qa-brain-routing-plan", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report pilot-metrics [--output <md|json>]",
        ("report", "pilot-metrics", "--help"),
        ("--output",),
    ),
    CliContract(
        (
            "entroping report agent-bundle [--output <md|json>] "
            "[--role <builder|auditor|breaker>] [--scope <path>]"
        ),
        ("report", "agent-bundle", "--help"),
        ("--output", "--role", "--scope"),
    ),
    CliContract(
        "entroping report traceability [--output <md|json>]",
        ("report", "traceability", "--help"),
        ("--output",),
    ),
    CliContract(
        (
            "entroping report github-annotations "
            "[--junit <path>] [--drift <path>] [--traceability] [--max-annotations <n>]"
        ),
        ("report", "github-annotations", "--help"),
        ("--junit", "--drift", "--traceability", "--max-annotations"),
    ),
    CliContract(
        (
            "entroping report sarif "
            "[--output <path>] [--junit <path>] [--drift <path>] [--traceability]"
        ),
        ("report", "sarif", "--help"),
        ("--output", "--junit", "--drift", "--traceability"),
    ),
    CliContract(
        ("entroping report promote-drift-baseline [--candidate <path>] [--output <path>]"),
        ("report", "promote-drift-baseline", "--help"),
        ("--candidate", "--output"),
    ),
    CliContract(
        (
            "entroping report review-summary "
            "[--output md] [--junit <path>] [--run-json <path>] [--drift <path>] "
            "[--traceability]"
        ),
        ("report", "review-summary", "--help"),
        ("--output", "--junit", "--run-json", "--drift", "--traceability"),
    ),
)

DEPRECATED_INVOCATIONS = (
    ("gen",),
    ("fix",),
    ("scan",),
    ("chaos",),
    ("verify",),
    ("build",),
    ("auth",),
    ("report", "--type", "json"),
    ("--verbose",),
    ("--dry-run",),
)

REPORT_ARTIFACTS = (
    ".entroping/latest-run.json",
    ".entroping/agent-runs/*.json",
    "reports/approvals/*.json",
    "reports/run-latest.json",
    "reports/junit.xml",
    "reports/run-latest.html",
    "reports/drift.json",
    "reports/drift-baseline.candidate.json",
    ".entroping/drift-baseline.json",
    "reports/bug.md",
    "reports/redaction-review.md",
    "reports/redaction-review.html",
    "reports/effective-policy.md",
    "reports/effective-policy.json",
    "reports/test-quality.md",
    "reports/test-quality.json",
    "reports/test-pyramid.md",
    "reports/test-pyramid.json",
    "reports/external-test-evidence.md",
    "reports/external-test-evidence.json",
    "stdout Effective Policy Diff Markdown/JSON",
    "reports/badges/*.json",
    "reports/evidence-bundle.json",
    "reports/design-partner-feedback.json",
    "reports/runtime-card.md",
    "reports/runtime-card.json",
    "reports/handoff.md",
    "reports/handoff.json",
    "reports/notification-packet.md",
    "reports/notification-packet.json",
    "reports/team-evidence-readiness.md",
    "reports/team-evidence-readiness.json",
    "reports/team-access-control-plan.md",
    "reports/team-access-control-plan.json",
    "reports/evidence-cloud-readiness.md",
    "reports/evidence-cloud-readiness.json",
    "reports/evidence-cloud-export.md",
    "reports/evidence-cloud-export.json",
    "reports/evidence-cloud-workspace.md",
    "reports/evidence-cloud-workspace.json",
    "reports/evidence-cloud-dashboard.html",
    "reports/evidence-cloud-dashboard.json",
    "reports/evidence-links.md",
    "reports/evidence-links.json",
    "reports/evidence-portal.html",
    "reports/evidence-portal.json",
    "reports/pr-evidence-card.md",
    "reports/pr-evidence-card.json",
    "reports/evidence-action-plan.md",
    "reports/evidence-action-plan.json",
    "reports/observability-packet.md",
    "reports/observability-packet.json",
    "reports/api-inventory.md",
    "reports/api-inventory.json",
    "reports/mutation-readiness.md",
    "reports/mutation-readiness.json",
    "reports/evidence-index.md",
    "reports/evidence-index.json",
    "reports/qa-brain-seed.md",
    "reports/qa-brain-seed.json",
    "reports/qa-brain-eval-plan.md",
    "reports/qa-brain-eval-plan.json",
    "reports/qa-brain-retrieval-plan.md",
    "reports/qa-brain-retrieval-plan.json",
    "reports/qa-brain-prompt-plan.md",
    "reports/qa-brain-prompt-plan.json",
    "reports/qa-brain-fine-tune-readiness.md",
    "reports/qa-brain-fine-tune-readiness.json",
    "reports/qa-brain-model-packaging-plan.md",
    "reports/qa-brain-model-packaging-plan.json",
    "reports/qa-brain-routing-plan.md",
    "reports/qa-brain-routing-plan.json",
    "reports/pilot-metrics.md",
    "reports/pilot-metrics.json",
    "reports/agent-bundle.md",
    "reports/agent-bundle.json",
    "reports/review-summary.md",
    "reports/entroping.sarif",
    "stdout Run Delta Markdown/JSON",
    "stdout Architect OpenAPI audit JSON",
    "stdout Markdown",
    "stdout GitHub Actions annotations",
)


def test_cli_compatibility_audit_doc_covers_current_docs_and_artifacts() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = {
        "TDS": (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8"),
        "COMMAND_CHEAT_SHEET": (
            REPO_ROOT / "docs" / "technical" / "COMMAND_CHEAT_SHEET.md"
        ).read_text(encoding="utf-8"),
        "CLI_COMPATIBILITY_AUDIT": (
            REPO_ROOT / "docs" / "technical" / "CLI_COMPATIBILITY_AUDIT.md"
        ).read_text(encoding="utf-8"),
    }

    for contract in LOCKED_CLI_CONTRACTS:
        for name, content in docs.items():
            assert contract.signature in content, f"{contract.signature} missing from {name}"

    assert "COMMAND_CHEAT_SHEET.md" in readme
    assert "CLI_COMPATIBILITY_AUDIT.md" in readme
    assert "| Workflow | Primary command | Purpose |" in readme

    audit = docs["CLI_COMPATIBILITY_AUDIT"]
    for artifact in REPORT_ARTIFACTS:
        assert artifact in audit
    for exit_code in ("`0`", "`1`", "`2`"):
        assert exit_code in audit
    assert "Locked alpha" in audit
    assert "No alias is compatibility-supported" in audit


def test_post_alpha_cli_ux_decisions_are_documented_before_surface_changes() -> None:
    audit = (REPO_ROOT / "docs" / "technical" / "CLI_COMPATIBILITY_AUDIT.md").read_text(
        encoding="utf-8"
    )
    qanstitution_reference = (
        REPO_ROOT / "docs" / "technical" / "QANSTITUTION_REFERENCE.md"
    ).read_text(encoding="utf-8")

    required_audit_phrases = [
        "## Post-Alpha UX Decision Queue",
        "Named environments remain the supported runtime contract",
        "arbitrary env-file paths remain deferred",
        "`tests/generated/` remains the only generated Hurl output root",
        "Historical brainstorm commands remain unavailable",
        "Friendly guidance may be added without adding aliases",
        "QAnstitution schema compatibility is not package versioning",
    ]
    for phrase in required_audit_phrases:
        assert phrase in audit

    required_schema_phrases = [
        "## QAnstitution Schema Compatibility",
        "`qanstitution.yaml` remains the only supported policy filename",
        "The top-level `version` field is policy metadata",
        "not the Python package version",
        "Unknown top-level fields continue to fail validation",
        "Removing, renaming, or making a field required needs a migration issue",
    ]
    for phrase in required_schema_phrases:
        assert phrase in qanstitution_reference


def test_typer_help_matches_locked_cli_contract_flags() -> None:
    runner = CliRunner()

    root_help = runner.invoke(app, ["--help"], env=HELP_ENV)
    assert root_help.exit_code == 0
    root_output = ANSI_RE.sub("", root_help.output)
    for command in (
        "init",
        "doctor",
        "config",
        "architect",
        "watch",
        "freeze",
        "map",
        "studio",
        "run",
        "report",
    ):
        assert command in root_output

    for contract in LOCKED_CLI_CONTRACTS:
        result = runner.invoke(app, list(contract.help_args), env=HELP_ENV)
        assert result.exit_code == 0, contract.help_args
        output = ANSI_RE.sub("", result.output)
        for flag in contract.flags:
            assert flag in output, f"{flag} missing from {contract.help_args}"


def test_deprecated_cli_aliases_are_not_accidentally_reintroduced() -> None:
    runner = CliRunner()

    for invocation in DEPRECATED_INVOCATIONS:
        result = runner.invoke(app, list(invocation))
        assert result.exit_code != 0, invocation
