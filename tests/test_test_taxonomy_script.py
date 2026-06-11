"""Tests for deterministic test-suite taxonomy reporting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "test_taxonomy.py"


def run_test_taxonomy(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_test_taxonomy_writes_reviewable_json_artifact(tmp_path: Path) -> None:
    output = tmp_path / "test-taxonomy.json"

    result = run_test_taxonomy("--output", str(output), "--strict")

    assert result.returncode == 0, result.stderr
    assert "Wrote test taxonomy: " in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.test-taxonomy.v1"
    assert payload["generated_by"] == "scripts/test_taxonomy.py"
    assert payload["test_file_count"] > 100
    assert payload["static_test_count"] > 1000
    assert set(payload["required_categories"]) == {
        "behavior",
        "docs-compliance",
        "script-integrity",
        "integration",
        "smoke",
        "regression",
        "security",
    }

    categories = payload["categories"]
    for category in payload["required_categories"]:
        assert categories[category]["file_count"] > 0
        assert categories[category]["static_test_count"] > 0

    assert any(
        entry["path"] == "tests/test_cli_real_hurl_e2e.py"
        for entry in categories["integration"]["files"]
    )
    assert any(
        entry["path"] == "tests/test_release_docs.py"
        for entry in categories["docs-compliance"]["files"]
    )
    assert any(
        entry["path"] == "tests/test_audit_quality_script.py"
        for entry in categories["script-integrity"]["files"]
    )


def test_test_taxonomy_dry_run_prints_summary_without_writing(tmp_path: Path) -> None:
    output = tmp_path / "test-taxonomy.json"

    result = run_test_taxonomy("--output", str(output), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would write test taxonomy: " in result.stdout
    assert "behavior:" in result.stdout
    assert not output.exists()
