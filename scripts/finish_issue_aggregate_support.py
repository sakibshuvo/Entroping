"""Bounded local Git and file operations for aggregate finish evidence."""

from __future__ import annotations

import os
import re
import selectors
import signal
import stat
import subprocess  # nosec B404
import time
from contextlib import suppress
from io import IOBase
from pathlib import Path
from typing import Final, cast

MAX_MANIFEST_BYTES: Final = 1_048_576
MAX_GIT_OUTPUT_BYTES: Final = 8_388_608
MAX_PATCH_BYTES: Final = 8_388_608
_CHUNK_BYTES: Final = 65_536
_COMMAND_TIMEOUT_SECONDS: Final = 30.0


class AggregateEvidenceError(RuntimeError):
    """Report one fixed aggregate-evidence failure."""


def _close_stream(value: object) -> None:
    if isinstance(value, int):
        with suppress(OSError):
            os.close(value)
    elif isinstance(value, IOBase):
        with suppress(OSError):
            value.close()


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        with suppress(OSError):
            process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)
        with suppress(OSError):
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=1)


def _run_bytes(
    command: list[str],
    max_bytes: int,
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run one argument-array command with bounded streaming pipes."""
    if max_bytes < 1 or (input_bytes is not None and len(input_bytes) > MAX_PATCH_BYTES):
        raise AggregateEvidenceError("bounded evidence command exceeded limit")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        raise AggregateEvidenceError("bounded evidence command failed") from exc
    selector = selectors.DefaultSelector()
    outputs: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    pending = memoryview(input_bytes) if input_bytes is not None else None
    completed = False
    try:
        if process.stdout is None or process.stderr is None:
            raise AggregateEvidenceError("bounded evidence command failed")
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        if process.stdin is not None:
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
                process.stdin = None
        deadline = time.monotonic() + _COMMAND_TIMEOUT_SECONDS
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AggregateEvidenceError("bounded evidence command timed out")
            events = selector.select(remaining)
            if not events:
                raise AggregateEvidenceError("bounded evidence command timed out")
            for key, _mask in events:
                if key.data == "stdin":
                    if pending is None:
                        raise AggregateEvidenceError("bounded evidence command failed")
                    try:
                        written = os.write(key.fd, pending[:_CHUNK_BYTES])
                    except BrokenPipeError:
                        written = len(pending)
                    pending = pending[written:]
                    if not pending:
                        selector.unregister(key.fileobj)
                        _close_stream(key.fileobj)
                        process.stdin = None
                    continue
                stream_name = cast(str, key.data)
                chunk = os.read(
                    key.fd,
                    min(_CHUNK_BYTES, max_bytes - len(outputs[stream_name]) + 1),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    _close_stream(key.fileobj)
                    continue
                outputs[stream_name].extend(chunk)
                if len(outputs[stream_name]) > max_bytes:
                    raise AggregateEvidenceError("bounded evidence command exceeded output limit")
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired as exc:
            raise AggregateEvidenceError("bounded evidence command timed out") from exc
        completed = True
        return subprocess.CompletedProcess(
            command,
            returncode,
            bytes(outputs["stdout"]),
            bytes(outputs["stderr"]),
        )
    except AggregateEvidenceError:
        raise
    except (OSError, ValueError) as exc:
        raise AggregateEvidenceError("bounded evidence command failed") from exc
    finally:
        selector.close()
        if not completed:
            _stop_process(process)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                with suppress(OSError):
                    stream.close()


def run(command: list[str], max_bytes: int) -> subprocess.CompletedProcess[str]:
    """Run one bounded, non-shell UTF-8 evidence command."""
    result = _run_bytes(command, max_bytes)
    try:
        stdout = result.stdout.decode("utf-8")
        stderr = result.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AggregateEvidenceError("bounded evidence command returned invalid text") from exc
    return subprocess.CompletedProcess(command, result.returncode, stdout, stderr)


def git(root: Path, *args: str) -> str:
    """Run a bounded Git read and return trimmed UTF-8 output."""
    result = run(["git", "-C", str(root), *args], MAX_GIT_OUTPUT_BYTES)
    if result.returncode != 0:
        raise AggregateEvidenceError("git evidence lookup failed")
    return result.stdout.strip()


def git_ok(root: Path, *args: str) -> bool:
    """Return whether a bounded Git predicate succeeds."""
    try:
        return run(["git", "-C", str(root), *args], 4096).returncode == 0
    except AggregateEvidenceError:
        return False


def read_tracked_manifest(root: Path, raw_path: str) -> bytes:
    """Read one committed regular manifest without following symlinks."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    absolute = path.absolute()
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = absolute.resolve(strict=True)
        relative = resolved_path.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AggregateEvidenceError("manifest path is invalid or untracked") from exc
    if resolved_path != absolute or not relative.parts:
        raise AggregateEvidenceError("manifest path is invalid or untracked")
    relative_name = relative.as_posix()
    listing = git(root, "ls-files", "--stage", "--", relative_name)
    rows = listing.splitlines()
    if (
        len(rows) != 1
        or not rows[0].startswith("100644 ")
        or not rows[0].endswith(f"\t{relative_name}")
        or not git_ok(root, "cat-file", "-e", f"HEAD:{relative_name}")
    ):
        raise AggregateEvidenceError("manifest path is invalid or untracked")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise AggregateEvidenceError("manifest path is invalid or unsafe") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_size > MAX_MANIFEST_BYTES
        ):
            raise AggregateEvidenceError("manifest path is invalid or unsafe")
        payload = os.read(descriptor, MAX_MANIFEST_BYTES + 1)
        if len(payload) != metadata.st_size or len(payload) > MAX_MANIFEST_BYTES:
            raise AggregateEvidenceError("manifest is oversized or changed")
        return payload
    except OSError as exc:
        raise AggregateEvidenceError("manifest path is invalid or unsafe") from exc
    finally:
        os.close(descriptor)


def patch_id(root: Path, commit: str) -> str:
    """Compute one stable patch identity from a committed Git object."""
    command = [
        "git",
        "-C",
        str(root),
        "diff-tree",
        "--root",
        "--no-commit-id",
        "-p",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        commit,
    ]
    try:
        patch_result = _run_bytes(command, MAX_PATCH_BYTES)
    except AggregateEvidenceError as exc:
        raise AggregateEvidenceError("patch evidence lookup failed") from exc
    if patch_result.returncode != 0:
        raise AggregateEvidenceError("patch evidence lookup failed")
    patch = patch_result.stdout
    try:
        result = _run_bytes(
            ["git", "patch-id", "--stable"],
            256,
            input_bytes=patch,
        )
    except AggregateEvidenceError as exc:
        raise AggregateEvidenceError("patch evidence lookup failed") from exc
    if result.returncode != 0:
        raise AggregateEvidenceError("patch evidence lookup failed")
    try:
        value = result.stdout.decode("ascii").split()[0]
    except (UnicodeDecodeError, IndexError) as exc:
        raise AggregateEvidenceError("patch evidence lookup failed") from exc
    if re.fullmatch(r"[a-f0-9]{40}", value) is None:
        raise AggregateEvidenceError("patch evidence lookup failed")
    return value


def repository_slug(root: Path) -> str:
    """Return the normalized GitHub origin slug."""
    remote = git(root, "remote", "get-url", "origin")
    if remote.startswith("git@github.com:"):
        slug = remote.removeprefix("git@github.com:")
    elif remote.startswith("https://github.com/"):
        slug = remote.removeprefix("https://github.com/")
    else:
        raise AggregateEvidenceError("repository identity is invalid")
    return slug.removesuffix(".git").rstrip("/")
