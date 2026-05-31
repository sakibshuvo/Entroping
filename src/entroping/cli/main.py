"""Command-line entrypoint for the Entroping scaffold."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import typer
from rich.console import Console

from entroping import __version__
from entroping.brain import (
    ArchitectOutputParseError,
    ArchitectRefactorError,
    ArchitectWriteError,
    BrainProviderError,
    PersonaLoadError,
    PromptBuildError,
    run_architect_prompt_build,
    run_architect_refactor,
)
from entroping.brain.safety import redact_secret_like_values
from entroping.bridge.openapi_audit import (
    audit_openapi_coverage,
    audit_report_to_dict,
    render_audit_markdown,
)
from entroping.bridge.openapi_to_hurl import (
    GeneratedHurlFile,
    OpenApiCompilationError,
    compile_openapi_to_hurl,
)
from entroping.bridge.story_traceability import (
    compile_story_traceability,
    render_story_traceability_markdown,
)
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.config_writer import (
    ConfigUpdateError,
    update_agent_model_with_persona_template,
)
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.drift_report import DriftReportError
from entroping.core.freeze import FreezeError, run_freeze, run_freeze_mock
from entroping.core.gate_injector import GateInjectionError
from entroping.core.hurl_discovery import discover_hurl_tests, normalize_tag_filters
from entroping.core.hurl_runner import (
    HurlBinaryNotFoundError,
    discover_hurl,
)
from entroping.core.hurl_validator import HurlValidationError
from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document
from entroping.core.report_writer import (
    ReportWriterError,
    load_run_report,
    write_bug_report,
)
from entroping.core.run_workflow import NoHurlTestsMatchedError, execute_run_workflow
from entroping.core.traffic_proxy import (
    DEFAULT_WATCH_PORT,
    TrafficProxyError,
    WatchConfig,
    run_watch,
)
from entroping.models.hurl import HurlMetadataSyntaxError
from entroping.models.qanstitution import AgentRole
from entroping.studio.app import run_studio_app
from entroping.studio.status import (
    StudioDependencyError,
    collect_studio_status,
    ensure_studio_available,
)

console = Console()

app = typer.Typer(
    name="entroping",
    help="AI-native quality governance for API and backend systems.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect or update non-secret configuration.")
architect_app = typer.Typer(help="Generate, refactor, and audit Hurl tests.")
report_app = typer.Typer(help="Generate human handoff artifacts.")

MINIMAL_QANSTITUTION = """project: "entroping-project"
version: "4.1"
description: "Minimal Entroping governance policy"

gates:
  - id: "global_latency"
    description: "Every endpoint should respond within two seconds"
    condition: "true"
    gate: "duration < 2000"
    enforcement: "block"

settings:
  timeout: 30000
  parallel_workers: 2
  follow_redirects: true
  retry: 0
"""


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"entroping {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the Entroping version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run Entroping."""
    _ = version


@app.command()
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


@app.command()
def doctor() -> None:
    """Check local tool availability without making network calls."""

    hurl = discover_hurl()
    console.print(f"Python: {sys.version.split()[0]}")
    if hurl.available:
        console.print(f"Hurl: [green]found[/green] at {hurl.path}")
    else:
        console.print("Hurl: [yellow]not found[/yellow] (install hurl before running suites)")

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


@config_app.command("list")
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


@config_app.command("set")
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
        created_path = _display_cli_path(result.persona_template_path)
        console.print(f"Created persona template: {created_path}")


