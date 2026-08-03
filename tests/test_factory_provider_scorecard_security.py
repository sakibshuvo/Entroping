"""Security boundary tests for provider scorecard evidence."""
# ruff: noqa: E402, E501

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from support.provider_scorecard import (  # pyright: ignore[reportImplicitRelativeImport]
    SCORECARD_KEY,
    case,
    cost_digest,
    document,
    report,
    validate,
    write_scorecard,
)

from entroping.core import owner_only_evidence  # noqa: E402
from scripts.factory_metrics_modules.errors import FactoryMetricsError  # noqa: E402
from scripts.factory_metrics_modules.provider_scorecard_io import (  # noqa: E402
    load_provider_scorecard,
)


def test_permission_swap_between_authorization_and_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an authenticated owner-only artifact whose mode changes at first read.
    path = write_scorecard(tmp_path, document(case(1)))
    original_read = owner_only_evidence.read_bounded_local_evidence_bytes_from_descriptor
    changed = False

    def change_mode_then_read(descriptor: int, *, max_bytes: int) -> tuple[bytes | None, str]:
        nonlocal changed
        if not changed:
            os.chmod(path, 0o644)
            changed = True
        return original_read(descriptor, max_bytes=max_bytes)

    monkeypatch.setattr(
        owner_only_evidence,
        "read_bounded_local_evidence_bytes_from_descriptor",
        change_mode_then_read,
    )
    monkeypatch.setenv("ENTROPING_FACTORY_SCORECARD_EVIDENCE_HMAC_KEY_V1", SCORECARD_KEY)

    # When/Then: bytes from a descriptor whose authorization changed cannot load.
    with pytest.raises(FactoryMetricsError, match="authentication failed"):
        _ = load_provider_scorecard(path)


def test_authenticated_scorecard_validates_and_wrong_or_missing_key_cannot_validate(
    tmp_path: Path,
) -> None:
    # Given: one owner-only, HMAC-authenticated scorecard.
    path = write_scorecard(tmp_path, document(case(1)))

    # When: the CLI receives the correct, wrong, and missing dedicated key.
    valid = validate(tmp_path, path)
    wrong = validate(tmp_path, path, key="b" * 64)
    missing = validate(tmp_path, path, key=None)

    # Then: only the dedicated correct key reaches validation.
    assert valid.returncode == 0
    assert wrong.returncode == missing.returncode == 1
    assert SCORECARD_KEY not in wrong.stdout + missing.stdout


def test_tampered_authenticated_scorecard_cannot_report_or_become_eligible(
    tmp_path: Path,
) -> None:
    # Given: a signed cohort whose unsigned bytes are changed after signing.
    value = document(case(1), case(2), case(3))
    cases = value["cases"]
    assert isinstance(cases, list) and isinstance(cases[0], dict)
    cases[0]["task_type"] = "tampered"
    path = write_scorecard(tmp_path, value)

    # When: report evaluates the changed document.
    result = report(tmp_path, path)

    # Then: authentication fails before an eligibility row can be emitted.
    assert result.returncode == 1
    assert "scorecards" not in result.stdout


def test_replay_identifiers_are_unique_across_cases(tmp_path: Path) -> None:
    # Given: distinct jobs that replay the same underlying work identity.
    first = case(1)
    second = case(2)
    identity = second["identity"]
    assert isinstance(identity, dict)
    identity.update(
        {"base_revision": "1" * 40, "head_revision": "b" * 39 + "1", "diff_sha256": "c" * 63 + "1"}
    )
    for name in ("review", "verification", "ci", "merge"):
        receipt = second[name]
        assert isinstance(receipt, dict)
        receipt.update(identity)
    second["cost_receipt_digest"] = cost_digest(identity, 1.5)
    path = write_scorecard(tmp_path, document(first, second))

    # When: strict evidence validation runs.
    result = validate(tmp_path, path)

    # Then: sample inflation by repeated work is rejected.
    assert result.returncode == 1
    assert "underlying work" in result.stdout


@pytest.mark.parametrize("field", ["reservation_id", "run_id", "pr_number"])
def test_replayed_reservation_ci_or_merged_pr_is_rejected(tmp_path: Path, field: str) -> None:
    # Given: two distinct work samples with one replayed attestation identifier.
    first = case(1)
    second = case(2)
    source = (
        first["identity"]
        if field == "reservation_id"
        else first["ci"]
        if field == "run_id"
        else first["merge"]
    )
    target = (
        second["identity"]
        if field == "reservation_id"
        else second["ci"]
        if field == "run_id"
        else second["merge"]
    )
    assert isinstance(source, dict) and isinstance(target, dict)
    target[field] = source[field]
    if field == "reservation_id":
        for name in ("review", "verification", "ci", "merge"):
            receipt = second[name]
            assert isinstance(receipt, dict)
            receipt[field] = source[field]
        identity = second["identity"]
        assert isinstance(identity, dict)
        second["cost_receipt_digest"] = cost_digest(identity, 1.5)
    path = write_scorecard(tmp_path, document(first, second))

    # When: the signed replay is submitted.
    result = validate(tmp_path, path)

    # Then: it is rejected before report aggregation.
    assert result.returncode == 1
    assert "duplicate" in result.stdout
