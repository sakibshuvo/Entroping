from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from factory_proposal_controller_test_receipt_contracts import MAX_SUMMARIZED_PATHS
from factory_proposal_controller_test_receipt_state import _walk
from factory_proposal_controller_test_receipts import _write_new_receipt
from factory_proposal_controller_test_restart import parse_child_state
from factory_proposal_controller_test_safety import simulated_provider_boundary
from pydantic import ValidationError


def test_provider_calls_are_observed_and_not_claimed_absent(tmp_path: Path) -> None:
    receipt = simulated_provider_boundary(tmp_path)
    assert receipt.provider_call_count == 1 and receipt.fake_call_count == 0
    assert "no-provider" not in receipt.invariants


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
        patch("factory_proposal_controller_test_receipts.os.write", return_value=1),
        pytest.raises(AssertionError, match="incomplete"),
    ):
        _write_new_receipt(path, "bounded")
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
