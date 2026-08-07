from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .factory_budget_ledger_models import FactoryBudgetLedgerError
from .factory_budget_ledger_periods import period_summary
from .factory_budget_ledger_reporting import balance_from_period
from .factory_budget_ledger_schema import LEDGER_SCHEMA_ID
from .factory_budget_ledger_storage import migrate_ledger, readonly_connection

type JsonScalar = str | int | bool


class LedgerArguments(argparse.Namespace):
    command: str
    repo: Path
    period: date

    def __init__(self) -> None:
        super().__init__()
        self.command = ""
        self.repo = Path()
        self.period = date.min


def main(argv: list[str] | None = None) -> int:
    args = LedgerArguments()
    _ = _parser().parse_args(argv, namespace=args)
    command = args.command
    repo = args.repo
    period = args.period
    try:
        if command not in {"summary", "balance", "migrate"}:
            raise FactoryBudgetLedgerError("arguments", "parsed arguments are invalid")
        if command == "migrate":
            migrated = migrate_ledger(repo)
            payload: dict[str, JsonScalar] = {
                "schema_version": "entroping.factory-budget-migration.v1",
                "migrated": migrated,
                "ledger_schema_version": LEDGER_SCHEMA_ID,
            }
        else:
            with readonly_connection(repo) as connection:
                summary = period_summary(connection, period)
            if command == "summary":
                payload = {
                    "schema_version": "entroping.factory-budget-period-summary.v2",
                    "period_start_utc": summary.period_start_utc,
                    "period_end_utc": summary.period_end_utc,
                    "currency": summary.currency,
                    "cash_cap_microcents": summary.cash_cap_microcents,
                    "emergency_reserve_microcents": summary.emergency_reserve_microcents,
                    "net_spent_microcents": summary.net_spent_microcents,
                    "active_reserved_microcents": summary.active_reserved_microcents,
                    "available_paid_microcents": summary.available_paid_microcents,
                    "entry_count": summary.entry_count,
                    "policy_id": summary.policy_id,
                    "policy_revision": summary.policy_revision,
                }
            else:
                balance = balance_from_period(summary)
                payload = {
                    "schema_version": "entroping.factory-budget-balance.v2",
                    "period_start_utc": balance.period_start_utc,
                    "currency": balance.currency,
                    "paid_limit_microcents": balance.paid_limit_microcents,
                    "net_spent_microcents": balance.net_spent_microcents,
                    "available_paid_microcents": balance.available_paid_microcents,
                    "paid_dispatch_permitted": balance.paid_dispatch_permitted,
                }
    except FactoryBudgetLedgerError as exc:
        print(f"factory_budget_ledger: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.factory_budget_ledger",
        description="Inspect or explicitly migrate the authoritative factory budget ledger.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("summary", "balance"):
        child = subparsers.add_parser(command)
        _ = child.add_argument("--repo", type=Path, required=True)
        _ = child.add_argument("--period", type=_parse_period, required=True)
    migrate = subparsers.add_parser("migrate")
    _ = migrate.add_argument("--repo", type=Path, required=True)
    return parser


def _parse_period(raw: str) -> date:
    try:
        value = date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("period must use YYYY-MM-01") from exc
    if value.day != 1:
        raise argparse.ArgumentTypeError("period must use YYYY-MM-01")
    return value
