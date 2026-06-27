"""Architecture guard for the Typer command adapter split."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_main_delegates_to_focused_command_modules() -> None:
    main_path = REPO_ROOT / "src" / "entroping" / "cli" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))

    imported_modules = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }
    imported_from = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "entroping.cli.commands" in imported_from
    assert {"architect_app", "config_app", "register_execution_commands", "report_app"} <= (
        imported_modules
    )
    assert not any(
        module.startswith(("entroping.brain", "entroping.bridge", "entroping.core"))
        for module in imported_from
    )


def test_focused_cli_command_modules_exist() -> None:
    commands_root = REPO_ROOT / "src" / "entroping" / "cli" / "commands"

    assert (commands_root / "__init__.py").exists()
    assert {path.name for path in commands_root.glob("*.py")} >= {
        "__init__.py",
        "architect.py",
        "config.py",
        "execution.py",
        "project.py",
    }


def test_report_command_package_exists() -> None:
    report_root = REPO_ROOT / "src" / "entroping" / "cli" / "commands" / "report"

    assert (report_root / "__init__.py").exists()
    assert {path.name for path in report_root.glob("*.py")} >= {
        "__init__.py",
        "_app.py",
        "_panels.py",
        "_helpers.py",
        "_launch.py",
        "_stable.py",
        "_maintainer.py",
        "_experimental.py",
    }


def test_report_package_re_exports_app() -> None:
    import typer

    from entroping.cli.commands import report_app

    assert isinstance(report_app, typer.Typer)
