from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_status_test_support import write_status_policy  # noqa: E402

from scripts import factory_status, factory_status_dispatch, factory_status_quota  # noqa: E402
from scripts.factory_status import collect_factory_status  # noqa: E402


def test_lane_pair_ceiling_accepts_boundary_and_rejects_next_pair(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Route pairing is bounded before quota evaluation or output construction."""

    write_status_policy(tmp_path, datetime.now(UTC))
    monkeypatch.setattr(factory_status_dispatch, "MAX_LANE_PAIRS", 2, raising=False)
    at_boundary = collect_factory_status(tmp_path)
    monkeypatch.setattr(factory_status_dispatch, "MAX_LANE_PAIRS", 1, raising=False)
    above_boundary = collect_factory_status(tmp_path)

    assert at_boundary.dispatch_lanes.status != "unsafe"
    assert above_boundary.dispatch_lanes.status == "unsafe"
    assert "dispatch-amplification-unsafe" in above_boundary.reason_codes


def test_quota_evaluation_ceiling_accepts_boundary_and_rejects_next_evaluation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Quota work is bounded before the ledger is opened or queried."""

    write_status_policy(tmp_path, datetime.now(UTC), quota_backed=True)
    monkeypatch.setattr(factory_status_quota, "MAX_QUOTA_EVALUATIONS", 2, raising=False)
    at_boundary = collect_factory_status(tmp_path)
    monkeypatch.setattr(factory_status_quota, "MAX_QUOTA_EVALUATIONS", 1, raising=False)
    above_boundary = collect_factory_status(tmp_path)

    assert at_boundary.dispatch_lanes.status != "unsafe"
    assert above_boundary.dispatch_lanes.status == "unsafe"
    assert "dispatch-amplification-unsafe" in above_boundary.reason_codes


def test_output_size_ceiling_accepts_exact_boundary_and_sanitizes_exceedance(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A valid but oversized projection collapses to a bounded unsafe report."""

    baseline = collect_factory_status(tmp_path)
    exact_size = len(baseline.model_dump_json().encode("utf-8"))
    monkeypatch.setattr(factory_status, "MAX_STATUS_OUTPUT_BYTES", exact_size, raising=False)
    at_boundary = collect_factory_status(tmp_path)
    monkeypatch.setattr(factory_status, "MAX_STATUS_OUTPUT_BYTES", exact_size - 1, raising=False)
    above_boundary = collect_factory_status(tmp_path)

    assert "output-limit-unsafe" not in at_boundary.reason_codes
    assert above_boundary.state == "unsafe"
    assert above_boundary.reason_codes == ("output-limit-unsafe",)
