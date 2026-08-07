"""Adapter for strict delivery terminal replay through finish_issue.sh."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_orchestration_errors import OrchestrationServiceError
from scripts.factory_orchestration_tools import trusted_tool_path
from scripts.factory_pr_delivery_github import REPOSITORY
from scripts.factory_pr_delivery_github_io import GitHubTransportError, trusted_gh_contract
from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_terminal_receipt,
    validate_record,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_pr_delivery_receipts import DeliveryReceipt

__all__ = ["DeliveryCleanupError", "run_strict_finish_issue"]


class DeliveryCleanupError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


_FINISH_SCRIPT = "finish_issue.sh"
_FINISH_HELPERS = (
    "_project_board_lib.sh",
    "factory_metrics_archive.py",
    "finish_issue_replay_evidence.py",
)
_FINISH_TIMEOUT_SECONDS = 300.0
_FINISH_MAX_OUTPUT_BYTES = 1_048_576
_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
)


def _fixed_finish_environment() -> dict[str, str]:
    try:
        _, gh_environment = trusted_gh_contract()
        tool_path = trusted_tool_path(("uv", "gh"))
    except (GitHubTransportError, OrchestrationServiceError):
        raise DeliveryCleanupError("cleanup-invalid") from None
    try:
        home = Path(gh_environment["HOME"]).resolve()
    except (KeyError, TypeError, OSError, RuntimeError):
        raise DeliveryCleanupError("cleanup-invalid") from None

    owner, _repository = REPOSITORY.split("/", 1)
    return {
        "HOME": str(home),
        "PATH": tool_path,
        "LC_ALL": gh_environment.get("LC_ALL", "C"),
        "LANG": gh_environment.get("LANG", "C"),
        "GIT_PAGER": "cat",
        "GH_PAGER": gh_environment.get("GH_PAGER", "cat"),
        "GH_FORCE_TTY": gh_environment.get("GH_FORCE_TTY", "0"),
        "NO_COLOR": gh_environment.get("NO_COLOR", "1"),
        "ENTROPING_REPO": REPOSITORY,
        "ENTROPING_PROJECT_OWNER": owner,
        "ENTROPING_PROJECT_NUMBER": "1",
    }


def _require_safe_directory(descriptor: int) -> None:
    try:
        metadata = _descriptor_metadata(descriptor)
    except (OSError, RuntimeError) as exc:
        raise DeliveryCleanupError("cleanup-invalid") from exc
    unsafe_mode = stat.S_IMODE(metadata.st_mode) & (
        stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID
    )
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or unsafe_mode
    ):
        raise DeliveryCleanupError("cleanup-invalid")


def _require_safe_script(descriptor: int) -> None:
    try:
        metadata = _descriptor_metadata(descriptor)
    except (OSError, RuntimeError) as exc:
        raise DeliveryCleanupError("cleanup-invalid") from exc
    unsafe_mode = stat.S_IMODE(metadata.st_mode) & (
        stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID
    )
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or unsafe_mode
    ):
        raise DeliveryCleanupError("cleanup-invalid")


def _descriptor_metadata(descriptor: int) -> os.stat_result:
    return os.fstat(descriptor)


@contextmanager
def _trusted_finish_descriptors(
    repo_root: Path,
) -> Iterator[tuple[int, int, int, int]]:
    descriptors: list[int] = []
    try:
        root_fd = os.open(repo_root, _DIRECTORY_OPEN_FLAGS)
        descriptors.append(root_fd)
        _require_safe_directory(root_fd)
        scripts_fd = os.open("scripts", _DIRECTORY_OPEN_FLAGS, dir_fd=root_fd)
        descriptors.append(scripts_fd)
        _require_safe_directory(scripts_fd)
        script_fd = os.open(_FINISH_SCRIPT, _FILE_OPEN_FLAGS, dir_fd=scripts_fd)
        descriptors.append(script_fd)
        _require_safe_script(script_fd)
        helper_fds: list[int] = []
        for helper in _FINISH_HELPERS:
            helper_fd = os.open(helper, _FILE_OPEN_FLAGS, dir_fd=scripts_fd)
            descriptors.append(helper_fd)
            _require_safe_script(helper_fd)
            helper_fds.append(helper_fd)
        yield script_fd, helper_fds[0], helper_fds[1], helper_fds[2]
    except OSError:
        raise DeliveryCleanupError("cleanup-invalid") from None
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def run_strict_finish_issue(
    repo_root: Path,
    envelope: DeliveryEnvelope,
    record: DeliveryJournalRecord,
) -> None:
    try:
        resolved_root = repo_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DeliveryCleanupError("cleanup-invalid") from exc
    try:
        resolved_envelope_root = envelope.main_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DeliveryCleanupError("cleanup-invalid") from exc
    if resolved_envelope_root != resolved_root:
        raise DeliveryCleanupError("cleanup-invalid")
    try:
        validate_record(envelope, record)
        terminal = read_terminal_receipt(record)
    except DeliveryJournalError:
        raise DeliveryCleanupError("cleanup-invalid") from None
    if terminal is None:
        raise DeliveryCleanupError("cleanup-invalid")
    if not _is_strict_terminal_receipt(terminal):
        raise DeliveryCleanupError("cleanup-invalid")
    if terminal.pr_number is None or terminal.merge_head is None:
        raise DeliveryCleanupError("cleanup-invalid")
    if terminal.pr_number != record.merge_pr_number:
        raise DeliveryCleanupError("cleanup-invalid")
    if terminal.merge_head != record.merge_head:
        raise DeliveryCleanupError("cleanup-invalid")
    if terminal.ci_digest != record.merge_ci_digest:
        raise DeliveryCleanupError("cleanup-invalid")
    merge_head = terminal.merge_head

    issue_number = str(envelope.orchestration_request.issue_number)
    with _trusted_finish_descriptors(resolved_root) as (
        script_fd,
        project_lib_fd,
        metrics_fd,
        replay_fd,
    ):
        command = (
            "/bin/bash",
            f"/dev/fd/{script_fd}",
            issue_number,
            "--worktree",
            str(envelope.worktree_path),
            "--expected-pr",
            str(record.merge_pr_number),
            "--expected-head",
            merge_head,
            "--expected-branch",
            envelope.orchestration_request.branch,
        )
        environment = _fixed_finish_environment()
        environment.update(
            {
                "ENTROPING_FINISH_PROJECT_LIB": f"/dev/fd/{project_lib_fd}",
                "ENTROPING_FINISH_METRICS_HELPER": f"/dev/fd/{metrics_fd}",
                "ENTROPING_FINISH_REPLAY_HELPER": f"/dev/fd/{replay_fd}",
            }
        )
        try:
            result = run_bounded_process(
                command,
                cwd=resolved_root,
                timeout_seconds=_FINISH_TIMEOUT_SECONDS,
                max_output_bytes=_FINISH_MAX_OUTPUT_BYTES,
                input_bytes=None,
                env=environment,
                capture_stdout=False,
                pass_fds=(script_fd, project_lib_fd, metrics_fd, replay_fd),
            )
        except BoundedProcessError:
            raise DeliveryCleanupError("cleanup-uncertain") from None

    if (
        result.returncode != 0
        or result.timed_out
        or result.output_limit_exceeded
        or result.cancelled
    ):
        raise DeliveryCleanupError("cleanup-uncertain")


def _is_strict_terminal_receipt(receipt: DeliveryReceipt) -> bool:
    return (
        receipt.authoritative
        and receipt.lifecycle == "merged"
        and receipt.reason == "cleanup-pending"
        and receipt.pr_number is not None
        and receipt.committed_head is not None
        and receipt.merge_head is not None
        and receipt.merge_head == receipt.committed_head
    )
