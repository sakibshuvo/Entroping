from __future__ import annotations

import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_retention_fs import entry_snapshot, list_names, open_relative_directory
from scripts.factory_retention_git import RetentionGitError, require_untracked_path
from scripts.factory_retention_journal import (
    JournalOperation,
    RetentionJournal,
    RetentionJournalError,
)
from scripts.factory_retention_journal import read_journal as _read_journal
from scripts.factory_retention_journal import write_journal as _write_journal


class RetentionApplyError(RuntimeError):
    pass


def new_journal(
    transaction_id: str,
    operations: list[JournalOperation],
) -> RetentionJournal:
    return RetentionJournal(
        transaction_id=transaction_id,
        status="moving",
        created_at=_now(),
        operations=operations,
    )


def resume_journal(
    repo_root: Path,
    journal_fd: int,
    trash_root_fd: int,
    journal: RetentionJournal,
    *,
    tracked: frozenset[str],
    authorize_staging: bool,
) -> None:
    try:
        journal.validate_state()
        with _open_trash_transaction(trash_root_fd, journal.transaction_id) as trash_fd:
            if journal.status == "moving":
                pending = any(item.state == "pending" for item in journal.operations)
                if pending and not authorize_staging:
                    _rollback_journal(repo_root, trash_fd, journal, tracked)
                    journal.status = "rolled_back"
                    journal.completed_at = _now()
                    write_journal(journal_fd, journal)
                    cleanup_completed_transaction(trash_root_fd, journal.transaction_id)
                    return
                for operation in journal.operations:
                    _stage_operation(repo_root, trash_fd, operation, tracked)
                    write_journal(journal_fd, journal)
                journal.status = "purging"
                write_journal(journal_fd, journal)
            for operation in journal.operations:
                _purge_operation(repo_root, trash_fd, operation, tracked)
                write_journal(journal_fd, journal)
        journal.status = "completed"
        journal.completed_at = _now()
        write_journal(journal_fd, journal)
        cleanup_completed_transaction(trash_root_fd, journal.transaction_id)
    except (OSError, RetentionGitError, RetentionJournalError) as exc:
        if isinstance(exc, RetentionApplyError):
            raise
        raise RetentionApplyError(str(exc)) from exc


def cleanup_completed_transaction(trash_root_fd: int, transaction_id: str) -> None:
    try:
        with _open_trash_transaction(trash_root_fd, transaction_id) as trash_fd:
            if list_names(trash_fd):
                raise RetentionApplyError("completed retention trash is not empty")
    except RetentionApplyError:
        if not _entry_exists(trash_root_fd, transaction_id):
            return
        raise
    os.rmdir(transaction_id, dir_fd=trash_root_fd)
    os.fsync(trash_root_fd)


def read_journal(journal_fd: int, name: str) -> RetentionJournal:
    try:
        return _read_journal(journal_fd, name)
    except RetentionJournalError as exc:
        raise RetentionApplyError(str(exc)) from exc


def write_journal(
    journal_fd: int,
    journal: RetentionJournal,
    *,
    exclusive: bool = False,
) -> None:
    try:
        _write_journal(journal_fd, journal, exclusive=exclusive)
    except RetentionJournalError as exc:
        raise RetentionApplyError(str(exc)) from exc


def _stage_operation(
    repo_root: Path,
    trash_fd: int,
    operation: JournalOperation,
    tracked: frozenset[str],
) -> None:
    require_untracked_path(operation.source, tracked)
    source = operation.source
    with open_relative_directory(repo_root, source.parts[:-1]) as source_fd:
        source_name = source.parts[-1]
        source_exists = _entry_exists(source_fd, source_name)
        trash_exists = _entry_exists(trash_fd, operation.trash_name)
        if source_exists and trash_exists:
            raise RetentionApplyError("retention source and staged entry both exist")
        if operation.state == "pending" and source_exists and not trash_exists:
            _require_snapshot(source_fd, source_name, operation)
            os.rename(
                source_name,
                operation.trash_name,
                src_dir_fd=source_fd,
                dst_dir_fd=trash_fd,
            )
            os.fsync(source_fd)
            os.fsync(trash_fd)
            _require_snapshot(trash_fd, operation.trash_name, operation)
            operation.state = "staged"
            return
        if operation.state == "staged" and not source_exists and trash_exists:
            _require_snapshot(trash_fd, operation.trash_name, operation)
            return
        raise RetentionApplyError("retention operation placement is inconsistent")


