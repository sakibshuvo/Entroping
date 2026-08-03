"""Deterministic value-free orchestration receipt construction."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.factory_orchestration_errors import OrchestrationServiceError
from scripts.factory_orchestration_git import PatchTruth
from scripts.factory_orchestration_models import (
    GateExitState,
    Lifecycle,
    OrchestrationReceipt,
    OrchestrationRequest,
    ReasonCode,
    receipt_id_for_payload,
)


def build_receipt(
    request: OrchestrationRequest,
    *,
    lifecycle: Lifecycle,
    reason: ReasonCode,
    authoritative: bool,
    paths: tuple[str, ...],
    additions: int,
    deletions: int,
    truth: PatchTruth | None = None,
    gates: tuple[GateExitState, ...] = (),
) -> OrchestrationReceipt:
    payload: dict[str, object] = {
        "schema_version": "entroping.factory-orchestration-receipt.v1",
        "request_id": request.request_id,
        "request_digest": request.request_digest,
        "issue_number": request.issue_number,
        "job_id": request.job_id,
        "assignment_id": request.assignment_id,
        "scheduler_owner_id": request.scheduler_owner_id,
        "scheduler_owner_epoch": request.scheduler_owner_epoch,
        "selector_digest": request.selector_digest,
        "selection_digest": request.selection_digest,
        "worktree_id": request.worktree_id,
        "worktree_path_sha256": hashlib.sha256(
            str(Path(request.worktree_path).resolve()).encode()
        ).hexdigest(),
        "branch": request.branch,
        "verification_lane": request.verification_lane,
        "lifecycle": lifecycle,
        "reason": reason,
        "authoritative": authoritative,
        "proposal_sha256": request.proposal_sha256,
        "allowed_scope_digest": request.allowed_scope_digest,
        "base_commit": request.base_commit,
        "result_head": None if truth is None else truth.head,
        "result_manifest_sha256": None if truth is None else truth.manifest_sha256,
        "diff_sha256": None if truth is None else truth.diff_sha256,
        "approved_paths": paths,
        "files_changed": len(paths),
        "additions": additions,
        "deletions": deletions,
        "gate_exit_states": gates,
    }
    identity_payload = {
        **payload,
        "gate_exit_states": [gate.model_dump(mode="json") for gate in gates],
    }
    return OrchestrationReceipt.model_validate(
        {"receipt_id": receipt_id_for_payload(identity_payload), **payload}, strict=True
    )


def inspection_values(inspected: dict[str, object]) -> tuple[tuple[str, ...], int, int]:
    paths = inspected.get("changed_files")
    additions = inspected.get("additions")
    deletions = inspected.get("deletions")
    if (
        not isinstance(paths, list)
        or not all(isinstance(path, str) for path in paths)
        or not isinstance(additions, int)
        or not isinstance(deletions, int)
    ):
        raise OrchestrationServiceError("proposal-invalid")
    return tuple(sorted(set(paths))), additions, deletions


def git_reason(code: str) -> ReasonCode:
    reasons: dict[str, ReasonCode] = {
        "worktree-mismatch": "worktree-mismatch",
        "worktree-dirty": "worktree-dirty",
        "stale-base": "stale-base",
        "proposal-invalid": "proposal-invalid",
        "scope-denied": "scope-denied",
        "patch-check-failed": "patch-check-failed",
        "patch-apply-failed": "patch-apply-failed",
        "post-apply-mismatch": "post-apply-mismatch",
    }
    return reasons.get(code, "post-apply-mismatch")


def gate_reason(code: str) -> ReasonCode:
    reasons: dict[str, ReasonCode] = {
        "gate-failed": "gate-failed",
        "gate-timeout": "gate-timeout",
        "gate-output-exceeded": "gate-output-exceeded",
        "gate-drift": "gate-drift",
        "cancelled": "cancelled",
    }
    return reasons.get(code, "gate-failed")
