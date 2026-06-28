"""CLI tests for external test evidence reports."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entroping.cli.commands import report as report_cli
from entroping.cli.main import app
from entroping.core.evidence.external_test_evidence import ExternalTestEvidenceError


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_report_external_test_evidence_writes_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "external-tests" / "unit-junit.xml",
        '<testsuite tests="2" failures="0" errors="0" skipped="0" />',
    )

    result = CliRunner().invoke(app, ["report", "external-test-evidence"])

    assert result.exit_code == 0
    assert "Wrote external test evidence: reports/external-test-evidence.md" in (
        result.output
    )
    markdown = Path("reports/external-test-evidence.md").read_text(encoding="utf-8")
    assert "# Entroping External Test Evidence" in markdown
    assert "| unit | covered | unit_junit | 2 |" in markdown


def test_report_external_test_evidence_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "external-test-evidence", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote external test evidence: reports/external-test-evidence.json" in (
        result.output
    )
    payload = json.loads(
        Path("reports/external-test-evidence.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "entroping.external-test-evidence.v1"
    assert payload["summary"]["status"] == "insufficient"


@pytest.mark.parametrize(
    ("filename", "source_id", "raw_text", "expected_key", "expected_value"),
    [
        (
            "unit-junit.xml",
            "unit_junit",
            '<testsuite tests="2" failures="0" errors="0" skipped="0" />',
            "tests",
            2,
        ),
        (
            "integration-junit.xml",
            "integration_junit",
            '<testsuite tests="3" failures="1" errors="0" skipped="0" />',
            "failures",
            1,
        ),
        (
            "component-junit.xml",
            "component_junit",
            "<testsuite><testcase /><testcase><skipped /></testcase></testsuite>",
            "skipped",
            1,
        ),
        (
            "contract-junit.xml",
            "contract_junit",
            '<testsuite tests="4" failures="0" errors="0" skipped="0" />',
            "tests",
            4,
        ),
        (
            "e2e-junit.xml",
            "e2e_junit",
            '<testsuite tests="1" failures="0" errors="0" skipped="0" />',
            "tests",
            1,
        ),
        (
            "coverage.xml",
            "coverage_xml",
            '<coverage line-rate="0.75" branch-rate="0.5" />',
            "line_coverage_percent",
            75.0,
        ),
        (
            "lcov.info",
            "lcov_info",
            "LF:4\nLH:3\nBRF:2\nBRH:1\n",
            "branch_coverage_percent",
            50.0,
        ),
        (
            "sarif.json",
            "sarif_json",
            '{"runs": [{"results": [{"level": "error"}, {"level": "none"}]}]}',
            "sarif_results_total",
            2,
        ),
    ],
)
def test_report_external_test_evidence_cli_reads_each_fixed_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    source_id: str,
    raw_text: str,
    expected_key: str,
    expected_value: int | float,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(Path("reports") / "external-tests" / filename, raw_text)

    result = CliRunner().invoke(
        app,
        ["report", "external-test-evidence", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(
        Path("reports/external-test-evidence.json").read_text(encoding="utf-8")
    )
    source = next(source for source in payload["sources"] if source["id"] == source_id)
    assert source["state"] == "present"
    assert source[expected_key] == expected_value


def test_report_external_test_evidence_rejects_unsupported_output() -> None:
    result = CliRunner().invoke(
        app,
        ["report", "external-test-evidence", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported external-test-evidence output" in result.output
    assert not Path("reports/external-test-evidence.html").exists()


def test_report_external_test_evidence_wraps_core_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external_test_evidence(*args: object, **kwargs: object) -> object:
        raise ExternalTestEvidenceError("external evidence path is unsafe")

    monkeypatch.setattr(
        report_cli,
        "run_external_test_evidence_report",
        fail_external_test_evidence,
    )

    result = CliRunner().invoke(app, ["report", "external-test-evidence"])

    assert result.exit_code == 1
    assert "external evidence path is unsafe" in result.output
