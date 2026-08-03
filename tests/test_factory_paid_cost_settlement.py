from __future__ import annotations

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import factory_budget_reservation_integrity  # noqa: E402
from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    CostReservationRequest,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
    ManualReconciliationInput,
    NoChargeReconciliationInput,
    PriceTerm,
    PriceUnit,
    SettlementReceipt,
    UsageEnvelope,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
OBSERVED_AT = NOW - timedelta(days=1)
EXPIRES_AT = NOW + timedelta(days=1)


def _period(
    *,
    cap: int = 100,
    reserve: int = 20,
) -> BudgetPeriodConfig:
    return BudgetPeriodConfig(
        starts_on=date(2026, 7, 1),
        cash_cap_microcents=cap,
        emergency_reserve_microcents=reserve,
        currency="USD",
        policy_id="monthly-budget",
        policy_revision=1,
        reserve_idempotency_key="reserve-2026-07-v1",
    )


def _price(
    *,
    snapshot_id: str = "request-price-v1",
    unit: PriceUnit = "request",
    quantity: int = 1,
    price_microcents: int = 60,
    observed_at: datetime = OBSERVED_AT,
    expires_at: datetime = EXPIRES_AT,
) -> PriceTerm:
    return PriceTerm(
        snapshot_id=snapshot_id,
        unit=unit,
        quantity=quantity,
        price_microcents=price_microcents,
        observed_at=observed_at,
        expires_at=expires_at,
    )


def _reservation(
    *,
    idempotency_key: str = "reserve-job-1",
    job_id: str = "review-20260715-job-1",
    requested_model: str = "deepseek-v4-pro",
    model_id: str = "deepseek/deepseek-v4-pro",
    envelope: UsageEnvelope | None = None,
    prices: tuple[PriceTerm, ...] | None = None,
    occurred_at: datetime = NOW,
) -> CostReservationRequest:
    return CostReservationRequest(
        idempotency_key=idempotency_key,
        job_id=job_id,
        provider_lane_id="deepseek-api/direct",
        provider_id="deepseek",
        model_id=model_id,
        requested_model=requested_model,
        cost_policy_lane_id="direct-pro-lane",
        policy_id="monthly-budget",
        policy_revision=1,
        occurred_at=occurred_at,
        usage_envelope=envelope or UsageEnvelope(requests=1),
        price_terms=prices or (_price(),),
    )


def _settlement(
    reservation_id: str,
    *,
    idempotency_key: str = "settle-job-1",
    job_id: str = "review-20260715-job-1",
    model_id: str = "deepseek/deepseek-v4-pro",
    requested_model: str = "deepseek-v4-pro",
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 1,
    minutes: int = 0,
    session_digest: str = "a" * 64,
) -> SettlementReceipt:
    return SettlementReceipt(
        idempotency_key=idempotency_key,
        reservation_id=reservation_id,
        job_id=job_id,
        provider_lane_id="deepseek-api/direct",
        provider_id="deepseek",
        model_id=model_id,
        requested_model=requested_model,
        provider_session_digest=session_digest,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        requests=requests,
        minutes=minutes,
        occurred_at=NOW + timedelta(minutes=1),
    )


def _mismatched_settlement(
    reservation_id: str,
    field: str,
    value: str,
) -> SettlementReceipt:
    match field:
        case "model_id":
            return _settlement(reservation_id, model_id=value)
        case "requested_model":
            return _settlement(reservation_id, requested_model=value)
        case "job_id":
            return _settlement(reservation_id, job_id=value)
        case "session_digest":
            return _settlement(reservation_id, session_digest=value)
        case _:
            raise AssertionError(f"unsupported test field: {field}")


def _open_ledger(tmp_path: Path, *, cap: int = 100, reserve: int = 20) -> FactoryBudgetLedger:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    _ = ledger.initialize_period(_period(cap=cap, reserve=reserve))
    return ledger


def test_concurrent_near_cap_reservations_admit_only_one_writer(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    barrier = Barrier(2)

    def attempt(index: int) -> str:
        _ = barrier.wait()
        try:
            _ = ledger.reserve_for_dispatch(
                _reservation(
                    idempotency_key=f"reserve-job-{index}",
                    job_id=f"review-20260715-job-{index}",
                )
            )
        except FactoryBudgetLedgerError as exc:
            return exc.code
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(attempt, range(2)))

    assert sorted(outcomes) == ["budget", "created"]
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.active_reserved_microcents == 60
    assert summary.available_paid_microcents == 20


