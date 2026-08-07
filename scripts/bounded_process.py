from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess  # nosec B404
import time
from collections.abc import Callable, Mapping, Sequence
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
    cancelled: bool = False


def run_bounded_process(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    env: Mapping[str, str] | None = None,
    stdout_consumer: Callable[[bytes], None] | None = None,
    stderr_consumer: Callable[[bytes], None] | None = None,
    capture_stdout: bool = True,
    input_bytes: bytes | None = None,
    cancelled: Callable[[], bool] | None = None,
    pass_fds: Sequence[int] = (),
) -> BoundedProcessResult:
    args = tuple(str(item) for item in command)
    if not args:
        raise BoundedProcessError("bounded command must not be empty")
    if timeout_seconds <= 0 or max_output_bytes <= 0:
        raise BoundedProcessError("bounded process limits must be positive")
    inherited_fds = tuple(pass_fds)
    if len(set(inherited_fds)) != len(inherited_fds) or any(
        type(descriptor) is not int or descriptor < 0 for descriptor in inherited_fds
    ):
        raise BoundedProcessError("bounded process descriptors are invalid")
    try:
        process = subprocess.Popen(  # nosec B603
            args,
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            pass_fds=inherited_fds,
        )
    except OSError as exc:
        raise BoundedProcessError("could not start bounded subprocess") from exc
    if process.stdout is None or process.stderr is None:
        _cleanup_process(process, None)
        raise BoundedProcessError("bounded subprocess pipes are unavailable")

    selector = selectors.DefaultSelector()
    try:
        _ = selector.register(process.stdout, selectors.EVENT_READ)
        _ = selector.register(process.stderr, selectors.EVENT_READ)
        input_offset = 0
        pending_input = b"" if input_bytes is None else input_bytes
        if input_bytes is not None:
            if process.stdin is None:
                raise BoundedProcessError("bounded subprocess stdin is unavailable")
            os.set_blocking(process.stdin.fileno(), False)
            _ = selector.register(process.stdin, selectors.EVENT_WRITE)
    except BaseException:
        _cleanup_process(process, selector)
        raise
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    consumed_bytes = {"stdout": 0, "stderr": 0}
    exceeded_streams: set[str] = set()
    timed_out = False
    was_cancelled = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            if cancelled is not None and cancelled() and process.poll() is None:
                was_cancelled = True
                _kill_process_group(process)
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
                if process.stdin is not None and key.fileobj is process.stdin:
                    try:
                        written = os.write(
                            key.fd,
                            pending_input[input_offset : input_offset + 65_536],
                        )
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = 0
                    input_offset += written
                    if written == 0 or input_offset == len(pending_input):
                        _ = selector.unregister(process.stdin)
                        process.stdin.close()
                    continue
                stream_name = "stdout" if key.fileobj is process.stdout else "stderr"
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    stream = process.stdout if stream_name == "stdout" else process.stderr
                    _ = selector.unregister(stream)
                    stream.close()
                    continue
                available = max_output_bytes - consumed_bytes[stream_name]
                accepted = chunk[: max(0, available)]
                consumed_bytes[stream_name] += len(accepted)
                if stream_name == "stdout" and stdout_consumer is not None and accepted:
                    try:
                        stdout_consumer(accepted)
                    except Exception as exc:
                        _kill_process_group(process)
                        _ = process.wait()
                        raise BoundedProcessError("bounded stdout consumer failed") from exc
                if stream_name == "stderr" and stderr_consumer is not None and accepted:
                    try:
                        stderr_consumer(accepted)
                    except Exception as exc:
                        _kill_process_group(process)
                        _ = process.wait()
                        raise BoundedProcessError("bounded stderr consumer failed") from exc
                buffer = buffers[stream_name]
                should_capture = stream_name != "stdout" or capture_stdout
                if available > 0 and should_capture:
                    buffer.extend(accepted)
                if len(chunk) > available:
                    exceeded_streams.add(stream_name)
                    _kill_process_group(process)
        returncode = process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _kill_process_group(process)
        _ = process.wait()
        raise BoundedProcessError("bounded subprocess cleanup failed") from exc
    finally:
        _cleanup_process(process, selector)

    if capture_stdout:
        stdout, stdout_decode_exceeded = _decode_output(
            bytes(buffers["stdout"]),
            max_output_bytes,
            "stdout" in exceeded_streams,
        )
    else:
        stdout = ""
        stdout_decode_exceeded = False
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
        cancelled=was_cancelled,
    )


def _decode_output(payload: bytes, limit: int, exceeded: bool) -> tuple[str, bool]:
    decoded = payload.decode("utf-8", errors="replace")
    if not exceeded and len(decoded.encode("utf-8")) <= limit:
        return decoded, False
    marker = OUTPUT_LIMIT_MARKER.encode("utf-8")
    if len(marker) >= limit:
        return marker[:limit].decode("utf-8", errors="ignore"), True
    head = decoded.encode("utf-8")[: limit - len(marker)].decode("utf-8", errors="ignore")
    return f"{head}{OUTPUT_LIMIT_MARKER}", True


def _cleanup_process(
    process: subprocess.Popen[bytes],
    selector: selectors.BaseSelector | None,
) -> None:
    _kill_process_group(process)
    if process.poll() is None:
        with suppress(subprocess.TimeoutExpired):
            _ = process.wait(timeout=5)
    if selector is not None:
        selector.close()
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()


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
