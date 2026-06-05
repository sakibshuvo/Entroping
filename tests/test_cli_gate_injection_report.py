"""CLI tests for gate-injection explanation reports."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entroping.cli.main import app


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


def test_report_gate_injection_writes_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "gate-injection", "--target", "tests/health.hurl", "--output", "json"],
    )

    assert result.exit_code == 0
    assert "Wrote gate injection report: reports/gate-injection.json" in result.output
    payload = json.loads(Path("reports/gate-injection.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.gate-injection-report.v1"
    assert payload["targets"][0]["gates"][0]["id"] == "global_latency"


def test_report_gate_injection_writes_markdown_report_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["report", "gate-injection", "--target", "tests/health.hurl"])

    assert result.exit_code == 0
    assert "Wrote gate injection report: reports/gate-injection.md" in result.output
    markdown = Path("reports/gate-injection.md").read_text(encoding="utf-8")
    assert "# Entroping Gate Injection Explanation" in markdown
    assert "global_latency" in markdown


def test_report_gate_injection_rejects_symlinked_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)
    Path("tests/link.hurl").symlink_to("health.hurl")

    result = CliRunner().invoke(app, ["report", "gate-injection", "--target", "tests/link.hurl"])

    assert result.exit_code == 1
    assert "Target must not use symlinks" in result.output


def test_report_gate_injection_rejects_unsupported_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_project(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "gate-injection", "--target", "tests/health.hurl", "--output", "html"],
    )

    assert result.exit_code == 2
    assert "Unsupported gate-injection output" in result.output
