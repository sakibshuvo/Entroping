from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bounded_process import OUTPUT_LIMIT_MARKER, run_bounded_process  # noqa: E402


def test_bounded_process_captures_normal_stdout_and_stderr(tmp_path: Path) -> None:
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            "import sys; print('hello'); print('warning', file=sys.stderr)",
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
    )
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == "warning\n"
    assert result.timed_out is False
    assert result.output_limit_exceeded is False


def test_bounded_process_streams_stdout_without_returning_raw_bytes(tmp_path: Path) -> None:
    chunks: list[bytes] = []

    result = run_bounded_process(
        [sys.executable, "-c", "print('json event')"],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
        stdout_consumer=chunks.append,
        capture_stdout=False,
    )

    assert b"".join(chunks) == b"json event\n"
    assert result.stdout == ""
    assert result.output_limit_exceeded is False


def test_bounded_process_enforces_limit_when_stdout_is_not_captured(tmp_path: Path) -> None:
    chunks: list[bytes] = []

    result = run_bounded_process(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1000000)"],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
        stdout_consumer=chunks.append,
        capture_stdout=False,
    )

    assert result.output_limit_exceeded is True
    assert len(b"".join(chunks)) <= 1_024
    assert result.stdout == ""


def test_bounded_process_consumer_failure_is_value_free(tmp_path: Path) -> None:
    def reject(_chunk: bytes) -> None:
        raise RuntimeError("secret provider output")

    with pytest.raises(RuntimeError, match="bounded stdout consumer failed") as exc_info:
        run_bounded_process(
            [sys.executable, "-c", "print('event')"],
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_bytes=1_024,
            stdout_consumer=reject,
            capture_stdout=False,
        )

    assert "secret provider output" not in str(exc_info.value)


def test_bounded_process_kills_output_flood_before_memory_growth(tmp_path: Path) -> None:
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 1000000); sys.stdout.flush()",
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
    )
    assert result.returncode != 0
    assert result.output_limit_exceeded is True
    assert len(result.stdout.encode("utf-8")) <= 1_024
    assert OUTPUT_LIMIT_MARKER.strip() in result.stdout


def test_bounded_process_timeout_kills_child_and_preserves_bounded_partial_output(
    tmp_path: Path,
) -> None:
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(5)",
        ],
        cwd=tmp_path,
        timeout_seconds=0.1,
        max_output_bytes=1_024,
    )
    assert result.returncode != 0
    assert result.timed_out is True
    assert result.stdout == "started\n"


def test_bounded_process_keeps_invalid_utf8_within_persistence_byte_limit(
    tmp_path: Path,
) -> None:
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            "import os; os.write(1, b'\\xff' * 32)",
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=64,
    )

    assert result.output_limit_exceeded is True
    assert len(result.stdout.encode("utf-8")) <= 64
    assert OUTPUT_LIMIT_MARKER.strip() in result.stdout


def test_bounded_process_cleans_group_after_leader_exits_with_descendant_alive(
    tmp_path: Path,
) -> None:
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "print(child.pid, flush=True)"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
    )
    child_pid = int(result.stdout.strip())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        os.kill(child_pid, signal.SIGKILL)
        raise AssertionError("bounded subprocess descendant remained alive")


def test_bounded_process_cleans_devnull_descendant_after_leader_exits(
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "child.pid"
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
    )

    child_pid = int(child_pid_path.read_text())
    if _process_is_executing(child_pid):
        os.kill(child_pid, signal.SIGKILL)
        pytest.fail("bounded DEVNULL descendant remained alive")
    assert result.returncode == 0


class _CallbackAbort(BaseException):
    pass


def _process_is_executing(pid: int) -> bool:
    observed = subprocess.run(
        ["/bin/ps", "-o", "state=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    return observed.returncode == 0 and not observed.stdout.strip().startswith("Z")


def test_bounded_process_base_exception_consumer_cleans_process_group(
    tmp_path: Path,
) -> None:
    leader_pid_path = tmp_path / "leader.pid"

    def abort(_chunk: bytes) -> None:
        raise _CallbackAbort

    with pytest.raises(_CallbackAbort):
        run_bounded_process(
            [
                sys.executable,
                "-c",
                (
                    "import os,pathlib,time; "
                    f"pathlib.Path({str(leader_pid_path)!r}).write_text(str(os.getpid())); "
                    "print('ready', flush=True); time.sleep(60)"
                ),
            ],
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_bytes=1_024,
            stdout_consumer=abort,
        )

    leader_pid = int(leader_pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(leader_pid, 0)


def test_bounded_process_base_exception_cancellation_callback_cleans_group(
    tmp_path: Path,
) -> None:
    leader_pid_path = tmp_path / "cancel-leader.pid"

    def abort_after_start() -> bool:
        if leader_pid_path.exists():
            raise _CallbackAbort
        return False

    with pytest.raises(_CallbackAbort):
        run_bounded_process(
            [
                sys.executable,
                "-c",
                (
                    "import os,pathlib,time; "
                    f"pathlib.Path({str(leader_pid_path)!r}).write_text(str(os.getpid())); "
                    "time.sleep(60)"
                ),
            ],
            cwd=tmp_path,
            timeout_seconds=5,
            max_output_bytes=1_024,
            cancelled=abort_after_start,
        )

    with pytest.raises(ProcessLookupError):
        os.kill(int(leader_pid_path.read_text()), 0)


def test_bounded_process_streams_exact_input_bytes(tmp_path: Path) -> None:
    # Given: a payload larger than a typical pipe buffer.
    payload = b"x" * 131_072

    # When: the bounded runner streams it to a controlled child stdin.
    result = run_bounded_process(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
        cwd=tmp_path,
        timeout_seconds=5,
        max_output_bytes=1_024,
        input_bytes=payload,
    )

    # Then: the child receives every byte exactly once.
    assert result.returncode == 0
    assert result.stdout == "131072\n"


def test_bounded_process_input_cannot_block_timeout(tmp_path: Path) -> None:
    # Given: a child that never reads a payload much larger than its pipe buffer.
    started = time.monotonic()

    # When: the bounded runner reaches its deadline.
    result = run_bounded_process(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        timeout_seconds=0.1,
        max_output_bytes=1_024,
        input_bytes=b"x" * 4_000_000,
    )

    # Then: non-reading stdin cannot defeat the process-group timeout.
    assert result.timed_out is True
    assert result.returncode != 0
    assert time.monotonic() - started < 2


def test_bounded_process_cancellation_kills_process_group(tmp_path: Path) -> None:
    # Given: a long-lived leader with a long-lived descendant.
    started = time.monotonic()
    result = run_bounded_process(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "print(child.pid, flush=True); time.sleep(60)"
            ),
        ],
        cwd=tmp_path,
        timeout_seconds=10,
        max_output_bytes=1_024,
        cancelled=lambda: time.monotonic() - started >= 0.1,
    )

    # When/Then: cancellation terminates the whole process group promptly.
    assert result.cancelled is True
    assert result.returncode != 0
    child_pid = int(result.stdout.strip())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        os.kill(child_pid, signal.SIGKILL)
        raise AssertionError("cancelled subprocess descendant remained alive")
