"""Maintainer-only Tier A worktree orchestration composition."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.factory_orchestration_authority import (
    authority_and_integrity,
    validate_scheduler_authority,
)
from scripts.factory_orchestration_errors import OrchestrationGitError, OrchestrationServiceError
from scripts.factory_orchestration_gates import (
    GateRunError,
    commands_for_lane,
    run_gate_commands,
)
from scripts.factory_orchestration_git import (
    apply_exact_patch,
    validate_reusable_worktree,
)
from scripts.factory_orchestration_git_process import checkout_identity_sha256
from scripts.factory_orchestration_journal import OrchestrationJournal
from scripts.factory_orchestration_models import (
    Lifecycle,
    OrchestrationReceipt,
    OrchestrationRequest,
    ReasonCode,
)
from scripts.factory_orchestration_preflight import preflight
from scripts.factory_orchestration_receipts import (
    build_receipt,
    gate_reason,
    git_reason,
)
from scripts.factory_orchestration_runtime import (
    ensure_main_or_uncertain,
    start_issue,
    validate_creation_target,
)
from scripts.factory_scheduler_root import SchedulerRootError, resolve_scheduler_root


def orchestrate(
    repo_root: Path,
    request: OrchestrationRequest,
    proposal: bytes,
    *,
    apply: bool,
    cancelled: Callable[[], bool] = lambda: False,
) -> OrchestrationReceipt:
    """Plan or apply one scheduler-owned immutable orchestration request."""

    try:
        root = resolve_scheduler_root(repo_root)
    except SchedulerRootError as exc:
        raise OrchestrationServiceError("authority-mismatch") from exc
    checked = preflight(root, request, proposal)
    approved_paths = checked.paths
    additions = checked.additions
    deletions = checked.deletions
    if checked.terminal is not None:
        return checked.terminal
    if not apply:
        if Path(request.worktree_path).exists():
            _ = validate_reusable_worktree(root, request)
        else:
            validate_creation_target(root, request)
        return build_receipt(
            request,
            lifecycle="prepared",
            reason="plan-only",
            authoritative=False,
            paths=approved_paths,
            additions=additions,
            deletions=deletions,
        )

    journal = OrchestrationJournal(root)
    main_identity = checkout_identity_sha256(root)
    target_exists = Path(request.worktree_path).exists()
    if target_exists:
        _ = validate_reusable_worktree(root, request)
    else:
        validate_creation_target(root, request)
    prepared = journal.prepare(request)
    if prepared.receipt is not None:
        return prepared.receipt
    if not target_exists:
        try:
            start_issue(root, request, cancelled=cancelled)
            _ = validate_reusable_worktree(root, request)
        except (OrchestrationGitError, OrchestrationServiceError, OSError) as exc:
            _ = journal.transition(
                request,
                expected="prepared",
                lifecycle="uncertain",
                reason="interrupted",
            )
            raise OrchestrationServiceError("uncertain-recovery-required") from exc
        ensure_main_or_uncertain(journal, request, "prepared", root, main_identity)
    if cancelled():
        receipt = build_receipt(
            request,
            lifecycle="cancelled",
            reason="cancelled",
            authoritative=True,
            paths=approved_paths,
            additions=additions,
            deletions=deletions,
        )
        ensure_main_or_uncertain(journal, request, "prepared", root, main_identity)
        _ = journal.transition(
            request,
            expected="prepared",
            lifecycle="cancelled",
            receipt=receipt,
        )
        return receipt
    validate_scheduler_authority(root, request)
    _ = journal.transition(request, expected="prepared", lifecycle="applying")
    try:
        truth = apply_exact_patch(root, request, proposal, cancelled=cancelled)
    except OrchestrationGitError as exc:
        if exc.code == "interrupted":
            _ = journal.transition(
                request,
                expected="applying",
                lifecycle="uncertain",
                reason="interrupted",
            )
            raise OrchestrationServiceError("uncertain-recovery-required") from exc
        reason: ReasonCode = "cancelled" if exc.code == "cancelled" else git_reason(exc.code)
        lifecycle: Lifecycle = "cancelled" if reason == "cancelled" else "failed"
        receipt = build_receipt(
            request,
            lifecycle=lifecycle,
            reason=reason,
            authoritative=True,
            paths=approved_paths,
            additions=additions,
            deletions=deletions,
        )
        ensure_main_or_uncertain(journal, request, "applying", root, main_identity)
        _ = journal.transition(
            request,
            expected="applying",
            lifecycle=lifecycle,
            receipt=receipt,
        )
        return receipt
    ensure_main_or_uncertain(journal, request, "applying", root, main_identity)
    _ = journal.transition(request, expected="applying", lifecycle="applied")
    try:
        validate_scheduler_authority(root, request)
    except OrchestrationServiceError as exc:
        _ = journal.transition(
            request,
            expected="applied",
            lifecycle="uncertain",
            reason="interrupted",
        )
        raise OrchestrationServiceError("uncertain-recovery-required") from exc
    _ = journal.transition(request, expected="applied", lifecycle="gating")
    selected_commands = commands_for_lane(
        request.verification_lane,
        repo_root=Path(request.worktree_path),
    )
    try:
        gate_results = run_gate_commands(
            selected_commands,
            cwd=Path(request.worktree_path),
            cancelled=cancelled,
            integrity_check=lambda: authority_and_integrity(
                root, request, truth, main_identity=main_identity
            ),
        )
    except GateRunError as exc:
        if exc.code == "gate-drift":
            _ = journal.transition(
                request,
                expected="gating",
                lifecycle="uncertain",
                reason="interrupted",
            )
            raise OrchestrationServiceError("uncertain-recovery-required") from exc
        lifecycle = "cancelled" if exc.code == "cancelled" else "failed"
        reason = gate_reason(exc.code)
        receipt = build_receipt(
            request,
            lifecycle=lifecycle,
            reason=reason,
            authoritative=True,
            paths=approved_paths,
            additions=additions,
            deletions=deletions,
            truth=truth,
            gates=exc.results,
        )
        ensure_main_or_uncertain(journal, request, "gating", root, main_identity)
        _ = journal.transition(
            request,
            expected="gating",
            lifecycle=lifecycle,
            receipt=receipt,
        )
        return receipt
    if not authority_and_integrity(root, request, truth):
        _ = journal.transition(
            request,
            expected="gating",
            lifecycle="uncertain",
            reason="interrupted",
        )
        raise OrchestrationServiceError("uncertain-recovery-required")
    ensure_main_or_uncertain(journal, request, "gating", root, main_identity)
    receipt = build_receipt(
        request,
        lifecycle="accepted",
        reason="accepted",
        authoritative=True,
        paths=approved_paths,
        additions=additions,
        deletions=deletions,
        truth=truth,
        gates=gate_results,
    )
    _ = journal.transition(
        request,
        expected="gating",
        lifecycle="accepted",
        receipt=receipt,
    )
    return receipt
