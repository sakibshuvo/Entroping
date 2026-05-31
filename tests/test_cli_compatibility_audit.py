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
    CliContract("entroping init [--minimal]", ("init", "--help"), ("--minimal",)),
    CliContract("entroping doctor", ("doctor", "--help"), ()),
    CliContract("entroping config list", ("config", "list", "--help"), ()),
    CliContract(
        "entroping config set --agent <builder|auditor|breaker> --model <model-id>",
        ("config", "set", "--help"),
        ("--agent", "--model"),
    ),
    CliContract(
        "entroping architect build [--new] [--prompt <text>] [--strategy merge] [--tag <tag>]",
        ("architect", "build", "--help"),
        ("--new", "--prompt", "--strategy", "--tag"),
    ),
    CliContract(
        "entroping architect refactor --target <glob> --prompt <text>",
        ("architect", "refactor", "--help"),
        ("--target", "--prompt"),
    ),
    CliContract(
        "entroping architect audit [--focus logic] [--output <json|md>]",
        ("architect", "audit", "--help"),
        ("--focus", "--output"),
    ),
    CliContract(
        "entroping watch [--port <port>] [--target <url>]",
        ("watch", "--help"),
        ("--port", "--target"),
    ),
    CliContract(
        "entroping freeze --name <flow> [--golden] [--mock <service>]",
        ("freeze", "--help"),
        ("--name", "--golden", "--mock"),
    ),
    CliContract(
        "entroping map [--export <mermaid|dot|md|png>]",
        ("map", "--help"),
        ("--export",),
    ),
    CliContract("entroping studio [--env <name>]", ("studio", "--help"), ("--env",)),
    CliContract(
        "entroping run [--env <name>] [--tag <tag>] [--ci] [--parallel] "
        "[--report <html|junit|json|drift> ...] [--drift-check]",
        ("run", "--help"),
        ("--env", "--tag", "--ci", "--parallel", "--report", "--drift-check"),
    ),
    CliContract("entroping report bug", ("report", "bug", "--help"), ()),
    CliContract(
        "entroping report redaction [--output <md|html>]",
        ("report", "redaction", "--help"),
        ("--output",),
    ),
    CliContract(
        "entroping report traceability [--output md]",
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
    "reports/run-latest.json",
    "reports/junit.xml",
    "reports/run-latest.html",
    "reports/drift.json",
    "reports/drift-baseline.candidate.json",
    "reports/bug.md",
    "reports/redaction-review.md",
    "reports/redaction-review.html",
    "stdout Markdown",
    "stdout GitHub Actions annotations",
)


def test_cli_compatibility_audit_doc_covers_current_docs_and_artifacts() -> None:
    docs = {
        "README": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
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

    audit = docs["CLI_COMPATIBILITY_AUDIT"]
    for artifact in REPORT_ARTIFACTS:
        assert artifact in audit
    for exit_code in ("`0`", "`1`", "`2`"):
        assert exit_code in audit
    assert "Locked alpha" in audit
    assert "No alias is compatibility-supported" in audit


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
