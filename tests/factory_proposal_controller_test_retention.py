from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from unittest.mock import patch

from factory_proposal_controller_test_support import (
    ScenarioObservation,
    ScenarioReceipt,
    offline_scenario,
    record_receipt,
)
from factory_scheduler_test_support import NOW, dead, owner, request

from scripts import factory_retention_apply, factory_retention_transaction
from scripts.factory_budget_ledger import FactoryBudgetLedger, FactoryBudgetLedgerError
from scripts.factory_retention_apply import (
    RetentionApplyError,
    apply_retention_plan,
    recover_incomplete,
)
from scripts.factory_retention_inventory import inventory_factory
from scripts.factory_retention_models import (
    RetentionClassPolicy,
    RetentionPolicy,
    RetentionStatePolicy,
)
from scripts.factory_retention_plan import plan_retention
from scripts.factory_retention_types import MANAGED_CLASSES, POLICY_SCHEMA_VERSION
from scripts.factory_scheduler import FactoryScheduler
from scripts.factory_tick_runner import TickRunnerError, run_tick

SOAK_REQUESTED_ITERATIONS: Final[int] = 3
MAX_SOAK_ACCEPTED_ITERATIONS: Final[int] = 4
_STATES: Final[dict[str, tuple[str, ...]]] = {
    "ai_job": ("completed", "failed"),
    "ai_review": ("accepted", "rejected"),
    "factory_log": ("rotated",),
    "factory_metrics_archive": ("archived",),
    "retention_journal": ("completed", "rolled_back"),
}


def _policy() -> RetentionPolicy:
    return RetentionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        class_policies=tuple(
            RetentionClassPolicy(
                schema_version=POLICY_SCHEMA_VERSION,
                artifact_class=item,
                byte_ceiling=1,
                state_policies=tuple(
                    RetentionStatePolicy(state=state, max_age_days=1) for state in _STATES[item]
                ),
            )
            for item in MANAGED_CLASSES
        ),
    )


def _without_git[T](action: Callable[[], T]) -> T:
    with patch.object(factory_retention_apply, "_tracked_paths", return_value=frozenset()):
        return action()


@offline_scenario
def retention_recovery(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "retention-recovery")
    logs = root / ".entroping" / "factory-logs"
    logs.mkdir(parents=True)
    for index in range(3):
        entry = logs / f"factory-tick.out.log.{index + 1}"
        entry.write_text("bounded\n", encoding="utf-8")
        os.utime(entry, (1, 1))
    inventory = inventory_factory(root)
    plan = plan_retention(_policy(), inventory.candidates, datetime(2026, 7, 28, tzinfo=UTC))
    assert plan.total_delete_count == 3
    original = factory_retention_transaction._purge_entry
    interrupted = False

    def interrupt_after_first_purge(parent_fd: int, name: str) -> None:
        nonlocal interrupted
        original(parent_fd, name)
        if not interrupted:
            interrupted = True
            raise OSError("interrupted retention")

    with patch.object(
        factory_retention_transaction, "_purge_entry", side_effect=interrupt_after_first_purge
    ):
        try:
            _without_git(lambda: apply_retention_plan(root, plan, inventory))
        except RetentionApplyError:
            pass
        else:
            raise AssertionError("retention interruption was not observed")
    assert _without_git(lambda: recover_incomplete(root)) == 1
    return observed.receipt(
        return_class="recovered",
        crash_point="purge",
        checks={
            "bounded-pressure": True,
            "durable-reopen": True,
            "offline": True,
            "no-source-mutation": True,
        },
    )


