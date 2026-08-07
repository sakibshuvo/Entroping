"""Strict filesystem tests for finish-issue replay evidence."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.finish_issue_replay_evidence as replay_evidence  # noqa: E402
from scripts.finish_issue_replay_evidence import (  # noqa: E402
    MAX_BYTES,
    ReadStage,
    ReplayEvidenceError,
    ReplayIdentity,
    advance_replay_evidence,
    main,
    read_replay_evidence,
)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    return root


def _identity(root: Path) -> ReplayIdentity:
    return ReplayIdentity(
        issue=1576,
        pull_request=42,
        expected_head="a" * 40,
        expected_branch="issue/1576-finish-replay",
        merged_at="2026-08-06T16:00:00Z",
        worktree_path=str(root / "issue-worktree"),
    )


def _target(root: Path, identity: ReplayIdentity | None = None) -> Path:
    selected = identity or _identity(root)
    return (
        root
        / ".entroping"
        / "finish-issue-replay"
        / (
            f"issue-{selected.issue}-pr-{selected.pull_request}-"
            f"{selected.expected_head}.json"
        )
    )


def _legacy_target(root: Path) -> Path:
    return root / ".entroping" / "finish-issue-replay" / "issue-1576.json"


def _lock_target(root: Path) -> Path:
    return root / ".entroping" / "finish-issue-replay" / "issue-1576.lock"


def _payload(
    identity: ReplayIdentity, *, stage: str = "worktree-removal-attempted"
) -> dict[str, str | int]:
    return {
        "schema_version": "entroping.finish-issue-replay.v1",
        "issue": identity.issue,
        "pull_request": identity.pull_request,
        "expected_head": identity.expected_head,
        "expected_branch": identity.expected_branch,
        "merged_at": identity.merged_at,
        "worktree_path": identity.worktree_path,
        "stage": stage,
    }


def _write_payload(
    root: Path,
    payload: bytes,
    *,
    target_identity: ReplayIdentity | None = None,
) -> Path:
    target = _target(root, target_identity)
    directory = target.parent
    directory.mkdir(mode=0o700, parents=True)
    os.chmod(directory.parent, 0o700)
    target.write_bytes(payload)
    target.chmod(0o600)
    return target


def _write_legacy_payload(root: Path, payload: bytes) -> Path:
    target = _legacy_target(root)
    target.parent.mkdir(mode=0o700, parents=True)
    os.chmod(target.parent.parent, 0o700)
    target.write_bytes(payload)
    target.chmod(0o600)
    return target


def _args(root: Path, identity: ReplayIdentity, action: str) -> list[str]:
    return [
        action,
        "--repo-root",
        str(root),
        "--issue",
        str(identity.issue),
        "--pull-request",
        str(identity.pull_request),
        "--expected-head",
        identity.expected_head,
        "--expected-branch",
        identity.expected_branch,
        "--merged-at",
        identity.merged_at,
        "--worktree-path",
        identity.worktree_path,
    ]


def test_replay_evidence_creates_owner_only_state_and_reads_it(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    state_directory = root / ".entroping"
    state_directory.mkdir(mode=0o755)
    state_directory.chmod(0o755)

    assert read_replay_evidence(root, identity) == "none"
    assert (
        advance_replay_evidence(root, identity, "worktree-removal-attempted")
        == "worktree-removal-attempted"
    )

    assert read_replay_evidence(root, identity) == "worktree-removal-attempted"
    assert stat.S_IMODE(_target(root).stat().st_mode) == 0o600
    assert stat.S_IMODE(_lock_target(root).stat().st_mode) == 0o600
    assert stat.S_IMODE(_target(root).parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_directory.stat().st_mode) == 0o755


def test_advance_locks_before_read_and_unlocks_after_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    events: list[str] = []
    original_read = replay_evidence._read_from
    original_replace = replay_evidence._atomic_replace

    def _flock(descriptor: int, operation: int) -> None:
        assert descriptor >= 0
        events.append("lock" if operation == fcntl.LOCK_EX else "unlock")

    def _read(directory_fd: int, expected: ReplayIdentity) -> ReadStage:
        events.append("read")
        return original_read(directory_fd, expected)

    def _replace(directory_fd: int, name: str, payload: bytes) -> None:
        events.append("publish")
        original_replace(directory_fd, name, payload)

    monkeypatch.setattr(fcntl, "flock", _flock)
    monkeypatch.setattr(replay_evidence, "_read_from", _read)
    monkeypatch.setattr(replay_evidence, "_atomic_replace", _replace)

    assert (
        advance_replay_evidence(root, identity, "worktree-removal-attempted")
        == "worktree-removal-attempted"
    )
    assert events == ["lock", "read", "publish", "unlock"]


@pytest.mark.parametrize("unsafe_kind", ["symlink", "mode"])
def test_advance_rejects_unsafe_lock_without_mutating_evidence(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    _ = advance_replay_evidence(root, identity, "worktree-removal-attempted")
    evidence_before = _target(root).read_bytes()
    lock = _lock_target(root)
    if unsafe_kind == "symlink":
        outside = tmp_path / "outside.lock"
        outside.write_bytes(b"")
        lock.unlink()
        lock.symlink_to(outside)
    else:
        lock.chmod(0o640)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        advance_replay_evidence(root, identity, "branch-deletion-attempted")

    assert _target(root).read_bytes() == evidence_before


def test_replay_evidence_advances_monotonically_and_idempotently(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    advance_replay_evidence(root, identity, "worktree-removal-attempted")
    initial = _target(root).read_bytes()

    assert (
        advance_replay_evidence(root, identity, "worktree-removal-attempted")
        == "worktree-removal-attempted"
    )
    assert _target(root).read_bytes() == initial
    assert (
        advance_replay_evidence(root, identity, "branch-deletion-attempted")
        == "branch-deletion-attempted"
    )
    branch = _target(root).read_bytes()
    assert (
        advance_replay_evidence(root, identity, "branch-deletion-attempted")
        == "branch-deletion-attempted"
    )
    assert _target(root).read_bytes() == branch

    assert (
        advance_replay_evidence(root, identity, "remote-branch-deletion-attempted")
        == "remote-branch-deletion-attempted"
    )
    remote = _target(root).read_bytes()
    assert (
        advance_replay_evidence(root, identity, "remote-branch-deletion-attempted")
        == "remote-branch-deletion-attempted"
    )
    assert _target(root).read_bytes() == remote

    with pytest.raises(ReplayEvidenceError, match="invalid replay transition"):
        advance_replay_evidence(root, identity, "worktree-removal-attempted")


def test_replay_evidence_rejects_skipping_first_stage(tmp_path: Path) -> None:
    root = _root(tmp_path)

    with pytest.raises(ReplayEvidenceError, match="invalid replay transition"):
        advance_replay_evidence(root, _identity(root), "branch-deletion-attempted")

    assert not _target(root).exists()


def test_replay_evidence_isolates_reclosing_pull_request_identity(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    reclosing = replace(
        identity,
        pull_request=43,
        expected_head="b" * 40,
        expected_branch="issue/1576-reclosing-finish-replay",
        merged_at="2026-08-07T19:00:00Z",
    )
    advance_replay_evidence(root, identity, "worktree-removal-attempted")

    assert read_replay_evidence(root, reclosing) == "none"
    assert (
        advance_replay_evidence(root, reclosing, "worktree-removal-attempted")
        == "worktree-removal-attempted"
    )
    assert read_replay_evidence(root, identity) == "worktree-removal-attempted"
    assert read_replay_evidence(root, reclosing) == "worktree-removal-attempted"


def test_replay_evidence_rejects_identity_conflict_at_exact_identity_path(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    reclosing = replace(identity, pull_request=43, expected_head="b" * 40)
    _write_payload(
        root,
        json.dumps(_payload(identity), sort_keys=True, separators=(",", ":")).encode(),
        target_identity=reclosing,
    )

    with pytest.raises(ReplayEvidenceError, match="conflicting replay evidence"):
        read_replay_evidence(root, reclosing)


def test_replay_evidence_reads_and_migrates_exact_legacy_identity(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    _write_legacy_payload(
        root,
        json.dumps(_payload(identity), sort_keys=True, separators=(",", ":")).encode(),
    )

    assert read_replay_evidence(root, identity) == "worktree-removal-attempted"
    assert (
        advance_replay_evidence(root, identity, "branch-deletion-attempted")
        == "branch-deletion-attempted"
    )
    assert _legacy_target(root).exists()
    assert _target(root, identity).exists()
    assert read_replay_evidence(root, identity) == "branch-deletion-attempted"


def test_replay_evidence_preserves_but_ignores_different_legacy_identity(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    reclosing = replace(
        identity,
        pull_request=43,
        expected_head="b" * 40,
        expected_branch="issue/1576-reclosing-finish-replay",
        merged_at="2026-08-07T19:00:00Z",
    )
    legacy = _write_legacy_payload(
        root,
        json.dumps(_payload(identity), sort_keys=True, separators=(",", ":")).encode(),
    )

    assert read_replay_evidence(root, reclosing) == "none"
    assert legacy.exists()


def test_replay_evidence_rejects_malformed_legacy_for_reclosing_identity(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    reclosing = replace(_identity(root), pull_request=43, expected_head="b" * 40)
    _write_legacy_payload(root, b"not-json")

    with pytest.raises(ReplayEvidenceError, match="invalid replay evidence"):
        read_replay_evidence(root, reclosing)


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({"schema_version": "entroping.finish-issue-replay.v1"}).encode(),
        b'{"schema_version":"entroping.finish-issue-replay.v1","schema_version":"entroping.finish-issue-replay.v1"}',
    ],
)
def test_replay_evidence_rejects_malformed_payload(tmp_path: Path, payload: bytes) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    _write_payload(root, payload)

    with pytest.raises(ReplayEvidenceError, match="invalid replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_unknown_key(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    payload = _payload(identity)
    payload["unexpected"] = "value"
    _write_payload(root, json.dumps(payload).encode())

    with pytest.raises(ReplayEvidenceError, match="invalid replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_oversize_payload(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    _write_payload(root, b"x" * (MAX_BYTES + 1))

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_unsafe_file_mode(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    target = _write_payload(root, json.dumps(_payload(identity)).encode())
    target.chmod(0o640)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_symlink_file(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_payload(identity)), encoding="utf-8")
    _target(root).parent.mkdir(mode=0o700, parents=True)
    os.chmod(_target(root).parent.parent, 0o700)
    _target(root).symlink_to(outside)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_symlink_directory(tmp_path: Path) -> None:
    root = _root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (root / ".entroping").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, _identity(root))


@pytest.mark.parametrize(
    ("directory_name", "mode"),
    [("repo", 0o775), ("repo", 0o777), (".entroping", 0o775), (".entroping", 0o777)],
)
def test_replay_evidence_rejects_writable_ancestor_directory(
    tmp_path: Path, directory_name: str, mode: int
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    advance_replay_evidence(root, identity, "worktree-removal-attempted")
    directory = root if directory_name == "repo" else root / directory_name
    directory.chmod(mode)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_evidence_rejects_nonprivate_managed_directory(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)
    advance_replay_evidence(root, identity, "worktree-removal-attempted")
    _target(root).parent.chmod(0o750)

    with pytest.raises(ReplayEvidenceError, match="unsafe replay evidence"):
        read_replay_evidence(root, identity)


def test_replay_identity_rejects_invalid_values(tmp_path: Path) -> None:
    root = _root(tmp_path)
    identity = _identity(root)

    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, issue=0)
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, expected_head="A" * 40)
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, expected_branch="bad..branch")
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, worktree_path="relative/path")
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, merged_at="2026-08-06T16:00:00+01:00")
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, merged_at="2026-08-06T16:00:00.000000Z")
    with pytest.raises(ReplayEvidenceError, match="invalid replay identity"):
        replace(identity, merged_at="not-a-timestamp")


def test_replay_evidence_cli_uses_named_identity_and_fixed_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    identity = _identity(root)

    assert main(_args(root, identity, "read")) == 0
    assert capsys.readouterr() == ("none\n", "")
    assert main([*_args(root, identity, "advance"), "--stage", "worktree-removal-attempted"]) == 0
    assert capsys.readouterr() == ("worktree-removal-attempted\n", "")
    assert main([*_args(root, replace(identity, pull_request=43), "read")]) == 0
    assert capsys.readouterr() == ("none\n", "")