def test_reservation_exact_replay_is_bound_and_secretless(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    request = _reservation()

    first = ledger.reserve_for_dispatch(request)
    replay = ledger.reserve_for_dispatch(request)

    assert first.created is True
    assert first.state == "dispatching"
    assert first.held_microcents == 60
    assert replay.created is False
    assert replay == first.with_created(False)
    assert request.idempotency_key not in ledger.db_path.read_bytes().decode(
        "utf-8", errors="ignore"
    )

    with pytest.raises(FactoryBudgetLedgerError, match="idempotency key conflicts"):
        _ = ledger.reserve_for_dispatch(
            _reservation(requested_model="deepseek-v4-flash")
        )


def test_verified_receipt_posts_actual_once_and_releases_remainder(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(
        _reservation(
            envelope=UsageEnvelope(input_tokens=10, output_tokens=10),
            prices=(
                _price(
                    snapshot_id="input-price-v1",
                    unit="input_token",
                    price_microcents=2,
                ),
                _price(
                    snapshot_id="output-price-v1",
                    unit="output_token",
                    price_microcents=3,
                ),
            ),
        )
    )

    first = ledger.settle_reservation(
        _settlement(
            reservation.reservation_id,
            input_tokens=4,
            output_tokens=3,
            requests=0,
        )
    )
    replay = ledger.settle_reservation(
        _settlement(
            reservation.reservation_id,
            input_tokens=4,
            output_tokens=3,
            requests=0,
        )
    )

    assert first.created is True
    assert first.state == "settled"
    assert first.actual_microcents == 17
    assert replay.created is False
    assert replay.entry_id == first.entry_id
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.active_reserved_microcents == 0
    assert summary.net_spent_microcents == 17
    assert summary.available_paid_microcents == 63

    with pytest.raises(FactoryBudgetLedgerError, match="idempotency key conflicts"):
        _ = ledger.settle_reservation(
            _settlement(
                reservation.reservation_id,
                output_tokens=1,
                requests=0,
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("model_id", "deepseek/deepseek-v4-flash", "model_mismatch"),
        ("requested_model", "deepseek-v4-flash", "model_mismatch"),
        ("job_id", "review-20260715-other-job", "job_mismatch"),
        ("session_digest", "b" * 63, "malformed_receipt"),
    ],
)
def test_malformed_or_conflicting_receipt_preserves_hold(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())

    outcome = ledger.settle_reservation(
        _mismatched_settlement(reservation.reservation_id, field, value)
    )

    assert outcome.state == "uncertain"
    assert outcome.reason == reason
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.active_reserved_microcents == 60
    assert summary.net_spent_microcents == 0


def test_partial_then_late_complete_receipt_settles_without_double_charge(
    tmp_path: Path,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())

    partial = ledger.mark_reservation_uncertain(
        reservation.reservation_id,
        idempotency_key="partial-receipt-job-1",
        reason="partial_receipt",
        occurred_at=NOW + timedelta(minutes=1),
        evidence_digest="b" * 64,
    )
    late = ledger.settle_reservation(_settlement(reservation.reservation_id))

    assert partial.state == "uncertain"
    assert partial.held_microcents == 60
    assert late.state == "settled"
    assert late.actual_microcents == 60
    assert ledger.period_summary(date(2026, 7, 1)).net_spent_microcents == 60


def test_over_hold_receipt_stays_uncertain_until_explicit_reconciliation(
    tmp_path: Path,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())

    outcome = ledger.settle_reservation(
        _settlement(reservation.reservation_id, requests=2)
    )

    assert outcome.state == "uncertain"
    assert outcome.reason == "actual_exceeds_reservation"
    assert ledger.period_summary(date(2026, 7, 1)).active_reserved_microcents == 60


def test_value_free_reconciliation_releases_only_with_explicit_evidence(
    tmp_path: Path,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())
    command = NoChargeReconciliationInput(
        idempotency_key="no-charge-reconcile-job-1",
        reservation_id=reservation.reservation_id,
        evidence_digest="c" * 64,
        occurred_at=NOW + timedelta(minutes=2),
        reason="provider_confirmed_no_charge",
    )

    first = ledger.reconcile_no_charge(command)
    replay = ledger.reconcile_no_charge(command)

    assert first.created is True
    assert first.state == "reconciled"
    assert first.actual_microcents == 0
    assert replay.created is False
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.active_reserved_microcents == 0
    assert summary.net_spent_microcents == 0

    late = ledger.settle_reservation(
        _settlement(
            reservation.reservation_id,
            idempotency_key="late-after-reconcile-job-1",
        )
    )
    assert late.state == "reconciled"
    assert late.reason == "reservation_already_terminal"
    assert ledger.period_summary(date(2026, 7, 1)).net_spent_microcents == 0


def test_manual_reconciliation_posts_bound_adjustment_once(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())
    command = ManualReconciliationInput(
        idempotency_key="manual-reconcile-job-1",
        reservation_id=reservation.reservation_id,
        evidence_digest="d" * 64,
        amount_microcents=40,
        occurred_at=NOW + timedelta(minutes=2),
        source_id="provider-invoice-review",
    )

    first = ledger.reconcile_manual_debit(command)
    replay = ledger.reconcile_manual_debit(command)

    assert first.created is True
    assert first.actual_microcents == 40
    assert replay.created is False
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.active_reserved_microcents == 0
    assert summary.net_spent_microcents == 40


@pytest.mark.parametrize(
    ("amount_microcents", "source_id"),
    ((41, "provider-invoice-review"), (40, "different-provider-evidence")),
)
def test_manual_reconciliation_replay_rejects_changed_authority(
    tmp_path: Path,
    amount_microcents: int,
    source_id: str,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())
    command = ManualReconciliationInput(
        idempotency_key="manual-reconcile-job-1",
        reservation_id=reservation.reservation_id,
        evidence_digest="d" * 64,
        amount_microcents=40,
        occurred_at=NOW + timedelta(minutes=2),
        source_id="provider-invoice-review",
    )
    _ = ledger.reconcile_manual_debit(command)

    with pytest.raises(FactoryBudgetLedgerError, match="idempotency key conflicts"):
        _ = ledger.reconcile_manual_debit(
            ManualReconciliationInput(
                idempotency_key=command.idempotency_key,
                reservation_id=command.reservation_id,
                evidence_digest=command.evidence_digest,
                amount_microcents=amount_microcents,
                occurred_at=command.occurred_at,
                source_id=source_id,
            )
        )


@pytest.mark.parametrize(
    "limit_name",
    ("MAX_COST_RESERVATIONS", "MAX_RESERVATION_PRICES"),
)
def test_global_reservation_capacity_blocks_boundary_crossing_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
) -> None:
    ledger = _open_ledger(tmp_path, cap=1_000, reserve=20)
    _ = ledger.reserve_for_dispatch(_reservation())
    monkeypatch.setattr(factory_budget_reservation_integrity, limit_name, 1)

    with pytest.raises(FactoryBudgetLedgerError, match="global .* limit reached"):
        _ = ledger.reserve_for_dispatch(
            _reservation(
                idempotency_key="reserve-job-2",
                job_id="review-20260715-job-2",
            )
        )

    assert ledger.reservation_for_job("review-20260715-job-2") is None


def test_global_reservation_event_capacity_rolls_back_state_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())
    monkeypatch.setattr(
        factory_budget_reservation_integrity,
        "MAX_RESERVATION_EVENTS",
        1,
    )

    with pytest.raises(FactoryBudgetLedgerError, match="event limit reached"):
        _ = ledger.mark_reservation_uncertain(
            reservation.reservation_id,
            idempotency_key="uncertain-job-1",
            reason="worker_interrupted",
            occurred_at=NOW + timedelta(minutes=1),
            evidence_digest="f" * 64,
        )

    stored = ledger.reservation_for_job("review-20260715-job-1")
    assert stored is not None
    assert stored.state == "dispatching"


