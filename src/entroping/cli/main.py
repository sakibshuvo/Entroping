"""Command-line entrypoint for the Entroping scaffold."""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from entroping import __version__
from entroping.core.hurl_runner import discover_hurl

console = Console()

app = typer.Typer(
    name="entroping",
    help="AI-native quality governance for API and backend systems.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect or update non-secret configuration.")
architect_app = typer.Typer(help="Generate, refactor, and audit Hurl tests.")
report_app = typer.Typer(help="Generate human handoff artifacts.")


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

    directories = [Path("tests"), Path("envs"), Path("rules"), Path(".entroping")]
    if not minimal:
        directories.extend([Path("agents"), Path("reports")])
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    console.print("[green]Initialized Entroping project structure.[/green]")


@app.command()
def doctor() -> None:
    """Check local tool availability without making network calls."""

    hurl = discover_hurl()
    console.print(f"Python: {sys.version.split()[0]}")
    if hurl.available:
        console.print(f"Hurl: [green]found[/green] at {hurl.path}")
    else:
        console.print("Hurl: [yellow]not found[/yellow]")


@config_app.command("list")
def config_list() -> None:
    """Show resolved non-secret configuration."""

    _not_implemented("config list")


@config_app.command("set")
def config_set(
    agent: Annotated[str, typer.Option("--agent", help="Agent role to configure.")],
    model: Annotated[str, typer.Option("--model", help="Provider/model identifier.")],
) -> None:
    """Configure model routing for an agent role."""

    _ = (agent, model)
    _not_implemented("config set")


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

    _ = (new, prompt, strategy, tag)
    _not_implemented("architect build")


@architect_app.command("refactor")
def architect_refactor(
    target: Annotated[str, typer.Option("--target", help="Target Hurl glob.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Refactor instruction.")],
) -> None:
    """Safely update existing Hurl tests."""

    _ = (target, prompt)
    _not_implemented("architect refactor")


@architect_app.command("audit")
def architect_audit(
    focus: Annotated[str | None, typer.Option("--focus", help="logic, security, or perf.")] = None,
    output: Annotated[str | None, typer.Option("--output", help="json or md.")] = None,
) -> None:
    """Audit test quality and governance gaps."""

    _ = (focus, output)
    _not_implemented("architect audit")


@app.command()
def watch(
    port: Annotated[int | None, typer.Option("--port", help="Local proxy port.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target upstream URL.")] = None,
) -> None:
    """Start traffic observation."""

    _ = (port, target)
    _not_implemented("watch")


@app.command()
def freeze(
    name: Annotated[str, typer.Option("--name", help="Captured flow name.")],
    golden: Annotated[bool, typer.Option("--golden", help="Add golden assertions.")] = False,
    mock: Annotated[str | None, typer.Option("--mock", help="Dependency to mock.")] = None,
) -> None:
    """Convert captured traffic into Hurl tests and mocks."""

    _ = (name, golden, mock)
    _not_implemented("freeze")


@app.command()
def map(
    export: Annotated[
        str | None,
        typer.Option("--export", help="mermaid, dot, md, or png."),
    ] = None,
) -> None:
    """Export observed dependency maps."""

    _ = export
    _not_implemented("map")


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
    tag: Annotated[str | None, typer.Option("--tag", help="Tag filter.")] = None,
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

    _ = (env, tag, ci, parallel, report, drift_check)
    _not_implemented("run")


@report_app.command("bug")
def report_bug() -> None:
    """Generate a Markdown bug report from the latest failure."""

    _not_implemented("report bug")


app.add_typer(config_app, name="config")
app.add_typer(architect_app, name="architect")
app.add_typer(report_app, name="report")
