from __future__ import annotations

import plistlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "meta" / "FACTORY_OPERATIONS.md"
TEMPLATE = (
    REPO_ROOT
    / "docs"
    / "meta"
    / "templates"
    / "com.entroping.factory-tick.plist"
)


def _section(document: str, heading: str, next_heading: str) -> str:
    start = document.index(heading)
    end = document.index(next_heading, start)
    return document[start:end]


def test_factory_runbook_is_inactive_until_owned_safety_surfaces_exist() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "template is inactive by default and must not be bootstrapped yet" in (
        " ".join(runbook.split())
    )
    assert "`factoryctl tick`" in runbook
    assert "tracked by issue #1569" in runbook
    assert "`factoryctl status`" in runbook
    assert "tracked by issue #1572" in runbook
    assert "retention tracked by issue #1562" in " ".join(runbook.split())
    assert "not size-bounded by launchd" in runbook
    assert "append without rotation" in runbook


def test_factory_runbook_orders_stop_after_status_and_settlement() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    install = _section(runbook, "## Future Install", "## Status and Logs")
    lifecycle = _section(runbook, "## Disable, Restart", "## Recovery Boundaries")

    assert install.index("factoryctl status") < install.index("launchctl bootout")
    assert install.index("terminal tick and settled budget") < install.index(
        "launchctl bootout"
    )
    assert lifecycle.index("factoryctl status") < lifecycle.index("launchctl bootout")
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
        if "factoryctl status" in block:
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
        "{{TICK_INTERVAL_SECONDS}}",
        "{{WORKING_DIRECTORY}}",
    }
    assert "$" not in template
    assert "LaunchAgents" not in template

    rendered = (
        template.replace("{{FACTORYCTL_EXECUTABLE}}", "/opt/entroping/factoryctl")
        .replace("{{WORKING_DIRECTORY}}", "/opt/entroping/repository")
        .replace("{{FACTORY_PATH}}", "/opt/entroping:/usr/bin:/bin:/usr/sbin:/sbin")
        .replace("{{LOG_DIRECTORY}}", "/opt/entroping/logs")
        .replace("{{TICK_INTERVAL_SECONDS}}", "300")
    )
    assert plistlib.loads(rendered.encode("utf-8")) == {
        "Label": "com.entroping.factory-tick",
        "ProgramArguments": ["/opt/entroping/factoryctl", "tick"],
        "WorkingDirectory": "/opt/entroping/repository",
        "EnvironmentVariables": {
            "PATH": "/opt/entroping:/usr/bin:/bin:/usr/sbin:/sbin"
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval": 300,
        "Disabled": True,
        "Umask": 63,
        "StandardOutPath": "/opt/entroping/logs/factory-tick.out.log",
        "StandardErrorPath": "/opt/entroping/logs/factory-tick.err.log",
    }


def test_factory_runbook_is_linked_from_the_vault_index() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(
        encoding="utf-8"
    )

    assert "[[docs/meta/FACTORY_OPERATIONS|FACTORY_OPERATIONS]]" in index
