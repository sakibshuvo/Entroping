"""Smoke tests for optional local Git hook installation."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_target_hygiene_script(repo_root: Path) -> None:
    script_path = repo_root / "scripts" / "repo_hygiene.sh"
    script_path.parent.mkdir()
    script_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script_path.chmod(0o755)


def test_install_hooks_help_documents_dry_run_and_force() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install_hooks.sh"), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--force" in result.stdout
    assert "pre-commit" in result.stdout


def test_install_hooks_dry_run_does_not_write_hook(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install_hooks.sh"), "--dry-run"],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Would install pre-commit hook" in result.stdout
    assert not hook_path.exists()


def test_install_hooks_writes_executable_pre_commit_hook(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    write_target_hygiene_script(tmp_path)
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install_hooks.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert hook_path.is_file()
    assert os.access(hook_path, os.X_OK)
    assert "repo_hygiene.sh" in hook_path.read_text(encoding="utf-8")


def test_install_hooks_refuses_repo_without_hygiene_script(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install_hooks.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "repo_hygiene.sh is missing or not executable" in result.stderr


def test_install_hooks_refuses_to_overwrite_existing_hook_without_force(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
    hook_path.write_text("# existing hook\n", encoding="utf-8")

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "install_hooks.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert hook_path.read_text(encoding="utf-8") == "# existing hook\n"
