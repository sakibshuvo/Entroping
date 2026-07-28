from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

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
