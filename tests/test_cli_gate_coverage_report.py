"""CLI tests for policy gate coverage reports."""

import json
from pathlib import Path
from typing import NoReturn

import pytest
from typer.testing import CliRunner

import entroping.cli.commands.report as report_commands
from entroping.cli.main import app
from entroping.core.gate_coverage_report import GateCoverageOutput, GateCoverageReportError


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_project(root: Path) -> None:
    _write_text(
        root / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
""",
    )
    _write_text(
        root / "tests" / "health.hurl",
        """
# entroping: tags=smoke

GET http://api.example.test/health
HTTP 200
""",
    )


def test_report_gate_coverage_writes_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote gate coverage report: reports/gate-coverage.json" in result.output
    payload = json.loads(Path("reports/gate-coverage.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.gate-coverage-report.v1"
    assert payload["summary"]["matched_gates"] == 1
    assert payload["gates"][0]["id"] == "global_latency"


def test_report_gate_coverage_writes_markdown_report_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage"])

    assert result.exit_code == 0
    assert "Wrote gate coverage report: reports/gate-coverage.md" in result.output
    markdown = Path("reports/gate-coverage.md").read_text(encoding="utf-8")
    assert "# Entroping Policy Gate Coverage Matrix" in markdown
    assert "global_latency" in markdown


def test_report_gate_coverage_rejects_unsupported_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported gate-coverage output" in result.output


def test_report_gate_coverage_prints_workflow_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_report(*, project_root: Path, output: GateCoverageOutput) -> NoReturn:
        raise GateCoverageReportError("policy is invalid")

    monkeypatch.setattr(report_commands, "run_gate_coverage_report", fail_report)

    result = CliRunner().invoke(app, ["report", "gate-coverage"])

    assert result.exit_code == 1
    assert "policy is invalid" in result.output
