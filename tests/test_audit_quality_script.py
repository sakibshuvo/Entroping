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
    assert "pytest-cov" in result.stdout
    assert "radon" in result.stdout
    assert "vulture" in result.stdout
    assert "--dry-run" in result.stdout


def test_audit_quality_dry_run_shows_repeatable_steps() -> None:
    result = run_audit_quality("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would run coverage gate" in result.stdout
    assert "Would run Radon complexity gate" in result.stdout
    assert "Would run Vulture dead-code discovery" in result.stdout
    assert "coverage fail-under: 85" in result.stdout


def test_audit_quality_rejects_unknown_options() -> None:
    result = run_audit_quality("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr
