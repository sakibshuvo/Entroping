from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import fcntl
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from factory_scheduler_test_support import (
    NOW,
    dead,
    owner,
    paid_request_with_reservation,
    request,
    scheduler,
)

from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_storage_fs import nofollow_flag, open_lock


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True)
    path.chmod(0o700)


def _held_lock(path: Path) -> int:
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | nofollow_flag(), 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def test_secure_lock_open_retries_transient_creation_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory_fd = os.open(tmp_path, os.O_RDONLY)
    real_open = os.open
    attempts = 0

    def racing_open(
        path: str,
        flags: int,
        mode: int = 0o600,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal attempts
        if path == "retention.lock":
            attempts += 1
            if attempts == 1:
                raise FileNotFoundError(path)
            assert flags & nofollow_flag()
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("scripts.factory_scheduler_storage_fs.os.open", racing_open)
    descriptor: int | None = None
    try:
        descriptor = open_lock(directory_fd, "retention.lock")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)

    assert attempts == 2


@pytest.mark.parametrize("lock_scope", ["retention", "initialization"])
def test_scheduler_lock_contention_returns_bounded_state_busy(
    tmp_path: Path,
    lock_scope: str,
) -> None:
    state_root = tmp_path / ".entroping"
    scheduler_root = state_root / "factory-scheduler"
    _private_directory(state_root)
    if lock_scope == "retention":
        lock_path = state_root / "retention.lock"
    else:
        _private_directory(scheduler_root)
        lock_path = scheduler_root / "scheduler.lock"
    descriptor = _held_lock(lock_path)
    pool = ThreadPoolExecutor(max_workers=1)

    try:
        future = pool.submit(
            scheduler(tmp_path).tick,
            request=request(1, worker_class="free-local"),
            owner=owner(1),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
        receipt = future.result(timeout=1)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        pool.shutdown(wait=True)

    assert receipt.decision == "blocked"
    assert receipt.reason == "state-busy"


def test_paid_handoff_retention_lock_contention_is_bounded(tmp_path: Path) -> None:
    _ledger, candidate = paid_request_with_reservation(tmp_path)
    descriptor = _held_lock(tmp_path / ".entroping" / "retention.lock")
    pool = ThreadPoolExecutor(max_workers=1)

    try:
        future = pool.submit(
            FactoryScheduler(tmp_path).tick,
            request=candidate,
            owner=owner(1),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
        receipt = future.result(timeout=1)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        pool.shutdown(wait=True)

    assert receipt.decision == "blocked"
    assert receipt.reason == "reservation-busy"