def _rollback_journal(
    repo_root: Path,
    trash_fd: int,
    journal: RetentionJournal,
    tracked: frozenset[str],
) -> None:
    for operation in reversed(journal.operations):
        require_untracked_path(operation.source, tracked)
        source = operation.source
        with open_relative_directory(repo_root, source.parts[:-1]) as source_fd:
            source_name = source.parts[-1]
            source_exists = _entry_exists(source_fd, source_name)
            trash_exists = _entry_exists(trash_fd, operation.trash_name)
            if operation.state == "pending":
                if source_exists and not trash_exists:
                    _require_snapshot(source_fd, source_name, operation)
                elif not source_exists and trash_exists:
                    _require_snapshot(trash_fd, operation.trash_name, operation)
                    os.rename(
                        operation.trash_name,
                        source_name,
                        src_dir_fd=trash_fd,
                        dst_dir_fd=source_fd,
                    )
                    os.fsync(trash_fd)
                    os.fsync(source_fd)
                else:
                    raise RetentionApplyError("pending retention source changed before rollback")
            elif operation.state == "staged":
                if source_exists or not trash_exists:
                    raise RetentionApplyError("staged retention source changed before rollback")
                _require_snapshot(trash_fd, operation.trash_name, operation)
                os.rename(
                    operation.trash_name,
                    source_name,
                    src_dir_fd=trash_fd,
                    dst_dir_fd=source_fd,
                )
                os.fsync(trash_fd)
                os.fsync(source_fd)
            else:
                raise RetentionApplyError("moving journal cannot be rolled back")
            operation.state = "restored"


def _purge_operation(
    repo_root: Path,
    trash_fd: int,
    operation: JournalOperation,
    tracked: frozenset[str],
) -> None:
    require_untracked_path(operation.source, tracked)
    if operation.state == "purged":
        return
    with open_relative_directory(repo_root, operation.source.parts[:-1]) as source_fd:
        if _entry_exists(source_fd, operation.source.parts[-1]):
            raise RetentionApplyError("retention source reappeared during purge")
    if not _entry_exists(trash_fd, operation.trash_name):
        operation.state = "purged"
        return
    _purge_entry(trash_fd, operation.trash_name)
    operation.state = "purged"


def _purge_entry(parent_fd: int, name: str) -> None:
    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISREG(metadata.st_mode):
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return
    if not stat.S_ISDIR(metadata.st_mode):
        raise RetentionApplyError("staged retention entry is a symlink or special file")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    child_fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        for child_name in list_names(child_fd):
            _purge_entry(child_fd, child_name)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _require_snapshot(
    directory_fd: int,
    name: str,
    operation: JournalOperation,
) -> None:
    if entry_snapshot(directory_fd, name) != operation.snapshot:
        raise RetentionApplyError("retention entry fingerprint changed")


@contextmanager
def _open_trash_transaction(
    trash_root_fd: int,
    transaction_id: str,
) -> Generator[int, None, None]:
    if not transaction_id or Path(transaction_id).name != transaction_id:
        raise RetentionApplyError("retention transaction id is invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(transaction_id, flags, dir_fd=trash_root_fd)
    except OSError as exc:
        raise RetentionApplyError("retention trash transaction is missing or unsafe") from exc
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _entry_exists(directory_fd: int, name: str) -> bool:
    try:
        _ = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
