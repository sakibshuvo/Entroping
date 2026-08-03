from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from factory_proposal_controller_test_cli import run_cli_safety_sequence
from factory_proposal_controller_test_paths import ignored_state_escapes
from factory_proposal_controller_test_receipt_contracts import (
    MAX_SUMMARIZED_BYTES,
    MAX_SUMMARIZED_FILE_BYTES,
    MAX_SUMMARIZED_FILES,
    MAX_SUMMARIZED_PATHS,
)
from factory_proposal_controller_test_receipts import _validate_payload
from factory_proposal_controller_test_retention import (
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
    overlapping_ticks,
    replay_and_conflict,
)
from factory_proposal_controller_test_settlement import (
    overlapping_settlement_replay,
    paid_exact_settlement,
    restart_boundaries,
)
from factory_proposal_controller_test_support import (
    MAX_LIST_ITEMS,
    MAX_RECEIPT_BYTES,
    RECEIPT_SCHEMA_VERSION,
    ScenarioObservation,
    offline_direct_boundary,
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
    receipts = run_cli_safety_sequence(tmp_path)
    for receipt in receipts:
        _assert_receipt(receipt.path)
    blocked = next(item for item in receipts if item.scenario == "blocked-dispatch-cli")
    assert blocked.fake_call_count == 0 and "no-worker" in blocked.invariants


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
    blocked = cash_and_quota_exhaustion(tmp_path / "cash")
    _assert_receipt(blocked.path)
    assert blocked.fake_call_count == 0 and "no-worker" in blocked.invariants
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
        for action in (
            lambda: socket.socket().bind(("127.0.0.1", 0)),
            lambda: socket.socket().listen(1),
            lambda: socket.socket().accept(),
        ):
            with pytest.raises(AssertionError):
                action()
        with pytest.raises(AssertionError):
            subprocess.Popen(["/usr/bin/git", "--version"])
        with pytest.raises(AssertionError):
            os.system("/usr/bin/git --version")
        with pytest.raises(AssertionError):
            os.spawnv(os.P_WAIT, "/usr/bin/git", ("git", "--version"))
        if hasattr(os, "posix_spawn"):
            with pytest.raises(AssertionError):
                os.posix_spawn("/usr/bin/git", ("git", "--version"), os.environ)
        if hasattr(os, "posix_spawnp"):
            with pytest.raises(AssertionError):
                os.posix_spawnp("/usr/bin/git", ("git", "--version"), os.environ)
    for code in (
        "import socket; socket.socket().connect_ex(('127.0.0.1', 9))",
        "import subprocess; subprocess.Popen(['/usr/bin/git', '--version'])",
        "import os; os.system('/usr/bin/git --version')",
        "import os; os.posix_spawn('/usr/bin/git', ('git', '--version'), os.environ)",
        "import os; os.posix_spawnp('/usr/bin/git', ('git', '--version'), os.environ)",
        "import socket; socket.socket().bind(('127.0.0.1', 0))",
        "import socket; socket.socket().listen(1)",
        "import socket; socket.socket().accept()",
    ):
        result = run_offline_python(tmp_path, code)
        assert result.returncode != 0 and "offline test boundary reached" in result.stderr
    seam = run_offline_python(
        tmp_path,
        "from pathlib import Path; import scripts.factory_scheduler as scheduler; "
        "root = Path.cwd(); assert scheduler.resolve_scheduler_root(root) == root",
    )
    assert seam.returncode == 0, seam.stderr


def test_receipt_rejects_categorical_and_value_leak_boundaries(tmp_path: Path) -> None:
    observed = ScenarioObservation.begin(tmp_path, "receipt-boundary")
    for value in ("/tmp/crash", "raw-worker-output", "x" * 97):
        with pytest.raises(AssertionError):
            observed.receipt(return_class="assigned", crash_point=value)
    base = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scenario": "receipt-boundary",
        "crash_point": "none",
        "return_class": "assigned",
        "state_digest": "a" * 64,
        "fake_call_count": 0,
        "changed_paths": (),
        "file_total": 0,
        "byte_total": 0,
        "durations_ms": {"compose": 0, "verify": 0},
        "invariants": ("offline",),
    }
    for changed in (("/absolute",), tuple("x" for _ in range(MAX_LIST_ITEMS + 1)), ("x" * 97,)):
        payload = {**base, "changed_paths": changed}
        with pytest.raises(AssertionError):
            _validate_payload(payload, json.dumps(payload))
    payload = {**base, "invariants": tuple("offline" for _ in range(MAX_LIST_ITEMS + 1))}
    with pytest.raises(AssertionError):
        _validate_payload(payload, json.dumps(payload))
    for marker in ("secret", "token", "credential", "password", "api-key", "provider-output"):
        payload = {**base, "scenario": f"receipt-{marker}"}
        with pytest.raises(AssertionError):
            _validate_payload(payload, json.dumps(payload))


def test_state_summary_aborts_at_each_streaming_bound(tmp_path: Path) -> None:
    file_root = tmp_path / "files" / ".entroping"
    file_root.mkdir(parents=True)
    for index in range(MAX_SUMMARIZED_FILES + 1):
        (file_root / f"{index}.txt").touch()
    with pytest.raises(AssertionError, match="file count"):
        ScenarioObservation.begin(tmp_path / "files", "file-overflow")
    path_root = tmp_path / "paths" / ".entroping"
    path_root.mkdir(parents=True)
    for index in range(MAX_SUMMARIZED_PATHS + 1):
        (path_root / f"d-{index}").mkdir()
    with pytest.raises(AssertionError, match="path count"):
        ScenarioObservation.begin(tmp_path / "paths", "path-overflow")
    byte_root = tmp_path / "bytes" / ".entroping"
    byte_root.mkdir(parents=True)
    for index in range(3):
        (byte_root / f"{index}.bin").write_bytes(b"x" * (MAX_SUMMARIZED_BYTES // 3 + 1))
    with pytest.raises(AssertionError, match="aggregate"):
        ScenarioObservation.begin(tmp_path / "bytes", "byte-overflow")
    large_root = tmp_path / "large" / ".entroping"
    large_root.mkdir(parents=True)
    (large_root / "single.bin").write_bytes(b"x" * (MAX_SUMMARIZED_FILE_BYTES + 1))
    with pytest.raises(AssertionError, match="per-file"):
        ScenarioObservation.begin(tmp_path / "large", "per-file-overflow")
