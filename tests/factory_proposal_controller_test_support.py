from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"
_RUN_SUBPROCESS = subprocess.run


@dataclass(frozen=True, slots=True)
class ScenarioReceipt:
    scenario: str
    crash_point: str
    return_class: str
    state_digest: str
    fake_call_count: int
    changed_paths: tuple[str, ...]
    file_total: int
    byte_total: int
    invariants: tuple[str, ...]
    path: Path


def offline_child_environment(root: Path) -> dict[str, str]:
    """Create a child environment that rejects network and PATH-based Git access."""

    site_root = root / "offline-site"
    site_root.mkdir(exist_ok=True)
    (site_root / "sitecustomize.py").write_text(
        "import socket\n"
        "def _blocked(*_args, **_kwargs):\n"
        "    raise RuntimeError('offline test boundary reached')\n"
        "socket.create_connection = _blocked\n"
        "socket.socket.connect = _blocked\n",
        encoding="utf-8",
    )
    return {"PATH": "", "PYTHONPATH": str(site_root)}


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _RUN_SUBPROCESS(
        [sys.executable, str(FACTORYCTL), *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=offline_child_environment(root),
        timeout=10,
    )


@contextmanager
def offline_direct_boundary() -> Iterator[None]:
    """Fail direct composition scenarios if they reach network or process seams."""

    with (
        patch(
            "socket.create_connection",
            side_effect=AssertionError("offline network seam reached"),
        ),
        patch(
            "subprocess.run",
            side_effect=AssertionError("offline process seam reached"),
        ),
    ):
        yield


def offline_scenario[T](function: Callable[[Path], T]) -> Callable[[Path], T]:
    """Apply the direct offline boundary while preserving isolated CLI launch access."""

    def wrapped(root: Path) -> T:
        with offline_direct_boundary():
            return function(root)

    return wrapped


def record_receipt(
    root: Path,
    *,
    scenario: str,
    return_class: str,
    changed_paths: tuple[str, ...],
    fake_call_count: int = 0,
    crash_point: str = "none",
    invariants: tuple[str, ...] = (),
) -> ScenarioReceipt:
    """Persist only stable, value-free scenario evidence inside the fixture."""

    file_total, byte_total, state_digest = state_summary(root)
    evidence_root = os.environ.get("ENTROPING_PROPOSAL_RECEIPTS_DIR")
    receipt_root = Path(evidence_root) if evidence_root is not None else root / "receipts"
    receipt_root.mkdir(exist_ok=True)
    path = receipt_root / f"{scenario}.json"
    payload = {
        "scenario": scenario,
        "crash_point": crash_point,
        "return_class": return_class,
        "state_digest": state_digest,
        "fake_call_count": fake_call_count,
        "changed_paths": changed_paths,
        "file_total": file_total,
        "byte_total": byte_total,
        "durations_ms": {"compose": 0, "verify": 0},
        "invariants": invariants,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return ScenarioReceipt(
        scenario=scenario,
        crash_point=crash_point,
        return_class=return_class,
        state_digest=state_digest,
        fake_call_count=fake_call_count,
        changed_paths=changed_paths,
        file_total=file_total,
        byte_total=byte_total,
        invariants=invariants,
        path=path,
    )


def state_summary(root: Path) -> tuple[int, int, str]:
    """Summarize fixture state without copying names or contents into receipts."""

    manifest = hashlib.sha256()
    file_total = 0
    byte_total = 0
    for path in sorted(root.rglob("*")):
        metadata = path.stat(follow_symlinks=False)
        if path.is_file():
            file_total += 1
            byte_total += metadata.st_size
        manifest.update(path.relative_to(root).as_posix().encode("utf-8"))
        manifest.update(str(metadata.st_mode).encode("ascii"))
        manifest.update(str(metadata.st_size).encode("ascii"))
    return file_total, byte_total, manifest.hexdigest()


def source_digest() -> str:
    """Bind every receipt sequence to an unchanged checkout source manifest."""

    digest = hashlib.sha256()
    for path in sorted(REPO_ROOT.glob("scripts/**/*.py")):
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_source_unchanged(before: str) -> None:
    assert source_digest() == before
