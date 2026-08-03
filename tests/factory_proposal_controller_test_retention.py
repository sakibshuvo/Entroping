from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from unittest.mock import patch

from factory_proposal_controller_test_support import (
    ScenarioReceipt,
    assert_source_unchanged,
    offline_scenario,
    record_receipt,
    source_digest,
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

MAX_SOAK_ITERATIONS: Final[int] = 3
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
                artifact_class=artifact_class,
                byte_ceiling=1,
                state_policies=tuple(
                    RetentionStatePolicy(state=state, max_age_days=1)
                    for state in _STATES[artifact_class]
                ),
            )
            for artifact_class in MANAGED_CLASSES
        ),
    )


def _without_git[T](action: Callable[[], T]) -> T:
    with patch.object(
        factory_retention_apply,
        "_tracked_paths",
        return_value=frozenset(),
    ):
        return action()


@offline_scenario
def run_retention_and_soak_sequence(root: Path) -> tuple[ScenarioReceipt, ...]:
    before = source_digest()
    receipts = [_retention_recovery(root / "retention")]
    receipts.append(_ignored_state_escapes(root / "escapes"))
    receipts.append(_offline_soak(root / "soak"))
    assert_source_unchanged(before)
    return tuple(receipts)


def _retention_recovery(root: Path) -> ScenarioReceipt:
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

    try:
        factory_retention_transaction._purge_entry = interrupt_after_first_purge
        try:
            _ = _without_git(lambda: apply_retention_plan(root, plan, inventory))
        except RetentionApplyError:
            pass
        else:
            raise AssertionError("retention interruption was not observed")
        factory_retention_transaction._purge_entry = original
        assert _without_git(lambda: recover_incomplete(root)) == 1
    finally:
        factory_retention_transaction._purge_entry = original
    return record_receipt(
        root,
        scenario="retention-recovery",
        return_class="recovered",
        changed_paths=("retention-journal", "retention-trash"),
        crash_point="purge",
        invariants=("bounded-pressure", "durable-reopen"),
    )


def _ignored_state_escapes(root: Path) -> ScenarioReceipt:
    scheduler_root = root / "scheduler"
    scheduler_root.mkdir(parents=True)
    first = FactoryScheduler(scheduler_root).tick(
        request=request(1, worker_class="free-local"),
        owner=owner(1),
        as_of=NOW,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    assert first.assignment_id is not None
    database = scheduler_root / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    outside = root / "outside-scheduler.sqlite3"
    database.rename(outside)
    database.symlink_to(outside)
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
    os.link(ledger.db_path, ledger.db_path.with_name("ledger.alias"))
    try:
        FactoryBudgetLedger.open_project(ledger_root)
    except FactoryBudgetLedgerError:
        pass
    else:
        raise AssertionError("hardlinked ledger was accepted")
    log_root = root / "logs"
    log_root.mkdir()
    external = root / "outside-logs"
    external.mkdir()
    log_directory = log_root / ".entroping" / "factory-logs"
    log_directory.parent.mkdir(parents=True)
    log_directory.symlink_to(external, target_is_directory=True)
    executable = root / "offline-factoryctl"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    try:
        _ = run_tick(
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
        _ = _without_git(lambda: recover_incomplete(journal_root.parents[1]))
    except RetentionApplyError:
        pass
    else:
        raise AssertionError("malformed journal was accepted")
    return record_receipt(
        root,
        scenario="ignored-state-escapes",
        return_class="fail-closed",
        changed_paths=("scheduler", "ledger", "logs", "journal"),
        invariants=("symlink", "hardlink", "outside-unchanged"),
    )


def _offline_soak(root: Path) -> ScenarioReceipt:
    root.mkdir(parents=True)
    for index in range(MAX_SOAK_ITERATIONS):
        iteration = root / f"iteration-{index}"
        iteration.mkdir()
        receipt = FactoryScheduler(iteration).tick(
            request=request(index + 20, worker_class="free-local"),
            owner=owner(index + 20),
            as_of=NOW,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
        assert receipt.decision == "assigned"
        assert FactoryScheduler(iteration).snapshot().active_assignment_count == 1
    return record_receipt(
        root,
        scenario="offline-soak",
        return_class="bounded-complete",
        changed_paths=("scheduler",),
        invariants=("offline", f"iterations<={MAX_SOAK_ITERATIONS}", "no-provider"),
    )
