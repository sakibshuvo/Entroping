from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest
from factory_scheduler_test_support import (
    NOW,
    dead,
    owner,
    paid_request_with_reservation,
    request,
)

from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_models import AssignmentRequest, LeaseOwner


def test_paid_assignment_requires_a_reservation_handoff() -> None:
    payload = request().model_dump(mode="json")
    payload["reservation_id"] = None

    with pytest.raises(ValueError, match="paid assignments require a reservation id"):
        AssignmentRequest.model_validate(payload, strict=True)


def test_paid_assignment_requires_authoritative_reservation_evidence(
    tmp_path: Path,
) -> None:
    missing = FactoryScheduler(
        tmp_path,
        reservation_guard=lambda _request: nullcontext(False),
    )
    unavailable = FactoryScheduler(
        tmp_path,
        reservation_guard=lambda _request: nullcontext(None),
    )

    mismatch = missing.tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    unknown = unavailable.tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert mismatch.reason == "reservation-mismatch"
    assert unknown.reason == "reservation-unavailable"
    assert not (tmp_path / ".entroping").exists()


def test_default_paid_handoff_requires_existing_ledger_without_creating_state(
    tmp_path: Path,
) -> None:
    receipt = FactoryScheduler(tmp_path).tick(
        request=request(),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "reservation-unavailable"
    assert not (tmp_path / ".entroping").exists()


def test_paid_assignment_accepts_matching_dispatching_budget_reservation(
    tmp_path: Path,
) -> None:
    _ledger, candidate = paid_request_with_reservation(tmp_path)

    receipt = FactoryScheduler(tmp_path).tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "assigned"
    assert receipt.paid_work_authorized is False


def test_paid_handoff_returns_bounded_receipt_when_budget_ledger_is_busy(
    tmp_path: Path,
) -> None:
    ledger, candidate = paid_request_with_reservation(tmp_path)
    competing = sqlite3.connect(ledger.db_path, timeout=0.05, autocommit=True)
    _ = competing.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        receipt = FactoryScheduler(tmp_path).tick(
            request=candidate,
            owner=owner(1),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
    finally:
        _ = competing.execute("ROLLBACK")
        competing.close()

    assert time.monotonic() - started < 1.0
    assert receipt.decision == "blocked"
    assert receipt.reason == "reservation-busy"
    assert not (tmp_path / ".entroping" / "factory-scheduler").exists()


def test_paid_reservation_handoff_holds_ledger_until_assignment_commit(
    tmp_path: Path,
) -> None:
    subject = FactoryScheduler(tmp_path)
    first = subject.tick(
        request=request(2, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert first.lease_epoch is not None
    subject.complete_assignment(
        assignment_id=first.assignment_id,
        owner=owner(1),
        epoch=first.lease_epoch,
        completed_at=NOW + timedelta(milliseconds=100),
    )
    ledger, candidate = paid_request_with_reservation(tmp_path)
    handoff_entered = Event()
    release_handoff = Event()

    def pause_after_guard(_owner_value: LeaseOwner) -> bool:
        handoff_entered.set()
        if not release_handoff.wait(timeout=2):
            raise AssertionError("reservation handoff test timed out")
        return False

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            subject.tick,
            request=candidate,
            owner=owner(2),
            as_of=NOW + timedelta(seconds=2),
            lease_seconds=30,
            plan_only=False,
            owner_health=pause_after_guard,
        )
        assert handoff_entered.wait(timeout=2)
        competing = sqlite3.connect(ledger.db_path, timeout=0.05, autocommit=True)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                _ = competing.execute("BEGIN IMMEDIATE")
        finally:
            release_handoff.set()
        receipt = future.result(timeout=2)
        _ = competing.execute("BEGIN IMMEDIATE")
        _ = competing.execute("ROLLBACK")
        competing.close()

    assert receipt.decision == "assigned"


def test_paid_replay_and_conflict_precede_current_reservation_validation(
    tmp_path: Path,
) -> None:
    candidate = request()
    first = FactoryScheduler(
        tmp_path,
        reservation_guard=lambda _request: nullcontext(True),
    ).tick(
        request=candidate,
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    def unexpected_guard(_request: AssignmentRequest) -> nullcontext[bool]:
        raise AssertionError("immutable scheduler replay must precede reservation state")

    subject = FactoryScheduler(tmp_path, reservation_guard=unexpected_guard)
    replay = subject.tick(
        request=candidate,
        owner=owner(2),
        as_of=NOW + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    conflict = subject.tick(
        request=candidate.model_copy(update={"job_id": "changed-job"}),
        owner=owner(2),
        as_of=NOW + timedelta(seconds=2),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert replay.decision == "assigned"
    assert replay.reason == "exact-replay"
    assert replay.assignment_id == first.assignment_id
    assert conflict.decision == "blocked"
    assert conflict.reason == "request-id-conflict"
