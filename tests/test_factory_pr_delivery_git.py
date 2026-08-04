from __future__ import annotations

import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from factory_orchestration_test_support import git
from factory_pr_delivery_test_support import (
    accepted_artifacts,
    private_ssh_home,
    raw_git,
    write_delivery_request,
)

from scripts.bounded_process import BoundedProcessResult

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_pr_delivery_ssh as delivery_ssh  # noqa: E402
from scripts.factory_pr_delivery_git import (  # noqa: E402
    DeliveryGitError,
    build_push_spec,
    commit_exact_diff,
    push_exact_commit,
)
from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_scheduler_storage import writable_connection  # noqa: E402


def _envelope(tmp_path: Path):
    main, worktree, payload = accepted_artifacts(tmp_path)
    path = tmp_path / "private/delivery-request.json"
    write_delivery_request(path, payload)
    return main, worktree, load_delivery_envelope(path)


def test_accepted_diff_becomes_one_exact_controller_commit(tmp_path: Path) -> None:
    # Given: one accepted unstaged diff whose base, digest, manifest, and paths are bound.
    main, worktree, envelope = _envelope(tmp_path)
    base = envelope.orchestration_receipt.result_head

    # When: the controller commits at its fixed timestamp and identity.
    result = commit_exact_diff(
        main,
        envelope,
        committed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
    )

    # Then: the exact accepted bytes form one parented commit and leave no residue.
    assert git(worktree, "rev-list", "--parents", "-n", "1", result.committed_head) == (
        f"{result.committed_head} {base}"
    )
    assert git(worktree, "show", "-s", "--format=%s", result.committed_head) == (
        "docs(factory): deliver issue #1574"
    )
    assert git(worktree, "show", "-s", "--format=%an <%ae>", result.committed_head) == (
        "Entroping Factory Controller <factory-controller@entroping.invalid>"
    )
    assert raw_git(
        worktree,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        base,
        result.committed_head,
        "--",
    ) == raw_git(
        worktree,
        "show",
        "--format=",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-renames",
        result.committed_head,
        "--",
    )
    assert git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all") == ""
    assert git(main, "rev-parse", "HEAD") == base


def test_commit_uses_stored_authority_after_live_lease_expiry(tmp_path: Path) -> None:
    # Given: accepted work whose live scheduler lease expired after execution settled.
    main, worktree, envelope = _envelope(tmp_path)

    # When: delivery runs after the lease expiry boundary.
    result = commit_exact_diff(
        main,
        envelope,
        committed_at=datetime(2026, 8, 3, 14, 0, tzinfo=UTC),
    )

    # Then: stored assignment and execution authority, not the live lease, governs delivery.
    assert git(worktree, "rev-parse", "HEAD") == result.committed_head


def test_commit_rejects_scheduler_execution_drift_before_mutation(tmp_path: Path) -> None:
    # Given: accepted work whose stored execution evidence was changed after acceptance.
    main, worktree, envelope = _envelope(tmp_path)
    with writable_connection(main, initialized_at="2026-08-03T12:30:00+00:00") as connection:
        _ = connection.execute(
            "UPDATE scheduler_execution_state SET evidence_digest = ? WHERE assignment_id = ?",
            ("e" * 64, envelope.orchestration_request.assignment_id),
        )
    before = git(worktree, "rev-parse", "HEAD")

    # When/Then: scheduler drift is rejected before any Git mutation.
    with pytest.raises(DeliveryGitError) as exc_info:
        commit_exact_diff(main, envelope, committed_at=datetime.now(UTC))
    assert exc_info.value.code == "authority-mismatch"
    assert git(worktree, "rev-parse", "HEAD") == before


