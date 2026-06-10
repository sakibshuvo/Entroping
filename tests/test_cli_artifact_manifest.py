"""CLI tests for report artifact manifests."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entroping.cli.main import app


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")


def test_report_artifact_manifest_writes_default_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        '{"schema_version":"entroping.run-report.v1"}\n',
    )

    result = CliRunner().invoke(app, ["report", "artifact-manifest"])

    assert result.exit_code == 0
    assert "Wrote artifact manifest: reports/artifact-manifest.json" in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.report-artifact-manifest.v1"
    assert payload["summary"]["total_present"] == 1
    assert payload["summary"]["total_missing"] == 7


def test_report_artifact_manifest_rejects_unsafe_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--output", "../artifact-manifest.json"],
    )

    assert result.exit_code == 1
    assert "output path must stay inside" in result.output
