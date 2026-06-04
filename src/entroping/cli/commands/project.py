"""Project setup and local health commands."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from entroping.brain.persona_loader import PersonaLoadError, load_agent_persona
from entroping.cli.shared import console, display_cli_path, safe_cli_text
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.hurl_runner import discover_hurl
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly
from entroping.models.qanstitution import AgentRole, Qanstitution

MINIMAL_QANSTITUTION = """project: "entroping-project"
version: "4.1"
description: "Minimal Entroping governance policy"

gates:
  - id: "no_server_errors"
    description: "Fail when an endpoint returns a server error"
    condition: "true"
    gate: "status < 500"
    enforcement: "block"
  - id: "global_latency"
    description: "Every endpoint should respond within two seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"
  - id: "request_id_header"
    description: "Warn when a response is missing a request ID header for debugging"
    condition: "true"
    gate: 'header "X-Request-Id" exists'
    enforcement: "warn"

settings:
  timeout: 30000
  parallel_workers: 2
  follow_redirects: true
  retry: 0
"""
_AGENT_ROLE_ORDER: tuple[AgentRole, ...] = ("builder", "auditor", "breaker")


def register_project_commands(root_app: typer.Typer) -> None:
    root_app.command()(init)
    root_app.command()(doctor)


def init(
    minimal: Annotated[
        bool,
        typer.Option("--minimal", help="Create only the minimum required runtime files."),
    ] = False,
) -> None:
    """Create the standard local Entroping project directories."""

    directories = [Path("tests"), Path("envs"), Path(".entroping")]
    if not minimal:
        directories.extend([Path("rules"), Path("agents"), Path("reports")])
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    config_path = Path("qanstitution.yaml")
    if config_path.exists():
        console.print("qanstitution.yaml already exists; left unchanged.")
    else:
        config_path.write_text(MINIMAL_QANSTITUTION, encoding="utf-8")
        console.print("Created minimal qanstitution.yaml.")
    console.print("[green]Initialized Entroping project structure.[/green]")


def doctor() -> None:
    """Check local tool availability without making network calls."""

    hurl = discover_hurl()
    hurl_parser = discover_hurl("hurlfmt")
    console.print(f"Python: {sys.version.split()[0]}")
    if hurl.available:
        console.print(f"Hurl: [green]found[/green] at {hurl.path}")
    else:
        console.print("Hurl: [yellow]not found[/yellow] (install hurl before running suites)")
    if hurl_parser.available:
        console.print(f"Hurl parser: [green]found[/green] at {hurl_parser.path}")
    else:
        console.print(
            "Hurl parser: [yellow]not found[/yellow] "
            "(install hurlfmt before Architect generated-Hurl validation)"
        )
    _report_traffic_state_health()

    config_path = Path("qanstitution.yaml")
    if not config_path.exists():
        console.print("QAnstitution: [yellow]not found[/yellow] (run entroping init --minimal)")
        return

    try:
        law = load_qanstitution(config_path)
    except QanstitutionLoadError as exc:
        console.print("[red]QAnstitution: invalid[/red]")
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(
        f"QAnstitution: [green]valid[/green] ({len(law.gates)} gates, "
        f"{len(law.imports)} imports)"
    )
    _report_agent_readiness(law, config_path=config_path)


def _report_traffic_state_health() -> None:
    state_path = Path(".entroping") / "state.db"
    if not state_path.exists():
        console.print(
            "Traffic state: [yellow]not found[/yellow] "
            "(capture traffic with entroping watch)"
        )
        return

    try:
        exchanges = list_project_exchanges_readonly(Path.cwd())
    except TrafficStoreError as exc:
        console.print("[red]Traffic state: invalid[/red]")
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    suffix = "exchange" if len(exchanges) == 1 else "exchanges"
    console.print(
        "[green]Traffic state: valid[/green] "
        f"(.entroping/state.db, {len(exchanges)} {suffix})"
    )


def _report_agent_readiness(law: Qanstitution, *, config_path: Path) -> None:
    if not law.agents:
        console.print("Agents: [yellow]none configured[/yellow] (AI commands optional)")
        return

    noun = "agent" if len(law.agents) == 1 else "agents"
    console.print(f"Agents: {len(law.agents)} configured {noun}")
    invalid = False
    for role in _AGENT_ROLE_ORDER:
        if role not in law.agents:
            continue
        try:
            persona = load_agent_persona(law, role, config_path=config_path)
        except PersonaLoadError as exc:
            invalid = True
            console.print(f"[red]Agent {role}: invalid[/red]")
            console.print(safe_cli_text(exc), style="red", markup=False)
            continue

        console.print(
            f"Agent {role}: ready "
            f"(model {safe_cli_text(persona.model)}, "
            f"persona {display_cli_path(persona.source_path)})",
            style="green",
            markup=False,
        )
        _report_agent_api_key_env(role, persona.api_key_env)

    if invalid:
        raise typer.Exit(1)


def _report_agent_api_key_env(role: AgentRole, api_key_env: str | None) -> None:
    if api_key_env is None:
        console.print(f"Agent {role} api_key_env: [yellow]not configured[/yellow]")
        return
    if api_key_env in os.environ:
        console.print(f"Agent {role} api_key_env {api_key_env}: [green]set[/green]")
    else:
        console.print(f"Agent {role} api_key_env {api_key_env}: [yellow]not set[/yellow]")