def test_active_reservation_does_not_trip_period_entry_count_limit(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path, cap=500_000, reserve=20)
    _ = ledger.reserve_for_dispatch(
        _reservation(prices=(_price(price_microcents=100_000),))
    )

    receipt = ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="separate-provider-charge",
            kind="provider_charge",
            direction="debit",
            amount_microcents=1,
            occurred_at=NOW + timedelta(minutes=1),
            currency="USD",
            source_id="other-provider",
        )
    )

    assert receipt.created is True
    assert receipt.summary.entry_count == 2
    assert receipt.summary.active_reserved_microcents == 100_000


def test_stale_price_and_duplicate_units_block_before_hold(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)

    with pytest.raises(FactoryBudgetLedgerError, match="price term is stale"):
        _ = ledger.reserve_for_dispatch(
            _reservation(prices=(_price(expires_at=NOW),))
        )
    with pytest.raises(FactoryBudgetLedgerError, match="duplicate price unit"):
        _ = ledger.reserve_for_dispatch(
            _reservation(
                prices=(
                    _price(snapshot_id="request-price-v1"),
                    _price(snapshot_id="request-price-v2"),
                )
            )
        )

    assert ledger.period_summary(date(2026, 7, 1)).active_reserved_microcents == 0


def test_reservation_state_is_recoverable_by_job_identity(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())

    recovered = ledger.reservation_for_job("review-20260715-job-1")

    assert recovered is not None
    assert recovered == reservation.with_created(False)
    assert recovered.state == "dispatching"


def test_schema_v3_preserves_exact_hold_projection(tmp_path: Path) -> None:
    ledger = _open_ledger(tmp_path)
    reservation = ledger.reserve_for_dispatch(_reservation())

    with sqlite3.connect(ledger.db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        assert connection.execute(
            "SELECT value FROM ledger_metadata WHERE key = 'schema_version'"
        ).fetchone() == ("entroping.factory-budget-ledger.v3",)
        assert connection.execute(
            "SELECT active_reserved_microcents FROM budget_periods"
        ).fetchone() == (60,)
        assert connection.execute(
            "SELECT state FROM cost_reservations WHERE public_id = ?",
            (reservation.reservation_id,),
        ).fetchone() == ("dispatching",)
