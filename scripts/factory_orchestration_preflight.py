"""Immutable proposal and live-authority orchestration preflight."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from scripts.factory_orchestration_authority import (
    validate_delivery_policy,
    validate_scheduler_authority,
)
from scripts.factory_orchestration_errors import OrchestrationGitError, OrchestrationServiceError
from scripts.factory_orchestration_git import (
    validate_inspected_scope,
    validate_main_base,
)
from scripts.factory_orchestration_journal import OrchestrationJournal
from scripts.factory_orchestration_models import OrchestrationReceipt, OrchestrationRequest
from scripts.factory_orchestration_receipts import git_reason, inspection_values
from scripts.factory_patch_inspection import PatchInspectionError, inspect_proposal_bytes


@dataclass(frozen=True, slots=True)
class Preflight:
    paths: tuple[str, ...]
    additions: int
    deletions: int
    terminal: OrchestrationReceipt | None


def preflight(root: Path, request: OrchestrationRequest, proposal: bytes) -> Preflight:
    if hashlib.sha256(proposal).hexdigest() != request.proposal_sha256:
        raise OrchestrationServiceError("proposal-drift")
    try:
        inspected = inspect_proposal_bytes(proposal)
        validate_inspected_scope(request, inspected, repo_root=root)
    except PatchInspectionError as exc:
        raise OrchestrationServiceError("proposal-invalid") from exc
    except OrchestrationGitError as exc:
        raise OrchestrationServiceError(git_reason(exc.code)) from exc
    paths, additions, deletions = inspection_values(inspected)
    database = root / ".entroping" / "factory-orchestration" / "orchestration.sqlite3"
    if database.is_file():
        terminal = OrchestrationJournal(root).terminal_receipt(request)
        if terminal is not None:
            return Preflight(paths, additions, deletions, terminal)
    validate_scheduler_authority(root, request)
    try:
        validate_main_base(root, request)
    except OrchestrationGitError as exc:
        raise OrchestrationServiceError(git_reason(exc.code)) from exc
    validate_delivery_policy(root, request)
    return Preflight(paths, additions, deletions, None)
