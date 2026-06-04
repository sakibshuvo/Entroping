"""Configuration command adapter."""

from pathlib import Path
from typing import Annotated

import typer

from entroping.cli.shared import console, display_cli_path
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.config_writer import (
    ConfigUpdateError,
    update_agent_model_with_persona_template,
)
from entroping.core.policy_pack_vendor import PolicyPackVendorError, vendor_policy_pack
from entroping.models.qanstitution import AgentRole

app = typer.Typer(help="Inspect or update non-secret configuration.")


@app.command("list")
def config_list() -> None:
    """Show resolved non-secret configuration."""

    try:
        law = load_qanstitution(Path("qanstitution.yaml"))
    except QanstitutionLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"Project: {law.project}")
    if law.version is not None:
        console.print(f"Version: {law.version}")
    if law.description is not None:
        console.print(f"Description: {law.description}")

    if law.sources is None:
        console.print("Sources: none")
    else:
        console.print("Sources:")
        if law.sources.spec is not None:
            console.print(f"  Spec: {law.sources.spec}")
        if law.sources.stories is not None:
            console.print(f"  Stories: {law.sources.stories}")
        if law.sources.traffic is not None:
            console.print(f"  Traffic: {law.sources.traffic}")
        if law.sources.graph is not None:
            console.print(f"  Graph: {law.sources.graph}")
        if law.sources.types is not None:
            console.print(f"  Types: {law.sources.types}")

    console.print(f"Imports: {len(law.imports)}")
    console.print(f"Gates: {len(law.gates)}")
    console.print("Settings:")
    console.print(f"  timeout: {law.settings.timeout}")
    console.print(f"  parallel_workers: {law.settings.parallel_workers}")
    console.print(f"  follow_redirects: {str(law.settings.follow_redirects).lower()}")
    console.print(f"  retry: {law.settings.retry}")

    if not law.agents:
        console.print("Agents: none")
        return

    console.print("Agents:")
    for role in _agent_role_order():
        agent_config = law.agents.get(role)
        if agent_config is None:
            continue
        console.print(f"  {role}:")
        console.print(f"    source: {agent_config.source}")
        console.print(f"    model: {agent_config.model}")
        if agent_config.api_base is not None:
            console.print(f"    api_base: {agent_config.api_base}")
        if agent_config.api_key_env is not None:
            console.print(f"    api_key_env: {agent_config.api_key_env}")
        console.print(f"    temperature: {agent_config.temperature}")
        if agent_config.max_tokens is not None:
            console.print(f"    max_tokens: {agent_config.max_tokens}")


@app.command("set")
def config_set(
    agent: Annotated[AgentRole, typer.Option("--agent", help="Agent role to configure.")],
    model: Annotated[str, typer.Option("--model", help="Provider/model identifier.")],
) -> None:
    """Configure model routing for an agent role."""

    try:
        result = update_agent_model_with_persona_template(
            Path("qanstitution.yaml"),
            agent=agent,
            model=model,
        )
    except ConfigUpdateError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    law = result.law
    agent_config = law.agents[agent]
    console.print(f"[green]Configured {agent} model:[/green] {agent_config.model}")
    console.print(f"Persona source: {agent_config.source}")
    if result.persona_template_path is not None:
        created_path = display_cli_path(result.persona_template_path)
        console.print(f"Created persona template: {created_path}")


@app.command("vendor-policy-pack")
def config_vendor_policy_pack(
    pack: Annotated[Path, typer.Option("--pack", help="Local policy-pack directory.")],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Destination directory under policy-packs/."),
    ] = None,
) -> None:
    """Vendor a reviewed local policy pack into this project."""

    try:
        result = vendor_policy_pack(
            project_root=Path.cwd(),
            config_path=Path("qanstitution.yaml"),
            pack_path=pack,
            name=name,
        )
    except PolicyPackVendorError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    noun = "gate" if len(result.gate_ids) == 1 else "gates"
    console.print(f"[green]Vendored policy pack {result.pack_id}[/green]")
    console.print(f"Destination: {display_cli_path(result.destination)}")
    console.print(f"Import: {result.import_ref}")
    console.print(f"Gates: {len(result.gate_ids)} {noun}")
    if result.final_gate_ids:
        console.print(f"Final gates: {', '.join(result.final_gate_ids)}")


def _agent_role_order() -> tuple[AgentRole, ...]:
    return ("builder", "auditor", "breaker")
