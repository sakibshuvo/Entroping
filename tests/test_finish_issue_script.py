"""Smoke tests for the issue-session finish script."""

import fcntl
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_metrics_archive import (  # noqa: E402
    FactoryMetricsArchiveError,
    preserve_archive,
)
from scripts.finish_issue_replay_evidence import (  # noqa: E402
    ReplayIdentity,
    advance_replay_evidence,
    read_replay_evidence,
)

SCRIPT = REPO_ROOT / "scripts" / "finish_issue.sh"


@pytest.mark.parametrize(
    "internal_environment",
    [
        {"ENTROPING_FINISH_SCRIPT_DIR": "/dev/fd/3"},
        {"ENTROPING_FINISH_PROJECT_LIB": "/dev/fd/3"},
        {
            "ENTROPING_FINISH_PROJECT_LIB": "/dev/fd/not-a-descriptor",
            "ENTROPING_FINISH_METRICS_HELPER": "/dev/fd/4",
            "ENTROPING_FINISH_REPLAY_HELPER": "/dev/fd/5",
        },
    ],
)
def test_finish_issue_rejects_invalid_internal_helper_capabilities(
    internal_environment: dict[str, str],
) -> None:
    environment = dict(os.environ)
    environment.update(internal_environment)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 1
    assert "internal finish helper capabilities are invalid" in result.stderr


def test_finish_issue_uses_pinned_internal_helper_capabilities() -> None:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    scripts_fd = os.open(REPO_ROOT / "scripts", directory_flags)
    names = (
        "finish_issue.sh",
        "_project_board_lib.sh",
        "factory_metrics_archive.py",
        "finish_issue_replay_evidence.py",
    )
    descriptors = tuple(os.open(name, os.O_RDONLY, dir_fd=scripts_fd) for name in names)
    try:
        environment = dict(os.environ)
        environment.update(
            {
                "ENTROPING_FINISH_PROJECT_LIB": f"/dev/fd/{descriptors[1]}",
                "ENTROPING_FINISH_METRICS_HELPER": f"/dev/fd/{descriptors[2]}",
                "ENTROPING_FINISH_REPLAY_HELPER": f"/dev/fd/{descriptors[3]}",
            }
        )
        result = subprocess.run(
            ["/bin/bash", f"/dev/fd/{descriptors[0]}", "--help"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            pass_fds=descriptors,
        )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        os.close(scripts_fd)

    assert result.returncode == 0
    assert result.stderr == ""


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
    (repo / ".gitignore").write_text(".entroping/\n", encoding="utf-8")
    run_git(repo, "add", ".gitignore", "README.md")
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
    head_sha: str | None = None,
    closing_pr_numbers: tuple[int, ...] = (123,),
) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_gh = fake_bin / "gh"
    mutation_marker = shlex.quote(str(tmp_path / "finish-mutation"))
    checks = checks_json or (
        '[{"__typename":"CheckRun","name":"checks","status":"COMPLETED","conclusion":"SUCCESS"}]'
    )
    closing_refs = json.dumps(
        [
            {
                "number": number,
                "url": f"https://github.com/sakibshuvo/Entroping/pull/{number}",
            }
            for number in closing_pr_numbers
        ],
        separators=(",", ":"),
    )
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        f'  [[ "$3" == "{issue_number}" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        f'"title":"Dry run feature","url":"https://github.com/sakibshuvo/Entroping/issues/{issue_number}",'
        f'"state":"{issue_state}",'
        f'"closedByPullRequestsReferences":{closing_refs}'
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "pr view" ]]; then\n'
        '  [[ "$3" == "123" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        '"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123",'
        f'"state":"{pr_state}","headRefName":"{branch_name}",'
        + (f'"headRefOid":"{head_sha}",' if head_sha is not None else "")
        + '"mergedAt":"2026-05-30T00:00:00Z",'
        f'"statusCheckRollup":{checks}'
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "issue edit" ]]; then\n'
        f"  touch {mutation_marker}\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project view" ]]; then\n'
        "  printf '%s\\n' '{\"id\":\"project-id\"}'\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project field-list" ]]; then\n'
        "  printf '%s\\n' "
        '\'{"fields":[{"name":"Status","id":"field-id",'
        '"options":[{"name":"Done","id":"done-id"}]}]}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-list" ]]; then\n'
        "  printf '%s\\n' "
        f'\'{{"items":[{{"id":"item-id","content":{{"number":{issue_number}}}}}]}}\'\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "project item-edit" ]]; then\n'
        f"  touch {mutation_marker}\n"
        "  exit 0\n"
        "fi\n"
        'echo "unexpected gh args: $*" >&2\n'
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
        'state_dir="${FAKE_GH_STATE:?}"\n'
        'calls="$state_dir/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        f'  [[ "$3" == "{issue_number}" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        f'"title":"Finished feature","url":"https://github.com/sakibshuvo/Entroping/issues/{issue_number}",'
        '"state":"CLOSED",'
        '"closedByPullRequestsReferences":[{"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123"}]'
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "pr view" ]]; then\n'
        '  [[ "$3" == "123" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        '"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123",'
        f'"state":"MERGED","headRefName":"{branch_name}","mergedAt":"2026-05-30T00:00:00Z",'
        '"statusCheckRollup":[{"__typename":"CheckRun","name":"checks","status":"COMPLETED","conclusion":"SUCCESS"}]'
        "}\n"
        "JSON\n"
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
        '"options":[{"name":"Done","id":"done-id"}]}]}\'\n'
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
        "      printf '%s\\n' "
        f'\'{{"items":[{{"id":"item-id","content":{{"number":{issue_number}}}}}]}}\'\n'
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
    return fake_bin, fake_state


