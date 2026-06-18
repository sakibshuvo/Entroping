"""CLI tests for generated-test quality score reports."""

import json
from pathlib import Path
from typing import NoReturn

import pytest
from typer.testing import CliRunner

import entroping.cli.commands.report as report_commands
from entroping.cli.main import app
from entroping.core.test_quality_report import (
    TestQualityOutput as QualityOutput,
)
from entroping.core.test_quality_report import (
    TestQualityReportError as QualityReportError,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def _write_generated_test(root: Path) -> None:
    _write_text(
        root / "tests" / "generated" / "profile_auth.hurl",
        """
        # entroping: source=openapi
        # entroping: tags=generated,security,negative
        # entroping: operation_id=getProfile
        # entroping: negative_category=invalid-auth

        GET {{base_url}}/profile
        HTTP 401
        [Asserts]
        jsonpath "$.error" exists
        jsonpath "$.error" isString
        """,
    )


def test_report_test_quality_writes_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_generated_test(tmp_path)

    result = CliRunner().invoke(app, ["report", "test-quality", "--output", "json"])

    assert result.exit_code == 0
    assert "Wrote generated-test quality report: reports/test-quality.json" in result.output
    payload = json.loads(Path("reports/test-quality.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-quality-report.v1"
    assert payload["summary"]["generated_tests"] == 1


def test_report_test_quality_writes_markdown_report_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_generated_test(tmp_path)

    result = CliRunner().invoke(app, ["report", "test-quality"])

    assert result.exit_code == 0
    assert "Wrote generated-test quality report: reports/test-quality.md" in result.output
    markdown = Path("reports/test-quality.md").read_text(encoding="utf-8")
    assert "# Entroping Generated-Test Quality Score" in markdown
    assert "profile_auth.hurl" in markdown


def test_report_test_quality_rejects_unsupported_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_generated_test(tmp_path)

    result = CliRunner().invoke(app, ["report", "test-quality", "--output", "html"])

    assert result.exit_code == 2
    assert "Unsupported test-quality output" in result.output


def test_report_test_quality_prints_workflow_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail_report(*, project_root: Path, output: QualityOutput) -> NoReturn:
        _ = project_root, output
        raise QualityReportError("generated tests are unreadable")

    monkeypatch.setattr(report_commands, "run_test_quality_report", fail_report)

    result = CliRunner().invoke(app, ["report", "test-quality"])

    assert result.exit_code == 1
    assert "generated tests are unreadable" in result.output
