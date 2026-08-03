from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from factory_proposal_controller_test_cli import run_cli_safety_sequence
from factory_proposal_controller_test_retention import (
    ignored_state_escapes,
    offline_soak,
    retention_recovery,
)
from factory_proposal_controller_test_safety import (
    authority_observations,
    cash_and_quota_exhaustion,
    uncertain_settlement_cases,
)
from factory_proposal_controller_test_sequences import (
    free_local_assignment,
    overlapping_settlement_replay,
    overlapping_ticks,
    paid_exact_settlement,
    replay_and_conflict,
    restart_boundaries,
)
from factory_proposal_controller_test_support import (
    MAX_LIST_ITEMS,
    MAX_RECEIPT_BYTES,
    RECEIPT_SCHEMA_VERSION,
    ScenarioObservation,
    offline_direct_boundary,
    record_receipt,
    run_offline_python,
)


def _assert_receipt(receipt_path: Path) -> None:
    raw = receipt_path.read_bytes()
    payload = json.loads(raw)
    assert len(raw) <= MAX_RECEIPT_BYTES
    assert payload["schema_version"] == RECEIPT_SCHEMA_VERSION
    assert set(payload) == {
        "schema_version",
        "scenario",
        "crash_point",
        "return_class",
        "state_digest",
        "fake_call_count",
        "changed_paths",
        "file_total",
        "byte_total",
        "durations_ms",
        "invariants",
    }
    assert len(payload["state_digest"]) == 64
    assert len(payload["changed_paths"]) <= MAX_LIST_ITEMS
    assert len(payload["invariants"]) <= MAX_LIST_ITEMS
    assert not any(
        marker in raw.decode("utf-8").lower()
        for marker in ("secret", "token", "credential", "password", "api-key", "provider-output")
    )


def test_cli_receipts_are_observed_and_value_free(tmp_path: Path) -> None:
    for receipt in run_cli_safety_sequence(tmp_path):
        _assert_receipt(receipt.path)


def test_free_assignment_invokes_the_counted_fake_worker(tmp_path: Path) -> None:
    receipt = free_local_assignment(tmp_path)
    _assert_receipt(receipt.path)
    assert receipt.fake_call_count == 1


def test_paid_settlement_reopens_and_charges_once(tmp_path: Path) -> None:
    receipt = paid_exact_settlement(tmp_path)
    _assert_receipt(receipt.path)
    assert receipt.fake_call_count == 1


def test_restart_boundaries_use_fresh_children(tmp_path: Path) -> None:
    receipt = restart_boundaries(tmp_path)
    _assert_receipt(receipt.path)
    assert receipt.fake_call_count == 1


def test_replay_conflict_and_overlapping_ticks_fail_closed(tmp_path: Path) -> None:
    for receipt in (
        replay_and_conflict(tmp_path / "replay"),
        overlapping_ticks(tmp_path / "overlap"),
    ):
        _assert_receipt(receipt.path)


def test_overlapping_settlement_replay_charges_once(tmp_path: Path) -> None:
    _assert_receipt(overlapping_settlement_replay(tmp_path).path)


def test_authority_observations_have_exact_safe_outcomes(tmp_path: Path) -> None:
    for receipt in authority_observations(tmp_path):
        _assert_receipt(receipt.path)


def test_cash_quota_and_uncertain_holds_are_isolated(tmp_path: Path) -> None:
    _assert_receipt(cash_and_quota_exhaustion(tmp_path / "cash").path)
    for receipt in uncertain_settlement_cases(tmp_path / "uncertain"):
        _assert_receipt(receipt.path)


def test_retention_escape_and_soak_scenarios_are_bounded(tmp_path: Path) -> None:
    for receipt in (
        retention_recovery(tmp_path / "retention"),
        ignored_state_escapes(tmp_path / "escapes"),
        offline_soak(tmp_path / "soak"),
    ):
        _assert_receipt(receipt.path)


def test_parent_and_child_offline_guards_deny_network_process_and_git(tmp_path: Path) -> None:
    with offline_direct_boundary():
        with pytest.raises(AssertionError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 9))
        with pytest.raises(AssertionError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect_ex(("127.0.0.1", 9))
        with pytest.raises(AssertionError):
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9))
        with pytest.raises(AssertionError):
            subprocess.Popen(["/usr/bin/git", "--version"])
        with pytest.raises(AssertionError):
            os.system("/usr/bin/git --version")
        with pytest.raises(AssertionError):
            os.spawnv(os.P_WAIT, "/usr/bin/git", ("git", "--version"))
    for code in (
        "import socket; socket.socket().connect_ex(('127.0.0.1', 9))",
        "import subprocess; subprocess.Popen(['/usr/bin/git', '--version'])",
        "import os; os.system('/usr/bin/git --version')",
    ):
        result = run_offline_python(tmp_path, code)
        assert result.returncode != 0 and "offline test boundary reached" in result.stderr


def test_receipt_rejects_canaries_and_oversized_durable_state(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        record_receipt(
            ScenarioObservation.begin(tmp_path, "secret-canary"),
            return_class="assigned",
            crash_point="none",
            checks={"offline": True},
        )
    oversized = tmp_path / ".entroping" / "oversized.bin"
    oversized.parent.mkdir()
    oversized.write_bytes(b"x" * 2_000_001)
    with pytest.raises(AssertionError):
        ScenarioObservation.begin(tmp_path, "oversized-state")
