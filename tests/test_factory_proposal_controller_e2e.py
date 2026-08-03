from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from factory_proposal_controller_test_cli import run_cli_safety_sequence
from factory_proposal_controller_test_retention import run_retention_and_soak_sequence
from factory_proposal_controller_test_sequences import run_budget_and_recovery_sequence
from factory_proposal_controller_test_support import ScenarioReceipt


def _assert_receipts(
    receipts: Iterable[ScenarioReceipt],
    expected_scenarios: tuple[str, ...],
) -> None:
    observed = tuple(receipts)
    assert tuple(receipt.scenario for receipt in observed) == expected_scenarios
    for receipt in observed:
        assert len(receipt.state_digest) == 64
        assert receipt.fake_call_count >= 0
        assert receipt.file_total >= 0
        assert receipt.byte_total >= 0
        assert receipt.changed_paths
        payload = json.loads(receipt.path.read_text(encoding="utf-8"))
        assert set(payload) == {
            "byte_total",
            "changed_paths",
            "crash_point",
            "durations_ms",
            "fake_call_count",
            "file_total",
            "invariants",
            "return_class",
            "scenario",
            "state_digest",
        }
        assert "secret" not in receipt.path.read_text(encoding="utf-8").lower()


def test_controller_cli_scenarios_are_plan_first_and_value_free(tmp_path: Path) -> None:
    # Given: an offline harness with network and Git commands unavailable to child CLIs.
    # When: it drives idle, invalid, blocked, and plan-first recovery command paths.
    # Then: every command emits a bounded receipt and only explicit recovery applies state.
    _assert_receipts(
        run_cli_safety_sequence(tmp_path),
        (
            "idle-cli",
            "plan-only-cli",
            "invalid-cli",
            "blocked-dispatch-cli",
            "plan-first-recovery-cli",
            "explicit-recovery-apply-cli",
        ),
    )


def test_controller_persists_budget_duplicate_and_recovery_boundaries(
    tmp_path: Path,
) -> None:
    # Given: a real local ledger and scheduler with fixed fake usage receipts.
    # When: assignments, settlement, duplicate ticks, restart boundaries, and authority drift run.
    # Then: one capacity winner survives and all unsafe authority remains fail-closed.
    _assert_receipts(
        run_budget_and_recovery_sequence(tmp_path),
        (
            "free-local-assignment",
            "paid-exact-settlement",
            "request-replay-conflict",
            "restart-boundaries",
            "overlapping-process-ticks",
            "authority-observations",
            "cash-quota-exhaustion",
            "uncertain-settlement",
        ),
    )


def test_controller_retention_escapes_and_soak_remain_offline(
    tmp_path: Path,
) -> None:
    # Given: bounded fixture state with no provider, network, Git, or source mutation authority.
    # When: retention recovery, ignored-state escapes, and a finite soak sequence execute.
    # Then: durable recovery succeeds, escape attempts fail closed, and the soak stays bounded.
    _assert_receipts(
        run_retention_and_soak_sequence(tmp_path),
        ("retention-recovery", "ignored-state-escapes", "offline-soak"),
    )
