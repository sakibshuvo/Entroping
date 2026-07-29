from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_issue_selector_cache import (  # noqa: E402
    CACHE_RELATIVE_PATH,
    CacheError,
    read_snapshot,
    write_snapshot,
)
from scripts.factory_issue_selector_models import (  # noqa: E402
    GitHubSnapshot,
    JsonObject,
    SnapshotMetadata,
)
from scripts.factory_issue_selector_parser import parse_issue  # noqa: E402

AS_OF = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def _snapshot() -> GitHubSnapshot:
    body = (
        "## Outcome\n\nSelect.\n\n## Scope\n\nRead.\n\n"
        "## Non-goals\n\nNo dispatch.\n\n"
        "## Acceptance criteria\n\n- Deterministic.\n\n"
        "## Verification\n\nVerification lane: `normal-code`.\n\n"
        "## Autonomy\n\nTier B.\n\n"
        "## Allowed files\n\n- scripts/selector.py\n\n"
        "PRIVATE-BODY-MARKER"
    )
    issue = parse_issue(
        {
            "number": 80,
            "title": "Selector",
            "state": "open",
            "html_url": "https://github.com/sakibshuvo/Entroping/issues/80",
            "body": body,
            "labels": [
                {"name": "type:feature"},
                {"name": "priority:p1"},
                {"name": "status:ready"},
                {"name": "autonomy:tier-b"},
            ],
            "assignees": [],
            "milestone": {"title": "Factory"},
        }
    )
    return GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=AS_OF,
            expires_at=AS_OF + timedelta(seconds=60),
            complete=True,
        ),
        issues=(issue,),
        open_pr_issue_numbers=frozenset({79}),
    )


def test_snapshot_cache_round_trip_is_owner_only_and_sanitized(tmp_path: Path) -> None:
    write_snapshot(tmp_path, _snapshot())

    cache_path = tmp_path / CACHE_RELATIVE_PATH
    cached = cache_path.read_text(encoding="utf-8")
    restored = read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")

    assert cache_path.stat().st_mode & 0o777 == 0o600
    assert "PRIVATE-BODY-MARKER" not in cached
    assert "user_evidence" not in cached
    assert restored == _snapshot()


def test_snapshot_cache_rejects_symlink_destination(tmp_path: Path) -> None:
    external = tmp_path / "external.json"
    external.write_text("{}", encoding="utf-8")
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    cache_path.parent.mkdir(parents=True)
    try:
        cache_path.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(CacheError, match="non-symlink"):
        write_snapshot(tmp_path, _snapshot())

    assert external.read_text(encoding="utf-8") == "{}"


def test_snapshot_cache_rejects_group_readable_or_corrupt_file(tmp_path: Path) -> None:
    write_snapshot(tmp_path, _snapshot())
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    cache_path.chmod(0o640)

    with pytest.raises(CacheError, match="owner-only"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")

    cache_path.chmod(0o600)
    cache_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(CacheError, match="invalid JSON"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")


@pytest.mark.parametrize(
    "raw",
    (
        '{"schema_version":"first","schema_version":"second"}',
        '{"schema_version":NaN}',
    ),
)
def test_snapshot_cache_rejects_ambiguous_json(tmp_path: Path, raw: str) -> None:
    write_snapshot(tmp_path, _snapshot())
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    cache_path.write_text(raw, encoding="utf-8")

    with pytest.raises(CacheError, match="invalid JSON"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")


def test_snapshot_cache_rejects_wrong_repo_and_excessive_ttl(tmp_path: Path) -> None:
    write_snapshot(tmp_path, _snapshot())
    with pytest.raises(CacheError, match="repository mismatch"):
        read_snapshot(tmp_path, expected_repo="other/project")

    snapshot = _snapshot()
    oversized = GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo=snapshot.metadata.repo,
            fetched_at=AS_OF,
            expires_at=AS_OF + timedelta(seconds=301),
            complete=True,
        ),
        issues=snapshot.issues,
        open_pr_issue_numbers=snapshot.open_pr_issue_numbers,
    )
    with pytest.raises(CacheError, match="TTL"):
        write_snapshot(tmp_path, oversized)


def test_snapshot_cache_rejects_special_file(tmp_path: Path) -> None:
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    cache_path.parent.mkdir(parents=True)
    os.mkfifo(cache_path)
    try:
        with pytest.raises(CacheError, match="regular"):
            read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")
    finally:
        cache_path.unlink()


@pytest.mark.parametrize(
    ("evidence", "remove_label"),
    (
        ({"valid": False, "verified": True, "severity": "blocker", "warning": None}, False),
        ({"valid": True, "verified": False, "severity": None, "warning": None}, False),
        ({"valid": False, "verified": False, "severity": "major", "warning": None}, False),
        (
            {
                "valid": True,
                "verified": True,
                "severity": "blocker",
                "warning": "user-evidence-invalid",
            },
            False,
        ),
        ({"valid": True, "verified": True, "severity": "blocker", "warning": None}, True),
    ),
)
def test_snapshot_cache_rejects_impossible_evidence_states(
    tmp_path: Path, evidence: JsonObject, remove_label: bool
) -> None:
    snapshot = _snapshot()
    issue = snapshot.issues[0]
    labels = tuple(
        sorted(issue.labels + (() if remove_label else ("evidence:user-verified",)))
    )
    verified_issue = replace(issue, labels=labels)
    write_snapshot(
        tmp_path,
        GitHubSnapshot(
            metadata=snapshot.metadata,
            issues=(verified_issue,),
            open_pr_issue_numbers=snapshot.open_pr_issue_numbers,
        ),
    )
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["issues"][0]["evidence"] = evidence
    if remove_label:
        payload["issues"][0]["labels"] = list(issue.labels)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CacheError, match="cached evidence state is invalid"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")


def test_snapshot_cache_rejects_writable_or_permissive_managed_directories(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path, _snapshot())
    managed_root = tmp_path / ".entroping"
    cache_directory = (tmp_path / CACHE_RELATIVE_PATH).parent

    cache_directory.chmod(0o750)
    with pytest.raises(CacheError, match="managed directory permissions"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")

    cache_directory.chmod(0o700)
    managed_root.chmod(0o775)
    with pytest.raises(CacheError, match="managed directory permissions"):
        write_snapshot(tmp_path, _snapshot())


def test_snapshot_cache_rejects_inconsistent_raw_and_derived_labels(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path, _snapshot())
    cache_path = tmp_path / CACHE_RELATIVE_PATH
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["issues"][0]["labels"] = []
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CacheError, match="cached issue labels are inconsistent"):
        read_snapshot(tmp_path, expected_repo="sakibshuvo/Entroping")
