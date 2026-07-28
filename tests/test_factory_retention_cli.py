from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixture(repo: Path) -> tuple[Path, Path, Path]:
    _ = subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=True,
        capture_output=True,
    )
    completed = repo / ".entroping" / "ai-jobs" / "completed"
    failed = repo / ".entroping" / "ai-jobs" / "failed"
    reviews = repo / ".entroping" / "ai-reviews"
    policy = repo / ".entroping" / "policy.json"
    for path in (completed, failed, reviews):
        path.mkdir(parents=True, exist_ok=True)
    review = reviews / "review-j1"
    review.mkdir()
    _ = (review / "metadata.json").write_text(
        json.dumps(
            {
                "status": "ready_for_codex",
                "codex_inbox_status": "rejected",
                "reviewed_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    _ = (review / "result.md").write_text("private provider output", encoding="utf-8")
    job = completed / "j1.json"
    _ = job.write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job.v1",
                "job_id": "j1",
                "queue_status": "completed",
                "artifact_dir": str(review),
                "completed_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    _ = policy.write_text(
        (REPO_ROOT / "docs/meta/factory-retention-policy.example.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return job, review, policy


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_retention",
            *args,
            "--repo-root",
            str(repo),
            "--policy",
            ".entroping/policy.json",
            "--as-of",
            "2026-07-28T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_plan_json_is_read_only_and_value_free(tmp_path: Path) -> None:
    job, review, _ = _fixture(tmp_path)
    result = _run(tmp_path, "plan", "--json")
    assert result.returncode == 0, result.stderr
    raw_payload = cast(object, json.loads(result.stdout))
    assert isinstance(raw_payload, dict)
    payload = cast(dict[str, object], raw_payload)
    assert payload["mode"] == "plan-only"
    assert job.exists() and review.exists()
    assert "private provider output" not in result.stdout
    assert not (tmp_path / ".entroping" / "retention-journal").exists()


def test_prune_without_apply_remains_plan_only(tmp_path: Path) -> None:
    job, review, _ = _fixture(tmp_path)
    result = _run(tmp_path, "prune")
    assert result.returncode == 0, result.stderr
    assert "Mode: plan-only" in result.stdout
    assert "No files changed" in result.stdout
    assert job.exists() and review.exists()


def test_prune_apply_deletes_only_selected_bundle_and_keeps_receipt(tmp_path: Path) -> None:
    job, review, _ = _fixture(tmp_path)
    queued = tmp_path / ".entroping" / "ai-jobs" / "queued" / "active.json"
    queued.parent.mkdir()
    _ = queued.write_text("{}", encoding="utf-8")
    result = _run(tmp_path, "prune", "--apply", "--json")
    assert result.returncode == 0, result.stderr
    assert not job.exists() and not review.exists()
    assert queued.exists()
    journals = tuple((tmp_path / ".entroping" / "retention-journal").glob("*.json"))
    assert len(journals) == 1
    assert '"status": "completed"' in journals[0].read_text(encoding="utf-8")


def test_bad_timestamp_and_symlinked_policy_fail_without_mutation(tmp_path: Path) -> None:
    job, review, policy = _fixture(tmp_path)
    bad_time = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_retention",
            "plan",
            "--repo-root",
            str(tmp_path),
            "--policy",
            ".entroping/policy.json",
            "--as-of",
            "2026-07-28T00:00:00+01:00",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert bad_time.returncode == 2
    assert "as-of must be UTC" in bad_time.stderr
    replacement = tmp_path / "policy-target.json"
    policy.replace(replacement)
    policy.symlink_to(replacement)
    unsafe_policy = _run(tmp_path, "plan")
    assert unsafe_policy.returncode == 2
    assert "non-symlink" in unsafe_policy.stderr
    assert job.exists() and review.exists()


def test_default_broken_policy_symlink_fails_instead_of_using_example(tmp_path: Path) -> None:
    _ = _fixture(tmp_path)
    local_policy = tmp_path / ".entroping" / "factory-retention-policy.json"
    local_policy.symlink_to(tmp_path / "missing-policy.json")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.factory_retention",
            "plan",
            "--repo-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 2
    assert "non-symlink" in result.stderr


def test_help_exposes_explicit_apply_boundary() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.factory_retention", "prune", "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "--apply" in result.stdout
    assert "Apply the fresh validated plan" in result.stdout
