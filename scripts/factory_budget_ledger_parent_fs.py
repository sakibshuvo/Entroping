from __future__ import annotations

import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path

from scripts.factory_retention_fs import RetentionFsError

from .factory_budget_ledger_models import FactoryBudgetLedgerError


@contextmanager
def open_private_relative_directory(
    repo_root: Path,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> Generator[int, None, None]:
    flags = os.O_RDONLY | _directory_flag() | _nofollow_flag()
    try:
        root_descriptor = _open_repository_root(repo_root, flags)
    except OSError as exc:
        raise RetentionFsError("could not open private ledger directory") from exc
    try:
        try:
            _validate_repository_root(root_descriptor)
        except OSError as exc:
            raise RetentionFsError("could not open private ledger directory") from exc
        with _open_relative_directory_path(
            root_descriptor,
            parts,
            flags,
            create=create,
            shared_state=True,
        ) as current:
            yield current
    finally:
        os.close(root_descriptor)


@contextmanager
def _open_relative_directory_path(
    parent_descriptor: int,
    parts: tuple[str, ...],
    flags: int,
    *,
    create: bool,
    shared_state: bool,
) -> Generator[int, None, None]:
    if not parts:
        yield parent_descriptor
        return
    part = parts[0]
    if not part or part in {".", ".."} or Path(part).name != part:
        raise RetentionFsError("ledger directory path is invalid")
    if create:
        try:
            with suppress(FileExistsError):
                os.mkdir(part, mode=0o700, dir_fd=parent_descriptor)
        except OSError as exc:
            raise RetentionFsError("could not open private ledger directory") from exc
    try:
        child_descriptor = os.open(part, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise RetentionFsError("could not open private ledger directory") from exc
    try:
        try:
            if shared_state:
                _validate_shared_state_directory(child_descriptor)
            else:
                _validate_private_directory(child_descriptor)
        except OSError as exc:
            raise RetentionFsError("could not open private ledger directory") from exc
        with _open_relative_directory_path(
            child_descriptor,
            parts[1:],
            flags,
            create=create,
            shared_state=False,
        ) as current:
            yield current
    finally:
        os.close(child_descriptor)


def _open_repository_root(repo_root: Path, flags: int) -> int:
    current = os.open(repo_root.anchor, flags)
    completed = False
    try:
        for part in repo_root.parts[1:]:
            child = os.open(part, flags, dir_fd=current)
            accepted = False
            try:
                _validate_parent_rename_authority(
                    os.fstat(current),
                    os.fstat(child),
                )
                accepted = True
            finally:
                if not accepted:
                    os.close(child)
            try:
                os.close(current)
            except OSError:
                os.close(child)
                raise
            current = child
        completed = True
        return current
    finally:
        if not completed:
            os.close(current)


def _validate_parent_rename_authority(
    parent: os.stat_result,
    child: os.stat_result,
) -> None:
    effective_user = os.geteuid()
    if parent.st_uid not in {0, effective_user}:
        raise FactoryBudgetLedgerError(
            "path",
            "repository ancestor permits cross-account replacement",
        )
    writable_by_other_accounts = bool(stat.S_IMODE(parent.st_mode) & 0o022)
    sticky = bool(parent.st_mode & stat.S_ISVTX)
    protected_child_owner = child.st_uid in {0, effective_user}
    if writable_by_other_accounts and not (sticky and protected_child_owner):
        raise FactoryBudgetLedgerError(
            "path",
            "repository ancestor permits cross-account replacement",
        )


def _validate_repository_root(directory_fd: int) -> None:
    metadata = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FactoryBudgetLedgerError(
            "path",
            "repository root must be owner-controlled",
        )


def _validate_shared_state_directory(directory_fd: int) -> None:
    metadata = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FactoryBudgetLedgerError(
            "path",
            "ledger shared state directory is unsafe",
        )


def _validate_private_directory(directory_fd: int) -> None:
    metadata = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.geteuid()
    ):
        raise FactoryBudgetLedgerError("path", "ledger state directory is unsafe")


def _nofollow_flag() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _directory_flag() -> int:
    return getattr(os, "O_DIRECTORY", 0)
