"""Focused Typer command adapters."""

from entroping.cli.commands.architect import app as architect_app
from entroping.cli.commands.config import app as config_app
from entroping.cli.commands.execution import register_execution_commands
from entroping.cli.commands.project import MINIMAL_QANSTITUTION, register_project_commands
from entroping.cli.commands.report import app as report_app

__all__ = [
    "MINIMAL_QANSTITUTION",
    "architect_app",
    "config_app",
    "register_execution_commands",
    "register_project_commands",
    "report_app",
]
