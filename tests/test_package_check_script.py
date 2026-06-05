"""Smoke tests for package artifact verification."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "package_check.sh"


def run_package_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_package_check_help_documents_build_and_metadata_verification() -> None:
    result = run_package_check("--help")

    assert result.returncode == 0
    assert "uv build" in result.stdout
    assert "License-Expression" in result.stdout
    assert "py.typed" in result.stdout
    assert "--dry-run" in result.stdout


def test_package_check_dry_run_shows_deterministic_steps() -> None:
    result = run_package_check("--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would remove dist/" in result.stdout
    assert "Would run: uv build" in result.stdout
    assert "Would verify wheel metadata, py.typed marker, and sdist contents" in result.stdout


def test_package_check_builds_and_verifies_artifacts() -> None:
    result = run_package_check()

    assert result.returncode == 0, result.stderr
    assert "Package artifacts OK" in result.stdout
    assert "License-Expression: Apache-2.0" in result.stdout
    assert "Typing marker: entroping/py.typed" in result.stdout
    assert (
        "GitHub Actions starter template: entroping/templates/github-actions/entroping-ci.yml"
        in result.stdout
    )
    assert (REPO_ROOT / "dist" / "entroping-0.1.1-py3-none-any.whl").is_file()
    assert (REPO_ROOT / "dist" / "entroping-0.1.1.tar.gz").is_file()
