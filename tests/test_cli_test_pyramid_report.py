"""CLI tests for local test-pyramid evidence reports."""

import json
from pathlib import Path
from typing import NoReturn

import pytest
from typer.testing import CliRunner

import entroping.cli.commands.report as report_commands
from entroping.cli.main import app
from entroping.core.test_pyramid_report import TestPyramidReportError


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_report_test_pyramid_writes_markdown_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "test-pyramid"])

    assert result.exit_code == 0
    assert "Wrote test pyramid report: reports/test-pyramid.md" in result.output
    markdown = Path("reports/test-pyramid.md").read_text(encoding="utf-8")
    assert "# Entroping Test Pyramid Evidence" in markdown
    assert "Missing Runtime Governance Proof" in markdown


def test_report_test_pyramid_writes_json_without_raw_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(
        Path("reports") / "run-latest.json",
        {
            "schema_version": "entroping.run-report.v1",
            "summary": {"total": 1, "passed": 1, "failed": 0},
            "tests": [{"stdout": "secret-test-pyramid-value"}],
        },
    )

    result = CliRunner().invoke(app, ["report", "test-pyramid", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote test pyramid report: reports/test-pyramid.json" in result.output
    payload = json.loads(Path("reports/test-pyramid.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-pyramid-report.v1"
    assert "secret-test-pyramid-value" not in json.dumps(payload)


def test_report_test_pyramid_rejects_unsupported_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "test-pyramid", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported test-pyramid output: html" in result.output
    assert not Path("reports/test-pyramid.html").exists()


def test_report_test_pyramid_prints_report_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_report(*args: object, **kwargs: object) -> NoReturn:
        _ = (args, kwargs)
        raise TestPyramidReportError("failed local evidence read")

    monkeypatch.setattr(report_commands, "run_test_pyramid_report", fail_report)

    result = CliRunner().invoke(app, ["report", "test-pyramid"])

    assert result.exit_code == 1
    assert "failed local evidence read" in result.output
