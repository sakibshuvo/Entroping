"""Strict value-free contracts for maintainer Tier A orchestration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scripts.factory_control_plane_policy import normalize_repo_path
from scripts.factory_scheduler_models import (
    AssignmentId,
    Identifier,
    PositiveEpoch,
    ProcessToken,
    WorktreeId,
)

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Branch = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]
Count = Annotated[int, Field(ge=0, le=1_000_000)]
type Lifecycle = Literal[
    "prepared",
    "applying",
    "applied",
    "gating",
    "accepted",
    "failed",
    "cancelled",
    "uncertain",
]
type VerificationLane = Literal[
    "tiny-docs",
    "docs-guardrail",
    "tests-only",
    "normal-code",
    "security-runtime",
    "release-ci-architecture",
]
type GateState = Literal["passed", "failed", "timed-out", "output-exceeded", "cancelled"]
type ReasonCode = Literal[
    "plan-only",
    "accepted",
    "request-conflict",
    "authority-mismatch",
    "worktree-mismatch",
    "worktree-dirty",
    "stale-base",
    "proposal-invalid",
    "proposal-drift",
    "scope-denied",
    "patch-check-failed",
    "patch-apply-failed",
    "post-apply-mismatch",
    "gate-failed",
    "gate-timeout",
    "gate-output-exceeded",
    "gate-drift",
    "cancelled",
    "interrupted",
    "uncertain-recovery-required",
]


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )


class OrchestrationRequest(StrictModel):
    schema_version: Literal["entroping.factory-orchestration-request.v1"]
    request_id: Identifier
    issue_number: Annotated[int, Field(ge=1, le=2_147_483_647)]
    job_id: Identifier
    assignment_id: AssignmentId
    scheduler_owner_id: Identifier
    scheduler_owner_pid: Annotated[int, Field(ge=1, le=2_147_483_647)]
    scheduler_owner_start_token: ProcessToken
    scheduler_owner_epoch: PositiveEpoch
    selector_digest: Digest
    selection_digest: Digest
    worktree_id: WorktreeId
    autonomy_tier: Literal["tier-a"]
    verification_lane: VerificationLane
    allowed_scopes: Annotated[tuple[str, ...], Field(min_length=1, max_length=128)]
    allowed_scope_digest: Digest
    worktree_path: str
    branch: Branch
    common_git_dir: str
    base_commit: Commit
    proposal_path: str
    proposal_sha256: Digest

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.branch in {"main", "master"}:
            raise ValueError("orchestration branch must be non-main")
        for raw in (self.worktree_path, self.common_git_dir, self.proposal_path):
            path = Path(raw)
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("orchestration paths must be absolute and normalized")
        normalized = tuple(normalize_repo_path(scope) for scope in self.allowed_scopes)
        if any(scope is None for scope in normalized):
            raise ValueError("allowed scopes must be normalized repository paths")
        if normalized != self.allowed_scopes:
            raise ValueError("allowed scopes must use their canonical spelling")
        if tuple(sorted(set(self.allowed_scopes))) != self.allowed_scopes:
            raise ValueError("allowed scopes must be unique and sorted")
        if _scope_digest(self.allowed_scopes) != self.allowed_scope_digest:
            raise ValueError("allowed scope digest does not match its scopes")
        return self

    @property
    def request_digest(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class GateExitState(StrictModel):
    name: Identifier
    command_id: Identifier
    exit_code: Annotated[int, Field(ge=0, le=255)] | None
    signal_number: Annotated[int, Field(ge=1, le=255)] | None
    state: GateState
    stdout_sha256: Digest
    stderr_sha256: Digest
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_exit(self) -> Self:
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("gate timestamps must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("gate timestamps must be monotonic")
        if self.exit_code is not None and self.signal_number is not None:
            raise ValueError("gate exit and signal states are mutually exclusive")
        if self.state == "passed" and (self.exit_code != 0 or self.signal_number is not None):
            raise ValueError("passed gate must have exit code zero")
        if self.state == "failed" and (self.exit_code in {None, 0} and self.signal_number is None):
            raise ValueError("failed gate requires a nonzero exit or signal")
        if self.state != "passed" and self.exit_code == 0:
            raise ValueError("non-passing gate cannot have exit code zero")
        return self


class OrchestrationReceipt(StrictModel):
    schema_version: Literal["entroping.factory-orchestration-receipt.v1"] = (
        "entroping.factory-orchestration-receipt.v1"
    )
    receipt_id: Annotated[
        str,
        StringConstraints(pattern=r"^orchestration_[a-f0-9]{64}$"),
    ]
    request_id: Identifier
    request_digest: Digest
    issue_number: Annotated[int, Field(ge=1, le=2_147_483_647)]
    job_id: Identifier
    assignment_id: AssignmentId
    scheduler_owner_id: Identifier
    scheduler_owner_epoch: PositiveEpoch
    selector_digest: Digest
    selection_digest: Digest
    worktree_id: WorktreeId
    worktree_path_sha256: Digest
    branch: Branch
    verification_lane: VerificationLane
    lifecycle: Lifecycle
    reason: ReasonCode
    authoritative: bool
    proposal_sha256: Digest
    allowed_scope_digest: Digest
    base_commit: Commit
    result_head: Commit | None
    result_manifest_sha256: Digest | None
    diff_sha256: Digest | None
    approved_paths: Annotated[tuple[str, ...], Field(max_length=128)]
    files_changed: Count
    additions: Count
    deletions: Count
    gate_exit_states: Annotated[tuple[GateExitState, ...], Field(max_length=8)]

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        accepted = self.lifecycle == "accepted"
        if accepted != (self.reason == "accepted"):
            raise ValueError("receipt lifecycle and reason are inconsistent")
        if accepted and (
            not self.authoritative
            or self.result_head is None
            or self.result_manifest_sha256 is None
            or self.diff_sha256 is None
            or not self.gate_exit_states
            or any(gate.state != "passed" for gate in self.gate_exit_states)
        ):
            raise ValueError("accepted receipt requires authoritative revision binding")
        if self.reason == "plan-only" and (self.authoritative or self.lifecycle != "prepared"):
            raise ValueError("plan-only receipt must remain non-authoritative and prepared")
        payload = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != receipt_id_for_payload(payload):
            raise ValueError("receipt identity digest is invalid")
        return self


def _scope_digest(scopes: tuple[str, ...]) -> str:
    encoded = json.dumps(list(scopes), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def receipt_id_for_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"orchestration_{hashlib.sha256(encoded).hexdigest()}"
