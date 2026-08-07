from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path
from typing import overload
from unittest.mock import patch

from factory_proposal_controller_test_receipt_contracts import (
    MAX_LIST_ITEMS,
    MAX_RECEIPT_BYTES,
    RECEIPT_SCHEMA_VERSION,
    ScenarioReceipt,
)
from factory_proposal_controller_test_receipts import (
    PendingReceipt,
    ScenarioObservation,
    compose_counted_worker,
    finalize_receipt,
    scenario_receipt_from_path,
)
from factory_proposal_controller_test_source_manifest import SourceManifest, source_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"
try:
    _TRUSTED_POPEN = importlib.import_module("entroping_offline_capability").TRUSTED_POPEN
except ImportError:
    _TRUSTED_POPEN = subprocess.Popen

_SCENARIO_CHILD = """import json, sys
from pathlib import Path
module = __import__(sys.argv[1], fromlist=[sys.argv[2]])
result = getattr(module, sys.argv[2])(Path.cwd())
receipts = (result,) if hasattr(result, 'path') else result
print(json.dumps([str(item.path) for item in receipts], separators=(',', ':')))
"""


def offline_child_environment(root: Path) -> dict[str, str]:
    """Create a child environment that rejects network and process launches."""

    site_root = root / "offline-site"
    site_root.mkdir(parents=True, exist_ok=True)
    code = """import os, socket, subprocess, sys, types
_capability = types.ModuleType('entroping_offline_capability')
_capability.TRUSTED_POPEN = subprocess.Popen
sys.modules['entroping_offline_capability'] = _capability
def _blocked(*_args, **_kwargs): raise RuntimeError('offline test boundary reached')
for _name in ('create_connection', 'getaddrinfo'): setattr(socket, _name, _blocked)
for _name in (
    'connect', 'connect_ex', 'send', 'sendall', 'sendto', 'sendmsg',
    'bind', 'listen', 'accept',
):
    if hasattr(socket.socket, _name): setattr(socket.socket, _name, _blocked)
for _name in ('Popen', 'run', 'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput'):
    if hasattr(subprocess, _name): setattr(subprocess, _name, _blocked)
for _name in (
    'system', 'spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 'spawnv', 'spawnve',
    'spawnvp', 'spawnvpe', 'posix_spawn', 'posix_spawnp', 'execv', 'execve', 'execvp', 'execvpe',
):
    if hasattr(os, _name): setattr(os, _name, _blocked)
import scripts.factory_scheduler as _factory_scheduler
_factory_scheduler.resolve_scheduler_root = lambda value: value
"""
    (site_root / "sitecustomize.py").write_text(code, encoding="utf-8")
    environment = {
        "PATH": "",
        "PYTHONPATH": os.pathsep.join((str(site_root), str(REPO_ROOT / "tests"), str(REPO_ROOT))),
    }
    receipt_root = os.environ.get("ENTROPING_PROPOSAL_RECEIPTS_DIR")
    if receipt_root is not None:
        environment["ENTROPING_PROPOSAL_RECEIPTS_DIR"] = str(Path(receipt_root).absolute())
    return environment


def _trusted_child(
    root: Path,
    arguments: list[str],
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if arguments[0] != sys.executable:
        raise AssertionError("offline child executable is not allowlisted")
    environment = offline_child_environment(root)
    if environment_updates is not None:
        environment.update(environment_updates)
    process = _TRUSTED_POPEN(
        arguments,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=environment,
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


def run_offline_python(root: Path, code: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return _trusted_child(root, [sys.executable, "-c", code, *arguments])


@contextmanager
def offline_direct_boundary() -> Iterator[None]:
    """Reject every direct network and process-launch seam in a scenario."""

    blocked = AssertionError("offline direct seam reached")
    with ExitStack() as stack:
        for name in ("create_connection",):
            stack.enter_context(patch(f"socket.{name}", side_effect=blocked))
        for name in (
            "connect",
            "connect_ex",
            "send",
            "sendall",
            "sendto",
            "sendmsg",
            "bind",
            "listen",
            "accept",
        ):
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
            "posix_spawn",
            "posix_spawnp",
            "execv",
            "execve",
            "execvp",
            "execvpe",
        ):
            if hasattr(os, name):
                stack.enter_context(patch(f"os.{name}", side_effect=blocked))
        yield


@overload
def offline_scenario(
    function: Callable[[Path], PendingReceipt],
) -> Callable[[Path], ScenarioReceipt]:
    raise NotImplementedError


@overload
def offline_scenario(
    function: Callable[[Path], tuple[PendingReceipt, ...]],
) -> Callable[[Path], tuple[ScenarioReceipt, ...]]:
    raise NotImplementedError


def offline_scenario(
    function: Callable[[Path], PendingReceipt | tuple[PendingReceipt, ...]],
) -> Callable[[Path], ScenarioReceipt | tuple[ScenarioReceipt, ...]]:
    @wraps(function)
    def wrapped(root: Path) -> ScenarioReceipt | tuple[ScenarioReceipt, ...]:
        child_mode = os.environ.get("ENTROPING_PROPOSAL_SCENARIO_CHILD") == "1"
        if not child_mode:
            before = source_manifest()
            child_process = _trusted_child(
                root,
                [sys.executable, "-c", _SCENARIO_CHILD, function.__module__, function.__name__],
                {
                    "ENTROPING_PROPOSAL_SCENARIO_CHILD": "1",
                    "ENTROPING_PROPOSAL_SOURCE_DIGEST": before.digest,
                },
            )
            assert child_process.returncode == 0, child_process.stderr
            after = source_manifest()
            if after != before:
                raise AssertionError("scenario mutated tracked or untracked source or Git state")
            paths = json.loads(child_process.stdout)
            if (
                not isinstance(paths, list)
                or not paths
                or not all(isinstance(path, str) for path in paths)
            ):
                raise AssertionError("scenario child returned a malformed receipt list")
            receipts = tuple(scenario_receipt_from_path(Path(path)) for path in paths)
            return receipts[0] if len(receipts) == 1 else receipts
        expected = os.environ.get("ENTROPING_PROPOSAL_SOURCE_DIGEST")
        if expected is None:
            raise AssertionError("scenario child source manifest is missing")
        before = SourceManifest(expected)
        with (
            patch(
                "scripts.factory_scheduler.resolve_scheduler_root", side_effect=lambda value: value
            ),
        ):
            result = function(root)
        after = before
        if isinstance(result, PendingReceipt):
            return finalize_receipt(result, before, after)
        return tuple(finalize_receipt(item, before, after) for item in result)

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
    "compose_counted_worker",
    "offline_direct_boundary",
    "offline_scenario",
    "run_cli",
    "run_offline_python",
    "source_digest",
]
