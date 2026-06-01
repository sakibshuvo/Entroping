"""Project setup and local health commands."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from entroping.cli.shared import console
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.hurl_runner import discover_hurl

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
