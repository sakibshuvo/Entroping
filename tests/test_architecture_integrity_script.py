"""Smoke tests for the architecture-integrity gate."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "architecture_integrity.sh"


def test_architecture_integrity_help_documents_boundary_checks() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "AST import-boundary checks" in result.stdout
    assert "tests/test_architecture_boundaries.py" in result.stdout
    assert "provider-free" in result.stdout


def test_architecture_integrity_passes_current_repo() -> None:
    result = subprocess.run(
        [str(SCRIPT)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Architecture integrity OK" in result.stdout


def test_feature_gate_runs_architecture_integrity_before_python_checks() -> None:
    feature_gate = (REPO_ROOT / "scripts" / "feature_gate.sh").read_text(
        encoding="utf-8"
    )

    assert "scripts/architecture_integrity.sh" in feature_gate
    assert feature_gate.index("scripts/architecture_integrity.sh") < feature_gate.index(
        "scripts/check.sh"
    )
