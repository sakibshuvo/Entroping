from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
    LedgerEntryInput,
)
from scripts.factory_budget_ledger_models import canonical_occurred_at  # noqa: E402


def _period(
    *,
    starts_on: date = date(2026, 7, 1),
    cash_cap_microcents: int = 20_000_000_000,
    emergency_reserve_microcents: int = 2_000_000_000,
    currency: str = "USD",
    policy_id: str = "monthly-budget",
    policy_revision: int = 1,
    reserve_idempotency_key: str = "reserve-2026-07-v1",
) -> BudgetPeriodConfig:
    return BudgetPeriodConfig(
        starts_on=starts_on,
        cash_cap_microcents=cash_cap_microcents,
        emergency_reserve_microcents=emergency_reserve_microcents,
        currency=currency,
        policy_id=policy_id,
        policy_revision=policy_revision,
        reserve_idempotency_key=reserve_idempotency_key,
    )


DEFAULT_OCCURRED_AT = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _entry(
    *,
    idempotency_key: str = "provider-charge-1",
    kind: str = "provider_charge",
    direction: str = "debit",
    amount_microcents: int = 1_000_000_000,
    occurred_at: datetime = DEFAULT_OCCURRED_AT,
    currency: str = "USD",
    source_id: str = "openai",
    reference_idempotency_key: str | None = None,
) -> LedgerEntryInput:
    return LedgerEntryInput(
        idempotency_key=idempotency_key,
        kind=kind,
        direction=direction,
        amount_microcents=amount_microcents,
        occurred_at=occurred_at,
        currency=currency,
        source_id=source_id,
        reference_idempotency_key=reference_idempotency_key,
    )


@pytest.mark.parametrize(
    ("kind", "source_id"),
    [
        ("provider_charge", "openai"),
        ("fixed_subscription_charge", "codex-subscription"),
    ],
)
def test_record_charge_exact_replay_is_a_noop_and_key_is_not_stored(
    tmp_path: Path,
    kind: str,
    source_id: str,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    raw_key = f"{kind}-secretless-1"
    entry = _entry(
        idempotency_key=raw_key,
        kind=kind,
        source_id=source_id,
    )

    first = ledger.record_entry(entry)
    replay = ledger.record_entry(entry)

    assert first.created is True
    assert replay.created is False
    assert replay.entry_id == first.entry_id
    assert first.summary.net_spent_microcents == 1_000_000_000
    assert first.summary.entry_count == 2
    assert raw_key not in ledger.db_path.read_bytes().decode("utf-8", errors="ignore")


def test_record_entry_rejects_conflicting_global_idempotency_key(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    ledger.record_entry(_entry(idempotency_key="shared-key"))

    with pytest.raises(FactoryBudgetLedgerError, match="idempotency key conflicts"):
        ledger.record_entry(
            _entry(
                idempotency_key="shared-key",
                kind="fixed_subscription_charge",
                source_id="codex-subscription",
            )
        )

    assert ledger.period_summary(date(2026, 7, 1)).entry_count == 2


def test_charge_cannot_consume_the_emergency_reserve(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period(cash_cap_microcents=100, emergency_reserve_microcents=20))
    ledger.record_entry(_entry(amount_microcents=80))

    with pytest.raises(FactoryBudgetLedgerError, match="paid entry exceeds available budget"):
        ledger.record_entry(_entry(idempotency_key="provider-charge-2", amount_microcents=1))

    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.net_spent_microcents == 80
    assert summary.available_paid_microcents == 0
    assert summary.entry_count == 2


def test_concurrent_near_cap_charges_admit_only_one_writer(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period(cash_cap_microcents=100, emergency_reserve_microcents=20))
    ledger.record_entry(_entry(amount_microcents=70))
    barrier = Barrier(2)

    def attempt(index: int) -> str:
        barrier.wait()
        try:
            ledger.record_entry(_entry(idempotency_key=f"concurrent-{index}", amount_microcents=10))
        except FactoryBudgetLedgerError as exc:
            return exc.code
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(attempt, range(2)))

    assert sorted(outcomes) == ["budget", "created"]
    summary = ledger.period_summary(date(2026, 7, 1))
    assert summary.net_spent_microcents == 80
    assert summary.entry_count == 3


def test_refund_is_linked_bounded_and_credited_in_its_receipt_month(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period())
    ledger.record_entry(_entry(idempotency_key="july-charge", amount_microcents=100))
    ledger.initialize_period(
        _period(
            starts_on=date(2026, 8, 1),
            reserve_idempotency_key="reserve-2026-08-v1",
        )
    )

    receipt = ledger.record_entry(
        _entry(
            idempotency_key="august-refund",
            kind="refund",
            direction="credit",
            amount_microcents=30,
            occurred_at=datetime(2026, 8, 2, tzinfo=UTC),
            reference_idempotency_key="july-charge",
        )
    )

    assert receipt.summary.net_spent_microcents == -30
    assert receipt.summary.available_paid_microcents == 18_000_000_000
    with pytest.raises(FactoryBudgetLedgerError, match="refund exceeds the original charge"):
        ledger.record_entry(
            _entry(
                idempotency_key="excess-refund",
                kind="refund",
                direction="credit",
                amount_microcents=71,
                occurred_at=datetime(2026, 8, 3, tzinfo=UTC),
                reference_idempotency_key="july-charge",
            )
        )


def test_manual_credit_never_increases_net_authority_above_period_limit(
    tmp_path: Path,
) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(_period(cash_cap_microcents=100, emergency_reserve_microcents=20))
    credited = ledger.record_entry(
        _entry(
            idempotency_key="manual-credit",
            kind="manual_adjustment",
            direction="credit",
            amount_microcents=30,
            source_id="maintainer-correction",
        )
    )

    assert credited.summary.net_spent_microcents == -30
    assert credited.summary.available_paid_microcents == 80
    ledger.record_entry(
        _entry(
            idempotency_key="post-credit-charge",
            amount_microcents=80,
        )
    )
    ledger.record_entry(
        _entry(
            idempotency_key="credit-offset-charge",
            amount_microcents=30,
        )
    )
    with pytest.raises(FactoryBudgetLedgerError, match="paid entry exceeds available budget"):
        ledger.record_entry(_entry(idempotency_key="minted-budget", amount_microcents=1))
    assert ledger.period_summary(date(2026, 7, 1)).net_spent_microcents == 80


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (_entry(currency="CAD"), "currency must be USD"),
        (_entry(amount_microcents=True), "amount must be an integer"),
        (_entry(amount_microcents=2**63), "amount exceeds"),
        (_entry(occurred_at=datetime(2026, 7, 15)), "timestamp must include"),
        (
            _entry(kind="refund", direction="debit"),
            "refund entries must be credits",
        ),
    ],
)
def test_entry_boundary_rejects_invalid_financial_values(
    entry: LedgerEntryInput,
    message: str,
) -> None:
    with pytest.raises(FactoryBudgetLedgerError, match=message):
        entry.validate()


def test_entry_boundary_maps_non_datetime_timestamp_to_domain_error() -> None:
    with pytest.raises(FactoryBudgetLedgerError, match="timestamp must be a datetime"):
        canonical_occurred_at(date(2026, 7, 15))
