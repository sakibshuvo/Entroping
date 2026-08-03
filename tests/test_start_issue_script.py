"""Smoke tests for the issue-session launcher script."""

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
START_ISSUE_SCRIPT = REPO_ROOT / "scripts" / "start_issue.sh"


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def create_start_issue_fixture_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    run_git(tmp_path, "init", "--bare", str(origin))

    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "start-issue-fixture"
version = "0.0.0"
requires-python = ">=3.12"
""".lstrip(),
        encoding="utf-8",
    )
    session_prompt = repo / "src" / "entroping" / "core" / "session_prompt.py"
    session_prompt.parent.mkdir(parents=True)
    (repo / "src" / "entroping" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "entroping" / "core" / "__init__.py").write_text("", encoding="utf-8")
    session_prompt.write_text(
        """
from __future__ import annotations

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--issue")
parser.add_argument("--title")
parser.add_argument("--url")
parser.add_argument("--worktree")
parser.add_argument("--branch")
parser.add_argument("--repo")
parser.add_argument("--mode")
args = parser.parse_args()
print(f"# Entroping Issue Session: #{args.issue}")
print(f"Mode: {args.mode}")
print(f"Context pack: `scripts/context_pack.sh --mode {args.mode}`")
""".lstrip(),
        encoding="utf-8",
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "init")
    run_git(repo, "remote", "add", "origin", str(origin))
    run_git(repo, "push", "-u", "origin", "main")
    return repo


def test_start_issue_help_documents_dry_run_mode() -> None:
    result = subprocess.run(
        [str(START_ISSUE_SCRIPT), "--help"],
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
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Dry run feature","url":"https://github.com/sakibshuvo/Entroping/issues/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
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
            str(START_ISSUE_SCRIPT),
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
    assert "scripts/context_pack.sh --mode implementation" in result.stdout
    assert not (worktree_parent / "Entroping-issue-99").exists()


def test_start_issue_review_dry_run_uses_review_context_pack(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Review feature","url":"https://github.com/sakibshuvo/Entroping/issues/100","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
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
            str(START_ISSUE_SCRIPT),
            "100",
            "review/context-pack",
            "--mode",
            "review",
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
    assert "Review feature" in result.stdout
    assert "Mode: review" in result.stdout
    assert "scripts/context_pack.sh --mode review" in result.stdout
    assert "scripts/context_pack.sh --mode implementation" not in result.stdout
    assert not (worktree_parent / "Entroping-issue-100").exists()


def test_start_issue_refuses_branch_that_already_exists_on_origin(tmp_path: Path) -> None:
    repo = create_start_issue_fixture_repo(tmp_path)
    branch_name = "tooling/existing-remote"
    run_git(repo, "checkout", "-b", branch_name)
    run_git(repo, "push", "-u", "origin", branch_name)
    run_git(repo, "checkout", "main")
    run_git(repo, "branch", "-D", branch_name)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Existing remote","url":"https://github.com/sakibshuvo/Entroping/issues/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)

    result = subprocess.run(
        [str(START_ISSUE_SCRIPT), "99", branch_name],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert f"remote branch already exists on origin: {branch_name}" in result.stderr
    assert not (worktree_parent / "Entroping-issue-99").exists()


def test_start_issue_exact_base_does_not_advance_main(tmp_path: Path) -> None:
    # Given: local main at the authorized base while origin/main advances.
    repo = create_start_issue_fixture_repo(tmp_path)
    base = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    publisher = tmp_path / "publisher"
    run_git(tmp_path, "clone", "-b", "main", str(tmp_path / "origin.git"), str(publisher))
    run_git(publisher, "config", "user.email", "test@example.com")
    run_git(publisher, "config", "user.name", "Test User")
    (publisher / "remote.txt").write_text("ahead\n", encoding="utf-8")
    run_git(publisher, "add", "remote.txt")
    run_git(publisher, "commit", "-m", "remote ahead")
    run_git(publisher, "push", "origin", "main")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Exact base","url":"https://example.invalid/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "issue edit" ]]; then exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)

    # When: the launcher is given the exact orchestration base.
    result = subprocess.run(
        [
            str(START_ISSUE_SCRIPT),
            "99",
            "feat/exact-base",
            "--base-commit",
            base,
        ],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    # Then: main is untouched and the worktree is created at exactly that base.
    assert result.returncode == 0, result.stderr
    worktree = worktree_parent / "Entroping-issue-99"
    assert run_git(repo, "rev-parse", "HEAD").stdout.strip() == base
    assert run_git(worktree, "rev-parse", "HEAD").stdout.strip() == base
    assert not (repo / "remote.txt").exists()


def test_start_issue_adds_missing_issue_to_project_before_marking_in_progress(
    tmp_path: Path,
) -> None:
    repo = create_start_issue_fixture_repo(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'state_dir="${FAKE_GH_STATE:?}"\n'
        'calls="$state_dir/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Project add feature","url":"https://github.com/sakibshuvo/Entroping/issues/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "issue edit" ]]; then\n'
        '  printf \'issue edit %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project view" ]]; then\n'
        "  printf '%s\\n' '{\"id\":\"project-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project field-list" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"fields":[{"name":"Status","id":"field-id",'
        '"options":[{"name":"In Progress","id":"in-progress-id"}]}]}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-list" ]]; then\n'
        '  if [[ -f "$state_dir/project-added" ]]; then\n'
        '    count_file="$state_dir/item-list-after-add-count"\n'
        "    count=0\n"
        '    [[ -f "$count_file" ]] && count=$(cat "$count_file")\n'
        "    count=$((count + 1))\n"
        '    printf \'%s\\n\' "$count" > "$count_file"\n'
        "    if ((count >= 2)); then\n"
        '      printf \'%s\\n\' \'{"items":[{"id":"item-id","content":{"number":99}}]}\'\n'
        "    else\n"
        "      printf '%s\\n' '{\"items\":[]}'\n"
        "    fi\n"
        "  else\n"
        "    printf '%s\\n' '{\"items\":[]}'\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-add" ]]; then\n'
        '  printf \'project item-add %s\\n\' "$*" >> "$calls"\n'
        '  touch "$state_dir/project-added"\n'
        "  printf '%s\\n' '{\"id\":\"item-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-edit" ]]; then\n'
        '  printf \'project item-edit %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_GH_STATE"] = str(fake_state)
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)
    env["ENTROPING_PROJECT_ITEM_LOOKUP_RETRY_DELAY_SECONDS"] = "0"

    result = subprocess.run(
        [str(START_ISSUE_SCRIPT), "99", "feat/project-add"],
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
    assert (worktree_parent / "Entroping-issue-99").is_dir()


def test_start_issue_finds_existing_project_item_beyond_first_200(
    tmp_path: Path,
) -> None:
    repo = create_start_issue_fixture_repo(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'state_dir="${FAKE_GH_STATE:?}"\n'
        'calls="$state_dir/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Large project feature","url":"https://github.com/sakibshuvo/Entroping/issues/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "issue edit" ]]; then\n'
        '  printf \'issue edit %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project view" ]]; then\n'
        "  printf '%s\\n' '{\"id\":\"project-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project field-list" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"fields":[{"name":"Status","id":"field-id",'
        '"options":[{"name":"In Progress","id":"in-progress-id"}]}]}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-list" ]]; then\n'
        '  printf \'project item-list %s\\n\' "$*" >> "$calls"\n'
        "  limit=0\n"
        "  previous=''\n"
        '  for arg in "$@"; do\n'
        '    if [[ "$previous" == \'--limit\' ]]; then limit="$arg"; fi\n'
        '    previous="$arg"\n'
        "  done\n"
        "  if ((limit > 200)); then\n"
        '    printf \'%s\\n\' \'{"items":[{"id":"late-item-id","content":{"number":99}}]}\'\n'
        "  else\n"
        "    printf '%s\\n' '{\"items\":[]}'\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-add" ]]; then\n'
        '  printf \'project item-add %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-edit" ]]; then\n'
        '  printf \'project item-edit %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_GH_STATE"] = str(fake_state)
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)

    result = subprocess.run(
        [str(START_ISSUE_SCRIPT), "99", "feat/large-project"],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    calls = (fake_state / "calls.log").read_text(encoding="utf-8")
    assert "project item-list" in calls
    assert "project item-add" not in calls
    assert "project item-edit" in calls
    assert "late-item-id" in calls
    assert (worktree_parent / "Entroping-issue-99").is_dir()


def test_start_issue_skips_project_update_when_graphql_quota_is_exhausted(
    tmp_path: Path,
) -> None:
    repo = create_start_issue_fixture_repo(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'calls="${FAKE_GH_STATE:?}/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"title":"Quota feature","url":"https://github.com/sakibshuvo/Entroping/issues/99","state":"OPEN"}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "issue edit" ]]; then\n'
        '  printf \'issue edit %s\\n\' "$*" >> "$calls"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "api rate_limit" ]]; then\n'
        "  printf '%s\\n' '0'\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1" == "project" ]]; then\n'
        "  printf 'unexpected project command: %s\\n' \"$*\" >&2\n"
        "  exit 2\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
    worktree_parent = tmp_path / "worktrees"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_GH_STATE"] = str(fake_state)
    env["ENTROPING_WORKTREE_PARENT"] = str(worktree_parent)

    result = subprocess.run(
        [str(START_ISSUE_SCRIPT), "99", "tooling/quota-preflight"],
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "GitHub Project GraphQL quota is low" in result.stderr
    assert "need at least 50" in result.stderr
    calls = (fake_state / "calls.log").read_text(encoding="utf-8")
    assert "issue edit" in calls
    assert "project " not in calls
    assert (worktree_parent / "Entroping-issue-99").is_dir()