def run_finish_issue(
    repo: Path,
    fake_bin: Path,
    tmp_path: Path,
    *args: str,
    controller_fds: tuple[int, int, int, int] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(tmp_path)
    script = str(SCRIPT)
    pass_fds: tuple[int, ...] = ()
    if controller_fds is not None:
        script_fd, project_lib_fd, metrics_fd, replay_fd = controller_fds
        script = f"/dev/fd/{script_fd}"
        pass_fds = controller_fds
        env["PYTHONPATH"] = str(REPO_ROOT)
        env.update(
            {
                "ENTROPING_FINISH_PROJECT_LIB": f"/dev/fd/{project_lib_fd}",
                "ENTROPING_FINISH_METRICS_HELPER": f"/dev/fd/{metrics_fd}",
                "ENTROPING_FINISH_REPLAY_HELPER": f"/dev/fd/{replay_fd}",
            }
        )
    command = [script, *args]
    if controller_fds is not None:
        command = ["/bin/bash", script, *args]
    return subprocess.run(
        command,
        check=False,
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        pass_fds=pass_fds,
    )


def open_finish_controller_fds() -> tuple[int, int, int, int]:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    scripts_fd = os.open(REPO_ROOT / "scripts", directory_flags)
    try:
        return (
            os.open("finish_issue.sh", os.O_RDONLY, dir_fd=scripts_fd),
            os.open("_project_board_lib.sh", os.O_RDONLY, dir_fd=scripts_fd),
            os.open("factory_metrics_archive.py", os.O_RDONLY, dir_fd=scripts_fd),
            os.open(
                "finish_issue_replay_evidence.py", os.O_RDONLY, dir_fd=scripts_fd
            ),
        )
    finally:
        os.close(scripts_fd)


def write_fake_git(
    fake_bin: Path,
    *,
    fail_worktree_list: bool = False,
    fail_show_ref: bool = False,
) -> None:
    real_git = shutil.which("git")
    assert real_git is not None
    worktree_failure = (
        'if [[ "$*" == *"worktree list --porcelain"* ]]; then exit 2; fi\n'
        if fail_worktree_list
        else ""
    )
    show_ref_failure = (
        'if [[ "$*" == *"show-ref --verify --quiet refs/heads/feat/dry-run"* ]]; '
        "then exit 2; fi\n"
        if fail_show_ref
        else ""
    )
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{worktree_failure}"
        f"{show_ref_failure}"
        f"exec {shlex.quote(real_git)} \"$@\"\n",
        encoding="utf-8",
    )
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)


def replay_identity(repo: Path, worktree: Path, head: str) -> ReplayIdentity:
    return ReplayIdentity(
        issue=99,
        pull_request=123,
        expected_head=head,
        expected_branch="feat/dry-run",
        merged_at="2026-05-30T00:00:00Z",
        worktree_path=str(worktree.resolve()),
    )


