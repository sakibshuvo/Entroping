"""Smoke tests for the issue-session launcher script."""

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_start_issue_help_documents_dry_run_mode() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "start_issue.sh"), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "worktree" in result.stdout


def test_start_issue_dry_run_generates_prompt_without_creating_worktree(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1 $2\" == \"issue view\" ]]; then\n"
        "  printf '%s\\n' "
        '\'{\"title\":\"Dry run feature\",\"url\":\"https://github.com/sakibshuvo/Entroping/issues/99\",\"state\":\"OPEN\"}\'\n'
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected gh args: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)

    result = subprocess.run(
        [
            str(REPO_ROOT / "scripts" / "start_issue.sh"),
            "99",
            "feat/dry-run",
            "--dry-run",
        ],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "Dry run feature" in result.stdout
    assert "Entroping Issue Session: #99" in result.stdout
    assert not (worktree_parent / "Entroping-issue-99").exists()
