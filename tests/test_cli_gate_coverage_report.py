"""CLI tests for policy gate coverage reports."""

import json
from collections.abc import Callable
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


def _write_partially_covered_project(root: Path) -> None:
    _write_text(
        root / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
  - id: admin_guard
    condition: path startswith '/admin'
    gate: status == 403
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


def _write_fractionally_covered_project(root: Path) -> None:
    _write_text(
        root / "qanstitution.yaml",
        """
project: checkout-api
gates:
  - id: global_latency
    condition: "true"
    gate: duration < 2000
    enforcement: block
  - id: admin_guard
    condition: path startswith '/admin'
    gate: status == 403
    enforcement: block
  - id: billing_guard
    condition: path startswith '/billing'
    gate: status == 403
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


def _write_empty_policy_project(root: Path) -> None:
    _write_text(
        root / "qanstitution.yaml",
        """
project: checkout-api
gates: []
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


def test_report_gate_coverage_passes_when_matched_gate_percent_meets_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_partially_covered_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--fail-under", "50"])

    assert result.exit_code == 0
    markdown = Path("reports/gate-coverage.md").read_text(encoding="utf-8")
    assert "Matched gates: 1" in markdown
    assert "Unmatched gates: 1" in markdown


def test_report_gate_coverage_fails_after_writing_when_matched_gate_percent_is_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_partially_covered_project(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "gate-coverage", "--output", "json", "--fail-under", "51"],
    )

    assert result.exit_code == 1
    assert "below required threshold 51" in result.output
    payload = json.loads(Path("reports/gate-coverage.json").read_text(encoding="utf-8"))
    assert payload["summary"]["matched_gates"] == 1
    assert payload["summary"]["total_gates"] == 2


def test_report_gate_coverage_formats_fractional_threshold_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_fractionally_covered_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--fail-under", "34"])

    assert result.exit_code == 1
    assert "Policy gate coverage 33.3% is below required threshold 34." in result.output
    markdown = Path("reports/gate-coverage.md").read_text(encoding="utf-8")
    assert "Matched gates: 1" in markdown
    assert "Unmatched gates: 2" in markdown


def test_report_gate_coverage_fails_zero_gate_project_below_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_empty_policy_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--fail-under", "1"])

    assert result.exit_code == 1
    assert "Policy gate coverage 0% is below required threshold 1." in result.output
    payload = Path("reports/gate-coverage.md").read_text(encoding="utf-8")
    assert "Effective gates: 0" in payload


@pytest.mark.parametrize(
    ("project_writer", "threshold"),
    [
        (_write_empty_policy_project, "0"),
        (_write_project, "100"),
    ],
)
def test_report_gate_coverage_passes_on_exact_fail_under_boundary(
    project_writer: Callable[[Path], None],
    threshold: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project_writer(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--fail-under", threshold])

    assert result.exit_code == 0
    assert "Wrote gate coverage report: reports/gate-coverage.md" in result.output


@pytest.mark.parametrize("threshold", ["-1", "101"])
def test_report_gate_coverage_rejects_invalid_fail_under_before_writing(
    threshold: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-coverage", "--fail-under", threshold])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert not Path("reports/gate-coverage.md").exists()


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
