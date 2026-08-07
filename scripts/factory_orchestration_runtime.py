"""Worktree creation and main-checkout preservation helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.bounded_process import BoundedProcessError, run_bounded_process
from scripts.factory_orchestration_errors import OrchestrationServiceError
from scripts.factory_orchestration_git_process import checkout_identity_sha256
from scripts.factory_orchestration_journal import OrchestrationJournal
from scripts.factory_orchestration_models import Lifecycle, OrchestrationRequest
from scripts.factory_orchestration_tools import trusted_tool_path


def start_issue(
    root: Path,
    request: OrchestrationRequest,
    *,
    cancelled: Callable[[], bool],
) -> None:
    """Delegate canonical worktree creation to the repository script."""

    validate_creation_target(root, request)
    script = root / "scripts" / "start_issue.sh"
    try:
        result = run_bounded_process(
            (
                "/bin/bash",
                str(script),
                str(request.issue_number),
                request.branch,
                "--base-commit",
                request.base_commit,
            ),
            cwd=root,
            timeout_seconds=300,
            max_output_bytes=1_048_576,
            env={
                "PATH": trusted_tool_path(("uv", "gh")),
                "LC_ALL": "C",
                "LANG": "C",
            },
            capture_stdout=False,
            cancelled=cancelled,
        )
    except BoundedProcessError as exc:
        raise OrchestrationServiceError("worktree-mismatch") from exc
    if result.cancelled:
        raise OrchestrationServiceError("cancelled")
    if result.returncode != 0 or result.timed_out or result.output_limit_exceeded:
        raise OrchestrationServiceError("worktree-mismatch")


def validate_creation_target(root: Path, request: OrchestrationRequest) -> None:
    """Reject noncanonical creation targets before lifecycle intent is written."""

    expected_path = root.parent / f"Entroping-issue-{request.issue_number}"
    if Path(request.worktree_path) != expected_path:
        raise OrchestrationServiceError("worktree-mismatch")


def ensure_main_or_uncertain(
    journal: OrchestrationJournal,
    request: OrchestrationRequest,
    expected_lifecycle: Lifecycle,
    root: Path,
    expected_identity: str,
) -> None:
    if checkout_identity_sha256(root) == expected_identity:
        return
    _ = journal.transition(
        request,
        expected=expected_lifecycle,
        lifecycle="uncertain",
        reason="interrupted",
    )
    raise OrchestrationServiceError("uncertain-recovery-required")
