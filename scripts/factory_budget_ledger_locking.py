from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from scripts.factory_retention_fs import RetentionFsError

from .factory_budget_ledger_fs import open_lock
from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_parent_fs import open_private_relative_directory

LOCK_RETRY_SECONDS = 0.01


@contextmanager
def retention_guard(
    repo_root: Path,
    *,
    busy_timeout_milliseconds: int | None = None,
) -> Generator[None, None, None]:
    try:
        with open_private_relative_directory(
            repo_root,
            (".entroping",),
            create=False,
        ) as state_fd:
            descriptor = open_lock(state_fd, "retention.lock")
            try:
                _acquire_shared(
                    descriptor,
                    busy_timeout_milliseconds=busy_timeout_milliseconds,
                )
                yield
            finally:
                os.close(descriptor)
    except RetentionFsError as exc:
        raise FactoryBudgetLedgerError(
            "path",
            "ledger state path is unsafe",
        ) from exc


def _acquire_shared(
    descriptor: int,
    *,
    busy_timeout_milliseconds: int | None,
) -> None:
    if busy_timeout_milliseconds is None:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        return
    deadline = time.monotonic() + (busy_timeout_milliseconds / 1_000)
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return
        except BlockingIOError as exc:
            if time.monotonic() >= deadline:
                raise FactoryBudgetLedgerError(
                    "busy",
                    "ledger retention lock is busy",
                ) from exc
            time.sleep(LOCK_RETRY_SECONDS)
