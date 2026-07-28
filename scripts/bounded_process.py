from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess  # nosec B404
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

OUTPUT_LIMIT_MARKER = "[output truncated: byte limit exceeded]\n"


class BoundedProcessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BoundedProcessResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_limit_exceeded: bool


def run_bounded_process(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    env: Mapping[str, str] | None = None,
) -> BoundedProcessResult:
    args = tuple(str(item) for item in command)
    if not args:
        raise BoundedProcessError("bounded command must not be empty")
    if timeout_seconds <= 0 or max_output_bytes <= 0:
        raise BoundedProcessError("bounded process limits must be positive")
    try:
        process = subprocess.Popen(  # nosec B603
            args,
            cwd=cwd,
            env=None if env is None else dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise BoundedProcessError("could not start bounded subprocess") from exc
    if process.stdout is None or process.stderr is None:
        _kill_process_group(process)
        raise BoundedProcessError("bounded subprocess pipes are unavailable")

    selector = selectors.DefaultSelector()
    _ = selector.register(process.stdout, selectors.EVENT_READ)
    _ = selector.register(process.stderr, selectors.EVENT_READ)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    exceeded_streams: set[str] = set()
    timed_out = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0 and process.poll() is None:
                timed_out = True
                _kill_process_group(process)
            events = selector.select(timeout=max(0.0, min(0.1, remaining)))
            if not events and process.poll() is not None:
                events = selector.select(timeout=0)
                if not events:
                    _kill_process_group(process)
                    break
            for key, _ in events:
                stream_name = "stdout" if key.fileobj is process.stdout else "stderr"
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    stream = process.stdout if stream_name == "stdout" else process.stderr
                    _ = selector.unregister(stream)
                    stream.close()
                    continue
                buffer = buffers[stream_name]
                available = max_output_bytes - len(buffer)
                if available > 0:
                    buffer.extend(chunk[:available])
                if len(chunk) > available:
                    exceeded_streams.add(stream_name)
                    _kill_process_group(process)
        returncode = process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _kill_process_group(process)
        _ = process.wait()
        raise BoundedProcessError("bounded subprocess cleanup failed") from exc
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            if not stream.closed:
                stream.close()

    stdout, stdout_decode_exceeded = _decode_output(
        bytes(buffers["stdout"]),
        max_output_bytes,
        "stdout" in exceeded_streams,
    )
    stderr, stderr_decode_exceeded = _decode_output(
        bytes(buffers["stderr"]),
        max_output_bytes,
        "stderr" in exceeded_streams,
    )
    return BoundedProcessResult(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_limit_exceeded=bool(
            exceeded_streams or stdout_decode_exceeded or stderr_decode_exceeded
        ),
    )


def _decode_output(payload: bytes, limit: int, exceeded: bool) -> tuple[str, bool]:
    decoded = payload.decode("utf-8", errors="replace")
    if not exceeded and len(decoded.encode("utf-8")) <= limit:
        return decoded, False
    marker = OUTPUT_LIMIT_MARKER.encode("utf-8")
    if len(marker) >= limit:
        return marker[:limit].decode("utf-8", errors="ignore"), True
    head = decoded.encode("utf-8")[: limit - len(marker)].decode(
        "utf-8", errors="ignore"
    )
    return f"{head}{OUTPUT_LIMIT_MARKER}", True


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        _kill_process_group_fallback(process)


def _kill_process_group_fallback(process: subprocess.Popen[bytes]) -> None:
    pkill = shutil.which("pkill")
    if pkill is not None:
        try:
            completed = subprocess.run(  # nosec B603
                [pkill, "-KILL", "-g", str(process.pid)],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is not None and completed.returncode == 0:
            return
    group_exists = _process_group_exists(process.pid)
    if group_exists is False:
        return
    with suppress(ProcessLookupError):
        process.kill()
    if _process_group_exists(process.pid) is False:
        return
    raise BoundedProcessError("could not guarantee bounded subprocess group cleanup")


def _process_group_exists(group_id: int) -> bool | None:
    pgrep = shutil.which("pgrep")
    if pgrep is None:
        return None
    try:
        completed = subprocess.run(  # nosec B603
            [pgrep, "-g", str(group_id)],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None