def seed_replay_stage(
    repo: Path,
    worktree: Path,
    head: str,
    stage: str,
) -> ReplayIdentity:
    identity = replay_identity(repo, worktree, head)
    _ = advance_replay_evidence(repo, identity, "worktree-removal-attempted")
    if stage == "branch-deletion-attempted":
        _ = advance_replay_evidence(repo, identity, "branch-deletion-attempted")
    return identity


def branch_exists(repo: Path) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", "refs/heads/feat/dry-run"],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def strict_args(head: str) -> tuple[str, ...]:
    return (
        "99",
        "--expected-pr",
        "123",
        "--expected-head",
        head,
        "--expected-branch",
        "feat/dry-run",
    )


def test_strict_expected_identity_checks_exact_pr_head_branch_and_worktree(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)

    result = run_finish_issue(
        repo,
        fake_bin,
        tmp_path,
        "99",
        "--dry-run",
        "--expected-pr",
        "123",
        "--expected-head",
        head,
        "--expected-branch",
        "feat/dry-run",
    )

    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert read_replay_evidence(repo, replay_identity(repo, worktree, head)) == "none"


def test_strict_expected_identity_selects_expected_reclosing_pr(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(
        tmp_path,
        head_sha=head,
        closing_pr_numbers=(122, 123),
    )

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "PR: #123" in result.stdout


def test_strict_expected_identity_rejects_missing_expected_closing_pr(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(
        tmp_path,
        head_sha=head,
        closing_pr_numbers=(122,),
    )

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head), "--dry-run")

    assert result.returncode == 1
    assert "closing PR identity does not match expected PR" in result.stderr


def test_strict_expected_identity_idempotent_replay_real_cleanup(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)

    args = strict_args(head)
    first_result = run_finish_issue(repo, fake_bin, tmp_path, *args)
    assert first_result.returncode == 0
    assert not worktree.exists()
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", "refs/heads/feat/dry-run"],
            check=False,
            capture_output=True,
        ).returncode
        == 1
    )

    second_result = run_finish_issue(repo, fake_bin, tmp_path, *args)
    assert second_result.returncode == 0
    assert not worktree.exists()
    assert not branch_exists(repo)
    assert (
        read_replay_evidence(repo, replay_identity(repo, worktree, head))
        == "branch-deletion-attempted"
    )


