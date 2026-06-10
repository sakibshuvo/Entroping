"""Project setup and local health commands."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from entroping.brain.persona_loader import PersonaLoadError, load_agent_persona
from entroping.cli.shared import console, display_cli_path, safe_cli_text
from entroping.core.ci_readiness import collect_ci_readiness
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.github_actions_starter import (
    GitHubActionsStarterError,
    install_github_actions_starter,
)
from entroping.core.hurl_runner import (
    HURL_MINIMUM_SUPPORTED_VERSION,
    HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
    discover_hurl,
)
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly
from entroping.models.doctor import (
    DoctorAgentHealth,
    DoctorCiReadiness,
    DoctorCiReadinessCheck,
    DoctorHealthReport,
    DoctorHealthStatus,
    DoctorHurlCompatibility,
    DoctorQanstitutionHealth,
    DoctorToolHealth,
    DoctorTrafficStateHealth,
)
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
_DOCTOR_OUTPUTS = frozenset({"text", "json"})


def register_project_commands(root_app: typer.Typer) -> None:
    root_app.command(rich_help_panel="Core Workflow")(init)
    root_app.command(rich_help_panel="Core Workflow")(doctor)


def init(
    minimal: Annotated[
        bool,
        typer.Option("--minimal", help="Create only the minimum required runtime files."),
    ] = False,
    github_actions: Annotated[
        bool,
        typer.Option("--github-actions", help="Install the reviewed GitHub Actions CI starter."),
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
    if github_actions:
        try:
            starter = install_github_actions_starter(project_root=Path.cwd())
        except GitHubActionsStarterError as exc:
            console.print(safe_cli_text(str(exc)), style="red")
            raise typer.Exit(1) from exc
        console.print(
            f"Installed GitHub Actions starter workflow: {display_cli_path(starter.path)}"
        )
    console.print("[green]Initialized Entroping project structure.[/green]")


def doctor(
    ci: Annotated[
        bool,
        typer.Option("--ci", help="Run strict CI-readiness checks without provider calls."),
    ] = False,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: text or json."),
    ] = "text",
) -> None:
    """Check local tool availability without making network calls."""

    normalized_output = output.strip().lower()
    if normalized_output not in _DOCTOR_OUTPUTS:
        console.print(f"[yellow]Unsupported doctor output: {output}[/yellow]")
        raise typer.Exit(2)

    report = _collect_doctor_health(ci=ci)
    if normalized_output == "json":
        sys.stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        _render_doctor_health(report)

    if report.status == "error":
        raise typer.Exit(1)


def _collect_doctor_health(*, ci: bool = False) -> DoctorHealthReport:
    hurl = discover_hurl()
    hurl_parser = discover_hurl("hurlfmt")
    hurl_health = _tool_health("hurl", hurl.available, hurl.path)
    hurl_compatibility = _hurl_compatibility_health(hurl)
    hurl_parser_health = _tool_health("hurlfmt", hurl_parser.available, hurl_parser.path)
    traffic_state = _collect_traffic_state_health()
    config_path = Path("qanstitution.yaml")
    qanstitution, law = _collect_qanstitution_health(config_path)
    agents = _collect_agent_readiness(law, config_path=config_path) if law is not None else []
    ci_readiness = (
        collect_ci_readiness(
            project_root=Path.cwd(),
            hurl_available=hurl.available,
            hurl_compatibility=hurl_compatibility,
            law=law,
        )
        if ci
        else None
    )
    statuses = [
        hurl_health.status,
        hurl_compatibility.status,
        hurl_parser_health.status,
        traffic_state.status,
        qanstitution.status,
        *(agent.status for agent in agents),
    ]
    if ci_readiness is not None:
        statuses.append(ci_readiness.status)
    return DoctorHealthReport(
        status=_overall_status(statuses),
        python_version=sys.version.split()[0],
        tools={
            "hurl": hurl_health,
            "hurl_parser": hurl_parser_health,
        },
        hurl_compatibility=hurl_compatibility,
        traffic_state=traffic_state,
        qanstitution=qanstitution,
        agents=agents,
        ci_readiness=ci_readiness,
    )


def _tool_health(name: str, available: bool, path: str | None) -> DoctorToolHealth:
    if available:
        return DoctorToolHealth(
            status="ok",
            available=True,
            path=path,
            message=f"{name} found",
        )
    return DoctorToolHealth(
        status="warn",
        available=False,
        path=None,
        message=f"{name} not found",
    )


def _hurl_compatibility_health(hurl: object) -> DoctorHurlCompatibility:
    available = _status_bool(hurl, "available")
    path = _status_optional_str(hurl, "path")
    if not available:
        return DoctorHurlCompatibility(
            status="warn",
            compatibility="missing",
            version=None,
            minimum_version=HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
            path=None,
            message=(
                "hurl not found; install hurl "
                f"{HURL_MINIMUM_SUPPORTED_VERSION_TEXT} or newer"
            ),
        )

    version_checked = _status_bool(hurl, "version_checked")
    version = _status_optional_str(hurl, "version")
    version_parts = _status_version_parts(hurl)
    if not version_checked:
        return DoctorHurlCompatibility(
            status="ok",
            compatibility="compatible",
            version=version,
            minimum_version=HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
            path=path,
            message="hurl found",
        )

    if version_parts is None or version is None:
        version_error = _status_optional_str(hurl, "version_error")
        version_output = _status_optional_str(hurl, "version_output")
        detail = version_error or version_output or "no version output"
        return DoctorHurlCompatibility(
            status="warn",
            compatibility="unparsable",
            version=None,
            minimum_version=HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
            path=path,
            message=f"hurl version is unparsable from: {safe_cli_text(detail)}",
        )

    if version_parts < HURL_MINIMUM_SUPPORTED_VERSION:
        return DoctorHurlCompatibility(
            status="warn",
            compatibility="unsupported",
            version=version,
            minimum_version=HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
            path=path,
            message=(
                f"hurl {version} is older than the minimum supported version "
                f"{HURL_MINIMUM_SUPPORTED_VERSION_TEXT}"
            ),
        )

    return DoctorHurlCompatibility(
        status="ok",
        compatibility="compatible",
        version=version,
        minimum_version=HURL_MINIMUM_SUPPORTED_VERSION_TEXT,
        path=path,
        message=(
            f"hurl {version} is compatible with minimum supported version "
            f"{HURL_MINIMUM_SUPPORTED_VERSION_TEXT}"
        ),
    )


def _status_bool(status: object, name: str) -> bool:
    raw = getattr(status, name, False)
    return raw if isinstance(raw, bool) else False


def _status_optional_str(status: object, name: str) -> str | None:
    raw = getattr(status, name, None)
    return raw if isinstance(raw, str) else None


def _status_version_parts(status: object) -> tuple[int, int, int] | None:
    raw = getattr(status, "version_parts", None)
    if not isinstance(raw, tuple) or len(raw) != 3:
        return None
    if not all(isinstance(part, int) for part in raw):
        return None
    return raw


def _collect_qanstitution_health(
    config_path: Path,
) -> tuple[DoctorQanstitutionHealth, Qanstitution | None]:
    if not config_path.exists():
        return (
            DoctorQanstitutionHealth(
                status="warn",
                path=str(config_path),
                message="qanstitution.yaml not found",
            ),
            None,
        )

    try:
        law = load_qanstitution(config_path)
    except QanstitutionLoadError as exc:
        return (
            DoctorQanstitutionHealth(
                status="error",
                path=str(config_path),
                message=safe_cli_text(exc),
            ),
            None,
        )

    return (
        DoctorQanstitutionHealth(
            status="ok",
            path=str(config_path),
            project=law.project,
            gate_count=len(law.gates),
            import_count=len(law.imports),
            message="qanstitution.yaml valid",
        ),
        law,
    )


def _collect_traffic_state_health() -> DoctorTrafficStateHealth:
    state_path = Path(".entroping") / "state.db"
    if not state_path.exists():
        return DoctorTrafficStateHealth(
            status="warn",
            path=str(state_path),
            message="traffic state not found",
        )

    try:
        exchanges = list_project_exchanges_readonly(Path.cwd())
    except TrafficStoreError as exc:
        return DoctorTrafficStateHealth(
            status="error",
            path=str(state_path),
            message=safe_cli_text(exc),
        )

    return DoctorTrafficStateHealth(
        status="ok",
        path=str(state_path),
        exchange_count=len(exchanges),
        message="traffic state valid",
    )


def _collect_agent_readiness(law: Qanstitution, *, config_path: Path) -> list[DoctorAgentHealth]:
    agents: list[DoctorAgentHealth] = []
    for role in _AGENT_ROLE_ORDER:
        if role not in law.agents:
            continue
        agent_config = law.agents[role]
        try:
            persona = load_agent_persona(law, role, config_path=config_path)
        except PersonaLoadError as exc:
            agents.append(
                DoctorAgentHealth(
                    role=role,
                    status="error",
                    model=safe_cli_text(agent_config.model),
                    source=safe_cli_text(agent_config.source),
                    api_key_env=agent_config.api_key_env,
                    api_key_env_present=(
                        None
                        if agent_config.api_key_env is None
                        else agent_config.api_key_env in os.environ
                    ),
                    message=safe_cli_text(exc),
                )
            )
            continue

        api_key_env_present = (
            None if persona.api_key_env is None else persona.api_key_env in os.environ
        )
        agents.append(
            DoctorAgentHealth(
                role=role,
                status="warn"
                if persona.api_key_env is not None and not api_key_env_present
                else "ok",
                model=safe_cli_text(persona.model),
                source=display_cli_path(persona.source_path),
                api_key_env=persona.api_key_env,
                api_key_env_present=api_key_env_present,
                message="api_key_env not set"
                if persona.api_key_env is not None and not api_key_env_present
                else "agent ready",
            )
        )
    return agents


def _render_doctor_health(report: DoctorHealthReport) -> None:
    console.print(f"Python: {report.python_version}")
    _render_hurl_health(report.tools["hurl"], report.hurl_compatibility)
    _render_tool_health(
        "Hurl parser",
        report.tools["hurl_parser"],
        missing_guidance="install hurlfmt before Architect generated-Hurl validation",
    )
    _render_traffic_state_health(report.traffic_state)
    _render_qanstitution_health(report.qanstitution)
    if report.qanstitution.status == "ok":
        _render_agent_readiness(report.agents)
    if report.ci_readiness is not None:
        _render_ci_readiness(report.ci_readiness)


def _render_tool_health(label: str, tool: DoctorToolHealth, *, missing_guidance: str) -> None:
    if tool.status == "ok":
        console.print(f"{label}: [green]found[/green] at {tool.path}")
        return
    console.print(f"{label}: [yellow]not found[/yellow] ({missing_guidance})")


def _render_hurl_health(
    tool: DoctorToolHealth,
    compatibility: DoctorHurlCompatibility,
) -> None:
    if compatibility.compatibility == "compatible":
        if compatibility.version is None:
            console.print(f"Hurl: [green]found[/green] at {tool.path}")
            return
        console.print(
            "Hurl: [green]found[/green] at "
            f"{tool.path} (version {compatibility.version}, "
            f"compatible with >= {compatibility.minimum_version})"
        )
        return
    if compatibility.compatibility == "missing":
        console.print(
            "Hurl: [yellow]not found[/yellow] "
            f"(install hurl {compatibility.minimum_version} or newer before running suites)"
        )
        return
    if compatibility.compatibility == "unsupported":
        console.print(
            "[yellow]Hurl: unsupported version[/yellow] "
            f"{compatibility.version} at {tool.path} "
            f"(minimum supported {compatibility.minimum_version})"
        )
        return
    console.print(f"[yellow]Hurl: version unparsable[/yellow] at {tool.path}")
    console.print(compatibility.message, style="yellow", markup=False)


def _render_traffic_state_health(traffic_state: DoctorTrafficStateHealth) -> None:
    if traffic_state.status == "warn":
        console.print(
            "Traffic state: [yellow]not found[/yellow] "
            "(capture traffic with entroping watch)"
        )
        return
    if traffic_state.status == "error":
        console.print("[red]Traffic state: invalid[/red]")
        console.print(traffic_state.message, style="red", markup=False)
        return

    exchange_count = traffic_state.exchange_count or 0
    suffix = "exchange" if exchange_count == 1 else "exchanges"
    console.print(
        "[green]Traffic state: valid[/green] "
        f"(.entroping/state.db, {exchange_count} {suffix})"
    )


def _render_qanstitution_health(qanstitution: DoctorQanstitutionHealth) -> None:
    if qanstitution.status == "warn":
        console.print("QAnstitution: [yellow]not found[/yellow] (run entroping init --minimal)")
        return
    if qanstitution.status == "error":
        console.print("[red]QAnstitution: invalid[/red]")
        console.print(qanstitution.message, style="red", markup=False)
        return

    console.print(
        f"QAnstitution: [green]valid[/green] ({qanstitution.gate_count or 0} gates, "
        f"{qanstitution.import_count or 0} imports)"
    )


def _render_agent_readiness(agents: list[DoctorAgentHealth]) -> None:
    if not agents:
        console.print("Agents: [yellow]none configured[/yellow] (AI commands optional)")
        return

    noun = "agent" if len(agents) == 1 else "agents"
    console.print(f"Agents: {len(agents)} configured {noun}")
    for agent in agents:
        if agent.status == "error":
            console.print(f"[red]Agent {agent.role}: invalid[/red]")
            console.print(agent.message, style="red", markup=False)
            continue
        console.print(
            f"Agent {agent.role}: ready "
            f"(model {agent.model}, persona {agent.source})",
            style="green",
            markup=False,
        )
        _render_agent_api_key_env(agent)


def _render_agent_api_key_env(agent: DoctorAgentHealth) -> None:
    if agent.api_key_env is None:
        console.print(f"Agent {agent.role} api_key_env: [yellow]not configured[/yellow]")
        return
    if agent.api_key_env_present:
        console.print(f"Agent {agent.role} api_key_env {agent.api_key_env}: [green]set[/green]")
    else:
        console.print(
            f"Agent {agent.role} api_key_env {agent.api_key_env}: [yellow]not set[/yellow]"
        )


def _render_ci_readiness(readiness: DoctorCiReadiness) -> None:
    if readiness.status == "error":
        console.print("[red]CI readiness: invalid[/red]")
    elif readiness.status == "warn":
        console.print("[yellow]CI readiness: warnings[/yellow]")
    else:
        console.print("[green]CI readiness: ready[/green]")

    for check in readiness.checks:
        _render_ci_readiness_check(check)


def _render_ci_readiness_check(check: DoctorCiReadinessCheck) -> None:
    label = check.id.replace("_", " ")
    label = f"{label[:1].upper()}{label[1:]}"
    if check.status == "error":
        console.print(f"[red]{label}: invalid[/red]")
        console.print(check.message, style="red", markup=False)
        return
    if check.status == "warn":
        console.print(f"[yellow]{label}: warning[/yellow]")
        console.print(check.message, style="yellow", markup=False)
        return
    console.print(f"{label}: [green]ok[/green]")


def _overall_status(statuses: list[DoctorHealthStatus]) -> DoctorHealthStatus:
    if "error" in statuses:
        return "error"
    if "warn" in statuses:
        return "warn"
    return "ok"
