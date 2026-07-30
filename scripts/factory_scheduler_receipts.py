from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    LeaseOwner,
)
from scripts.factory_scheduler_validation import aware_utc


def blocked_state_receipt(
    *,
    request: AssignmentRequest | None,
    observed_at: datetime,
    reason: str,
) -> DecisionReceipt:
    return decision_receipt(
        request=request,
        owner=None,
        epoch=None,
        observed_at=_bounded_receipt_time(observed_at),
        decision="blocked",
        reason=reason,
        authoritative=True,
        counts=(0, 0, 0),
    )


def decision_receipt(
    *,
    request: AssignmentRequest | None,
    owner: LeaseOwner | None,
    epoch: int | None,
    observed_at: datetime,
    decision: str,
    reason: str,
    authoritative: bool,
    counts: tuple[int, int, int],
    assignment_id: str | None = None,
    decision_id: str | None = None,
    lease_owner_id: str | None = None,
) -> DecisionReceipt:
    digest = "idle" if request is None else request_digest(request)
    resolved_decision_id = decision_id or make_decision_id(
        request_digest_value=digest,
        epoch=epoch,
        observed_at=observed_at,
        decision=decision,
        reason=reason,
    )
    return DecisionReceipt.model_validate(
        {
            "decision_id": resolved_decision_id,
            "decision": decision,
            "reason": reason,
            "authoritative": authoritative,
            "paid_work_authorized": False,
            "request_id": None if request is None else request.request_id,
            "job_id": None if request is None else request.job_id,
            "issue_number": None if request is None else request.issue_number,
            "worktree_id": None if request is None else request.worktree_id,
            "assignment_id": assignment_id,
            "lease_owner_id": (
                lease_owner_id
                if lease_owner_id is not None
                else (None if owner is None else owner.owner_id)
            ),
            "lease_epoch": epoch,
            "observed_at": observed_at,
            "active_paid": counts[0],
            "active_free_reviews": counts[1],
            "active_writers_in_scope": counts[2],
        },
        strict=True,
    )


def request_digest(request: AssignmentRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def assignment_id(request_digest_value: str) -> str:
    digest = hashlib.sha256(f"assign:{request_digest_value}".encode()).hexdigest()
    return f"assign_{digest}"


def make_decision_id(
    *,
    request_digest_value: str,
    epoch: int | None,
    observed_at: datetime,
    decision: str,
    reason: str,
) -> str:
    payload = "|".join(
        (
            request_digest_value,
            str(epoch),
            iso_utc(observed_at),
            decision,
            reason,
        )
    )
    return f"decision_{hashlib.sha256(payload.encode()).hexdigest()}"


def iso_utc(value: datetime) -> str:
    return aware_utc(value).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _bounded_receipt_time(value: datetime) -> datetime:
    try:
        return aware_utc(value)
    except (TypeError, ValueError):
        boundary = (
            datetime.max
            if isinstance(value, datetime) and value.year == datetime.max.year
            else datetime.min
        )
        return boundary.replace(tzinfo=UTC)
