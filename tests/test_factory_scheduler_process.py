from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_scheduler_models import LeaseOwner  # noqa: E402
from scripts.factory_scheduler_process import (  # noqa: E402
    _identity_digest,
    _process_start_identity,
    _read_ascii_bounded,
    current_lease_owner,
    probe_owner,
    process_start_token,
)


def test_bounded_process_identity_read_rejects_overflow_and_symlinks(
    tmp_path: Path,
) -> None:
    exact = tmp_path / "exact"
    exact.write_bytes(b"12345678")
    overflow = tmp_path / "overflow"
    overflow.write_bytes(b"123456789")
    linked = tmp_path / "linked"
    linked.symlink_to(exact.name)

    assert _read_ascii_bounded(exact, max_bytes=8) == "12345678"
    assert _read_ascii_bounded(overflow, max_bytes=8) is None
    assert _read_ascii_bounded(linked, max_bytes=8) is None


def test_current_owner_has_stable_start_identity() -> None:
    owner = current_lease_owner("current-scheduler")

    assert owner.process_start_token.startswith("proc_")
    assert process_start_token(owner.pid) == owner.process_start_token
    assert probe_owner(owner) is True


def test_process_identity_digest_fences_same_pid_at_a_new_start_time() -> None:
    pid = 42
    first = _identity_digest(pid, "macos:100:123456")
    reused = _identity_digest(pid, "macos:100:123457")

    assert first != reused


def test_live_process_identity_uses_os_start_precision() -> None:
    identity = _process_start_identity(os.getpid())

    assert identity is not None
    assert identity.startswith(("macos:", "linux:"))


def test_probe_reports_exited_process_as_dead() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    token = process_start_token(process.pid)
    assert token is not None
    owner = LeaseOwner(
        owner_id="short-child",
        pid=process.pid,
        process_start_token=token,
    )
    assert process.wait(timeout=5) == 0

    assert probe_owner(owner) is False
