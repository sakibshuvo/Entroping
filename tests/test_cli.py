"""CLI smoke tests for the initial scaffold."""

from typer.testing import CliRunner

from entroping.cli.main import app


def test_root_help_includes_locked_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "architect" in result.output
    assert "doctor" in result.output
    assert "run" in result.output


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "entroping 0.1.0" in result.output

