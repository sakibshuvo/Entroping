from __future__ import annotations

import hashlib
import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

models = importlib.import_module("scripts.factory_orchestration_models")
receipts = importlib.import_module("scripts.factory_orchestration_receipts")
git_boundary = importlib.import_module("scripts.factory_orchestration_git")


def _scope_digest(scopes: tuple[str, ...]) -> str:
    payload = json.dumps(list(scopes), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def request_payload(tmp_path: Path) -> dict[str, object]:
    scopes = ("docs/user/example.md",)
    return {
        "schema_version": "entroping.factory-orchestration-request.v1",
        "request_id": "orchestrate-1574-1",
        "issue_number": 1574,
        "job_id": "implementation-1574-1",
        "assignment_id": f"assign_{'1' * 64}",
        "scheduler_owner_id": "factory-owner-1",
        "scheduler_owner_pid": 10001,
        "scheduler_owner_start_token": f"proc_{1:064x}",
        "scheduler_owner_epoch": 7,
        "selector_digest": "8" * 64,
        "selection_digest": "9" * 64,
        "worktree_id": f"wt_{'2' * 64}",
        "autonomy_tier": "tier-a",
        "verification_lane": "tiny-docs",
        "allowed_scopes": scopes,
        "allowed_scope_digest": _scope_digest(scopes),
        "worktree_path": str(tmp_path / "Entroping-issue-1574"),
        "branch": "feat/example",
        "common_git_dir": str(tmp_path / "repo" / ".git"),
        "base_commit": "a" * 40,
        "proposal_path": str(tmp_path / "private" / "proposal.diff"),
        "proposal_sha256": "b" * 64,
    }


def test_request_is_frozen_and_digest_bound(tmp_path: Path) -> None:
    # Given: a complete immutable Tier A orchestration identity.
    subject = models.OrchestrationRequest.model_validate(request_payload(tmp_path), strict=True)

    # When/Then: its digest is stable and fields cannot be changed after parsing.
    assert len(subject.request_digest) == 64
    with pytest.raises(ValidationError):
        subject.issue_number = 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("autonomy_tier", "tier-b"),
        ("base_commit", "abc"),
        ("proposal_sha256", "ABC"),
        ("branch", "main"),
        ("worktree_path", "relative/path"),
        ("allowed_scopes", ["../escape.py"]),
        ("allowed_scope_digest", "0" * 64),
    ],
)
def test_request_rejects_identity_and_scope_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    # Given: one malformed immutable authority field.
    payload = request_payload(tmp_path)
    payload[field] = value

    # When/Then: strict parsing fails closed.
    with pytest.raises(ValidationError):
        models.OrchestrationRequest.model_validate(payload, strict=True)


def test_receipt_is_value_free_and_revision_bound(tmp_path: Path) -> None:
    # Given: one accepted lifecycle result built only from identities and counts.
    request = models.OrchestrationRequest.model_validate(request_payload(tmp_path), strict=True)
    gate = models.GateExitState(
        name="focused-tests",
        command_id="pytest-factory-orchestration-v1",
        exit_code=0,
        signal_number=None,
        state="passed",
        stdout_sha256="6" * 64,
        stderr_sha256="7" * 64,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    receipt = receipts.build_receipt(
        request,
        lifecycle="accepted",
        reason="accepted",
        authoritative=True,
        paths=("docs/user/example.md",),
        additions=1,
        deletions=0,
        truth=git_boundary.PatchTruth(
            head=request.base_commit,
            manifest_sha256="5" * 64,
            diff_sha256="4" * 64,
            paths=("docs/user/example.md",),
            status_sha256="3" * 64,
        ),
        gates=(gate,),
    )

    # When: the public receipt is serialized.
    encoded = receipt.model_dump_json()

    # Then: it contains no worker values, transcripts, environment, or patch body.
    assert len(encoded) < 4096
    for forbidden in ("raw_stdout", "raw_stderr", "transcript", "environment", "patch_body"):
        assert forbidden not in encoded.casefold()


def test_request_rejects_noncanonical_scope_alias(tmp_path: Path) -> None:
    # Given: a scope whose normalized meaning differs from its raw spelling.
    payload = request_payload(tmp_path)
    scopes = ("src//entroping/example.py", "tests/test_example.py")
    payload["allowed_scopes"] = scopes
    payload["allowed_scope_digest"] = _scope_digest(scopes)

    # When/Then: aliases cannot become accepted authority.
    with pytest.raises(ValidationError):
        models.OrchestrationRequest.model_validate(payload, strict=True)


def test_receipt_rejects_inconsistent_acceptance_state(tmp_path: Path) -> None:
    # Given: an accepted reason paired with a non-accepted lifecycle.
    request = models.OrchestrationRequest.model_validate(request_payload(tmp_path), strict=True)

    # When/Then: the impossible receipt state cannot be constructed.
    with pytest.raises(ValidationError):
        models.OrchestrationReceipt(
            receipt_id=f"orchestration_{'3' * 64}",
            request_id=request.request_id,
            request_digest=request.request_digest,
            issue_number=request.issue_number,
            job_id=request.job_id,
            assignment_id=request.assignment_id,
            scheduler_owner_id=request.scheduler_owner_id,
            scheduler_owner_epoch=request.scheduler_owner_epoch,
            selector_digest=request.selector_digest,
            selection_digest=request.selection_digest,
            worktree_id=request.worktree_id,
            worktree_path_sha256=hashlib.sha256(request.worktree_path.encode()).hexdigest(),
            branch=request.branch,
            verification_lane=request.verification_lane,
            lifecycle="failed",
            reason="accepted",
            authoritative=True,
            proposal_sha256=request.proposal_sha256,
            allowed_scope_digest=request.allowed_scope_digest,
            base_commit=request.base_commit,
            result_head=None,
            result_manifest_sha256=None,
            diff_sha256=None,
            approved_paths=(),
            files_changed=0,
            additions=0,
            deletions=0,
            gate_exit_states=(),
        )


def test_receipt_public_schema_excludes_process_identity_and_verifies_id(
    tmp_path: Path,
) -> None:
    request = models.OrchestrationRequest.model_validate(request_payload(tmp_path), strict=True)
    receipt = receipts.build_receipt(
        request,
        lifecycle="prepared",
        reason="plan-only",
        authoritative=False,
        paths=("docs/user/example.md",),
        additions=1,
        deletions=0,
    )
    payload = receipt.model_dump(mode="json")

    assert set(payload) == {
        "schema_version",
        "receipt_id",
        "request_id",
        "request_digest",
        "issue_number",
        "job_id",
        "assignment_id",
        "scheduler_owner_id",
        "scheduler_owner_epoch",
        "selector_digest",
        "selection_digest",
        "worktree_id",
        "worktree_path_sha256",
        "branch",
        "verification_lane",
        "lifecycle",
        "reason",
        "authoritative",
        "proposal_sha256",
        "allowed_scope_digest",
        "base_commit",
        "result_head",
        "result_manifest_sha256",
        "diff_sha256",
        "approved_paths",
        "files_changed",
        "additions",
        "deletions",
        "gate_exit_states",
    }
    assert request.worktree_path not in receipt.model_dump_json()
    with pytest.raises(ValidationError):
        models.OrchestrationReceipt.model_validate(
            {**payload, "receipt_id": f"orchestration_{'f' * 64}"},
            strict=True,
        )
    with pytest.raises(ValidationError):
        models.OrchestrationReceipt.model_validate(
            {**payload, "approved_paths": ("docs/user/other.md",)},
            strict=True,
        )
