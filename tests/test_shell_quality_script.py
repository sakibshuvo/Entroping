"""Tests for shell script syntax and optional ShellCheck gate."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "shell_quality.sh"


def run_shell_quality(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_shell_quality_help_documents_bash_and_shellcheck() -> None:
    result = run_shell_quality("--help")

    assert result.returncode == 0
    assert "bash -n" in result.stdout
    assert "ShellCheck" in result.stdout
    assert "--dry-run" in result.stdout


def test_shell_quality_dry_run_lists_deterministic_steps() -> None:
    result = run_shell_quality("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would run bash -n over tracked shell scripts" in result.stdout
    assert "Would run ShellCheck when shellcheck is available" in result.stdout


def test_shell_quality_passes_current_repo_or_skips_optional_shellcheck() -> None:
    result = run_shell_quality()

    assert result.returncode == 0, result.stderr
    assert "bash -n passed" in result.stdout
    assert (
        "ShellCheck passed" in result.stdout
        or "ShellCheck not found; skipped optional ShellCheck lint" in result.stdout
    )


def test_feature_gate_runs_shell_quality_before_python_checks() -> None:
    feature_gate = (REPO_ROOT / "scripts" / "feature_gate.sh").read_text(encoding="utf-8")

    assert "scripts/shell_quality.sh" in feature_gate
    assert feature_gate.index("scripts/shell_quality.sh") < feature_gate.index("scripts/check.sh")


def test_local_gate_scripts_disable_python_bytecode_noise() -> None:
    for script_name in ("check.sh", "feature_gate.sh", "regression.sh"):
        script = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")

        assert "export PYTHONDONTWRITEBYTECODE=1" in script
