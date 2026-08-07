"""Persist strict finish replay evidence through an owner-only fd boundary."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, assert_never

SCHEMA: Final = "entroping.finish-issue-replay.v1"
MAX_BYTES: Final = 4096
Stage = Literal[
    "worktree-removal-attempted",
    "branch-deletion-attempted",
    "remote-branch-deletion-attempted",
]
ReadStage = Literal[
    "none",
    "worktree-removal-attempted",
    "branch-deletion-attempted",
    "remote-branch-deletion-attempted",
]
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
_HEAD: Final = re.compile(r"[0-9a-f]{40}\Z")
_EXACT_KEYS: Final = {
    "schema_version",
    "issue",
    "pull_request",
    "expected_head",
    "expected_branch",
    "merged_at",
    "worktree_path",
    "stage",
}
_DIRECTORY_FLAGS: Final = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)


class ReplayEvidenceError(RuntimeError):
    """Report invalid or unsafe strict-finish replay evidence."""


@dataclass(frozen=True, slots=True)
class ReplayIdentity:
    """Exact live identity bound to one strict finish cleanup."""

    issue: int
    pull_request: int
    expected_head: str
    expected_branch: str
    merged_at: str
    worktree_path: str

    def __post_init__(self) -> None:
        if type(self.issue) is not int or self.issue < 1:
            raise ReplayEvidenceError("invalid replay identity")
        if type(self.pull_request) is not int or self.pull_request < 1:
            raise ReplayEvidenceError("invalid replay identity")
        if _HEAD.fullmatch(self.expected_head) is None:
            raise ReplayEvidenceError("invalid replay identity")
        if not _valid_branch(self.expected_branch):
            raise ReplayEvidenceError("invalid replay identity")
        if not _canonical_utc_timestamp(self.merged_at):
            raise ReplayEvidenceError("invalid replay identity")
        if not _canonical_absolute(self.worktree_path):
            raise ReplayEvidenceError("invalid replay identity")


def _bounded_text(value: str, *, maximum: int) -> bool:
    return (
        bool(value)
        and len(value.encode("utf-8")) <= maximum
        and value == value.strip()
        and all(ord(character) >= 32 and character != "\x7f" for character in value)
    )


def _valid_branch(value: str) -> bool:
    forbidden = " ~^:?*[\\"
    components = value.split("/")
    return (
        _bounded_text(value, maximum=160)
        and value != "@"
        and not value.startswith("-")
        and ".." not in value
        and "@{" not in value
        and not value.endswith(("/", "."))
        and all(
            component
            and not component.startswith(".")
            and not component.endswith(".lock")
            and not any(character in forbidden for character in component)
            for component in components
        )
    )


def _canonical_absolute(value: str) -> bool:
    return (
        _bounded_text(value, maximum=4096)
        and os.path.isabs(value)
        and os.path.normpath(value) == value
    )


def _canonical_utc_timestamp(value: str) -> bool:
    if not _bounded_text(value, maximum=256) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        return False
    return parsed.isoformat().replace("+00:00", "Z") == value


def _require_directory(descriptor: int, *, managed: bool) -> None:
    metadata = os.fstat(descriptor)
    mode = stat.S_IMODE(metadata.st_mode)
    safe_mode = mode == 0o700 if managed else mode & 0o022 == 0
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or not safe_mode:
        raise ReplayEvidenceError("unsafe replay evidence")


def _open_root(root: Path) -> int:
    root_text = os.fspath(root)
    if not _canonical_absolute(root_text):
        raise ReplayEvidenceError("invalid replay root")
    try:
        descriptor = os.open(root_text, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ReplayEvidenceError("unsafe replay evidence") from exc
    try:
        _require_directory(descriptor, managed=False)
    except ReplayEvidenceError:
        os.close(descriptor)
        raise
    return descriptor


def _open_child(parent: int, name: str, *, create: bool, managed: bool) -> int | None:
    if create:
        with suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReplayEvidenceError("unsafe replay evidence") from exc
    try:
        _require_directory(descriptor, managed=managed)
    except ReplayEvidenceError:
        os.close(descriptor)
        raise
    return descriptor


@contextmanager
def _evidence_directory(root: Path, *, create: bool) -> Iterator[int | None]:
    root_fd = _open_root(root)
    state_fd = evidence_fd = None
    try:
        state_fd = _open_child(root_fd, ".entroping", create=create, managed=False)
        if state_fd is None:
            yield None
            return
        evidence_fd = _open_child(
            state_fd,
            "finish-issue-replay",
            create=create,
            managed=True,
        )
        yield evidence_fd
    finally:
        if evidence_fd is not None:
            os.close(evidence_fd)
        if state_fd is not None:
            os.close(state_fd)
        os.close(root_fd)


def _file_name(identity: ReplayIdentity) -> str:
    return (
        f"issue-{identity.issue}-pr-{identity.pull_request}-"
        f"{identity.expected_head}.json"
    )


def _legacy_file_name(identity: ReplayIdentity) -> str:
    return f"issue-{identity.issue}.json"


def _require_safe_target(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ReplayEvidenceError("unsafe replay evidence")
    return metadata


def _read_payload(directory_fd: int, name: str) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ReplayEvidenceError("unsafe replay evidence") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_BYTES
        ):
            raise ReplayEvidenceError("unsafe replay evidence")
        payload = bytearray()
        while len(payload) < metadata.st_size:
            chunk = os.read(descriptor, metadata.st_size - len(payload))
            if not chunk:
                raise ReplayEvidenceError("invalid replay evidence")
            payload.extend(chunk)
        if os.read(descriptor, 1) or os.fstat(descriptor).st_size != metadata.st_size:
            raise ReplayEvidenceError("invalid replay evidence")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _json_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {}
    for key, item in pairs:
        if key in value:
            raise ReplayEvidenceError("invalid replay evidence")
        value[key] = item
    return value


def _positive_integer(value: JsonValue) -> int:
    if type(value) is not int or value < 1:
        raise ReplayEvidenceError("invalid replay evidence")
    return value


def _string(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise ReplayEvidenceError("invalid replay evidence")
    return value


def _stage(value: JsonValue) -> Stage:
    match value:
        case "worktree-removal-attempted":
            return value
        case "branch-deletion-attempted":
            return value
        case "remote-branch-deletion-attempted":
            return value
        case _:
            raise ReplayEvidenceError("invalid replay evidence")


def _decode(
    payload: bytes,
    expected: ReplayIdentity,
    *,
    allow_other_identity: bool = False,
) -> ReadStage:
    try:
        decoded: JsonValue = json.loads(payload.decode("utf-8"), object_pairs_hook=_json_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayEvidenceError("invalid replay evidence") from exc
    if not isinstance(decoded, dict) or set(decoded) != _EXACT_KEYS:
        raise ReplayEvidenceError("invalid replay evidence")
    if decoded["schema_version"] != SCHEMA:
        raise ReplayEvidenceError("invalid replay evidence")
    actual = ReplayIdentity(
        issue=_positive_integer(decoded["issue"]),
        pull_request=_positive_integer(decoded["pull_request"]),
        expected_head=_string(decoded["expected_head"]),
        expected_branch=_string(decoded["expected_branch"]),
        merged_at=_string(decoded["merged_at"]),
        worktree_path=_string(decoded["worktree_path"]),
    )
    if actual != expected:
        if allow_other_identity:
            return "none"
        raise ReplayEvidenceError("conflicting replay evidence")
    return _stage(decoded["stage"])


def _read_from(directory_fd: int, identity: ReplayIdentity) -> ReadStage:
    payload = _read_payload(directory_fd, _file_name(identity))
    if payload is not None:
        return _decode(payload, identity)
    legacy_payload = _read_payload(directory_fd, _legacy_file_name(identity))
    if legacy_payload is None:
        return "none"
    return _decode(legacy_payload, identity, allow_other_identity=True)


def read_replay_evidence(root: Path, identity: ReplayIdentity) -> ReadStage:
    """Read exact replay evidence without creating state."""
    with _evidence_directory(root, create=False) as directory_fd:
        if directory_fd is None:
            return "none"
        return _read_from(directory_fd, identity)


def _encode(identity: ReplayIdentity, stage: Stage) -> bytes:
    payload = {
        "schema_version": SCHEMA,
        "issue": identity.issue,
        "pull_request": identity.pull_request,
        "expected_head": identity.expected_head,
        "expected_branch": identity.expected_branch,
        "merged_at": identity.merged_at,
        "worktree_path": identity.worktree_path,
        "stage": stage,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_BYTES:
        raise ReplayEvidenceError("invalid replay evidence")
    return encoded


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written < 1:
            raise ReplayEvidenceError("replay evidence write failed")
        offset += written


def _atomic_replace(directory_fd: int, name: str, payload: bytes) -> None:
    _require_safe_target(directory_fd, name)
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _require_safe_target(directory_fd, name)
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)


def _open_issue_lock(directory_fd: int, identity: ReplayIdentity) -> int:
    name = f"issue-{identity.issue}.lock"
    common_flags = (
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    created = False
    try:
        descriptor = os.open(
            name,
            common_flags | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        created = True
    except FileExistsError:
        try:
            descriptor = os.open(name, common_flags, dir_fd=directory_fd)
        except OSError as exc:
            raise ReplayEvidenceError("unsafe replay evidence") from exc
    try:
        if created:
            os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ReplayEvidenceError("unsafe replay evidence")
    except (OSError, ReplayEvidenceError):
        os.close(descriptor)
        raise
    return descriptor


@contextmanager
def _issue_lock(directory_fd: int, identity: ReplayIdentity) -> Iterator[None]:
    descriptor = _open_issue_lock(directory_fd, identity)
    locked = False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _allows(current: ReadStage, requested: Stage) -> bool:
    match current:
        case "none":
            return requested == "worktree-removal-attempted"
        case "worktree-removal-attempted":
            return requested in {"worktree-removal-attempted", "branch-deletion-attempted"}
        case "branch-deletion-attempted":
            return requested in {
                "branch-deletion-attempted",
                "remote-branch-deletion-attempted",
            }
        case "remote-branch-deletion-attempted":
            return requested == "remote-branch-deletion-attempted"
        case unreachable:
            assert_never(unreachable)


def advance_replay_evidence(root: Path, identity: ReplayIdentity, stage: Stage) -> Stage:
    """Advance replay evidence monotonically and atomically."""
    with _evidence_directory(root, create=True) as directory_fd:
        if directory_fd is None:
            raise ReplayEvidenceError("unsafe replay evidence")
        with _issue_lock(directory_fd, identity):
            current = _read_from(directory_fd, identity)
            if not _allows(current, stage):
                raise ReplayEvidenceError("invalid replay transition")
            if current == stage:
                return stage
            _atomic_replace(directory_fd, _file_name(identity), _encode(identity, stage))
            return stage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("read", "advance"))
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument("--pull-request", required=True, type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--merged-at", required=True)
    parser.add_argument("--worktree-path", required=True)
    parser.add_argument(
        "--stage",
        choices=(
            "worktree-removal-attempted",
            "branch-deletion-attempted",
            "remote-branch-deletion-attempted",
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Read or advance replay evidence for the strict finish shell boundary."""
    args = _parser().parse_args(argv)
    try:
        identity = ReplayIdentity(
            issue=args.issue,
            pull_request=args.pull_request,
            expected_head=args.expected_head,
            expected_branch=args.expected_branch,
            merged_at=args.merged_at,
            worktree_path=args.worktree_path,
        )
        if args.action == "read":
            result: ReadStage = read_replay_evidence(args.repo_root, identity)
        else:
            if args.stage is None:
                raise ReplayEvidenceError("invalid replay stage")
            result = advance_replay_evidence(args.repo_root, identity, args.stage)
    except (ReplayEvidenceError, OSError, json.JSONDecodeError):
        print("finish-issue replay evidence error", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
