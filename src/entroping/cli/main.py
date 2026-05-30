"""Command-line entrypoint for the Entroping scaffold."""

import asyncio
import json
import sys
import tempfile
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
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.config_writer import (
    ConfigUpdateError,
    update_agent_model_with_persona_template,
)
from entroping.core.dependency_mapper import DependencyMapError, run_dependency_map
from entroping.core.env_loader import load_environment_variables
from entroping.core.freeze import FreezeError, run_freeze, run_freeze_mock
from entroping.core.gate_injector import GateInjectionError, write_injected_execution_copy
from entroping.core.hurl_discovery import discover_hurl_tests, normalize_tag_filters
from entroping.core.hurl_runner import (
    HurlBinaryNotFoundError,
    HurlRunOptions,
    discover_hurl,
    run_hurl_files,
)
from entroping.core.openapi_loader import OpenApiLoadError, load_openapi_document
from entroping.core.report_writer import (
    ReportWriterError,
    build_run_report,
    load_run_report,
    write_bug_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.traffic_proxy import (
    DEFAULT_WATCH_PORT,
    TrafficProxyError,
    WatchConfig,
    run_watch,
)
from entroping.models.qanstitution import AgentRole

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


def _not_implemented(command: str) -> None:
    console.print(f"[yellow]{command} is part of the planned v4.1 command surface.[/yellow]")
    console.print("The implementation scaffold is in place; runtime behavior is not built yet.")
    raise typer.Exit(2)


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
        _not_implemented("architect build")

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
        _print_cli_error(exc)
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
        _print_cli_error(exc)
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

    _ = env
    _not_implemented("studio")


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

    unsupported_options = _unsupported_run_options(drift_check=drift_check)
    if unsupported_options:
        joined = ", ".join(unsupported_options)
        console.print(f"[yellow]{joined} not implemented yet for entroping run.[/yellow]")
        raise typer.Exit(2)

    try:
        law = load_qanstitution(Path("qanstitution.yaml"))
        hurl_tests = discover_hurl_tests(tag_filters=tuple(tag_filters))
        env_variables = load_environment_variables(env) if env is not None else {}
    except (QanstitutionLoadError, FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    if not hurl_tests:
        console.print("[yellow]No Hurl tests matched the requested filters.[/yellow]")
        raise typer.Exit(1 if ci else 0)

    hurl_workers = law.settings.parallel_workers if parallel else 1
    state_dir = Path(".entroping")
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="run-", dir=state_dir) as execution_root:
            execution_copies = [
                write_injected_execution_copy(
                    hurl_test,
                    law.gates,
                    execution_root=Path(execution_root),
                )
                for hurl_test in hurl_tests
            ]
            suite = run_hurl_files(
                [execution.execution_path for execution in execution_copies],
                HurlRunOptions(timeout_ms=law.settings.timeout, variables=env_variables),
                max_workers=hurl_workers,
            )
            run_report = build_run_report(
                project=law.project,
                environment=env or "default",
                execution_copies=execution_copies,
                suite=suite,
                project_root=Path.cwd(),
            )
    except (GateInjectionError, HurlBinaryNotFoundError, ReportWriterError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    try:
        latest_state = write_json_report(run_report, state_dir / "latest-run.json")
        artifacts: list[Path] = []
        if "json" in report_formats:
            artifacts.append(write_json_report(run_report, Path("reports") / "run-latest.json"))
        if "junit" in report_formats:
            artifacts.append(write_junit_report(run_report, Path("reports") / "junit.xml"))
        if "html" in report_formats:
            artifacts.append(write_html_report(run_report, Path("reports") / "run-latest.html"))
    except ReportWriterError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"Hurl run: {suite.passed} passed, {suite.failed} failed")
    console.print(f"Wrote latest run state: {_display_cli_path(latest_state)}")
    for artifact in artifacts:
        console.print(f"Wrote report: {_display_cli_path(artifact)}")
    for result in suite.results:
        if result.passed:
            continue
        console.print(f"[red]{result.path.name}: {result.status}[/red]")
        if result.stdout:
            console.print(result.stdout, markup=False)
        if result.stderr:
            console.print(result.stderr, markup=False)

    raise typer.Exit(suite.exit_code)


def _unsupported_run_options(
    *,
    drift_check: bool,
) -> tuple[str, ...]:
    unsupported: list[str] = []
    if drift_check:
        unsupported.append("--drift-check")
    return tuple(unsupported)


def _agent_role_order() -> tuple[AgentRole, ...]:
    return ("builder", "auditor", "breaker")


def _normalize_report_formats(report: list[str] | None) -> tuple[str, ...]:
    if not report:
        return ()

    normalized: list[str] = []
    for raw_format in report:
        report_format = raw_format.strip().lower()
        if report_format not in {"html", "json", "junit"}:
            msg = f"Unsupported report format {raw_format!r}; supported formats: html, json, junit"
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

    generated_root = (Path.cwd() / "tests" / "generated").resolve()
    output_path = (Path.cwd() / relative_path).resolve()
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


def _display_cli_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _safe_cli_text(value: object) -> str:
    return redact_secret_like_values(str(value))


def _print_cli_error(exc: BaseException) -> None:
    console.print(_safe_cli_text(exc), style="red", markup=False)


app.add_typer(config_app, name="config")
app.add_typer(architect_app, name="architect")
app.add_typer(report_app, name="report")
