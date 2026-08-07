"""Trusted live-selection composition for scheduler delivery admission."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from scripts.factory_control_plane_policy import static_tier_a_doc_scope
from scripts.factory_issue_selector_core import select_issue
from scripts.factory_issue_selector_local import collect_active_state, scope_has_symlink
from scripts.factory_issue_selector_models import GitHubSnapshot, SelectionResult
from scripts.factory_orchestration_errors import OrchestrationGitError
from scripts.factory_orchestration_git_process import git_bytes, git_text
from scripts.factory_policy_import_closure import (
    PolicyImportError,
    PolicySource,
    committed_policy_sources,
    policy_import_closure,
    policy_module_name,
)
from scripts.factory_scheduler_models import AssignmentRequest, DeliveryAuthorityEnvelope

_POLICY_ID = "entroping.factory-delivery-selector-policy.v1"
_policy_import_closure = policy_import_closure
_POLICY_ENTRY_ROOTS = (
    "scripts/factory_scheduler_delivery.py",
)


@dataclass(frozen=True, slots=True)
class _DeliveryAdmission:
    snapshot: GitHubSnapshot
    expected_result_digest: str
    expected_envelope: DeliveryAuthorityEnvelope


class DeliveryAdmissionError(RuntimeError):
    pass


def _prepare_delivery_admission(
    root: Path,
    request: AssignmentRequest,
    snapshot: GitHubSnapshot,
    *,
    active_issues: frozenset[int],
    active_scopes: tuple[str, ...] = (),
    active_state_complete: bool = True,
    as_of: datetime,
) -> tuple[AssignmentRequest, _DeliveryAdmission]:
    if request.delivery_authority is not None or request.access_mode != "write":
        raise DeliveryAdmissionError("selection-invalid")
    result = _selection(
        root,
        snapshot,
        active_issues=active_issues,
        active_scopes=active_scopes,
        active_state_complete=active_state_complete,
        as_of=as_of,
    )
    selected = result.selected
    if selected is None or selected.issue_number != request.issue_number:
        raise DeliveryAdmissionError("selection-invalid")
    if selected.autonomy_tier != "tier-a" or selected.verification_lane not in {
        "tiny-docs",
        "docs-guardrail",
    }:
        raise DeliveryAdmissionError("selection-invalid")
    if any(
        not static_tier_a_doc_scope(scope, repo_root=root)
        for scope in selected.allowed_scopes
    ):
        raise DeliveryAdmissionError("selection-invalid")
    encoded_scopes = json.dumps(list(selected.allowed_scopes), separators=(",", ":")).encode()
    result_digest = _result_digest(result)
    envelope = DeliveryAuthorityEnvelope.model_validate(
        {
            "selector_digest": selector_policy_digest(root),
            "selection_digest": result_digest,
            "autonomy_tier": selected.autonomy_tier,
            "verification_lane": selected.verification_lane,
            "allowed_scopes": selected.allowed_scopes,
            "allowed_scope_digest": hashlib.sha256(encoded_scopes).hexdigest(),
        },
        strict=True,
    )
    return (
        request.model_copy(update={"delivery_authority": envelope}),
        _DeliveryAdmission(
            snapshot,
            result_digest,
            envelope,
        ),
    )


def _revalidate_delivery_admission(
    connection: sqlite3.Connection,
    root: Path,
    request: AssignmentRequest,
    admission: _DeliveryAdmission,
    *,
    as_of: datetime,
) -> bool:
    from scripts.factory_scheduler_active_state import active_delivery_state

    try:
        active = active_delivery_state(connection)
        if not active.complete:
            return False
        result = _selection(
            root,
            admission.snapshot,
            active_issues=active.issue_numbers,
            active_scopes=active.scopes,
            active_state_complete=active.complete,
            as_of=as_of,
        )
        return (
            _result_digest(result) == admission.expected_result_digest
            and request.delivery_authority == admission.expected_envelope
            and selector_policy_digest(root)
            == admission.expected_envelope.selector_digest
        )
    except (DeliveryAdmissionError, OrchestrationGitError):
        return False


def selector_policy_digest(root: Path) -> str:
    """Bind policy identity to canonical main and its fixed trusted source allowlist."""

    commit, sources = _verified_policy_sources(root)
    digest = hashlib.sha256()
    digest.update(_POLICY_ID.encode())
    digest.update(commit.encode())
    for source in sources:
        digest.update(source.path.encode())
        digest.update(source.content)
    return digest.hexdigest()


def _verified_policy_sources(root: Path) -> tuple[str, tuple[PolicySource, ...]]:
    commit = git_text(root, "rev-parse", "refs/heads/main")
    listing = git_text(root, "worktree", "list", "--porcelain")
    first = listing.split("\n\n", maxsplit=1)[0].splitlines()
    paths = [line.removeprefix("worktree ") for line in first if line.startswith("worktree ")]
    if len(paths) != 1:
        raise DeliveryAdmissionError("selection-invalid")
    try:
        canonical = Path(paths[0]).resolve(strict=True)
    except OSError as exc:
        raise DeliveryAdmissionError("selection-invalid") from exc
    if git_text(canonical, "rev-parse", "HEAD") != commit:
        raise DeliveryAdmissionError("selection-invalid")
    if git_bytes(
        canonical,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ):
        raise DeliveryAdmissionError("selection-invalid")
    try:
        sources = committed_policy_sources(
            root,
            commit=commit,
            roots=_POLICY_ENTRY_ROOTS,
        )
    except PolicyImportError as exc:
        raise DeliveryAdmissionError("selection-invalid") from exc
    for source in sources:
        module = sys.modules.get(policy_module_name(source.path))
        if module is None:
            continue
        loaded_path = module.__file__
        if loaded_path is None:
            raise DeliveryAdmissionError("selection-invalid")
        try:
            observed = Path(loaded_path).resolve(strict=True).read_bytes()
        except OSError as exc:
            raise DeliveryAdmissionError("selection-invalid") from exc
        if observed != source.content:
            raise DeliveryAdmissionError("selection-invalid")
    return commit, sources


def _selection(
    root: Path,
    snapshot: GitHubSnapshot,
    *,
    active_issues: frozenset[int],
    active_scopes: tuple[str, ...],
    active_state_complete: bool,
    as_of: datetime,
) -> SelectionResult:
    freshness = snapshot.metadata.freshness_error(as_of)
    if freshness is not None:
        raise DeliveryAdmissionError("selection-invalid")
    active = collect_active_state(
        repo_root=root,
        snapshot=snapshot,
        lease_state_complete=active_state_complete,
        lease_issue_numbers=active_issues,
        lease_scopes=active_scopes,
    )
    issues = tuple(
        replace(issue, allowed_scopes=())
        if any(scope_has_symlink(root, scope) for scope in issue.allowed_scopes)
        else issue
        for issue in snapshot.issues
    )
    return select_issue(
        issues=issues,
        snapshot=snapshot.metadata,
        active=active,
        as_of=as_of,
        autonomy_ceiling="tier-a",
    )


def _result_digest(result: SelectionResult) -> str:
    encoded = json.dumps(result.to_payload(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
