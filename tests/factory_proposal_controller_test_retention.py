from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from unittest.mock import patch

from factory_proposal_controller_test_receipt_contracts import ScenarioReceipt
from factory_proposal_controller_test_receipts import PendingReceipt
from factory_proposal_controller_test_support import (
    ScenarioObservation,
    offline_scenario,
)
from factory_scheduler_test_support import NOW, dead, owner, request

from scripts import factory_retention_apply, factory_retention_transaction
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
def retention_recovery(root: Path) -> PendingReceipt:
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
    return observed.receipt(return_class="recovered", crash_point="purge")


@offline_scenario
def offline_soak(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "offline-soak")
    completed = _run_soak(root, SOAK_REQUESTED_ITERATIONS)
    try:
        _run_soak(root, MAX_SOAK_ACCEPTED_ITERATIONS + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("overrun soak request was accepted")
    assert completed == SOAK_REQUESTED_ITERATIONS <= MAX_SOAK_ACCEPTED_ITERATIONS
    return observed.receipt(return_class="bounded-complete")


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
        offline_soak(root / "soak"),
    )
