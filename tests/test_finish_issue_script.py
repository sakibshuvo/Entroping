"""Smoke tests for the issue-session finish script."""

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "finish_issue.sh"


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def create_repo_with_worktree(
    tmp_path: Path,
    *,
    issue_number: int = 99,
    branch_name: str = "feat/dry-run",
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "init")

    worktree = tmp_path / f"Entroping-issue-{issue_number}"
    run_git(repo, "worktree", "add", str(worktree), "-b", branch_name)
    return repo, worktree


def write_fake_gh(
    tmp_path: Path,
    *,
    issue_number: int = 99,
    branch_name: str = "feat/dry-run",
    issue_state: str = "CLOSED",
    pr_state: str = "MERGED",
    checks_json: str | None = None,
) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_gh = fake_bin / "gh"
    checks = checks_json or (
        '[{"__typename":"CheckRun","name":"checks","status":"COMPLETED",'
        '"conclusion":"SUCCESS"}]'
    )
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1 $2\" == \"issue view\" ]]; then\n"
        f"  [[ \"$3\" == \"{issue_number}\" ]]\n"
        "  cat <<'JSON'\n"
        "{"
        f"\"title\":\"Dry run feature\",\"url\":\"https://github.com/sakibshuvo/Entroping/issues/{issue_number}\","
        f"\"state\":\"{issue_state}\","
        "\"closedByPullRequestsReferences\":[{\"number\":123,\"url\":\"https://github.com/sakibshuvo/Entroping/pull/123\"}]"
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"pr view\" ]]; then\n"
        "  [[ \"$3\" == \"123\" ]]\n"
        "  cat <<'JSON'\n"
        "{"
        "\"number\":123,\"url\":\"https://github.com/sakibshuvo/Entroping/pull/123\","
        f"\"state\":\"{pr_state}\",\"headRefName\":\"{branch_name}\",\"mergedAt\":\"2026-05-30T00:00:00Z\","
        f"\"statusCheckRollup\":{checks}"
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"issue edit\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project view\" ]]; then\n"
        "  printf '%s\\n' '{\"id\":\"project-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project field-list\" ]]; then\n"
        "  printf '%s\\n' "
        "'{\"fields\":[{\"name\":\"Status\",\"id\":\"field-id\","
        "\"options\":[{\"name\":\"Done\",\"id\":\"done-id\"}]}]}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project item-list\" ]]; then\n"
        "  printf '%s\\n' "
        f"'{{\"items\":[{{\"id\":\"item-id\",\"content\":{{\"number\":{issue_number}}}}}]}}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project item-edit\" ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected gh args: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def write_fake_gh_with_missing_project_item(
    tmp_path: Path,
    *,
    issue_number: int = 99,
    branch_name: str = "feat/dry-run",
) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "state_dir=\"${FAKE_GH_STATE:?}\"\n"
        "calls=\"$state_dir/calls.log\"\n"
        "if [[ \"$1 $2\" == \"issue view\" ]]; then\n"
        f"  [[ \"$3\" == \"{issue_number}\" ]]\n"
        "  cat <<'JSON'\n"
        "{"
        f"\"title\":\"Finished feature\",\"url\":\"https://github.com/sakibshuvo/Entroping/issues/{issue_number}\","
        "\"state\":\"CLOSED\","
        "\"closedByPullRequestsReferences\":[{\"number\":123,\"url\":\"https://github.com/sakibshuvo/Entroping/pull/123\"}]"
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"pr view\" ]]; then\n"
        "  [[ \"$3\" == \"123\" ]]\n"
        "  cat <<'JSON'\n"
        "{"
        "\"number\":123,\"url\":\"https://github.com/sakibshuvo/Entroping/pull/123\","
        f"\"state\":\"MERGED\",\"headRefName\":\"{branch_name}\",\"mergedAt\":\"2026-05-30T00:00:00Z\","
        "\"statusCheckRollup\":[{\"__typename\":\"CheckRun\",\"name\":\"checks\",\"status\":\"COMPLETED\",\"conclusion\":\"SUCCESS\"}]"
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"issue edit\" ]]; then\n"
        "  printf 'issue edit %s\\n' \"$*\" >> \"$calls\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project view\" ]]; then\n"
        "  printf '%s\\n' '{\"id\":\"project-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project field-list\" ]]; then\n"
        "  printf '%s\\n' "
        "'{\"fields\":[{\"name\":\"Status\",\"id\":\"field-id\","
        "\"options\":[{\"name\":\"Done\",\"id\":\"done-id\"}]}]}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project item-list\" ]]; then\n"
        "  if [[ -f \"$state_dir/project-added\" ]]; then\n"
        "    count_file=\"$state_dir/item-list-after-add-count\"\n"
        "    count=0\n"
        "    [[ -f \"$count_file\" ]] && count=$(cat \"$count_file\")\n"
        "    count=$((count + 1))\n"
        "    printf '%s\\n' \"$count\" > \"$count_file\"\n"
        "    if ((count >= 2)); then\n"
        "      printf '%s\\n' "
        f"'{{\"items\":[{{\"id\":\"item-id\",\"content\":{{\"number\":{issue_number}}}}}]}}'\n"
        "    else\n"
        "      printf '%s\\n' '{\"items\":[]}'\n"
        "    fi\n"
        "  else\n"
        "    printf '%s\\n' '{\"items\":[]}'\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project item-add\" ]]; then\n"
        "  printf 'project item-add %s\\n' \"$*\" >> \"$calls\"\n"
        "  touch \"$state_dir/project-added\"\n"
        "  printf '%s\\n' '{\"id\":\"item-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"project item-edit\" ]]; then\n"
        "  printf 'project item-edit %s\\n' \"$*\" >> \"$calls\"\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected gh args: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    return fake_bin, fake_state


def run_finish_issue(
    repo: Path,
    fake_bin: Path,
    tmp_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(tmp_path)
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_finish_issue_dry_run_reports_verified_cleanup_plan(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "PR: #123" in result.stdout
    assert "Would remove worktree" in result.stdout
    assert "Would delete local branch: feat/dry-run" in result.stdout
    assert worktree.exists()


def test_finish_issue_rejects_dirty_worktree_before_cleanup(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    (worktree / "dirty.txt").write_text("do not delete\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 1
    assert "worktree is not clean" in result.stderr
    assert worktree.exists()
    assert run_git(repo, "branch", "--list", "feat/dry-run").stdout.strip()


def test_finish_issue_removes_clean_worktree_and_squash_merged_branch(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 0, result.stderr
    assert "Removed worktree" in result.stdout
    assert "Deleted local branch: feat/dry-run" in result.stdout
    assert "Finish workflow complete" in result.stdout
    assert not worktree.exists()
    assert run_git(repo, "branch", "--list", "feat/dry-run").stdout.strip() == ""


def test_finish_issue_adds_missing_issue_to_project_before_marking_done(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin, fake_state = write_fake_gh_with_missing_project_item(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(tmp_path)
    env["FAKE_GH_STATE"] = str(fake_state)
    env["ENTROPING_PROJECT_ITEM_LOOKUP_RETRY_DELAY_SECONDS"] = "0"

    result = subprocess.run(
        [str(SCRIPT), "99"],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "issue #99 is not on the GitHub Project board" not in result.stderr
    calls = (fake_state / "calls.log").read_text(encoding="utf-8")
    assert "project item-add" in calls
    assert "https://github.com/sakibshuvo/Entroping/issues/99" in calls
    assert "project item-edit" in calls
    assert not worktree.exists()
