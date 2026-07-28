from __future__ import annotations

import argparse
import fcntl
import os
import stat
import sys
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from entroping.models import secrets
from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_retention_fs import RetentionFsError, open_relative_directory

DEFAULT_TIMEOUT_SECONDS = 3_600.0
DEFAULT_OUTPUT_BYTES = 262_144
DEFAULT_LOG_BYTES = 4_194_304
LOCK_NAME = ".factory-tick.lock"


class TickRunnerError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return run_tick(
            repo_root=Path.cwd(),
            factoryctl=cast(Path, args.factoryctl),
            log_directory=cast(Path, args.log_directory),
            timeout_seconds=cast(float, args.timeout_seconds),
            max_output_bytes=cast(int, args.max_output_bytes),
            max_log_bytes=cast(int, args.max_log_bytes),
        )
    except TickRunnerError as exc:
        print(f"factory_tick_runner: {exc}", file=sys.stderr)
        return 2


def run_tick(
    *,
    repo_root: Path,
    factoryctl: Path,
    log_directory: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    max_log_bytes: int,
) -> int:
    root = _validated_directory(repo_root, "working directory")
    executable = _validated_executable(factoryctl)
    expected_log_directory = root / ".entroping" / "factory-logs"
    if log_directory != expected_log_directory:
        raise TickRunnerError("log directory must be .entroping/factory-logs")
    if timeout_seconds <= 0 or max_output_bytes <= 0 or max_log_bytes <= 0:
        raise TickRunnerError("tick limits must be positive")
    if max_output_bytes > max_log_bytes:
        raise TickRunnerError("output limit must not exceed log limit")

    try:
        with open_relative_directory(root, (".entroping",), create=True) as state_fd:
            retention_lock_fd = _open_regular(state_fd, "retention.lock", append=False)
            try:
                fcntl.flock(retention_lock_fd, fcntl.LOCK_SH)
                returncode = _run_tick_locked(
                    root=root,
                    executable=executable,
                    timeout_seconds=timeout_seconds,
                    max_output_bytes=max_output_bytes,
                    max_log_bytes=max_log_bytes,
                )
            finally:
                os.close(retention_lock_fd)
    except (BoundedProcessError, OSError, RetentionFsError) as exc:
        raise TickRunnerError("bounded tick execution failed") from exc
    return returncode


def _run_tick_locked(
    *,
    root: Path,
    executable: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    max_log_bytes: int,
) -> int:
    with open_relative_directory(
        root,
        (".entroping", "factory-logs"),
        create=True,
    ) as log_fd:
        lock_fd = _open_regular(log_fd, LOCK_NAME, append=False)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            result = run_bounded_process(
                [executable, "tick"],
                cwd=root,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
            )
            stderr = result.stderr
            if result.timed_out:
                stderr = f"Factory tick timed out after {timeout_seconds} seconds.\n{stderr}"
            elif result.output_limit_exceeded:
                stderr = (
                    f"Factory tick exceeded the {max_output_bytes}-byte output limit.\n"
                    f"{stderr}"
                )
            stdout = _safe_persisted_output(result.stdout)
            stderr = _safe_persisted_output(stderr)
            _append_bounded(log_fd, "factory-tick.out.log", stdout, max_log_bytes)
            _append_bounded(
                log_fd,
                "factory-tick.err.log",
                _bounded_text(stderr, max_log_bytes),
                max_log_bytes,
            )
            os.fsync(log_fd)
        finally:
            os.close(lock_fd)

    if result.timed_out:
        return 124
    if result.output_limit_exceeded:
        return 1
    return result.returncode if result.returncode >= 0 else 1


def _safe_persisted_output(text: str) -> str:
    redacted = secrets.redact_secret_like_values(text)
    if secrets.contains_secret_like_value(redacted):
        raise TickRunnerError("captured tick output remained secret-like after redaction")
    return redacted


def _append_bounded(directory_fd: int, name: str, text: str, limit: int) -> None:
    payload = text.encode("utf-8")
    if len(payload) > limit:
        raise TickRunnerError("captured tick output exceeded its persistence limit")
    _rotate_if_needed(directory_fd, name, len(payload), limit)
    descriptor = _open_regular(directory_fd, name, append=True)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _bounded_text(text: str, limit: int) -> str:
    payload = text.encode("utf-8")
    if len(payload) <= limit:
        return text
    marker = b"[output truncated: byte limit exceeded]\n"
    if len(marker) >= limit:
        return marker[:limit].decode("utf-8", errors="ignore")
    head = payload[: limit - len(marker)].decode("utf-8", errors="ignore")
    return f"{head}{marker.decode('ascii')}"


def _rotate_if_needed(directory_fd: int, name: str, incoming: int, limit: int) -> None:
    metadata = _regular_metadata(directory_fd, name)
    if metadata is None or metadata.st_size + incoming <= limit:
        return
    rotated_name = f"{name}.1"
    rotated = _regular_metadata(directory_fd, rotated_name)
    if rotated is not None:
        os.unlink(rotated_name, dir_fd=directory_fd)
    if metadata.st_size <= limit:
        os.rename(name, rotated_name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    else:
        os.unlink(name, dir_fd=directory_fd)
    os.fsync(directory_fd)


def _regular_metadata(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise TickRunnerError("factory log entries must be regular files")
    return metadata


def _open_regular(directory_fd: int, name: str, *, append: bool) -> int:
    flags = os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_APPEND if append else 0
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise TickRunnerError("factory log entries must be regular files")
    return descriptor


def _validated_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TickRunnerError(f"{label} is unavailable") from exc
    if not resolved.is_dir() or _has_symlink_component(path):
        raise TickRunnerError(f"{label} must be a non-symlink directory")
    return resolved


def _validated_executable(path: Path) -> Path:
    if not path.is_absolute() or _has_symlink_component(path):
        raise TickRunnerError("factoryctl must be an absolute non-symlink path")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise TickRunnerError("factoryctl is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or not os.access(path, os.X_OK):
        raise TickRunnerError("factoryctl must be an executable regular file")
    return path


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one factory tick with bounded repo-owned stream logs."
    )
    _ = parser.add_argument("--factoryctl", type=Path, required=True)
    _ = parser.add_argument("--log-directory", type=Path, required=True)
    _ = parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    _ = parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_BYTES)
    _ = parser.add_argument("--max-log-bytes", type=int, default=DEFAULT_LOG_BYTES)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
