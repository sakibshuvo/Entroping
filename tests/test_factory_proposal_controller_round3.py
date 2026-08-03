from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from socket import getaddrinfo, socket
from subprocess import Popen
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from factory_proposal_controller_test_receipt_contracts import (
    MAX_SUMMARIZED_PATHS,
    ScenarioReceipt,
)
from factory_proposal_controller_test_receipt_state import _walk, write_new_receipt
from factory_proposal_controller_test_receipts import (
    PendingReceipt,
    ScenarioObservation,
    _validate_payload,
)
from factory_proposal_controller_test_restart import parse_child_state
from factory_proposal_controller_test_safety import simulated_provider_boundary
from factory_proposal_controller_test_sequences import free_local_assignment
from factory_proposal_controller_test_source_manifest import source_manifest
from factory_proposal_controller_test_support import offline_scenario
from pydantic import ValidationError

_CACHED_BIND = socket.bind
_CACHED_POSIX_SPAWN = os.posix_spawn


@offline_scenario
def startup_boundary_probe(root: Path) -> PendingReceipt:
    observed = ScenarioObservation.begin(root, "startup-boundary-probe")
    actions = (
        lambda: getaddrinfo("localhost", 80),
        lambda: Popen(["/usr/bin/true"]),
        lambda: _CACHED_POSIX_SPAWN("/usr/bin/true", ("true",), os.environ),
        lambda: _CACHED_BIND(socket(), ("127.0.0.1", 0)),
    )
    for action in actions:
        try:
            action()
        except RuntimeError as exc:
            assert str(exc) == "offline test boundary reached"
        else:
            raise AssertionError("cached startup alias bypassed offline boundary")
    return observed.receipt(return_class="fail-closed")


def test_provider_calls_are_observed_and_not_claimed_absent(tmp_path: Path) -> None:
    receipt = simulated_provider_boundary(tmp_path)
    assert receipt.provider_call_count == 1 and receipt.fake_call_count == 0
    assert "no-provider" not in receipt.invariants


def test_composed_scenario_installs_deny_boundary_before_module_import(tmp_path: Path) -> None:
    receipt = startup_boundary_probe(tmp_path)
    assert "offline" in receipt.invariants
    assert receipt.provider_call_count == receipt.fake_call_count == 0


