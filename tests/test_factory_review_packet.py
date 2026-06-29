"""Tests for compact AI worker review packets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "factory_review_packet.py"


def run_packet(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=command_env,
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_packet(stdout: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(stdout))


def test_factory_review_packet_reads_job_artifact_without_transcripts(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-abc123"
    artifact_dir.mkdir(parents=True)
    write_json(
        artifact_dir / "metadata.json",
        {
            "schema_version": "entroping.opencode-worker.v1",
            "status": "patch-proposed",
            "mode": "patch",
            "model": "opencode/deepseek-v4-flash-free",
            "issue": "1142",
            "artifact_dir": str(artifact_dir),
            "returncode": 0,
        },
    )
    (artifact_dir / "result.md").write_text(
        "STATUS: pass\n"
        "FILES_CHANGED: scripts/factory_review_packet.py, tests/test_factory_review_packet.py\n"
        "TESTS_RUN: uv run pytest tests/test_factory_review_packet.py -q\n"
        "KNOWN_ISSUES: none\n"
        "VERIFICATION_LANE: normal-code\n"
        "CI_STATUS: pass\n"
        "SUMMARY: Produced a compact review packet.\n",
        encoding="utf-8",
    )
    (artifact_dir / "tests.txt").write_text("2 passed\n", encoding="utf-8")
    (artifact_dir / "stdout.txt").write_text(
        "raw worker transcript that Codex should not read\n",
        encoding="utf-8",
    )
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/scripts/factory_review_packet.py b/scripts/factory_review_packet.py\n"
        "index 0000000..1111111 100644\n"
        "--- a/scripts/factory_review_packet.py\n"
        "+++ b/scripts/factory_review_packet.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+line one\n"
        "+line two\n",
        encoding="utf-8",
    )
    write_json(
        job_root / "completed" / "job-1.json",
        {
            "schema_version": "entroping.ai-job.v1",
            "job_id": "job-1",
            "queue_status": "completed",
            "engine": "opencode",
            "profile": "flash-free",
            "mode": "patch",
            "model": "opencode/deepseek-v4-flash-free",
            "issue": "1142",
            "autonomy_tier": "tier_a",
            "provider_lane": "opencode/native-deepseek",
            "provider_host": "OpenCode",
            "billing_path": "OpenCode free-model lane",
            "merge_authority": "Tier A autonomous after gates and green CI",
            "worker_status": "patch-proposed",
            "artifact_dir": str(artifact_dir),
        },
    )

    result = run_packet(
        "--job-id",
        "job-1",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert "raw worker transcript" not in result.stdout
    packet = read_packet(result.stdout)
    job = cast(dict[str, object], packet["job"])
    artifact = cast(dict[str, object], packet["artifact"])
    result_summary = cast(dict[str, str], artifact["result_summary"])
    diff_stat = cast(dict[str, object], artifact["proposal_diff"])

    assert job["job_id"] == "job-1"
    assert job["issue"] == "1142"
    assert job["autonomy_tier"] == "tier_a"
    assert job["provider_lane"] == "opencode/native-deepseek"
    assert artifact["metadata_path"] == str(artifact_dir / "metadata.json")
    assert artifact["tests_path"] == str(artifact_dir / "tests.txt")
    assert result_summary["STATUS"] == "pass"
    assert result_summary["KNOWN_ISSUES"] == "none"
    assert diff_stat["changed_files"] == ["scripts/factory_review_packet.py"]
    assert diff_stat["additions"] == 2
    assert diff_stat["deletions"] == 0


def test_factory_review_packet_rejects_missing_job(tmp_path: Path) -> None:
    result = run_packet(
        "--job-id",
        "missing-job",
        "--job-root",
        str(tmp_path / "ai-jobs"),
        "--artifact-root",
        str(tmp_path / "ai-reviews"),
    )

    assert result.returncode == 2
    assert "job id not found" in result.stderr


def test_factory_review_packet_accepts_direct_artifact_dir_without_stdout(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "review-abc123"
    artifact_dir.mkdir(parents=True)
    write_json(
        artifact_dir / "metadata.json",
        {
            "schema_version": "entroping.deepseek-worker.v1",
            "status": "completed",
            "mode": "review",
            "model": "deepseek-v4-flash",
            "issue": "1143",
            "artifact_dir": str(artifact_dir),
            "provider_lane": "deepseek-api/direct",
            "merge_authority": "Codex/human required",
            "verification_lane": "security-runtime",
            "ci_status": "pass",
            "returncode": 0,
        },
    )
    (artifact_dir / "result.md").write_text(
        "STATUS: pass\n"
        "VERIFICATION_LANE: security-runtime\n"
        "CI_STATUS: pass\n",
        encoding="utf-8",
    )
    (artifact_dir / "stdout.txt").write_text("verbose provider output\n", encoding="utf-8")

    result = run_packet(
        "--artifact-dir",
        str(artifact_dir),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert "verbose provider output" not in result.stdout
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    assert artifact["metadata_path"] == str(artifact_dir / "metadata.json")
    assert "stdout_path" not in artifact


def _write_marathon_handoff(
    artifact_dir: Path,
    metadata: dict[str, object],
    result_text: str = "",
) -> Path:
    artifact_dir.mkdir(parents=True)
    write_json(artifact_dir / "metadata.json", metadata)
    (artifact_dir / "result.md").write_text(
        result_text or "SUMMARY: marathon handoff fixture.\n", encoding="utf-8"
    )
    (artifact_dir / "tests.txt").write_text("tests: 0\n", encoding="utf-8")
    return artifact_dir


def test_deepseek_valid_marathon_handoff_accepted(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = _write_marathon_handoff(
        artifact_root / "issue-1194-beta-exit-scorecard",
        {
            "status": "ready_for_codex",
            "issue": 1194,
            "provider_lane": "deepseek",
            "provider_host": "opencode-deepseek-v4-pro",
            "billing_path": "opencode_deepseek",
            "model": "deepseek-v4-pro",
            "autonomy_tier": "Tier B assisted",
            "merge_authority": "Codex only",
            "worktree": "/tmp/Entroping-issue-1194",
            "branch": "deepseek/beta-exit-scorecard",
            "pr": "https://github.com/sakibshuvo/Entroping/pull/1214",
            "verification_lane": "docs-guardrail",
        },
        result_text=(
            "STATUS: pass\nFILES_CHANGED: scripts/beta_exit_scorecard.py\n"
            "TESTS_RUN: uv run pytest tests/test_beta_exit_scorecard.py -v\n"
            "KNOWN_ISSUES: none\nSUMMARY: Added beta exit scorecard.\n"
        ),
    )

    result = run_packet(
        "--artifact-dir", str(artifact_dir),
        "--artifact-root", str(artifact_root),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    meta = cast(dict[str, object], artifact["metadata"])
    assert meta["status"] == "ready_for_codex"
    assert meta["issue"] == 1194
    assert meta["provider_lane"] == "deepseek"
    assert meta["merge_authority"] == "Codex only"
    assert "review_flags" not in meta


def test_invalid_handoff_missing_issue_number_rejected(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = _write_marathon_handoff(
        artifact_root / "issue-unknown-no-issue",
        {
            "status": "ready_for_codex",
            "provider_lane": "deepseek",
            "model": "deepseek-v4-pro",
            "merge_authority": "Codex only",
        },
    )

    result = run_packet(
        "--artifact-dir", str(artifact_dir),
        "--artifact-root", str(artifact_root),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    meta = cast(dict[str, object], artifact["metadata"])
    review_flags = cast(list[str], meta["review_flags"])
    assert "metadata missing issue" in review_flags


def test_spark_valid_marathon_handoff_accepted(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = _write_marathon_handoff(
        artifact_root / "issue-1204-beta-readiness-aggregator",
        {
            "status": "ready_for_codex",
            "issue": 1204,
            "provider_lane": "spark",
            "provider_host": "codex-spark",
            "billing_path": "codex_spark",
            "model": "gpt-4o-mini",
            "autonomy_tier": "Tier A autonomous",
            "merge_authority": "Tier A autonomous after gates and green CI",
            "worktree": "/tmp/Entroping-issue-1204",
            "branch": "spark/beta-readiness-aggregator",
            "verification_lane": "docs-guardrail",
        },
        result_text=(
            "STATUS: pass\nFILES_CHANGED: scripts/beta_readiness_aggregator.py\n"
            "TESTS_RUN: uv run pytest tests/ -k readiness\n"
            "KNOWN_ISSUES: none\nSUMMARY: Spark handoff fixture.\n"
        ),
    )

    result = run_packet(
        "--artifact-dir", str(artifact_dir),
        "--artifact-root", str(artifact_root),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    meta = cast(dict[str, object], artifact["metadata"])
    assert meta["status"] == "ready_for_codex"
    assert meta["issue"] == 1204
    assert meta["provider_host"] == "codex-spark"
    assert meta["verification_lane"] == "docs-guardrail"
    assert "review_flags" not in meta


def test_invalid_handoff_missing_merge_authority_flagged(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = _write_marathon_handoff(
        artifact_root / "issue-1209-no-merge-auth",
        {
            "status": "ready_for_codex",
            "issue": 1209,
            "provider_lane": "spark",
            "model": "gpt-4o-mini",
        },
    )

    result = run_packet(
        "--artifact-dir", str(artifact_dir),
        "--artifact-root", str(artifact_root),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    meta = cast(dict[str, object], artifact["metadata"])
    review_flags = cast(list[str], meta["review_flags"])
    assert "metadata missing merge_authority" in review_flags


def test_handoff_must_have_status_ready_for_codex(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = _write_marathon_handoff(
        artifact_root / "issue-1213-incomplete",
        {
            "status": "in-progress",
            "issue": 1213,
            "provider_lane": "deepseek",
            "model": "deepseek-v4-pro",
            "merge_authority": "Codex only",
        },
    )

    result = run_packet(
        "--artifact-dir", str(artifact_dir),
        "--artifact-root", str(artifact_root),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    meta = cast(dict[str, object], artifact["metadata"])
    review_flags = cast(list[str], meta["review_flags"])
    assert "metadata status is not ready_for_codex" in review_flags


def test_factory_review_packet_rejects_missing_required_fields(tmp_path: Path) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "review-123"
    artifact_dir.mkdir(parents=True)
    write_json(
        artifact_dir / "metadata.json",
        {
            "schema_version": "entroping.deepseek-worker.v1",
            "status": "completed",
            "mode": "review",
            "model": "deepseek-v4-flash",
            "artifact_dir": str(artifact_dir),
            "provider_lane": "deepseek-api/direct",
            "returncode": 0,
        },
    )
    (artifact_dir / "result.md").write_text(
        "STATUS: pass\n"
        "CI_STATUS: pass\n",
        encoding="utf-8",
    )

    result = run_packet(
        "--artifact-dir",
        str(artifact_dir),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 2
    assert "review packet missing required fields" in result.stderr
    assert "issue" in result.stderr
    assert "verification_lane" in result.stderr
