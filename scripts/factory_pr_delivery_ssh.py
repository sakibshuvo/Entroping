"""Config-free SSH transport for one explicit delivery ref."""

from __future__ import annotations

import os
import pwd
import re
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from scripts.bounded_process import (
    BoundedProcessError,
    BoundedProcessResult,
    run_bounded_process,
)
from scripts.factory_pr_delivery_models import DeliveryGitError

_GIT: Final = "/usr/bin/git"
_SSH: Final = "/usr/bin/ssh"
_ORIGIN: Final = "git@github.com:sakibshuvo/Entroping.git"
_TIMEOUT: Final = 15.0
_OUTPUT_LIMIT: Final = 1_048_576
_ENV: Final = {
    "PATH": "/usr/bin:/bin",
    "LC_ALL": "C",
    "LANG": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


@dataclass(frozen=True, slots=True)
class PushSpec:
    argv: tuple[str, ...]
    ssh_argv: tuple[str, ...]
    env: dict[str, str]


@dataclass(frozen=True, slots=True)
class PushResult:
    state: str
    remote_head: str


DeleteBranchState = Literal["deleted", "absent"]


@dataclass(frozen=True, slots=True)
class DeleteBranchResult:
    state: DeleteBranchState
    remote_head: str | None


def build_push_spec(
    worktree: Path,
    *,
    branch: str,
    committed_head: str,
) -> PushSpec:
    """Build the only permitted explicit non-force push invocation."""

    if (
        not branch
        or branch in {"main", "master"}
        or re.fullmatch(r"[a-f0-9]{40}", committed_head) is None
    ):
        raise DeliveryGitError("authority-mismatch")
    fetch_url = _git_text(worktree, "remote", "get-url", "origin")
    push_url = _git_text(worktree, "remote", "get-url", "--push", "origin")
    if fetch_url != _ORIGIN or push_url != _ORIGIN:
        raise DeliveryGitError("remote-invalid")
    home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve()
    identity = home / ".ssh/id_ed25519"
    known_hosts = home / ".ssh/known_hosts"
    _require_private_regular(identity)
    _require_private_regular(known_hosts)
    ssh_argv = (
        _SSH,
        "-F",
        "/dev/null",
        "-oBatchMode=yes",
        "-oIdentitiesOnly=yes",
        "-oStrictHostKeyChecking=yes",
        "-oProxyCommand=none",
        "-oForwardAgent=no",
        "-oClearAllForwardings=yes",
        "-oConnectTimeout=10",
        "-i",
        str(identity),
        "-oUserKnownHostsFile=" + str(known_hosts),
    )
    argv = (
        _GIT,
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "-c",
        f"core.sshCommand={shlex.join(ssh_argv)}",
        "push",
        "--porcelain",
        "--no-verify",
        "--no-follow-tags",
        "--",
        "origin",
        f"{committed_head}:refs/heads/{branch}",
    )
    return PushSpec(argv=argv, ssh_argv=ssh_argv, env=dict(_ENV))


def push_exact_commit(
    worktree: Path,
    *,
    branch: str,
    committed_head: str,
) -> PushResult:
    """Push one exact ref or accept an exact remote replay after response loss."""

    spec = build_push_spec(
        worktree,
        branch=branch,
        committed_head=committed_head,
    )
    before = _remote_head(worktree, spec, branch)
    if before == committed_head:
        return PushResult("replay", committed_head)
    if before is not None:
        raise DeliveryGitError("remote-diverged")
    outcome = _run_external(spec.argv, cwd=worktree, env=spec.env)
    after = _remote_head(worktree, spec, branch)
    if after == committed_head:
        return PushResult("pushed", committed_head)
    if outcome.timed_out or outcome.output_limit_exceeded:
        raise DeliveryGitError("push-uncertain")
    if outcome.returncode != 0:
        raise DeliveryGitError("push-rejected")
    raise DeliveryGitError("push-uncertain")


def delete_remote_branch(
    worktree: Path,
    *,
    branch: str,
    expected_head: str,
) -> DeleteBranchResult:
    """Delete one exact remote branch with a strict lease or replay safely."""

    spec = build_push_spec(
        worktree,
        branch=branch,
        committed_head=expected_head,
    )
    before = _remote_head(worktree, spec, branch)
    if before is None:
        return DeleteBranchResult("absent", None)
    if before != expected_head:
        raise DeliveryGitError("remote-diverged")

    outcome: BoundedProcessResult | None = None
    push_index = spec.argv.index("push")
    delete_argv = (
        *spec.argv[: push_index + 4],
        f"--force-with-lease=refs/heads/{branch}:{expected_head}",
        "--",
        "origin",
        f":refs/heads/{branch}",
    )
    try:
        outcome = _run_external(delete_argv, cwd=worktree, env=spec.env)
    except DeliveryGitError:
        outcome = None
    try:
        after = _remote_head(worktree, spec, branch)
    except DeliveryGitError:
        raise DeliveryGitError("remote-delete-uncertain") from None
    if after is None:
        return DeleteBranchResult("deleted", None)
    if after != expected_head:
        raise DeliveryGitError("remote-diverged")
    if outcome is None:
        raise DeliveryGitError("remote-delete-uncertain")
    if outcome.timed_out or outcome.output_limit_exceeded or outcome.cancelled:
        raise DeliveryGitError("remote-delete-uncertain")
    if outcome.returncode != 0:
        raise DeliveryGitError("remote-delete-rejected")
    raise DeliveryGitError("remote-delete-uncertain")


def observe_remote_branch(
    worktree: Path,
    *,
    branch: str,
    expected_head: str,
) -> str | None:
    """Observe one exact origin ref using the same authority as deletion."""
    spec = build_push_spec(
        worktree,
        branch=branch,
        committed_head=expected_head,
    )
    return _remote_head(worktree, spec, branch)


def _remote_head(worktree: Path, spec: PushSpec, branch: str) -> str | None:
    push_index = spec.argv.index("push")
    argv = (
        *spec.argv[:push_index],
        "ls-remote",
        "--refs",
        "--exit-code",
        "--",
        "origin",
        f"refs/heads/{branch}",
    )
    result = _run_external(argv, cwd=worktree, env=spec.env)
    if (
        result.returncode == 2
        and not result.timed_out
        and not result.output_limit_exceeded
        and not result.cancelled
        and not result.stdout.strip()
    ):
        return None
    if (
        result.returncode != 0
        or result.timed_out
        or result.output_limit_exceeded
        or result.cancelled
    ):
        raise DeliveryGitError("remote-unavailable")
    fields = result.stdout.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        raise DeliveryGitError("remote-invalid")
    if re.fullmatch(r"[a-f0-9]{40}", fields[0]) is None:
        raise DeliveryGitError("remote-invalid")
    return fields[0]


def _run_external(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
) -> BoundedProcessResult:
    try:
        return run_bounded_process(
            list(argv),
            cwd=cwd,
            timeout_seconds=_TIMEOUT,
            max_output_bytes=_OUTPUT_LIMIT,
            env=env,
        )
    except BoundedProcessError:
        raise DeliveryGitError("remote-unavailable") from None


def _git_text(cwd: Path, *args: str) -> str:
    try:
        result = run_bounded_process(
            [_GIT, *args],
            cwd=cwd,
            timeout_seconds=_TIMEOUT,
            max_output_bytes=_OUTPUT_LIMIT,
            env=_ENV,
        )
    except BoundedProcessError:
        raise DeliveryGitError("git-failed") from None
    if result.returncode != 0 or result.timed_out or result.output_limit_exceeded:
        raise DeliveryGitError("git-failed")
    return result.stdout.strip()


def _require_private_regular(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        raise DeliveryGitError("ssh-credentials-invalid") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
    ):
        raise DeliveryGitError("ssh-credentials-invalid")