def test_source_manifest_detects_preexisting_untracked_source_mutation(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "issue-1575-untracked-probe.py"
    path.write_text("before = 1\n", encoding="utf-8")
    try:
        before = source_manifest()
        path.write_text("after = 2\n", encoding="utf-8")
        assert source_manifest() != before
    finally:
        path.unlink(missing_ok=True)


def test_receipt_contract_rejects_every_malformed_field_class() -> None:
    base = {
        "schema_version": 1,
        "scenario": "strict-receipt",
        "crash_point": "none",
        "return_class": "assigned",
        "state_digest": "a" * 64,
        "fake_call_count": 0,
        "provider_call_count": 0,
        "changed_paths": (),
        "file_total": 0,
        "byte_total": 0,
        "durations_ms": {"compose": 0, "verify": 0},
        "invariants": ("offline",),
    }
    mutations = (
        {"schema_version": 2},
        {"schema_version": True},
        {"scenario": ""},
        {"scenario": "UPPERCASE"},
        {"crash_point": "other"},
        {"return_class": "other"},
        {"state_digest": "A" * 64},
        {"state_digest": "z" * 64},
        {"fake_call_count": True},
        {"fake_call_count": -1},
        {"fake_call_count": 17},
        {"provider_call_count": "0"},
        {"provider_call_count": -1},
        {"file_total": -1},
        {"file_total": 513},
        {"byte_total": True},
        {"byte_total": 2_000_001},
        {"durations_ms": {"compose": 0}},
        {"durations_ms": {"compose": 0, "verify": 0, "extra": 0}},
        {"durations_ms": {"compose": -1, "verify": 0}},
        {"durations_ms": {"compose": True, "verify": 0}},
        {"durations_ms": {"compose": 60_001, "verify": 0}},
        {"changed_paths": (".entroping", ".entroping")},
        {"changed_paths": ("other",)},
        {"invariants": ("offline", "offline")},
        {"invariants": ("other",)},
        {"unexpected": 1},
    )
    for mutation in mutations:
        payload = {**base, **mutation}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with pytest.raises(AssertionError):
            _validate_payload(payload, encoded)
    encoded = json.dumps({**base, "scenario": "other"}, separators=(",", ":"))
    with pytest.raises(AssertionError):
        _validate_payload(base, encoded)


def test_receipt_write_survives_ancestor_swap_without_escape(tmp_path: Path) -> None:
    safe = tmp_path / "safe"
    original = tmp_path / "safe-original"
    external = tmp_path / "external"
    (safe / "receipts").mkdir(parents=True)
    external.mkdir()
    target = safe / "receipts" / "race.json"
    real_open = os.open
    swapped = False

    def strict_open(
        path: str, flags: int, mode: int | None = None, *, dir_fd: int | None = None
    ) -> int:
        if flags & os.O_CREAT:
            assert mode is not None and mode & 0o077 == 0
            return real_open(path, flags, mode, dir_fd=dir_fd)
        assert mode is None
        return real_open(path, flags, dir_fd=dir_fd)

    def swap_then_open(
        path: str, flags: int, mode: int | None = None, *, dir_fd: int | None = None
    ) -> int:
        nonlocal swapped
        if path == "receipts" and not swapped:
            safe.rename(original)
            safe.symlink_to(external, target_is_directory=True)
            swapped = True
        if flags & os.O_CREAT:
            assert mode is not None
            return strict_open(path, flags, mode, dir_fd=dir_fd)
        return strict_open(path, flags, dir_fd=dir_fd)

    with patch(
        "factory_proposal_controller_test_receipt_state.os.open", side_effect=swap_then_open
    ):
        write_new_receipt(target, "bounded")
    assert (original / "receipts" / "race.json").read_text() == "bounded"
    assert (original / "receipts" / "race.json").stat().st_mode & 0o077 == 0
    assert not (external / "race.json").exists()


def test_repeated_and_concurrent_receipts_match_deterministic_state(tmp_path: Path) -> None:
    roots = tuple(tmp_path / f"run-{index}" for index in range(4))
    first = free_local_assignment(roots[0])
    second = free_local_assignment(roots[1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = tuple(pool.map(free_local_assignment, roots[2:]))
    expected = _deterministic_view(first)
    assert _deterministic_view(second) == expected
    assert all(_deterministic_view(receipt) == expected for receipt in concurrent)


def _deterministic_view(receipt: ScenarioReceipt) -> tuple[str | int | tuple[str, ...], ...]:
    """Exclude only path and content digest, whose generated IDs are intentionally volatile."""

    return (
        receipt.scenario,
        receipt.crash_point,
        receipt.return_class,
        receipt.fake_call_count,
        receipt.provider_call_count,
        receipt.changed_paths,
        receipt.file_total,
        receipt.byte_total,
        receipt.invariants,
    )


def test_scandir_stops_at_first_disallowed_entry(tmp_path: Path) -> None:
    entries = _CountingEntries(tmp_path, MAX_SUMMARIZED_PATHS + 20)
    with (
        patch("factory_proposal_controller_test_receipt_state.os.scandir", return_value=entries),
        pytest.raises(AssertionError, match="path count"),
    ):
        tuple(_walk(tmp_path, MAX_SUMMARIZED_PATHS))
    assert entries.consumed == MAX_SUMMARIZED_PATHS and entries.closed


def test_child_payload_and_short_write_cleanup_are_strict(tmp_path: Path) -> None:
    malformed = {
        "assignment_state": None,
        "authorization_id": None,
        "phase": None,
        "phase_version": None,
        "reservation_state": "uncertain",
        "held_microcents": "60",
        "spent_microcents": 0,
        "terminal_outcome": None,
        "extra": True,
    }
    strict_extra = {**malformed, "held_microcents": 60}
    for payload in (malformed, strict_extra):
        with pytest.raises(ValidationError):
            parse_child_state(json.dumps(payload))
    path = tmp_path / "short-write.json"
    with (
        patch("factory_proposal_controller_test_receipt_state.os.write", return_value=1),
        pytest.raises(AssertionError, match="incomplete"),
    ):
        write_new_receipt(path, "bounded")
    assert not path.exists()


class _CountingEntries:
    def __init__(self, root: Path, total: int) -> None:
        self.root = root
        self.total = total
        self.consumed = 0
        self.closed = False

    def __iter__(self) -> _CountingEntries:
        return self

    def __next__(self) -> SimpleNamespace:
        if self.consumed == self.total:
            raise StopIteration
        self.consumed += 1
        path = self.root / f"entry-{self.consumed}"
        return SimpleNamespace(path=str(path), is_dir=lambda **_kwargs: False)

    def close(self) -> None:
        self.closed = True