def test_strict_controller_reuses_pinned_replay_helper(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    controller_fds = open_finish_controller_fds()
    try:
        result = run_finish_issue(
            repo,
            fake_bin,
            tmp_path,
            *strict_args(head),
            controller_fds=controller_fds,
        )
    finally:
        for descriptor in reversed(controller_fds):
            os.close(descriptor)

    assert result.returncode == 0
    assert not worktree.exists()
    assert not branch_exists(repo)
    assert (
        read_replay_evidence(repo, replay_identity(repo, worktree, head))
        == "branch-deletion-attempted"
    )


def test_strict_first_attempt_rejects_absent_worktree_and_branch(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    assert run_git(repo, "worktree", "remove", str(worktree), "--force").returncode == 0
    run_git(repo, "branch", "-D", "feat/dry-run")
    identity = replay_identity(repo, worktree, head)

    result = run_finish_issue(
        repo,
        fake_bin,
        tmp_path,
        "99",
        "--expected-pr",
        "123",
        "--expected-head",
        head,
        "--expected-branch",
        "feat/dry-run",
    )

    assert result.returncode == 1
    assert "strict cleanup requires" in result.stderr
    assert not worktree.exists()
    assert not branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "none"


def test_strict_first_attempt_rejects_absent_worktree_with_present_branch(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    run_git(repo, "worktree", "remove", str(worktree), "--force")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert branch_exists(repo)


def test_strict_first_attempt_rejects_absent_branch_with_present_worktree(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    run_git(worktree, "switch", "--detach")
    run_git(repo, "branch", "-D", "feat/dry-run")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert worktree.exists()
    assert not branch_exists(repo)


@pytest.mark.parametrize(
    ("proof_exists", "dangling"),
    [(False, False), (True, True)],
)
def test_strict_rejects_symlink_worktree_before_ref_or_project_cleanup(
    tmp_path: Path,
    proof_exists: bool,
    dangling: bool,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    link = tmp_path / "strict-worktree-link"
    target = worktree
    if dangling:
        run_git(repo, "worktree", "remove", str(worktree), "--force")
        target = tmp_path / "missing-worktree-target"
    link.symlink_to(target, target_is_directory=True)
    identity = ReplayIdentity(
        issue=99,
        pull_request=123,
        expected_head=head,
        expected_branch="feat/dry-run",
        merged_at="2026-05-30T00:00:00Z",
        worktree_path=str(target.resolve()),
    )
    if proof_exists:
        _ = advance_replay_evidence(repo, identity, "worktree-removal-attempted")

    result = run_finish_issue(
        repo,
        fake_bin,
        tmp_path,
        *strict_args(head),
        "--worktree",
        str(link),
    )

    assert result.returncode == 1
    assert "worktree path must not be a symlink" in result.stderr
    assert branch_exists(repo)
    assert not (tmp_path / "finish-mutation").exists()
    expected_stage = "worktree-removal-attempted" if proof_exists else "none"
    assert read_replay_evidence(repo, identity) == expected_stage


def test_strict_expected_identity_requires_all_three_arguments(tmp_path: Path) -> None:
    _repo, _worktree = create_repo_with_worktree(tmp_path)
    fake_bin = write_fake_gh(tmp_path)
    result = run_finish_issue(
        _repo,
        fake_bin,
        tmp_path,
        "99",
        "--dry-run",
        "--expected-pr",
        "123",
    )

    assert result.returncode == 1
    assert "must be supplied together" in result.stderr


def test_strict_worktree_stage_retries_present_worktree_cleanup(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 0
    assert not worktree.exists()
    assert not branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "branch-deletion-attempted"


def test_strict_worktree_stage_deletes_exact_present_branch(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")
    run_git(repo, "worktree", "remove", str(worktree), "--force")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 0
    assert not branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "branch-deletion-attempted"


def test_strict_worktree_probe_failure_preserves_branch_and_proof(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")
    run_git(repo, "worktree", "remove", str(worktree), "--force")
    write_fake_git(fake_bin, fail_worktree_list=True)

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert "worktree registration probe failed" in result.stderr
    assert branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "worktree-removal-attempted"
    assert not (tmp_path / "finish-mutation").exists()


def test_strict_show_ref_probe_failure_preserves_objects_and_proof(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")
    write_fake_git(fake_bin, fail_show_ref=True)

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert "local branch probe failed" in result.stderr
    assert worktree.exists()
    assert branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "worktree-removal-attempted"
    assert not (tmp_path / "finish-mutation").exists()


def test_strict_worktree_stage_rejects_both_objects_absent(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")
    run_git(repo, "worktree", "remove", str(worktree), "--force")
    run_git(repo, "branch", "-D", "feat/dry-run")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert read_replay_evidence(repo, identity) == "worktree-removal-attempted"


def test_strict_branch_stage_accepts_both_objects_absent(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "branch-deletion-attempted")
    run_git(repo, "worktree", "remove", str(worktree), "--force")
    run_git(repo, "branch", "-D", "feat/dry-run")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 0
    assert read_replay_evidence(repo, identity) == "branch-deletion-attempted"


def test_strict_branch_stage_rejects_reappeared_worktree(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    identity = seed_replay_stage(repo, worktree, head, "branch-deletion-attempted")

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert worktree.exists()
    assert branch_exists(repo)
    assert read_replay_evidence(repo, identity) == "branch-deletion-attempted"


@pytest.mark.parametrize("damage", ["conflict", "corrupt", "symlink"])
def test_strict_rejects_invalid_replay_evidence_before_cleanup(
    tmp_path: Path,
    damage: str,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    fake_bin = write_fake_gh(tmp_path, head_sha=head)
    if damage == "conflict":
        conflicting = replace(replay_identity(repo, worktree, head), pull_request=124)
        _ = advance_replay_evidence(repo, conflicting, "worktree-removal-attempted")
    else:
        _ = seed_replay_stage(repo, worktree, head, "worktree-removal-attempted")
        proof = repo / ".entroping" / "finish-issue-replay" / "issue-99.json"
        if damage == "corrupt":
            proof.write_text("not-json", encoding="utf-8")
        else:
            outside = tmp_path / "outside-proof.json"
            proof.replace(outside)
            proof.symlink_to(outside)

    result = run_finish_issue(repo, fake_bin, tmp_path, *strict_args(head))

    assert result.returncode == 1
    assert "strict cleanup replay evidence is invalid or unsafe" in result.stderr
    assert worktree.exists()
    assert branch_exists(repo)


def test_strict_expected_identity_rejects_mismatched_local_head(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    expected_head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    run_git(worktree, "commit", "--allow-empty", "-m", "simulate divergent local branch")
    mismatched_head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    assert mismatched_head != expected_head
    identity = seed_replay_stage(
        repo,
        worktree,
        expected_head,
        "worktree-removal-attempted",
    )
    assert run_git(repo, "worktree", "remove", str(worktree), "--force").returncode == 0
    assert not worktree.exists()
    assert read_replay_evidence(repo, identity) == "worktree-removal-attempted"

    fake_bin = write_fake_gh(tmp_path, head_sha=expected_head)
    result = run_finish_issue(
        repo,
        fake_bin,
        tmp_path,
        "99",
        "--expected-pr",
        "123",
        "--expected-head",
        expected_head,
        "--expected-branch",
        "feat/dry-run",
    )

    assert result.returncode == 1
    assert "local branch does not match expected head" in result.stderr
    assert subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", "refs/heads/feat/dry-run"],
        check=False,
        capture_output=True,
    ).returncode == 0
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "refs/heads/feat/dry-run"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == mismatched_head
    )
    assert not worktree.exists()


def write_factory_metrics_fixture(worktree: Path) -> tuple[Path, Path]:
    metrics_dir = worktree / ".entroping" / "factory-metrics"
    nested_dir = metrics_dir / "workers" / "deepseek"
    nested_dir.mkdir(parents=True)
    root_ledger = metrics_dir / "events.jsonl"
    nested_ledger = nested_dir / "events.jsonl"
    root_ledger.write_text(
        json.dumps(
            {
                "schema_version": "entroping.factory-metrics.v1",
                "event_id": "finish-root",
                "recorded_at": "2026-05-30T00:00:00Z",
                "event_type": "outcome",
                "role": "integrator",
                "agent": "codex",
                "metrics": {"estimated_tokens": 10},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    nested_ledger.write_text(
        json.dumps(
            {
                "schema_version": "entroping.factory-metrics.v1",
                "event_id": "finish-nested",
                "recorded_at": "2026-05-30T00:00:00Z",
                "event_type": "worker_job",
                "role": "dev_agent",
                "agent": "deepseek",
                "metrics": {"estimated_tokens": 25},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (metrics_dir / "ignored.txt").write_text("not a ledger\n", encoding="utf-8")
    return root_ledger, nested_ledger


def test_finish_issue_help_documents_keep_worktree_mode() -> None:
    result = subprocess.run(
        [str(SCRIPT), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--keep-worktree" in result.stdout
    assert "post-merge diagnostics" in result.stdout


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


def test_finish_issue_dry_run_reports_factory_metrics_without_writing(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would preserve factory metrics ledgers" in result.stdout
    assert "events.jsonl" in result.stdout
    assert "workers/deepseek/events.jsonl" in result.stdout
    assert "ignored.txt" not in result.stdout
    assert not (repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99").exists()
    assert worktree.exists()


def test_finish_issue_keep_worktree_verifies_without_cleanup(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99", "--keep-worktree")

    assert result.returncode == 0, result.stderr
    assert "KEEP WORKTREE" in result.stdout
    assert "Verified merged issue and CI; kept local cleanup state." in result.stdout
    assert "Removed worktree" not in result.stdout
    assert "Deleted local branch" not in result.stdout
    assert worktree.exists()
    assert run_git(repo, "branch", "--list", "feat/dry-run").stdout.strip()


def test_finish_issue_preserves_factory_metrics_before_worktree_removal(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    root_ledger, nested_ledger = write_factory_metrics_fixture(worktree)
    root_content = root_ledger.read_text(encoding="utf-8")
    nested_content = nested_ledger.read_text(encoding="utf-8")
    metrics_dir = worktree / ".entroping" / "factory-metrics"
    with suppress(OSError):
        (metrics_dir / "linked.jsonl").symlink_to(root_ledger)
        (metrics_dir / "linked-workers").symlink_to(metrics_dir / "workers")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 0, result.stderr
    assert "Preserved factory metrics ledgers (2 files)" in result.stdout
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    assert (destination / "events.jsonl").read_text(encoding="utf-8") == root_content
    assert (destination / "workers" / "deepseek" / "events.jsonl").read_text(
        encoding="utf-8"
    ) == nested_content
    assert not (destination / "ignored.txt").exists()
    assert not (destination / "linked.jsonl").exists()
    assert not (destination / "linked-workers").exists()
    metadata = cast(
        dict[str, object],
        json.loads((destination / "metadata.json").read_text(encoding="utf-8")),
    )
    assert metadata == {
        "schema_version": "entroping.factory-metrics-archive.v1",
        "issue": 99,
        "pull_request": 123,
        "status": "archived",
        "issue_state": "closed",
        "pr_state": "merged",
        "archived_at": "2026-05-30T00:00:00Z",
        "ledgers": [
            {
                "path": "events.jsonl",
                "byte_size": len(root_content.encode("utf-8")),
                "sha256": hashlib.sha256(root_content.encode("utf-8")).hexdigest(),
            },
            {
                "path": "workers/deepseek/events.jsonl",
                "byte_size": len(nested_content.encode("utf-8")),
                "sha256": hashlib.sha256(nested_content.encode("utf-8")).hexdigest(),
            },
        ],
    }
    assert not worktree.exists()


def test_finish_issue_rejects_symlinked_metrics_archive_destination(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    outside = tmp_path / "outside"
    outside.mkdir()
    archive_root = repo / ".entroping" / "factory-metrics" / "finished-issues"
    archive_root.mkdir(parents=True)
    (archive_root / "issue-99").symlink_to(outside, target_is_directory=True)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "factory metrics archive path is unsafe" in result.stderr
    assert list(outside.iterdir()) == []
    assert worktree.exists()


def test_finish_issue_rejects_conflicting_metrics_archive_provenance(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    destination.mkdir(parents=True)
    (destination / "metadata.json").write_text(
        '{"issue":99,"pull_request":999}\n', encoding="utf-8"
    )
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "different provenance" in result.stderr
    assert not (destination / "events.jsonl").exists()
    assert worktree.exists()


def test_finish_issue_rejects_oversized_factory_metrics_archive(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    metrics = worktree / ".entroping" / "factory-metrics"
    metrics.mkdir(parents=True)
    (metrics / "events.jsonl").write_bytes(b"")
    with (metrics / "events.jsonl").open("r+b") as stream:
        stream.truncate(67_108_865)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "aggregate byte limit" in result.stderr
    assert worktree.exists()


def test_finish_issue_rejects_non_metrics_jsonl_before_cleanup(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    metrics = worktree / ".entroping" / "factory-metrics"
    metrics.mkdir(parents=True)
    (metrics / "provider-transcript.jsonl").write_text(
        '{"provider_transcript":"not factory metrics"}\n', encoding="utf-8"
    )
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "invalid event" in result.stderr
    assert "provider_transcript" not in result.stderr
    assert worktree.exists()


def test_finish_issue_rejects_secret_like_metrics_without_echo(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    metrics = worktree / ".entroping" / "factory-metrics"
    metrics.mkdir(parents=True)
    secret = "sk-proj-synthetic-secret-value"
    (metrics / "events.jsonl").write_text(json.dumps({"note": secret}) + "\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "unredacted secret-like data" in result.stderr
    assert secret not in result.stderr
    assert worktree.exists()


def test_finish_issue_rejects_json_escaped_secret_without_echo(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    metrics = worktree / ".entroping" / "factory-metrics"
    metrics.mkdir(parents=True)
    secret = "sk-proj-synthetic-escaped-secret"
    event = {
        "schema_version": "entroping.factory-metrics.v1",
        "event_id": secret,
        "recorded_at": "2026-05-30T00:00:00Z",
        "event_type": "outcome",
        "role": "integrator",
        "agent": "codex",
        "metrics": {},
    }
    encoded = json.dumps(event).replace("sk-proj-", r"\u0073k-proj-")
    (metrics / "events.jsonl").write_text(encoded + "\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "invalid event" in result.stderr
    assert secret not in result.stderr
    assert worktree.exists()


def test_finish_issue_does_not_seal_unexpected_archive_ledger(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    destination.mkdir(parents=True)
    stale = "sk-proj-stale-unvalidated-secret"
    (destination / "stale.jsonl").write_text(stale + "\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "unexpected ledger" in result.stderr
    assert stale not in result.stderr
    assert not (destination / "metadata.json").exists()
    assert worktree.exists()


def test_finish_issue_accepts_identical_terminal_metrics_archive_retry(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    _ = preserve_archive(
        repo_root=repo,
        worktree_root=worktree,
        issue=99,
        pull_request=123,
        archived_at="2026-05-30T00:00:00Z",
    )
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 0, result.stderr
    assert "Preserved factory metrics ledgers (2 files)" in result.stdout
    assert not worktree.exists()


def test_metrics_archive_waits_for_source_writer_lock(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    lock_path = worktree / ".entroping" / "factory-metrics" / ".metrics-storage.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    command = (
        "from pathlib import Path; "
        "from scripts.factory_metrics_archive import preserve_archive; "
        f"preserve_archive(repo_root=Path({str(repo)!r}), "
        f"worktree_root=Path({str(worktree)!r}), issue=99, pull_request=123, "
        "archived_at='2026-05-30T00:00:00Z'); print('archived')"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", command],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.2)
        assert process.poll() is None
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    assert stdout.strip() == "archived"


def test_metrics_archive_refuses_to_rewrite_different_terminal_content(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    root_ledger, _ = write_factory_metrics_fixture(worktree)
    _ = preserve_archive(
        repo_root=repo,
        worktree_root=worktree,
        issue=99,
        pull_request=123,
        archived_at="2026-05-30T00:00:00Z",
    )
    archived = (
        repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99" / "events.jsonl"
    )
    original = archived.read_bytes()
    root_ledger.write_bytes(original + original)

    with pytest.raises(FactoryMetricsArchiveError, match="different provenance"):
        _ = preserve_archive(
            repo_root=repo,
            worktree_root=worktree,
            issue=99,
            pull_request=123,
            archived_at="2026-05-30T00:00:00Z",
        )

    assert archived.read_bytes() == original


def test_finish_issue_bounds_existing_metrics_archive_metadata(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    write_factory_metrics_fixture(worktree)
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    destination.mkdir(parents=True)
    (destination / "metadata.json").write_bytes(b"x" * 65_537)
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "metadata is unreadable" in result.stderr
    assert worktree.exists()


def test_metrics_archive_rejects_manifest_over_metadata_limit_before_sealing(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    metrics = worktree / ".entroping" / "factory-metrics"
    metrics.mkdir(parents=True)
    for index in range(512):
        event = {
            "schema_version": "entroping.factory-metrics.v1",
            "event_id": f"manifest-bound-{index:04d}",
            "recorded_at": "2026-05-30T00:00:00Z",
            "event_type": "outcome",
            "role": "integrator",
            "agent": "codex",
            "metrics": {},
        }
        _ = (metrics / f"ledger-{index:04d}.jsonl").write_text(
            json.dumps(event) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(FactoryMetricsArchiveError, match="metadata exceeds its byte limit"):
        _ = preserve_archive(
            repo_root=repo,
            worktree_root=worktree,
            issue=99,
            pull_request=123,
            archived_at="2026-05-30T00:00:00Z",
        )

    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    assert not destination.exists()
    assert len(tuple(metrics.glob("*.jsonl"))) == 512


def test_finish_issue_rejects_terminal_archive_ledgers_when_source_is_empty(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    (worktree / ".entroping" / "factory-metrics").mkdir(parents=True)
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    destination.mkdir(parents=True)
    (destination / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.factory-metrics-archive.v1",
                "issue": 99,
                "pull_request": 123,
                "status": "archived",
                "issue_state": "closed",
                "pr_state": "merged",
                "archived_at": "2026-05-30T00:00:00Z",
                "ledgers": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (destination / "stale.jsonl").write_text("corrupt\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "different ledger set" in result.stderr
    assert worktree.exists()


def test_finish_issue_rejects_terminal_archive_ledgers_when_source_is_absent(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    destination = repo / ".entroping" / "factory-metrics" / "finished-issues" / "issue-99"
    destination.mkdir(parents=True)
    (destination / "stale.jsonl").write_text("corrupt\n", encoding="utf-8")
    fake_bin = write_fake_gh(tmp_path)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 2
    assert "unexpected ledger" in result.stderr
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


def test_finish_issue_rejects_unknown_failed_ci_rollup_entry(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    checks_json = (
        '[{"__typename":"UnexpectedCheck","name":"custom-ci",'
        '"status":"COMPLETED","conclusion":"FAILURE"}]'
    )
    fake_bin = write_fake_gh(tmp_path, checks_json=checks_json)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 1
    assert "closing PR has non-passing checks" in result.stderr
    assert "custom-ci: unrecognized check state" in result.stderr
    assert worktree.exists()
    assert run_git(repo, "branch", "--list", "feat/dry-run").stdout.strip()


def test_finish_issue_accepts_unknown_passing_ci_rollup_entry(tmp_path: Path) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    checks_json = (
        '[{"__typename":"UnexpectedCheck","name":"custom-ci",'
        '"status":"COMPLETED","conclusion":"SUCCESS"}]'
    )
    fake_bin = write_fake_gh(tmp_path, checks_json=checks_json)

    result = run_finish_issue(repo, fake_bin, tmp_path, "99")

    assert result.returncode == 0, result.stderr
    assert "CI checks verified: 1" in result.stdout
    assert not worktree.exists()
    assert run_git(repo, "branch", "--list", "feat/dry-run").stdout.strip() == ""


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


def test_finish_issue_finds_existing_project_item_beyond_first_200(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'state_dir="${FAKE_GH_STATE:?}"\n'
        'calls="$state_dir/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        '  [[ "$3" == "99" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        '"title":"Finished large project feature",'
        '"url":"https://github.com/sakibshuvo/Entroping/issues/99",'
        '"state":"CLOSED",'
        '"closedByPullRequestsReferences":[{"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123"}]'
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "pr view" ]]; then\n'
        '  [[ "$3" == "123" ]]\n'
        "  cat <<'JSON'\n"
        "{"
        '"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123",'
        '"state":"MERGED","headRefName":"feat/dry-run","mergedAt":"2026-05-30T00:00:00Z",'
        '"statusCheckRollup":[{"__typename":"CheckRun","name":"checks","status":"COMPLETED","conclusion":"SUCCESS"}]'
        "}\n"
        "JSON\n"
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
        '"options":[{"name":"Done","id":"done-id"}]}]}\'\n'
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
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(tmp_path)
    env["FAKE_GH_STATE"] = str(fake_state)

    result = subprocess.run(
        [str(SCRIPT), "99"],
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
    assert not worktree.exists()


def test_finish_issue_skips_project_update_when_graphql_quota_is_exhausted(
    tmp_path: Path,
) -> None:
    repo, worktree = create_repo_with_worktree(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_state = tmp_path / "fake-gh-state"
    fake_state.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'calls="${FAKE_GH_STATE:?}/calls.log"\n'
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        "  cat <<'JSON'\n"
        "{"
        '"title":"Finished quota feature",'
        '"url":"https://github.com/sakibshuvo/Entroping/issues/99",'
        '"state":"CLOSED",'
        '"closedByPullRequestsReferences":[{"number":123,"url":"https://github.com/sakibshuvo/Entroping/pull/123"}]'
        "}\n"
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$1 $2" == "pr view" ]]; then\n'
        "  cat <<'JSON'\n"
        "{"
        '"number":123,'
        '"url":"https://github.com/sakibshuvo/Entroping/pull/123",'
        '"state":"MERGED",'
        '"headRefName":"feat/dry-run",'
        '"mergedAt":"2026-05-30T00:00:00Z",'
        '"statusCheckRollup":[{"__typename":"CheckRun","name":"checks","status":"COMPLETED","conclusion":"SUCCESS"}]'
        "}\n"
        "JSON\n"
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
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["ENTROPING_WORKTREE_PARENT"] = str(tmp_path)
    env["FAKE_GH_STATE"] = str(fake_state)

    result = subprocess.run(
        [str(SCRIPT), "99"],
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
    assert not worktree.exists()
