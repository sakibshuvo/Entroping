"""Tests for the queued AI worker job supervisor."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_jobs.py"


def run_ai_jobs(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def write_fake_opencode(path: Path, *, body: str) -> Path:
    binary = path / "opencode"
    binary.write_text(body, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def read_job(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, object], payload)


def test_ai_jobs_help_documents_queue_subcommands() -> None:
    result = run_ai_jobs("--help")

    assert result.returncode == 0
    assert "submit" in result.stdout
    assert "run-next" in result.stdout
    assert "status" in result.stdout
    assert "collect" in result.stdout


def test_ai_jobs_submit_writes_queued_job_with_model_profile(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash-free",
        "--file",
        "README.md",
        "--issue",
        "579",
        "--instruction",
        "Find concrete risks only.",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job_path = Path(str(payload["job_path"]))
    job = read_job(job_path)

    assert job_path.parent == job_root / "queued"
    assert job["queue_status"] == "queued"
    assert job["mode"] == "review"
    assert job["profile"] == "flash-free"
    assert job["model"] == "opencode/deepseek-v4-flash-free"
    assert job["files"] == ["README.md"]
    assert job["issue"] == "579"
    assert job["instruction"] == "Find concrete risks only."


def test_ai_jobs_submit_writes_deepseek_api_engine_with_provider_model(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"

    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    job = read_job(Path(str(payload["job_path"])))

    assert job["engine"] == "deepseek-api"
    assert job["profile"] == "pro"
    assert job["model"] == "deepseek-v4-pro"


def test_ai_jobs_submit_rejects_opencode_only_profile_for_deepseek_api(
    tmp_path: Path,
) -> None:
    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "flash-free",
        "--file",
        "README.md",
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "not supported by engine 'deepseek-api'" in result.stderr


def test_ai_jobs_submit_rejects_unknown_model_profile(tmp_path: Path) -> None:
    result = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "expensive-mystery",
        "--file",
        "README.md",
        "--job-root",
        str(tmp_path / "ai-jobs"),
    )

    assert result.returncode == 2
    assert "unknown model profile" in result.stderr


def test_ai_jobs_run_next_routes_deepseek_api_engine_to_direct_worker(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--worker-dry-run",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    completed_path = Path(str(payload["job_path"]))
    job = read_job(completed_path)
    artifact_dir = Path(str(job["artifact_dir"]))
    metadata = read_job(artifact_dir / "metadata.json")

    assert job["queue_status"] == "completed"
    assert job["engine"] == "deepseek-api"
    assert job["worker_status"] == "dry-run"
    assert metadata["schema_version"] == "entroping.deepseek-worker.v1"
    assert metadata["model"] == "deepseek-v4-pro"
    assert not (artifact_dir / "stdout.txt").exists()


def test_ai_jobs_run_next_completes_oldest_job_and_records_worker_result(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nprintf '%s\\n' 'worker review output'\n",
    )

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "flash",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    completed_path = Path(str(payload["job_path"]))
    job = read_job(completed_path)

    assert not list((job_root / "queued").glob("*.json"))
    assert not list((job_root / "running").glob("*.json"))
    assert completed_path.parent == job_root / "completed"
    assert job["queue_status"] == "completed"
    assert job["worker_status"] == "completed"
    assert job["worker_returncode"] == 0
    artifact_dir = Path(str(job["artifact_dir"]))
    assert artifact_dir.is_dir()
    assert artifact_dir.parent == artifact_root
    assert "worker review output" in (artifact_dir / "stdout.txt").read_text(
        encoding="utf-8"
    )
    assert "worker review output" not in completed_path.read_text(encoding="utf-8")


def test_ai_jobs_run_next_moves_failed_job_to_failed(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    artifact_root = tmp_path / "ai-reviews"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = write_fake_opencode(
        fake_bin,
        body="#!/usr/bin/env bash\nprintf '%s\\n' 'worker failed' >&2\nexit 7\n",
    )

    submit = run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--profile",
        "pro",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert submit.returncode == 0, submit.stderr

    result = run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(artifact_root),
        "--opencode-bin",
        str(fake_opencode),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_path = Path(str(payload["job_path"]))
    job = read_job(failed_path)

    assert failed_path.parent == job_root / "failed"
    assert job["queue_status"] == "failed"
    assert job["worker_status"] == "failed"
    assert job["worker_returncode"] == 7
    assert job["worker_process_returncode"] == 1
    assert Path(str(job["artifact_dir"])).is_dir()


def test_ai_jobs_status_summarizes_counts_without_raw_output(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued = job_root / "queued"
    completed = job_root / "completed"
    queued.mkdir(parents=True)
    completed.mkdir(parents=True)
    (queued / "queued.json").write_text('{"queue_status": "queued"}\n', encoding="utf-8")
    (completed / "done.json").write_text(
        '{"queue_status": "completed", "raw": "do not print me"}\n',
        encoding="utf-8",
    )

    result = run_ai_jobs("status", "--job-root", str(job_root), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["counts"] == {
        "queued": 1,
        "running": 0,
        "completed": 1,
        "failed": 0,
    }
    assert "do not print me" not in result.stdout


def test_ai_jobs_collect_lists_completed_artifacts_for_codex_review(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    completed = job_root / "completed"
    completed.mkdir(parents=True)
    artifact_dir = tmp_path / "ai-reviews" / "review-1"
    artifact_dir.mkdir(parents=True)
    (completed / "job-1.json").write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "queue_status": "completed",
                "mode": "patch",
                "model": "deepseek/deepseek-v4-pro",
                "issue": "579",
                "worker_status": "patch-proposed",
                "artifact_dir": str(artifact_dir),
                "raw": "do not print me",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_ai_jobs("collect", "--job-root", str(job_root), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["completed_jobs"] == [
        {
            "job_id": "job-1",
            "engine": "opencode",
            "mode": "patch",
            "model": "deepseek/deepseek-v4-pro",
            "issue": "579",
            "worker_status": "patch-proposed",
            "artifact_dir": str(artifact_dir),
        }
    ]
    assert "do not print me" not in result.stdout


def test_ai_jobs_run_next_reports_empty_queue(tmp_path: Path) -> None:
    result = run_ai_jobs("run-next", "--job-root", str(tmp_path / "ai-jobs"), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "empty"