@offline_scenario
def ignored_state_escapes(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "ignored-state-escapes")
    external = root / "external-sentinels"
    external.mkdir(parents=True)
    sentinels = _sentinels(external)
    scheduler_root = root / "scheduler"
    scheduler_root.mkdir()
    assigned = FactoryScheduler(scheduler_root).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    database = scheduler_root / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    escaped_db = external / "scheduler.sqlite3"
    database.rename(escaped_db)
    database.symlink_to(escaped_db)
    blocked = FactoryScheduler(scheduler_root).tick(
        request=request(2, worker_class="free-local"),
        owner=owner(2),
        as_of=NOW,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )
    assert blocked.reason == "state-invalid"
    ledger_root = root / "ledger"
    ledger_root.mkdir()
    ledger = FactoryBudgetLedger.open_project(ledger_root)
    os.link(ledger.db_path, external / "ledger.alias")
    try:
        FactoryBudgetLedger.open_project(ledger_root)
    except FactoryBudgetLedgerError:
        pass
    else:
        raise AssertionError("external hardlinked ledger was accepted")
    log_root = root / "logs"
    external_logs = external / "logs-target"
    external_logs.mkdir()
    log_directory = log_root / ".entroping" / "factory-logs"
    log_directory.parent.mkdir(parents=True)
    log_directory.symlink_to(external_logs, target_is_directory=True)
    executable = root / "offline-factoryctl"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    try:
        run_tick(
            repo_root=log_root,
            factoryctl=executable,
            log_directory=log_directory,
            timeout_seconds=1,
            max_output_bytes=64,
            max_log_bytes=64,
        )
    except TickRunnerError:
        pass
    else:
        raise AssertionError("symlinked log state was accepted")
    journal_root = root / "journal" / ".entroping" / "retention-journal"
    journal_root.mkdir(parents=True)
    (journal_root / "bad.json").write_text("{", encoding="utf-8")
    try:
        _without_git(lambda: recover_incomplete(journal_root.parents[1]))
    except RetentionApplyError:
        pass
    else:
        raise AssertionError("malformed journal was accepted")
    receipt_root = root / "receipt-escape"
    receipt_root.mkdir()
    (receipt_root / "receipts").symlink_to(external / "receipt-target")
    receipt_observed = ScenarioObservation.begin(receipt_root, "receipt-escape")
    with patch.dict(
        os.environ,
        {"ENTROPING_PROPOSAL_RECEIPTS_DIR": str(receipt_root / "receipts")},
    ):
        try:
            record_receipt(
                receipt_observed,
                return_class="fail-closed",
                crash_point="none",
                checks={"fail-closed": True},
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("receipt symlink escape was accepted")
    assert _sentinels(external) == sentinels
    return observed.receipt(
        return_class="fail-closed",
        checks={"fail-closed": True, "offline": True, "no-source-mutation": True},
    )


def _sentinels(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    for name in ("scheduler", "ledger", "logs", "journal", "receipt", "evidence"):
        path = root / f"{name}-sentinel"
        if not path.exists():
            path.write_text(f"{name}-sentinel-payload", encoding="utf-8")
    return tuple(
        (
            path.name,
            path.stat().st_ino,
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.glob("*-sentinel"))
    )


@offline_scenario
def offline_soak(root: Path) -> ScenarioReceipt:
    observed = ScenarioObservation.begin(root, "offline-soak")
    completed = _run_soak(root, SOAK_REQUESTED_ITERATIONS)
    try:
        _run_soak(root, MAX_SOAK_ACCEPTED_ITERATIONS + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("overrun soak request was accepted")
    assert completed == SOAK_REQUESTED_ITERATIONS <= MAX_SOAK_ACCEPTED_ITERATIONS
    return observed.receipt(
        return_class="bounded-complete",
        checks={
            "bounded-pressure": True,
            "offline": True,
            "no-provider": True,
            "no-source-mutation": True,
        },
    )


def _run_soak(root: Path, iterations: int) -> int:
    if iterations > MAX_SOAK_ACCEPTED_ITERATIONS:
        raise ValueError("soak request exceeds acceptance maximum")
    for index in range(iterations):
        current = root / f"iteration-{index}"
        current.mkdir()
        receipt = FactoryScheduler(current).tick(
            request=request(index + 20, worker_class="free-local"),
            owner=owner(index + 20),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
        assert (
            receipt.decision == "assigned"
            and FactoryScheduler(current).snapshot().active_assignment_count == 1
        )
    return iterations


def run_retention_and_soak_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    return (
        retention_recovery(root / "retention"),
        ignored_state_escapes(root / "escapes"),
        offline_soak(root / "soak"),
    )
