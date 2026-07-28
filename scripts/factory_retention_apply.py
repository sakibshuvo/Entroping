from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from scripts.factory_retention_fs import list_names, open_relative_directory
from scripts.factory_retention_git import (
    RetentionGitError,
    require_untracked_control_state,
    require_untracked_path,
    tracked_paths,
)
from scripts.factory_retention_inventory import RetentionInventory, inventory_factory
from scripts.factory_retention_journal import MAX_OPERATIONS, JournalOperation
from scripts.factory_retention_models import RetentionPlanReport
from scripts.factory_retention_transaction import (
    RetentionApplyError as RetentionApplyError,
)
from scripts.factory_retention_transaction import (
    cleanup_completed_transaction,
    new_journal,
    read_journal,
    resume_journal,
    write_journal,
)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    transaction_id: str
    reclaimed_count: int
    reclaimed_bytes: int
    recovered_transactions: int
    journal_path: str | None


def apply_retention_plan(
    repo_root: Path,
    plan: RetentionPlanReport,
    inventory: RetentionInventory,
) -> ApplyResult:
    with _exclusive_lock(repo_root):
        tracked = _tracked_paths(repo_root)
        recovered = _recover_incomplete(repo_root, tracked)
        fresh = inventory_factory(repo_root)
        if inventory.errors or fresh.errors:
            raise RetentionApplyError("retention inventory contains fail-closed errors")
        try:
            operations = _operations(plan, inventory, fresh, tracked)
        except RetentionGitError as exc:
            raise RetentionApplyError(str(exc)) from exc
        transaction_id = uuid.uuid4().hex
        if not operations:
            return ApplyResult(
                transaction_id=transaction_id,
                reclaimed_count=0,
                reclaimed_bytes=0,
                recovered_transactions=recovered,
                journal_path=None,
            )
        journal = new_journal(transaction_id, operations)
        with (
            open_relative_directory(
                repo_root, (".entroping", "retention-journal"), create=True
            ) as journal_fd,
            open_relative_directory(
                repo_root, (".entroping", "retention-trash"), create=True
            ) as trash_root_fd,
        ):
            os.mkdir(transaction_id, mode=0o700, dir_fd=trash_root_fd)
            os.fsync(trash_root_fd)
            write_journal(journal_fd, journal, exclusive=True)
            resume_journal(
                repo_root,
                journal_fd,
                trash_root_fd,
                journal,
                tracked=tracked,
                authorize_staging=True,
            )
        return ApplyResult(
            transaction_id=transaction_id,
            reclaimed_count=len(operations),
            reclaimed_bytes=sum(item.snapshot.byte_size for item in operations),
            recovered_transactions=recovered,
            journal_path=f".entroping/retention-journal/{transaction_id}.json",
        )


def recover_incomplete(repo_root: Path) -> int:
    with _exclusive_lock(repo_root):
        return _recover_incomplete(repo_root, _tracked_paths(repo_root))


def _recover_incomplete(repo_root: Path, tracked: frozenset[str]) -> int:
    parts = (".entroping", "retention-journal")
    if not repo_root.joinpath(*parts).exists():
        return 0
    recovered = 0
    with (
        open_relative_directory(repo_root, parts) as journal_fd,
        open_relative_directory(
            repo_root, (".entroping", "retention-trash"), create=True
        ) as trash_root_fd,
    ):
        for name in list_names(journal_fd):
            if not name.endswith(".json"):
                continue
            journal = read_journal(journal_fd, name)
            transaction_id = journal.transaction_id
            if name != f"{transaction_id}.json":
                raise RetentionApplyError("retention journal filename does not match its id")
            if journal.status in {"completed", "rolled_back"}:
                cleanup_completed_transaction(trash_root_fd, transaction_id)
                continue
            resume_journal(
                repo_root,
                journal_fd,
                trash_root_fd,
                journal,
                tracked=tracked,
                authorize_staging=False,
            )
            recovered += 1
    return recovered


def _operations(
    plan: RetentionPlanReport,
    original: RetentionInventory,
    fresh: RetentionInventory,
    tracked: frozenset[str],
) -> list[JournalOperation]:
    original_by_path = original.entry_by_path()
    fresh_by_path = fresh.entry_by_path()
    operations: list[JournalOperation] = []
    selected = tuple(item for item in plan.decisions if item.action == "delete")
    if len(selected) > MAX_OPERATIONS:
        raise RetentionApplyError("retention plan exceeds the operation limit")
    for index, decision in enumerate(selected):
        source = PurePosixPath(decision.relative_path)
        require_untracked_path(source, tracked)
        original_entry = original_by_path.get(decision.relative_path)
        fresh_entry = fresh_by_path.get(decision.relative_path)
        if original_entry is None or fresh_entry is None:
            raise RetentionApplyError("planned retention entry disappeared before apply")
        if original_entry.snapshot is None or original_entry.snapshot != fresh_entry.snapshot:
            raise RetentionApplyError("planned retention entry changed before apply")
        snapshot = original_entry.snapshot
        operations.append(
            JournalOperation(
                source=source,
                trash_name=(
                    f"{index:06d}-"
                    f"{hashlib.sha256(decision.relative_path.encode('utf-8')).hexdigest()[:16]}"
                ),
                state="pending",
                snapshot=snapshot,
            )
        )
    return operations


@contextmanager
def _exclusive_lock(repo_root: Path) -> Generator[None, None, None]:
    with open_relative_directory(repo_root, (".entroping",), create=True) as state_fd:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open("retention.lock", flags, 0o600, dir_fd=state_fd)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise RetentionApplyError("retention lock is not a regular file")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RetentionApplyError("another retention apply is already running") from exc
            yield
        finally:
            os.close(descriptor)


def _tracked_paths(repo_root: Path) -> frozenset[str]:
    try:
        tracked = tracked_paths(repo_root)
        require_untracked_control_state(tracked)
    except RetentionGitError as exc:
        raise RetentionApplyError(str(exc)) from exc
    return tracked
