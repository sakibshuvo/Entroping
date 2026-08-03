from __future__ import annotations

import plistlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "meta" / "FACTORY_OPERATIONS.md"
TEMPLATE = REPO_ROOT / "docs" / "meta" / "templates" / "com.entroping.factory-tick.plist"


def _section(document: str, heading: str, next_heading: str) -> str:
    start = document.index(heading)
    end = document.index(next_heading, start)
    return document[start:end]


def test_factory_runbook_is_inactive_until_owned_safety_surfaces_exist() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    safety_state = _section(
        runbook,
        "## Current Safety State",
        "## Provider Capability Registry",
    )
    scheduler = _section(
        runbook,
        "## Scheduler Lease and Assignment Authority",
        "## OpenCode Usage Receipts",
    )

    assert "template is inactive by default and must not be bootstrapped yet" in (
        " ".join(safety_state.split())
    )
    assert "crash/outage recovery" in safety_state
    assert "uv run python scripts/factoryctl.py status" in runbook
    assert "proposal-only end-to-end proof" in safety_state
    assert "`scripts/factoryctl.py tick`" in scheduler
    assert ".entroping/factory-scheduler/scheduler.sqlite3" in scheduler
    assert "budget ledger writer guard" in scheduler
    assert "held through the scheduler transaction commit" in scheduler
    assert "paid_work_authorized: false" in scheduler
    launchd = _section(runbook, "## Contract", "## Render and Validate")
    assert "scheduler lease and idempotency contract is the guard" in " ".join(launchd.split())


def test_factory_runbook_orders_stop_after_status_and_settlement() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    install = _section(runbook, "## Future Install", "## Status and Logs")
    lifecycle = _section(runbook, "## Disable, Restart", "## Recovery Boundaries")

    command = "uv run python scripts/factoryctl.py status"
    assert install.index(command) < install.index("launchctl bootout")
    assert install.index("terminal tick and settled budget") < install.index("launchctl bootout")
    assert lifecycle.index(command) < lifecycle.index("launchctl bootout")
    assert lifecycle.index("terminal and its reservation/cost settlement") < (
        lifecycle.index("launchctl bootout")
    )
    assert "launchctl print-disabled gui/$UID" in install
    assert "launchctl print-disabled gui/$UID" in lifecycle


def test_factory_runbook_commands_avoid_destructive_restart_and_shell_placeholders() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    command_blocks = [
        match.group(1)
        for match in re.finditer(
            r"```text\n(.*?)\n```",
            runbook,
            flags=re.DOTALL,
        )
    ]
    commands = "\n".join(command_blocks)

    for block in command_blocks:
        if "scripts/factoryctl.py status" in block:
            assert "launchctl bootout" not in block
    assert "launchctl kickstart -k" not in commands
    assert "launchctl load" not in commands
    assert "launchctl unload" not in commands
    assert "<LOG_DIRECTORY>" not in commands
    assert 'tail -n 100 "/absolute/path/to/logs/' in commands
    assert "launchctl print-disabled gui/$UID" in commands


def test_factory_tick_launchd_template_parses_to_the_safe_contract() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    placeholders = set(re.findall(r"\{\{[A-Z_]+\}\}", template))
    assert placeholders == {
        "{{FACTORYCTL_EXECUTABLE}}",
        "{{FACTORY_PATH}}",
        "{{LOG_DIRECTORY}}",
        "{{PYTHON_EXECUTABLE}}",
        "{{TICK_INTERVAL_SECONDS}}",
        "{{WORKING_DIRECTORY}}",
    }
    assert "$" not in template
    assert "LaunchAgents" not in template

    rendered = (
        template.replace("{{PYTHON_EXECUTABLE}}", "/opt/entroping/python")
        .replace("{{FACTORYCTL_EXECUTABLE}}", "/opt/entroping/factoryctl")
        .replace("{{WORKING_DIRECTORY}}", "/opt/entroping/repository")
        .replace("{{FACTORY_PATH}}", "/opt/entroping:/usr/bin:/bin:/usr/sbin:/sbin")
        .replace(
            "{{LOG_DIRECTORY}}",
            "/opt/entroping/repository/.entroping/factory-logs",
        )
        .replace("{{TICK_INTERVAL_SECONDS}}", "300")
    )
    assert plistlib.loads(rendered.encode("utf-8")) == {
        "Label": "com.entroping.factory-tick",
        "ProgramArguments": [
            "/opt/entroping/python",
            "-m",
            "scripts.factory_tick_runner",
            "--factoryctl",
            "/opt/entroping/factoryctl",
            "--log-directory",
            "/opt/entroping/repository/.entroping/factory-logs",
        ],
        "WorkingDirectory": "/opt/entroping/repository",
        "EnvironmentVariables": {"PATH": "/opt/entroping:/usr/bin:/bin:/usr/sbin:/sbin"},
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval": 300,
        "Disabled": True,
        "Umask": 63,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }


def test_factory_runbook_is_linked_from_the_vault_index() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")

    assert "[[docs/meta/FACTORY_OPERATIONS|FACTORY_OPERATIONS]]" in index


def test_factory_runbook_documents_authoritative_budget_ledger_boundaries() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())

    required = [
        ".entroping/factory-budget/ledger.sqlite3",
        "python -m scripts.factory_budget_ledger summary",
        "python -m scripts.factory_budget_ledger balance",
        "BEGIN IMMEDIATE",
        "journal_mode=DELETE",
        "synchronous=EXTRA",
        "read-only",
        "global idempotency",
        "refund",
        "manual adjustment",
        "non-spendable reserve",
        "reserves the route's worst-case enforceable usage",
        "Direct DeepSeek is currently the only supported metered queue lane",
        "Metered OpenCode remains blocked",
        "the hold stays `uncertain`",
        "do not call providers from product runtime",
    ]

    for term in required:
        assert term in normalized


def test_factory_runbook_documents_unattended_opencode_preflight_and_receipt() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(runbook.split())

    required = [
        "## Unattended OpenCode Isolation",
        "scripts/opencode_readiness.py --mode verification --format json",
        "scripts/opencode_worker.py --mode review",
        "capability-receipt.json",
        "value-free",
        "private ephemeral `HOME`",
        "`OPENCODE_CONFIG_CONTENT`",
        "no model-issued tools",
        "wrapper-validated explicit `--file` snapshots",
        "20 seconds total",
        "credential-free",
        "`DEEPSEEK_API_KEY`",
        "never persists its value",
        "textual unified-diff proposal",
        "does not apply it",
        "trusted executable",
        "OS or container isolation",
    ]
    for term in required:
        assert term in normalized
