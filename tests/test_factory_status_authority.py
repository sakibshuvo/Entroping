from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_status_test_support import write_status_policy  # noqa: E402

from scripts.factory_status_dispatch import collect_dispatch_lanes  # noqa: E402


@pytest.mark.parametrize(
    "filename",
    ("factory-cost-policy.example.json", "provider-capability-registry.json"),
)
def test_dispatch_authority_read_remains_bound_to_opened_descriptor(
    tmp_path: Path, monkeypatch: MonkeyPatch, filename: str
) -> None:
    """A same-UID pathname replacement cannot change validated authority content."""

    write_status_policy(tmp_path, datetime.now(UTC))
    path = tmp_path / "docs" / "meta" / filename
    original_inode = path.stat().st_ino
    replacement = path.with_suffix(f"{path.suffix}.replacement")
    replacement.write_text("{", encoding="utf-8")
    original_pread = os.pread
    swapped = False

    def swap_before_descriptor_read(descriptor: int, length: int, offset: int) -> bytes:
        nonlocal swapped
        if not swapped and os.fstat(descriptor).st_ino == original_inode:
            os.replace(replacement, path)
            swapped = True
        return original_pread(descriptor, length, offset)

    monkeypatch.setattr(os, "pread", swap_before_descriptor_read)

    status, reasons = collect_dispatch_lanes(tmp_path, datetime.now(UTC), [])

    assert swapped is True
    assert status.status == "unsafe"
    assert reasons == ("dispatch-policy-unsafe",)
