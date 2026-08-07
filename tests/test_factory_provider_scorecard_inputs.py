"""Adversarial input and replay tests for provider-scorecard evidence."""
# ruff: noqa: E402, E501

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from support.provider_scorecard import (  # pyright: ignore[reportImplicitRelativeImport]
    case,
    cost_digest,
    document,
    identity,
    sign,
    validate,
    write_scorecard,
    write_scorecard_bytes,
)


def test_fixed_independent_hmac_canonical_vector_validates(tmp_path: Path) -> None:
    value: dict[str, object] = {
        "schema_version": "entroping.provider-scorecard-evidence.v1",
        "cases": [],
        "authentication": {
            "scheme": "hmac-sha256",
            "key_id": "maintainer-local-v1",
            "signature": "f3b789e6b4e2e218a98e850648882dbfa11beab3d7406190ec1ef04abd1e2928",
        },
    }
    result = validate(tmp_path, write_scorecard(tmp_path, value))
    assert result.returncode == 0


@pytest.mark.parametrize("receipt_name", ("review", "verification", "ci", "merge"))
def test_duplicate_terminal_receipt_digest_is_rejected(tmp_path: Path, receipt_name: str) -> None:
    first, second = case(1), case(2)
    source, target = first[receipt_name], second[receipt_name]
    assert isinstance(source, dict) and isinstance(target, dict)
    target["digest"] = source["digest"]
    result = validate(tmp_path, write_scorecard(tmp_path, document(first, second)))
    assert result.returncode == 1
    assert "duplicate receipt digest" in result.stdout


def test_duplicate_later_outcome_digest_is_rejected_globally(tmp_path: Path) -> None:
    first_outcome = {
        **identity(1),
        "status": "passed",
        "observed_at": "2026-08-02T00:00:00Z",
        "merge_commit_revision": "f" * 39 + "1",
        "digest": "2" * 64,
    }
    second_outcome = {
        **identity(2),
        "status": "passed",
        "observed_at": "2026-08-02T00:00:00Z",
        "merge_commit_revision": "f" * 39 + "2",
        "digest": "2" * 64,
    }
    result = validate(
        tmp_path,
        write_scorecard(
            tmp_path,
            document(
                case(1, later_outcomes=[first_outcome]), case(2, later_outcomes=[second_outcome])
            ),
        ),
    )
    assert result.returncode == 1
    assert "duplicate receipt digest" in result.stdout


def test_receipt_digest_cannot_replay_a_cost_digest_cross_kind(tmp_path: Path) -> None:
    first, second = case(1), case(2)
    receipt = second["review"]
    assert isinstance(receipt, dict) and isinstance(first["cost_receipt_digest"], str)
    receipt["digest"] = first["cost_receipt_digest"]
    result = validate(tmp_path, write_scorecard(tmp_path, document(first, second)))
    assert result.returncode == 1
    assert "duplicate receipt digest" in result.stdout


def test_duplicate_job_id_is_rejected_even_when_work_differs(tmp_path: Path) -> None:
    first, second = case(1), case(2)
    second_identity = second["identity"]
    assert isinstance(second_identity, dict)
    second_identity["job_id"] = "job-1"
    for name in ("review", "verification", "ci", "merge"):
        receipt = second[name]
        assert isinstance(receipt, dict)
        receipt["job_id"] = "job-1"
    second["cost_receipt_digest"] = cost_digest(second_identity, 1.5)
    result = validate(tmp_path, write_scorecard(tmp_path, document(first, second)))
    assert result.returncode == 1
    assert "duplicate job" in result.stdout


@pytest.mark.parametrize(
    ("name", "raw", "message"),
    (
        (
            "duplicate.json",
            b'{"schema_version":"x","schema_version":"y","cases":[]}',
            "duplicate JSON key",
        ),
        ("utf8.json", b"\xff\xfe", "UTF-8"),
        ("nonfinite.json", b'{"schema_version":NaN,"cases":[]}', "non-finite"),
    ),
)
def test_unsafe_raw_json_is_rejected(tmp_path: Path, name: str, raw: bytes, message: str) -> None:
    result = validate(tmp_path, write_scorecard_bytes(tmp_path, raw, name=name))
    assert result.returncode == 1
    assert message in result.stdout


def test_extra_field_and_secret_like_content_are_rejected(tmp_path: Path) -> None:
    extra = sign(
        {"schema_version": "entroping.provider-scorecard-evidence.v1", "cases": [], "extra": True}
    )
    secret = document(case(1, task_type="sk-proj-abcdefghijklmnopqrstuvwxyz"))
    extra_result = validate(tmp_path, write_scorecard(tmp_path, extra, name="extra.json"))
    secret_result = validate(tmp_path, write_scorecard(tmp_path, secret, name="secret.json"))
    assert extra_result.returncode == secret_result.returncode == 1
    assert "extra" in extra_result.stdout.lower()
    assert "secret-like" in secret_result.stdout


def test_symlink_directory_oversize_and_permissions_are_rejected(tmp_path: Path) -> None:
    real = write_scorecard(tmp_path, document(case(1)), name="real.json")
    link = real.with_name("link.json")
    link.symlink_to(real)
    directory = real.with_name("directory.json")
    directory.mkdir()
    oversized = write_scorecard_bytes(tmp_path, b" " * (1024 * 1024 + 1), name="large.json")
    permissive = write_scorecard(tmp_path, document(case(2)), name="mode.json")
    os.chmod(permissive, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    results = (
        validate(tmp_path, link),
        validate(tmp_path, directory),
        validate(tmp_path, oversized),
        validate(tmp_path, permissive),
    )
    assert all(result.returncode == 1 for result in results)


def test_merge_status_and_commit_presence_must_agree(tmp_path: Path) -> None:
    missing_commit = case(1)
    first_merge = missing_commit["merge"]
    assert isinstance(first_merge, dict)
    first_merge["merge_commit_revision"] = None
    unexpected_commit = case(2)
    second_merge = unexpected_commit["merge"]
    assert isinstance(second_merge, dict)
    second_merge["status"] = "not_merged"
    first = validate(
        tmp_path, write_scorecard(tmp_path, document(missing_commit), name="missing.json")
    )
    second = validate(
        tmp_path, write_scorecard(tmp_path, document(unexpected_commit), name="unexpected.json")
    )
    assert first.returncode == second.returncode == 1
    assert "merge_commit" in first.stdout + second.stdout