@architect_app.command("build")
def architect_build(
    new: Annotated[bool, typer.Option("--new", help="Generate new tests.")] = False,
    prompt: Annotated[
        str | None,
        typer.Option("--prompt", help="Scoped generation intent."),
    ] = None,
    strategy: Annotated[str | None, typer.Option("--strategy", help="Merge strategy.")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tag generated tests.")] = None,
) -> None:
    """Generate Hurl tests from configured sources or prompts."""

    normalized_strategy: str | None = None
    if strategy is not None:
        normalized_strategy = strategy.strip().lower()
        if normalized_strategy != "merge":
            console.print(f"[yellow]Unsupported architect build strategy: {strategy}[/yellow]")
            raise typer.Exit(2)
    if prompt is not None:
        _run_architect_prompt_build(
            prompt=prompt,
            tag=tag,
            strategy="merge" if normalized_strategy == "merge" else "create",
        )
        return
    if normalized_strategy == "merge":
        console.print("[yellow]--strategy merge requires --prompt in the current alpha.[/yellow]")
        raise typer.Exit(2)
    if not new:
        console.print("[yellow]Choose a supported architect build mode:[/yellow]")
        console.print("  entroping architect build --new")
        console.print('  entroping architect build --prompt "<intent>"')
        console.print('  entroping architect build --strategy merge --prompt "<intent>"')
        raise typer.Exit(2)

    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect build --new"
            raise ValueError(msg)
        document = load_openapi_document(_configured_spec_reference(law.sources.spec))
        generated = compile_openapi_to_hurl(document, tags=tag_filters)
        written = [_write_generated_hurl_file(item) for item in generated]
    except (QanstitutionLoadError, OpenApiLoadError, OpenApiCompilationError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    noun = "test" if len(written) == 1 else "tests"
    console.print(f"[green]Generated {len(written)} Hurl {noun} under tests/generated.[/green]")
    for path in written:
        console.print(f"Wrote Hurl test: {_display_cli_path(path)}")


def _run_architect_prompt_build(
    *,
    prompt: str,
    tag: list[str] | None,
    strategy: str = "create",
) -> None:
    try:
        tag_filters = normalize_tag_filters(tag)
        law = load_qanstitution(Path("qanstitution.yaml"))
        result = run_architect_prompt_build(
            law=law,
            intent=prompt,
            tags=tuple(sorted(tag_filters)),
            strategy="merge" if strategy == "merge" else "create",
            project_root=Path.cwd(),
            config_path=Path("qanstitution.yaml"),
        )
    except (
        ArchitectOutputParseError,
        ArchitectWriteError,
        BrainProviderError,
        PersonaLoadError,
        PromptBuildError,
        QanstitutionLoadError,
        ValueError,
    ) as exc:
        _print_architect_error(exc)
        raise typer.Exit(1) from exc

    noun = "test" if len(result.written_paths) == 1 else "tests"
    console.print(f"[green]Generated {len(result.written_paths)} Architect Hurl {noun}.[/green]")
    console.print(f"Summary: {_safe_cli_text(result.summary)}", markup=False)
    console.print(f"Model: {_safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    for warning in result.warnings:
        console.print(f"Warning: {_safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {_safe_cli_text(_display_cli_path(path))}", markup=False)


@architect_app.command("refactor")
def architect_refactor(
    target: Annotated[str, typer.Option("--target", help="Target Hurl glob.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Refactor instruction.")],
) -> None:
    """Safely update existing Hurl tests."""

    try:
        law = load_qanstitution(Path("qanstitution.yaml"))
        result = run_architect_refactor(
            law=law,
            target_glob=target,
            prompt=prompt,
            project_root=Path.cwd(),
            config_path=Path("qanstitution.yaml"),
        )
    except (
        ArchitectOutputParseError,
        ArchitectRefactorError,
        ArchitectWriteError,
        BrainProviderError,
        PersonaLoadError,
        PromptBuildError,
        QanstitutionLoadError,
        ValueError,
    ) as exc:
        _print_architect_error(exc)
        raise typer.Exit(1) from exc

    noun = "test" if len(result.written_paths) == 1 else "tests"
    console.print(f"[green]Refactored {len(result.written_paths)} Architect Hurl {noun}.[/green]")
    console.print(f"Summary: {_safe_cli_text(result.summary)}", markup=False)
    console.print(f"Model: {_safe_cli_text(result.model)} ({result.latency_ms} ms)", markup=False)
    for warning in result.warnings:
        console.print(f"Warning: {_safe_cli_text(warning)}", style="yellow", markup=False)
    for path in result.written_paths:
        console.print(f"Wrote Hurl test: {_safe_cli_text(_display_cli_path(path))}", markup=False)


@architect_app.command("audit")
def architect_audit(
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Audit focus. Currently: logic."),
    ] = None,
    output: Annotated[str | None, typer.Option("--output", help="json or md.")] = None,
) -> None:
    """Audit test quality and governance gaps."""

    try:
        audit_focus = _normalize_architect_audit_focus(focus)
        audit_output = _normalize_architect_audit_output(output)
        law = load_qanstitution(Path("qanstitution.yaml"))
        if law.sources is None or law.sources.spec is None or not law.sources.spec.strip():
            msg = "sources.spec is required for architect audit"
            raise ValueError(msg)
        document = load_openapi_document(_configured_spec_reference(law.sources.spec))
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        report = audit_openapi_coverage(document, hurl_tests)
    except (QanstitutionLoadError, OpenApiLoadError, OpenApiCompilationError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    _ = audit_focus
    if audit_output == "json":
        sys.stdout.write(json.dumps(audit_report_to_dict(report), indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_audit_markdown(report))
        sys.stdout.write("\n")

    raise typer.Exit(0 if report.passed else 1)


@app.command()
def watch(
    port: Annotated[int | None, typer.Option("--port", help="Local proxy port.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target upstream URL.")] = None,
) -> None:
    """Start traffic observation."""

    try:
        config = WatchConfig(
            project_root=Path.cwd(),
            listen_port=port or DEFAULT_WATCH_PORT,
            target_url=target,
        )
        console.print(f"Capturing traffic on 127.0.0.1:{config.listen_port}")
        if config.target_url is not None:
            console.print(f"Target scope: {_safe_cli_text(config.target_url)}", markup=False)
        console.print("Persisting redacted traffic to .entroping/state.db")
        asyncio.run(run_watch(config))
    except KeyboardInterrupt:
        console.print("Stopped traffic capture.")
    except (TrafficProxyError, ValueError) as exc:
        _print_cli_error(exc)
        raise typer.Exit(1) from exc


@app.command()
def freeze(
    name: Annotated[str, typer.Option("--name", help="Captured flow name.")],
    golden: Annotated[bool, typer.Option("--golden", help="Add golden assertions.")] = False,
    mock: Annotated[str | None, typer.Option("--mock", help="Dependency to mock.")] = None,
) -> None:
    """Convert captured traffic into Hurl tests and mocks."""

    if mock is not None:
        try:
            mock_result = run_freeze_mock(project_root=Path.cwd(), name=name, service=mock)
        except (FreezeError, ValueError) as exc:
            _print_cli_error(exc)
            raise typer.Exit(1) from exc

        noun = "mapping" if mock_result.record_count == 1 else "mappings"
        console.print(
            f"[green]Froze {mock_result.record_count} traffic {noun} into WireMock.[/green]"
        )
        for output_path in mock_result.output_paths:
            console.print(f"Wrote WireMock mapping: {_display_cli_path(output_path)}")
        return

    try:
        freeze_result = run_freeze(project_root=Path.cwd(), name=name, golden=golden)
    except (FreezeError, ValueError) as exc:
        _print_cli_error(exc)
        raise typer.Exit(1) from exc

    noun = "record" if freeze_result.record_count == 1 else "records"
    console.print(f"[green]Froze {freeze_result.record_count} traffic {noun} into Hurl.[/green]")
    console.print(f"Wrote Hurl test: {_display_cli_path(freeze_result.output_path)}")


@app.command()
def map(
    export: Annotated[
        str | None,
        typer.Option("--export", help="mermaid, dot, md, or png."),
    ] = None,
) -> None:
    """Export observed dependency maps."""

    try:
        result = run_dependency_map(project_root=Path.cwd(), export_format=export)
    except (DependencyMapError, ValueError) as exc:
        _print_cli_error(exc)
        raise typer.Exit(1) from exc

    if result.output_path is not None:
        console.print(f"Wrote dependency map: {_display_cli_path(result.output_path)}")
        return

    console.print(result.content, markup=False, end="")


@app.command()
def studio(
    env: Annotated[str | None, typer.Option("--env", help="Environment name.")] = None,
) -> None:
    """Open the local Studio interface."""

    try:
        ensure_studio_available()
        status = collect_studio_status(project_root=Path.cwd(), environment=env)
    except StudioDependencyError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1) from exc

    run_studio_app(status)


@app.command()
def run(
    env: Annotated[str | None, typer.Option("--env", help="Environment name.")] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag filter; repeat for multiple tags."),
    ] = None,
    ci: Annotated[bool, typer.Option("--ci", help="Strict CI mode.")] = False,
    parallel: Annotated[
        bool,
        typer.Option("--parallel", help="Bounded parallel execution."),
    ] = False,
    report: Annotated[
        list[str] | None,
        typer.Option("--report", help="Report format; repeat for multiple formats."),
    ] = None,
    drift_check: Annotated[
        bool,
        typer.Option("--drift-check", help="Compare against baseline."),
    ] = False,
) -> None:
    """Run Hurl suites with QAnstitution gates."""

    try:
        tag_filters = normalize_tag_filters(tag)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--tag") from exc

    try:
        report_formats = _normalize_report_formats(report)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--report") from exc

    try:
        workflow_result = execute_run_workflow(
            project_root=Path.cwd(),
            environment=env,
            tag_filters=tuple(tag_filters),
            report_formats=report_formats,
            parallel=parallel,
            drift_check=drift_check,
        )
    except NoHurlTestsMatchedError as exc:
        console.print("[yellow]No Hurl tests matched the requested filters.[/yellow]")
        raise typer.Exit(1 if ci else 0) from exc
    except (
        DriftReportError,
        FileNotFoundError,
        GateInjectionError,
        HurlBinaryNotFoundError,
        QanstitutionLoadError,
        ReportWriterError,
        ValueError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    suite = workflow_result.suite
    drift_report = workflow_result.drift_report
    console.print(f"Hurl run: {suite.passed} passed, {suite.failed} failed")
    if drift_report is not None:
        if drift_report.summary.missing_baseline:
            console.print(
                "[yellow]Drift baseline not found: .entroping/drift-baseline.json. "
                "Copy .entroping/latest-run.json after reviewing a known-good run.[/yellow]"
            )
        else:
            noun = "finding" if drift_report.summary.drifted == 1 else "findings"
            console.print(f"Drift check: {drift_report.summary.drifted} {noun}")
    console.print(f"Wrote latest run state: {_display_cli_path(workflow_result.latest_state_path)}")
    for artifact in workflow_result.artifacts:
        console.print(f"Wrote report: {_display_cli_path(artifact)}")
    for result in suite.results:
        if result.passed:
            continue
        console.print(f"[red]{result.path.name}: {result.status}[/red]")
        if result.stdout:
            console.print(result.stdout, markup=False)
        if result.stderr:
            console.print(result.stderr, markup=False)

    raise typer.Exit(workflow_result.exit_code)


def _agent_role_order() -> tuple[AgentRole, ...]:
    return ("builder", "auditor", "breaker")


def _normalize_report_formats(report: list[str] | None) -> tuple[str, ...]:
    if not report:
        return ()

    normalized: list[str] = []
    for raw_format in report:
        report_format = raw_format.strip().lower()
        if report_format not in {"drift", "html", "json", "junit"}:
            msg = (
                f"Unsupported report format {raw_format!r}; "
                "supported formats: drift, html, json, junit"
            )
            raise ValueError(msg)
        if report_format not in normalized:
            normalized.append(report_format)
    return tuple(normalized)


def _normalize_architect_audit_focus(focus: str | None) -> str:
    if focus is None:
        return "logic"
    normalized = focus.strip().lower()
    if normalized != "logic":
        msg = f"Unsupported architect audit focus {focus!r}; supported focus: logic"
        raise ValueError(msg)
    return normalized


def _normalize_architect_audit_output(output: str | None) -> str:
    if output is None:
        return "md"
    normalized = output.strip().lower()
    if normalized not in {"json", "md"}:
        msg = f"Unsupported architect audit output {output!r}; supported outputs: json, md"
        raise ValueError(msg)
    return normalized


def _configured_spec_reference(spec: str) -> str | Path:
    parsed = urlparse(spec)
    if parsed.scheme:
        return spec

    spec_path = Path(spec)
    if spec_path.is_absolute():
        return spec_path
    return Path("qanstitution.yaml").resolve().parent / spec_path


def _write_generated_hurl_file(generated: GeneratedHurlFile) -> Path:
    relative_path = Path(generated.relative_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"Generated Hurl path must stay inside the project: {generated.relative_path}"
        raise ValueError(msg)

    project_root = Path.cwd().resolve()
    candidate = project_root / relative_path
    _reject_symlink_path_components(candidate, root=project_root)

    generated_root = project_root / "tests" / "generated"
    output_path = candidate.resolve()
    if not output_path.is_relative_to(generated_root):
        msg = f"Generated Hurl path must stay under tests/generated: {generated.relative_path}"
        raise ValueError(msg)

    if output_path.is_symlink():
        msg = f"Refusing to overwrite symlinked generated Hurl file: {output_path}"
        raise ValueError(msg)
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        if "# entroping: source=openapi" not in existing:
            msg = f"Refusing to overwrite non-OpenAPI Hurl file: {_display_cli_path(output_path)}"
            raise ValueError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generated.content, encoding="utf-8")
    return output_path


def _reject_symlink_path_components(path: Path, *, root: Path) -> None:
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to write symlinked generated Hurl path component: {current}"
            raise ValueError(msg)


@report_app.command("bug")
def report_bug() -> None:
    """Generate a Markdown bug report from the latest failure."""

    latest_state = Path(".entroping") / "latest-run.json"
    if not latest_state.exists():
        console.print("[yellow]No latest run found. Run entroping run before report bug.[/yellow]")
        raise typer.Exit(1)

    report = load_run_report(latest_state)
    if report.summary.failed == 0:
        console.print("[yellow]Latest Entroping run has no failures to report.[/yellow]")
        raise typer.Exit(1)

    try:
        output_path = write_bug_report(report, Path("reports") / "bug.md")
    except ReportWriterError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"Wrote bug report: {_display_cli_path(output_path)}")


@report_app.command("traceability")
def report_traceability(
    output: Annotated[
        str,
        typer.Option("--output", help="Output format. Currently: md."),
    ] = "md",
) -> None:
    """Generate a local Markdown story traceability report."""

    normalized_output = output.strip().lower()
    if normalized_output != "md":
        console.print(f"[yellow]Unsupported traceability output: {output}[/yellow]")
        raise typer.Exit(2)

    try:
        hurl_tests = discover_hurl_tests() if Path("tests").exists() else []
        report = compile_story_traceability(hurl_tests)
    except (FileNotFoundError, HurlMetadataSyntaxError, ValueError) as exc:
        _print_cli_error(exc)
        raise typer.Exit(1) from exc

    sys.stdout.write(render_story_traceability_markdown(report))
    raise typer.Exit(0 if report.passed else 1)


def _display_cli_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _safe_cli_text(value: object) -> str:
    return redact_secret_like_values(str(value))


def _print_cli_error(exc: BaseException) -> None:
    console.print(_safe_cli_text(exc), style="red", markup=False)


def _print_architect_error(exc: BaseException) -> None:
    _print_cli_error(exc)
    if isinstance(exc, ArchitectOutputParseError):
        console.print("Architect output validation failed before write.", style="yellow")
        console.print(
            "Expected JSON object with summary, optional warnings, and edits[].",
            style="yellow",
        )
        console.print("No Architect files were written.", style="yellow")
    if isinstance(exc, HurlValidationError):
        console.print("Architect Hurl validation failed before write.", style="yellow")
        console.print("No Architect files were written.", style="yellow")


app.add_typer(config_app, name="config")
app.add_typer(architect_app, name="architect")
app.add_typer(report_app, name="report")
