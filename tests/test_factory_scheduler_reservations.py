from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
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

from scripts.factory_budget_ledger import (
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    UsageEnvelope,
)
from scripts.factory_quota_models import DispatchAuthorizationRequest, TopUpAttestation
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_scheduler_models import AssignmentRequest, LeaseOwner
from scripts.factory_scheduler_reservation import budget_reservation_handoff
from scripts.factory_scheduler_schema import SCHEMA_ID, SCHEMA_VERSION
from scripts.factory_scheduler_schema_migration import initialize_previous_schema


def _paid_request_with_authorization(
    tmp_path: Path,
) -> tuple[FactoryBudgetLedger, AssignmentRequest]:
    now = datetime.now(UTC)
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    _ = ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(now.year, now.month, 1),
            cash_cap_microcents=100,
            emergency_reserve_microcents=20,
            currency="USD",
            policy_id="monthly-budget",
            policy_revision=1,
            reserve_idempotency_key=f"period-reserve-{now:%Y-%m}",
        )
    )
    authorization = ledger.authorize_dispatch(
        DispatchAuthorizationRequest(
            idempotency_key="authorize-scheduler-job-1",
            job_id=request().job_id,
            provider_lane_id="test-paid-included",
            provider_id="test-paid",
            cost_policy_lane_id="test-paid-included",
            policy_id="monthly-budget",
            policy_revision=1,
            billing_mode="included_quota",
            work_purpose="essential",
            usage_envelope=UsageEnvelope(requests=1),
            cash_reservation=None,
            quota_requirements=(),
            top_up_attestation=TopUpAttestation(
                attestation_id="scheduler-topup-disabled",
                provider_id="test-paid",
                provider_lane_id="test-paid-included",
                policy_id="monthly-budget",
                policy_revision=1,
                mode="disabled",
                source_kind="provider-policy-export",
                source_id="test-paid-policy",
                evidence_digest="a" * 64,
                observed_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=10),
            ),
            decision_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )
    candidate = AssignmentRequest.model_validate(
        {
            **request().model_dump(mode="json"),
            "reservation_id": None,
            "authorization_id": authorization.authorization_id,
        },
        strict=True,
    )
    return ledger, candidate


def test_paid_assignment_requires_a_dispatch_authorization_handoff() -> None:
    payload = request().model_dump(mode="json")
    payload["reservation_id"] = None

    with pytest.raises(ValueError, match="paid assignments require a dispatch authorization"):
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

    assert receipt.decision == "assigned", receipt.reason
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


def test_paid_authorization_handoff_holds_ledger_until_assignment_commit(
    tmp_path: Path,
) -> None:
    ledger, candidate = _paid_request_with_authorization(tmp_path)
    handoff_entered = Event()
    release_handoff = Event()

    def hold_authorization_guard() -> bool | None:
        with budget_reservation_handoff(tmp_path, candidate) as valid:
            handoff_entered.set()
            if not release_handoff.wait(timeout=2):
                raise AssertionError("authorization handoff test timed out")
            return valid

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_authorization_guard)
        assert handoff_entered.wait(timeout=2)
        competing = sqlite3.connect(ledger.db_path, timeout=0.05, autocommit=True)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                _ = competing.execute("BEGIN IMMEDIATE")
        finally:
            release_handoff.set()
        valid = future.result(timeout=2)
        _ = competing.execute("BEGIN IMMEDIATE")
        _ = competing.execute("ROLLBACK")
        competing.close()

    assert valid is True


def test_quota_authorization_assignment_is_durable_and_replayable(
    tmp_path: Path,
) -> None:
    _ledger, candidate = _paid_request_with_authorization(tmp_path)
    subject = FactoryScheduler(tmp_path)
    observed_at = datetime.now(UTC)

    assigned = subject.tick(
        request=candidate,
        owner=owner(1),
        as_of=observed_at,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    replay = subject.tick(
        request=candidate,
        owner=owner(2),
        as_of=observed_at + timedelta(seconds=1),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    conflict = subject.tick(
        request=candidate.model_copy(update={"authorization_id": f"auth-{'f' * 32}"}),
        owner=owner(2),
        as_of=observed_at + timedelta(seconds=2),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    evidence = subject.assignment_for_job_readonly(candidate.job_id)

    assert assigned.decision == "assigned"
    assert replay.reason == "exact-replay"
    assert replay.assignment_id == assigned.assignment_id
    assert conflict.reason == "request-id-conflict"
    assert evidence is not None
    assert evidence.request.authorization_id == candidate.authorization_id
    assert evidence.request.reservation_id is None


def test_existing_v1_scheduler_state_migrates_before_quota_assignment(
    tmp_path: Path,
) -> None:
    _ledger, candidate = _paid_request_with_authorization(tmp_path)
    state_dir = tmp_path / ".entroping" / "factory-scheduler"
    state_dir.mkdir()
    state_dir.chmod(0o700)
    database = state_dir / "scheduler.sqlite3"
    connection = sqlite3.connect(database, autocommit=True)
    try:
        initialize_previous_schema(connection, initialized_at=NOW.isoformat())
    finally:
        connection.close()
    database.chmod(0o600)

    receipt = FactoryScheduler(tmp_path).tick(
        request=candidate,
        owner=owner(1),
        as_of=datetime.now(UTC),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "assigned", receipt.reason
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert connection.execute(
            "SELECT value FROM scheduler_metadata WHERE key = 'schema_version'"
        ).fetchone() == (SCHEMA_ID,)
        assert connection.execute(
            "SELECT authorization_id FROM scheduler_assignments"
        ).fetchone() == (candidate.authorization_id,)
    finally:
        connection.close()


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
