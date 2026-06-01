"""Command-line entrypoint for Entroping."""

from typing import Annotated

import typer

from entroping import __version__
from entroping.cli.commands import (
    MINIMAL_QANSTITUTION,
    architect_app,
    config_app,
    register_execution_commands,
    register_project_commands,
    report_app,
)
from entroping.cli.shared import console
from entroping.cli.shared import display_cli_path as _display_cli_path

app = typer.Typer(
    name="entroping",
    help="AI-native quality governance for API and backend systems.",
    no_args_is_help=True,
)


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


register_project_commands(app)
register_execution_commands(app)
app.add_typer(config_app, name="config")
app.add_typer(architect_app, name="architect")
app.add_typer(report_app, name="report")

__all__ = ["MINIMAL_QANSTITUTION", "_display_cli_path", "app", "main"]
