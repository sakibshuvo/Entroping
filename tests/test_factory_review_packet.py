"""Tests for compact AI worker review packets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
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
        + "FILES_CHANGED: scripts/factory_review_packet.py, tests/test_factory_review_packet.py\n"
        + "TESTS_RUN: uv run pytest tests/test_factory_review_packet.py -q\n"
        + "KNOWN_ISSUES: none\n"
        + "VERIFICATION_LANE: normal-code\n"
        + "CI_STATUS: pass\n"
        + "SUMMARY: Produced a compact review packet.\n",
        encoding="utf-8",
    )
    (artifact_dir / "tests.txt").write_text("2 passed\n", encoding="utf-8")
    (artifact_dir / "stdout.txt").write_text(
        "raw worker transcript that Codex should not read\n",
        encoding="utf-8",
    )
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/scripts/factory_review_packet.py b/scripts/factory_review_packet.py\n"
        + "index 0000000..1111111 100644\n"
        + "--- a/scripts/factory_review_packet.py\n"
        + "+++ b/scripts/factory_review_packet.py\n"
        + "@@ -0,0 +1,2 @@\n"
        + "+line one\n"
        + "+line two\n",
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
            "autonomy_tier": "tier_b",
            "provider_lane": "opencode/native-deepseek",
            "provider_host": "OpenCode",
            "billing_path": "OpenCode free-model lane",
            "merge_authority": "Codex/human required",
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
    assert job["autonomy_tier"] == "tier_b"
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
        'STATUS: pass\nVERIFICATION_LANE: security-runtime\nCI_STATUS: pass\n',
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
            "STATUS: pass\n"
            + "FILES_CHANGED: scripts/beta_exit_scorecard.py\n"
            + "TESTS_RUN: uv run pytest tests/test_beta_exit_scorecard.py -v\n"
            + "KNOWN_ISSUES: none\n"
            + "SUMMARY: Added beta exit scorecard.\n"
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
            "STATUS: pass\n"
            + "FILES_CHANGED: scripts/beta_readiness_aggregator.py\n"
            + "TESTS_RUN: uv run pytest tests/ -k readiness\n"
            + "KNOWN_ISSUES: none\n"
            + "SUMMARY: Spark handoff fixture.\n"
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
        'STATUS: pass\nCI_STATUS: pass\n',
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


def test_factory_review_packet_rejects_tier_a_rename_from_protected_surface(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-protected-rename"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/scripts/ai_jobs.py b/docs/ai-jobs-example.py\n"
        "similarity index 100%\n"
        "rename from scripts/ai_jobs.py\n"
        "rename to docs/ai-jobs-example.py\n",
        encoding="utf-8",
    )
    write_json(
        job_root / "completed" / "job-protected.json",
        {
            "schema_version": "entroping.ai-job.v1",
            "job_id": "job-protected",
            "queue_status": "completed",
            "engine": "opencode",
            "mode": "patch",
            "model": "opencode/deepseek-v4-flash-free",
            "issue": "1561",
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
        "job-protected",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 2
    assert "Tier A control-plane protection" in result.stderr
    assert "scripts/ai_jobs.py" in result.stderr
    assert "route this proposal to Codex/human review" in result.stderr


def test_factory_review_packet_decodes_protected_rename_source_from_git_quoting(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-quoted-rename"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "proposal.diff").write_text(
        'diff --git "a/scripts/ai\\137jobs.py" b/docs/example.py\n'
        "similarity index 100%\n"
        'rename from "scripts/ai\\137jobs.py"\n'
        "rename to docs/example.py\n",
        encoding="utf-8",
    )
    write_json(
        job_root / "completed" / "job-quoted.json",
        {
            "schema_version": "entroping.ai-job.v1",
            "job_id": "job-quoted",
            "queue_status": "completed",
            "engine": "opencode",
            "mode": "patch",
            "model": "opencode/deepseek-v4-flash-free",
            "autonomy_tier": "tier_a",
            "artifact_dir": str(artifact_dir),
        },
    )

    result = run_packet(
        "--job-id",
        "job-quoted",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 2
    assert "scripts/ai_jobs.py (factory-scheduler)" in result.stderr


def test_factory_review_packet_rejects_copy_from_protected_credential_boundary(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-protected-copy"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/docs/example.py b/docs/copied-example.py\n"
        "similarity index 100%\n"
        "copy from scripts/ai_worker_file_safety.py\n"
        "copy to docs/copied-example.py\n",
        encoding="utf-8",
    )
    write_json(
        job_root / "completed" / "job-copy.json",
        {
            "schema_version": "entroping.ai-job.v1",
            "job_id": "job-copy",
            "queue_status": "completed",
            "engine": "opencode",
            "mode": "patch",
            "model": "opencode/deepseek-v4-flash-free",
            "autonomy_tier": "tier_a",
            "artifact_dir": str(artifact_dir),
        },
    )

    result = run_packet(
        "--job-id",
        "job-copy",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 2
    assert "scripts/ai_worker_file_safety.py (credential-boundary)" in result.stderr


def test_factory_review_packet_rejects_tier_a_symlink_patch(tmp_path: Path) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-symlink"
    artifact_dir.mkdir(parents=True)
    write_json(
        artifact_dir / "metadata.json",
        {
            "status": "patch-proposed",
            "autonomy_tier": "tier_b",
        },
    )
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/docs/control-link b/docs/control-link\n"
        "new file mode 120000\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/docs/control-link\n"
        "@@ -0,0 +1 @@\n"
        "+../scripts/ai_jobs.py\n",
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
    assert "docs/control-link (symlink-path)" in result.stderr


def test_factory_review_packet_rejects_index_only_symlink_patch(tmp_path: Path) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-index-symlink"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/docs/control-link b/docs/control-link\n"
        "index 1111111..2222222 120000 \t\n"
        "--- a/docs/control-link\n"
        "+++ b/docs/control-link\n"
        "@@ -1 +1 @@\n"
        "-../docs/old.md\n"
        "+../scripts/ai_jobs.py\n",
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
    assert "docs/control-link (symlink-path)" in result.stderr


def test_patch_inspection_rejects_truncated_numstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import factory_patch_inspection
    from scripts.script_safety import TRUNCATED_MESSAGE

    proposal = tmp_path / "proposal.diff"
    proposal.write_text(
        "diff --git a/README.md b/README.md\n"
        "index 1111111..2222222 100644\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n",
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["git"],
        returncode=0,
        stdout=f"1\t1\tREADME.md\0{TRUNCATED_MESSAGE}",
        stderr="",
    )
    monkeypatch.setattr(
        factory_patch_inspection,
        "run_subprocess",
        lambda *args, **kwargs: completed,
    )

    try:
        factory_patch_inspection.inspect_proposal_diff(proposal)
    except factory_patch_inspection.PatchInspectionError as exc:
        assert "exceeded the safe limit" in str(exc)
    else:
        raise AssertionError("truncated numstat output was accepted")


def test_factory_review_packet_preserves_both_paths_for_multi_file_patch(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "patch-multiple-files"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "proposal.diff").write_text(
        "diff --git a/docs/old.md b/docs/new.md\n"
        "similarity index 100%\n"
        "rename from docs/old.md\n"
        "rename to docs/new.md\n"
        "diff --git a/README.md b/README.md\n"
        "index 1111111..2222222 100644\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n",
        encoding="utf-8",
    )

    result = run_packet(
        "--artifact-dir",
        str(artifact_dir),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    packet = read_packet(result.stdout)
    artifact = cast(dict[str, object], packet["artifact"])
    proposal = cast(dict[str, object], artifact["proposal_diff"])
    assert proposal["changed_files"] == ["docs/old.md", "docs/new.md", "README.md"]


def test_factory_review_packet_blocks_secret_like_output(tmp_path: Path) -> None:
    artifact_root = tmp_path / "ai-reviews"
    artifact_dir = artifact_root / "secret-output"
    artifact_dir.mkdir(parents=True)
    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    write_json(
        artifact_dir / "metadata.json",
        {
            "status": "ready_for_codex",
            "provider_host": secret,
        },
    )

    result = run_packet(
        "--artifact-dir",
        str(artifact_dir),
        "--artifact-root",
        str(artifact_root),
        "--json",
    )

    assert result.returncode == 2
    assert "review packet contains secret-like output: provider token" in result.stderr
    assert secret not in result.stdout
    assert secret not in result.stderr
