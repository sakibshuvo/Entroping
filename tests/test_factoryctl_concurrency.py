from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import json
import subprocess
import sys
from dataclasses import dataclass
from multiprocessing import get_context
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_scheduler import FactoryScheduler  # noqa: E402


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def _run_overlapping_tick(
    repo: Path,
    index: int,
    start: Event,
    ready: Queue[str],
    results: Queue[CliResult],
) -> None:
    ready.put(f"ready-{index}")
    if not start.wait(timeout=5):
        results.put(CliResult(returncode=2, stdout="", stderr="start gate timed out"))
        return
    result = subprocess.run(
        [
            sys.executable,
            str(FACTORYCTL),
            "tick",
            "--apply",
            "--json",
            "--owner-id",
            f"process-owner-{index}",
            "--request-id",
            f"request-{index}",
            "--job-id",
            f"review-20260729-job-{index}",
            "--issue",
            "1569",
            "--worktree-id",
            f"wt_{'1' * 64}",
            "--worker-class",
            "free-local",
            "--access-mode",
            "read-only",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    results.put(
        CliResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    )


def test_overlapping_factoryctl_processes_commit_one_assignment(tmp_path: Path) -> None:
    context = get_context("spawn")
    ready: Queue[str] = context.Queue()
    start: Event = context.Event()
    results: Queue[CliResult] = context.Queue()
    processes = tuple(
        context.Process(
            target=_run_overlapping_tick,
            args=(tmp_path, index, start, ready, results),
        )
        for index in (1, 2)
    )

    try:
        for process in processes:
            process.start()
        assert {ready.get(timeout=5), ready.get(timeout=5)} == {"ready-1", "ready-2"}
        start.set()
        observed = (results.get(timeout=10), results.get(timeout=10))
    finally:
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    payloads = [json.loads(result.stdout) for result in observed]

    assert sorted(result.returncode for result in observed) == [0, 1]
    assert sorted((payload["decision"], payload["reason"]) for payload in payloads) == [
        ("assigned", "capacity-reserved"),
        ("blocked", "lease-held"),
    ]
    assert all(result.stderr == "" for result in observed)
    snapshot = FactoryScheduler(tmp_path).snapshot()
    assert snapshot.active_assignment_count == 1
    assert snapshot.active_free_reviews == 1
