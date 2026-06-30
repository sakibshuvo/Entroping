"""Smoke tests for the validation quality-audit script."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit_quality.sh"


def run_audit_quality(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_audit_quality_help_documents_quality_gates() -> None:
    result = run_audit_quality("--help")

    assert result.returncode == 0
    assert "test taxonomy" in result.stdout
    assert "long-file hotspot" in result.stdout
    assert "script-focused coverage and typing visibility" in result.stdout
    assert "quality trend summary" in result.stdout
    assert "pytest-cov" in result.stdout
    assert "radon" in result.stdout
    assert "ENTROPING_MAX_COMPLEXITY_RANK  Highest allowed Radon CC rank. Default: D." in (
        result.stdout
    )
    assert "vulture" in result.stdout
    assert "bounded performance smoke evidence under reports/" in result.stdout
    assert "--dry-run" in result.stdout


def test_audit_quality_dry_run_shows_repeatable_steps() -> None:
    result = run_audit_quality("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would write test taxonomy report" in result.stdout
    assert "Would run long-file hotspot report" in result.stdout
    assert "Would run coverage gate" in result.stdout
    assert "Would run script quality coverage and typing visibility report" in result.stdout
    assert "Would run Radon complexity gate" in result.stdout
    assert "Would run Vulture dead-code discovery" in result.stdout
    assert "Would write quality trend summary" in result.stdout
    assert "Would run bounded performance smoke" in result.stdout
    assert "coverage fail-under: 100" in result.stdout
    assert "max complexity rank: D" in result.stdout


def test_audit_quality_rejects_unknown_options() -> None:
    result = run_audit_quality("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr


def test_audit_quality_mi_gate_checks_all_list_entries() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "for candidate in entry" in script
    assert "entry[0]" not in script