@pytest.mark.parametrize("drift", ["untracked", "staged", "head", "branch", "operation"])
def test_precommit_drift_blocks_before_ref_mutation(tmp_path: Path, drift: str) -> None:
    # Given: accepted evidence followed by one unauthorized repository-state change.
    main, worktree, envelope = _envelope(tmp_path)
    base = envelope.orchestration_receipt.result_head
    if drift == "untracked":
        (worktree / "foreign.txt").write_text("foreign", encoding="utf-8")
    elif drift == "staged":
        git(worktree, "add", "docs/user/guide.md")
    elif drift == "head":
        git(worktree, "commit", "-am", "foreign")
    elif drift == "branch":
        git(worktree, "checkout", "--detach")
    else:
        git_dir = Path(git(worktree, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = worktree / git_dir
        (git_dir / "MERGE_HEAD").write_text(str(base), encoding="ascii")

    # When/Then: no delivery commit or branch repair occurs.
    before = git(worktree, "rev-parse", "HEAD")
    with pytest.raises(DeliveryGitError) as exc_info:
        commit_exact_diff(main, envelope, committed_at=datetime.now(UTC))
    assert exc_info.value.code == "authority-mismatch"
    assert git(worktree, "rev-parse", "HEAD") == before


def test_commit_bypasses_hooks_signing_editors_templates_aliases_and_ambient_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: hostile commit configuration and ambient Git variables.
    main, worktree, envelope = _envelope(tmp_path)
    sentinel = tmp_path / "executed"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {sentinel}\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    git(worktree, "config", "core.hooksPath", str(hooks))
    git(worktree, "config", "commit.gpgsign", "true")
    monkeypatch.setenv("GIT_EDITOR", f"touch {sentinel}")
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "alias.commit")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", f"!touch {sentinel}")

    # When: exact plumbing creates the authorized revision.
    _ = commit_exact_diff(main, envelope, committed_at=datetime.now(UTC))

    # Then: no configurable porcelain surface executed.
    assert not sentinel.exists()


def test_push_spec_is_explicit_config_free_and_credential_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: canonical fetch/push URLs and private Ed25519 inputs.
    _main, worktree, envelope = _envelope(tmp_path)
    git(worktree, "remote", "add", "origin", "git@github.com:sakibshuvo/Entroping.git")
    home = private_ssh_home(tmp_path)
    monkeypatch.setattr(
        delivery_ssh.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir=str(home)),
    )

    # When: the push boundary constructs its single permitted invocation.
    spec = build_push_spec(
        worktree,
        branch=envelope.orchestration_request.branch,
        committed_head="a" * 40,
    )

    # Then: source/destination, binary, SSH hardening, and scrubbed environment are fixed.
    assert spec.argv[0] == "/usr/bin/git"
    assert spec.argv[-3:] == (
        "--",
        "origin",
        f"{'a' * 40}:refs/heads/{envelope.orchestration_request.branch}",
    )
    assert "--force" not in spec.argv
    assert spec.env == {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    }
    assert spec.ssh_argv[0] == "/usr/bin/ssh"
    assert str(home / ".ssh/id_ed25519") in spec.ssh_argv
    assert stat.S_IMODE((home / ".ssh/known_hosts").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://github.com/sakibshuvo/Entroping.git", "remote-invalid"),
        ("git@github.com:other/Entroping.git", "remote-invalid"),
        ("ssh://token@github.com/sakibshuvo/Entroping.git", "remote-invalid"),
    ],
)
def test_push_spec_rejects_wrong_or_credential_bearing_urls(
    tmp_path: Path, url: str, code: str
) -> None:
    _main, worktree, envelope = _envelope(tmp_path)
    git(worktree, "remote", "add", "origin", url)
    with pytest.raises(DeliveryGitError) as exc_info:
        build_push_spec(
            worktree,
            branch=envelope.orchestration_request.branch,
            committed_head="a" * 40,
        )
    assert exc_info.value.code == code


@pytest.mark.parametrize(
    ("heads", "returncode", "timed_out", "expected"),
    [
        (("a" * 40,), 0, False, "replay"),
        ((None, "a" * 40), 0, False, "pushed"),
        ((None, "a" * 40), 1, False, "pushed"),
        ((None, None), 1, False, "push-rejected"),
        ((None, None), 1, True, "push-uncertain"),
        (("b" * 40,), 0, False, "remote-diverged"),
    ],
)
def test_push_replay_response_loss_timeout_and_divergence_are_classified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    heads: tuple[str | None, ...],
    returncode: int,
    timed_out: bool,
    expected: str,
) -> None:
    # Given: an explicit canonical remote and a controlled wire observation sequence.
    _main, worktree, envelope = _envelope(tmp_path)
    git(worktree, "remote", "add", "origin", "git@github.com:sakibshuvo/Entroping.git")
    home = private_ssh_home(tmp_path)
    monkeypatch.setattr(
        delivery_ssh.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir=str(home)),
    )
    observed = iter(heads)
    monkeypatch.setattr(delivery_ssh, "_remote_head", lambda *_args: next(observed))
    monkeypatch.setattr(
        delivery_ssh,
        "_run_external",
        lambda *_args, **_kwargs: BoundedProcessResult(
            args=("/usr/bin/git", "push"),
            returncode=returncode,
            stdout="attacker-controlled output",
            stderr="credential-like output",
            timed_out=timed_out,
            output_limit_exceeded=False,
        ),
    )

    # When/Then: only exact remote identity advances; failures expose fixed codes only.
    if expected in {"replay", "pushed"}:
        result = push_exact_commit(
            worktree,
            branch=envelope.orchestration_request.branch,
            committed_head="a" * 40,
        )
        assert result.state == expected
        assert result.remote_head == "a" * 40
    else:
        with pytest.raises(DeliveryGitError) as exc_info:
            push_exact_commit(
                worktree,
                branch=envelope.orchestration_request.branch,
                committed_head="a" * 40,
            )
        assert exc_info.value.code == expected
        assert "output" not in str(exc_info.value)
