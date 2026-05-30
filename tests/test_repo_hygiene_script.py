"""Smoke tests for deterministic repo-hygiene tooling."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_hygiene_help_documents_forbidden_tracked_paths() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh"), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert ".DS_Store" in result.stdout
    assert ".obsidian/graph.json" in result.stdout
    assert ".entroping/" in result.stdout


def test_repo_hygiene_rejects_forbidden_tracked_paths(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True)
    forbidden = tmp_path / ".DS_Store"
    forbidden.write_text("machine state\n", encoding="utf-8")
    subprocess.run(["git", "add", ".DS_Store"], check=True, cwd=tmp_path)

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Forbidden tracked local/generated files" in result.stderr
    assert ".DS_Store" in result.stderr


def test_repo_hygiene_passes_current_repo() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Repo hygiene OK" in result.stdout
