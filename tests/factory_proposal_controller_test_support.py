from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from factory_proposal_controller_test_receipts import (
    MAX_LIST_ITEMS,
    MAX_RECEIPT_BYTES,
    RECEIPT_SCHEMA_VERSION,
    ScenarioObservation,
    ScenarioReceipt,
    record_receipt,
)
from factory_proposal_controller_test_source_manifest import SourceManifest, source_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"
_TRUSTED_POPEN = subprocess.Popen


def offline_child_environment(root: Path) -> dict[str, str]:
    """Create a child environment that rejects network and process launches."""

    site_root = root / "offline-site"
    site_root.mkdir(exist_ok=True)
    code = """import os, socket, subprocess
def _blocked(*_args, **_kwargs): raise RuntimeError('offline test boundary reached')
for _name in ('create_connection',): setattr(socket, _name, _blocked)
for _name in ('connect', 'connect_ex', 'send', 'sendall', 'sendto', 'sendmsg'):
    if hasattr(socket.socket, _name): setattr(socket.socket, _name, _blocked)
for _name in ('Popen', 'run', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput'):
    if hasattr(subprocess, _name): setattr(subprocess, _name, _blocked)
for _name in (
    'system', 'spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 'spawnv', 'spawnve',
    'spawnvp', 'spawnvpe', 'execv', 'execve', 'execvp', 'execvpe',
):
    if hasattr(os, _name): setattr(os, _name, _blocked)
import scripts.factory_scheduler as _factory_scheduler
_factory_scheduler.resolve_scheduler_root = lambda value: value
"""
    (site_root / "sitecustomize.py").write_text(code, encoding="utf-8")
    return {"PATH": "", "PYTHONPATH": os.pathsep.join((str(site_root), str(REPO_ROOT)))}


def _trusted_child(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    if arguments[0] != sys.executable:
        raise AssertionError("offline child executable is not allowlisted")
    process = _TRUSTED_POPEN(
        arguments,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=offline_child_environment(root),
    )
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        _ = process.communicate()
        raise AssertionError("offline child timed out") from exc
    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _trusted_child(root, [sys.executable, str(FACTORYCTL), *args])


def run_offline_python(root: Path, code: str) -> subprocess.CompletedProcess[str]:
    return _trusted_child(root, [sys.executable, "-c", code])


def reopen_in_fresh_child(root: Path, component: Literal["scheduler", "ledger"]) -> None:
    scheduler_code = (
        "from pathlib import Path; from scripts.factory_scheduler import "
        "FactoryScheduler; FactoryScheduler(Path.cwd()).snapshot()"
    )
    ledger_code = (
        "from pathlib import Path; from scripts.factory_budget_ledger import "
        "FactoryBudgetLedger; FactoryBudgetLedger.open_project(Path.cwd())"
    )
    code = scheduler_code if component == "scheduler" else ledger_code
    result = run_offline_python(root, code)
    assert result.returncode == 0, result.stderr


@contextmanager
def offline_direct_boundary() -> Iterator[None]:
    """Reject every direct network and process-launch seam in a scenario."""

    blocked = AssertionError("offline direct seam reached")
    with ExitStack() as stack:
        for name in ("create_connection",):
            stack.enter_context(patch(f"socket.{name}", side_effect=blocked))
        for name in ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg"):
            if hasattr(__import__("socket").socket, name):
                stack.enter_context(patch(f"socket.socket.{name}", side_effect=blocked))
        for name in (
            "Popen",
            "run",
            "call",
            "check_call",
            "check_output",
            "getoutput",
            "getstatusoutput",
        ):
            stack.enter_context(patch(f"subprocess.{name}", side_effect=blocked))
        for name in (
            "system",
            "spawnl",
            "spawnle",
            "spawnlp",
            "spawnlpe",
            "spawnv",
            "spawnve",
            "spawnvp",
            "spawnvpe",
            "execv",
            "execve",
            "execvp",
            "execvpe",
        ):
            if hasattr(os, name):
                stack.enter_context(patch(f"os.{name}", side_effect=blocked))
        yield


def offline_scenario[T](function: Callable[[Path], T]) -> Callable[[Path], T]:
    def wrapped(root: Path) -> T:
        before = source_manifest()
        with (
            offline_direct_boundary(),
            patch(
                "scripts.factory_scheduler.resolve_scheduler_root", side_effect=lambda value: value
            ),
        ):
            result = function(root)
        assert source_manifest() == before
        return result

    return wrapped


def source_digest() -> SourceManifest:
    return source_manifest()


def assert_source_unchanged(before: SourceManifest) -> None:
    assert source_manifest() == before


__all__ = [
    "MAX_LIST_ITEMS",
    "MAX_RECEIPT_BYTES",
    "RECEIPT_SCHEMA_VERSION",
    "ScenarioObservation",
    "ScenarioReceipt",
    "assert_source_unchanged",
    "offline_direct_boundary",
    "offline_scenario",
    "record_receipt",
    "reopen_in_fresh_child",
    "run_cli",
    "run_offline_python",
    "source_digest",
]
