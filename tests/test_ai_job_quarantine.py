from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Protocol

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_JOBS_SCRIPT = REPO_ROOT / "scripts" / "ai_jobs.py"
QUARANTINE_SCRIPT = REPO_ROOT / "scripts" / "ai_job_quarantine.py"


class _QueueState(Protocol):
    job_root: Path


def _typed_violations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise AssertionError("routing scan must return a list")
    violations: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise AssertionError("routing violation must be an object")
        violation: dict[str, object] = {}
        for key, field_value in item.items():
            if not isinstance(key, str):
                raise AssertionError("routing violation keys must be strings")
            violation[key] = field_value
        violations.append(violation)
    return violations


def _load_ai_jobs_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("quarantine_test_ai_jobs", AI_JOBS_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ai_jobs module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_ai_jobs(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AI_JOBS_SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_quarantine(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(QUARANTINE_SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env} if env is not None else None,
    )


def _write_expensive_tier_a_job(job_root: Path, *, issue: str = "774") -> Path:
    queued_path = job_root / "queued" / "legacy-job.json"
    queued_path.parent.mkdir(parents=True, exist_ok=True)
    queued_path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job.v1",
                "job_id": "legacy-job",
                "queue_status": "queued",
                "engine": "opencode",
                "mode": "review",
                "profile": "pro",
                "model": "deepseek/deepseek-v4-pro",
                "issue": issue,
                "autonomy_tier": "tier_a",
                "provider_lane": "opencode/native-deepseek",
                "provider_host": "OpenCode",
                "billing_path": "OpenCode configured provider",
                "files": ["README.md"],
                "timeout_seconds": 1,
                "attempts": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return queued_path


def _write_fake_ready_gh(fake_bin: Path) -> dict[str, str]:
    fake_bin.mkdir(exist_ok=True)
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "print('{\"state\":\"OPEN\",\"labels\":[{\"name\":\"status:ready\"}]}')\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    return {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}


def _safe_tier_a_job(ai_jobs: ModuleType, *, issue: str | None = None) -> dict[str, object]:
    revision = ai_jobs._current_revision(REPO_ROOT)
    digests = ai_jobs._selected_file_digests(REPO_ROOT, ["README.md"])
    return {
        "schema_version": "entroping.ai-job.v1",
        "job_id": "safe-tier-a",
        "queue_status": "queued",
        "engine": "opencode",
        "mode": "review",
        "profile": "flash-free",
        "model": "opencode/deepseek-v4-flash-free",
        "issue": issue,
        "autonomy_tier": "tier_a",
        "files": ["README.md"],
        "file_sha256": digests,
        "source_revision": revision,
        "timeout_seconds": 1,
        "attempts": 0,
    }


def test_run_next_blocks_policy_violating_job_before_worker_dispatch(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)

    result = _run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(tmp_path / "ai-reviews"),
        "--worker-dry-run",
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "routing-violations-blocked"
    assert payload["violation_count"] == 1
    assert payload["violations"][0]["job_id"] == "legacy-job"
    assert queued_path.exists()
    assert not list((job_root / "completed").glob("*.json"))


def test_quarantine_defaults_to_read_only_plan(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)
    original = queued_path.read_bytes()

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "planned"
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["job_id"] == "legacy-job"
    assert payload["candidates"][0]["reason"] == "tier-a-routing-violation"
    assert queued_path.read_bytes() == original
    assert not (job_root / "quarantined").exists()


def test_quarantine_apply_moves_original_bytes_and_writes_receipt(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)
    original = queued_path.read_bytes()

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    candidate = payload["candidates"][0]
    quarantined_path = Path(candidate["target_path"])
    receipt_path = Path(candidate["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["status"] == "quarantined"
    assert not queued_path.exists()
    assert quarantined_path.read_bytes() == original
    assert receipt["schema_version"] == "entroping.ai-job-quarantine.v1"
    assert receipt["job_id"] == "legacy-job"
    assert receipt["reason"] == "tier-a-routing-violation"
    assert receipt["sha256"] == candidate["sha256"]
    assert receipt["source_path"] == str(queued_path)
    assert receipt["quarantined_path"] == str(quarantined_path)
    assert receipt["quarantined_at"]


def test_quarantine_apply_preserves_malformed_job_for_manual_review(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "malformed.json"
    queued_path.parent.mkdir(parents=True)
    original = b'{"job_id": "malformed"'
    queued_path.write_bytes(original)

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    candidate = payload["candidates"][0]
    assert candidate["reason"] == "malformed-job"
    assert Path(candidate["target_path"]).read_bytes() == original
    assert not queued_path.exists()


def test_quarantine_rejects_symlinked_queue_entries(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_dir = job_root / "queued"
    queued_dir.mkdir(parents=True)
    target = tmp_path / "outside.json"
    target.write_text('{"job_id": "outside"}\n', encoding="utf-8")
    (queued_dir / "linked.json").symlink_to(target)

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 2
    assert "regular non-symlink file" in result.stderr
    assert target.read_text(encoding="utf-8") == '{"job_id": "outside"}\n'


def test_quarantine_is_idempotent_after_candidates_are_moved(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root)
    first = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    second = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["candidate_count"] == 0


def test_run_next_preserves_existing_malformed_job_isolation(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "malformed.json"
    queued_path.parent.mkdir(parents=True)
    queued_path.write_text('{"job_id": "malformed"', encoding="utf-8")

    result = _run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--artifact-root",
        str(tmp_path / "ai-reviews"),
        "--worker-dry-run",
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["worker_status"] == "corrupt-queued-job"
    assert not queued_path.exists()
    assert (job_root / "failed" / "malformed.json").exists()


def test_requeue_defaults_to_plan_with_live_issue_and_explicit_routing(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'state': 'OPEN', 'labels': [{'name': 'status:ready'}]}))\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    result = _run_quarantine(
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--json",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    revalidation = payload["revalidation"]
    assert payload["status"] == "planned"
    assert revalidation["issue"] == "1557"
    assert revalidation["issue_state"] == "OPEN"
    assert revalidation["issue_ready"] is True
    assert revalidation["profile"] == "flash-free"
    assert revalidation["model"] == "opencode/deepseek-v4-flash-free"
    assert revalidation["files"] == ["README.md"]
    assert revalidation["source_revision"]
    assert not list((job_root / "queued").glob("*.json"))


def test_requeue_apply_creates_new_job_and_preserves_quarantine_evidence(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    quarantined_path = job_root / "quarantined" / "legacy-job.json"
    original = quarantined_path.read_bytes()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'state': 'OPEN', 'labels': [{'name': 'status:ready'}]}))\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    result = _run_quarantine(
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    queued_path = Path(payload["job_path"])
    requeued = json.loads(queued_path.read_text(encoding="utf-8"))
    assert payload["status"] == "requeued"
    assert requeued["job_id"] != "legacy-job"
    assert requeued["requeued_from"] == "legacy-job"
    assert requeued["queue_status"] == "queued"
    assert requeued["profile"] == "flash-free"
    assert requeued["model"] == "opencode/deepseek-v4-flash-free"
    assert requeued["revalidated_revision"] == payload["revalidation"]["source_revision"]
    assert requeued["revalidated_at"]
    assert quarantined_path.read_bytes() == original
    assert (job_root / "quarantine-receipts" / "legacy-job.json").exists()


def test_requeue_rejects_closed_or_not_ready_issues(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "print(os.environ['GH_ISSUE_PAYLOAD'])\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    path = f"{fake_bin}{os.pathsep}{os.environ['PATH']}"

    for issue_payload in (
        '{"state":"CLOSED","labels":[{"name":"status:ready"}]}',
        '{"state":"OPEN","labels":[]}',
    ):
        result = _run_quarantine(
            "requeue",
            "--job-root",
            str(job_root),
            "--job-id",
            "legacy-job",
            "--engine",
            "opencode",
            "--profile",
            "flash-free",
            "--json",
            env={"PATH": path, "GH_ISSUE_PAYLOAD": issue_payload},
        )

        assert result.returncode == 2
        assert "must be OPEN with status:ready" in result.stderr
        assert not list((job_root / "queued").glob("*.json"))


def test_requeue_rejects_tampered_quarantine_evidence(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    quarantined_path = job_root / "quarantined" / "legacy-job.json"
    quarantined_path.write_bytes(quarantined_path.read_bytes() + b" ")

    result = _run_quarantine(
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--json",
    )

    assert result.returncode == 2
    assert "digest does not match receipt" in result.stderr
    assert not list((job_root / "queued").glob("*.json"))


def test_requeue_apply_is_idempotent(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "print('{\"state\":\"OPEN\",\"labels\":[{\"name\":\"status:ready\"}]}')\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    args = (
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
    )
    env = {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

    first = _run_quarantine(*args, env=env)
    second = _run_quarantine(*args, env=env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["job_path"] == json.loads(second.stdout)["job_path"]
    assert len(list((job_root / "queued").glob("*.json"))) == 1


def test_requeue_rejects_tampered_idempotency_record(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    args = (
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
    )
    env = _write_fake_ready_gh(tmp_path / "bin")
    first = _run_quarantine(*args, env=env)
    assert first.returncode == 0, first.stderr
    record_path = job_root / "requeue-records" / "legacy-job.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["source_sha256"] = "0" * 64
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    repeated = _run_quarantine(*args, env=env)

    assert repeated.returncode == 2
    assert "idempotency record does not match source" in repeated.stderr
    assert len(list((job_root / "queued").glob("*.json"))) == 1


def test_requeue_rejects_tampered_replacement_provenance(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    args = (
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
    )
    env = _write_fake_ready_gh(tmp_path / "bin")
    first = _run_quarantine(*args, env=env)
    assert first.returncode == 0, first.stderr
    queued_path = Path(json.loads(first.stdout)["job_path"])
    queued_job = json.loads(queued_path.read_text(encoding="utf-8"))
    queued_job["quarantined_sha256"] = "0" * 64
    queued_path.write_text(
        json.dumps(queued_job, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    repeated = _run_quarantine(*args, env=env)

    assert repeated.returncode == 2
    assert "does not match its provenance record" in repeated.stderr
    assert len(list((job_root / "queued").glob("*.json"))) == 1


def test_structurally_invalid_json_object_is_quarantinable_and_isolated(
    tmp_path: Path,
) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "legacy-shape.json"
    queued_path.parent.mkdir(parents=True)
    queued_path.write_text('{"job_id":"legacy-shape"}\n', encoding="utf-8")

    plan = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--json",
    )
    dispatch = _run_ai_jobs(
        "run-next",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert plan.returncode == 0, plan.stderr
    assert json.loads(plan.stdout)["candidates"][0]["reason"] == "malformed-job"
    assert dispatch.returncode == 1
    assert json.loads(dispatch.stdout)["worker_status"] == "corrupt-queued-job"
    assert (job_root / "failed" / queued_path.name).exists()
    assert not list((job_root / "running").glob("*.json"))


def test_quarantine_rejects_symlinked_destination_directories(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)
    outside_quarantine = tmp_path / "outside-quarantine"
    outside_receipts = tmp_path / "outside-receipts"
    outside_quarantine.mkdir()
    outside_receipts.mkdir()
    (job_root / "quarantined").symlink_to(
        outside_quarantine,
        target_is_directory=True,
    )
    (job_root / "quarantine-receipts").symlink_to(
        outside_receipts,
        target_is_directory=True,
    )

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 2
    assert "non-symlink directory" in result.stderr
    assert queued_path.exists()
    assert not list(outside_quarantine.iterdir())
    assert not list(outside_receipts.iterdir())


@pytest.mark.parametrize("state", ["quarantined", "quarantine-receipts"])
def test_quarantine_rejects_symlinked_destination_entries(
    tmp_path: Path,
    state: str,
) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)
    outside = tmp_path / "outside.json"
    outside.write_text("outside\n", encoding="utf-8")
    destination = job_root / state / queued_path.name
    destination.parent.mkdir(parents=True)
    destination.symlink_to(outside)

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 2
    assert "regular non-symlink file" in result.stderr
    assert queued_path.exists()
    assert destination.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_quarantine_recovers_receipt_first_interruption(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued_path = _write_expensive_tier_a_job(job_root)
    plan = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--json",
    )
    assert plan.returncode == 0, plan.stderr
    candidate = json.loads(plan.stdout)["candidates"][0]
    receipt_path = Path(candidate["receipt_path"])
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job-quarantine.v1",
                "job_id": candidate["job_id"],
                "reason": candidate["reason"],
                "sha256": candidate["sha256"],
                "source_path": candidate["source_path"],
                "quarantined_path": candidate["target_path"],
                "quarantined_at": "interrupted-before-move",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert not queued_path.exists()
    assert Path(candidate["target_path"]).exists()
    assert receipt_path.exists()


def test_requeue_rejects_symlinked_idempotency_directory(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    outside = tmp_path / "outside-records"
    outside.mkdir()
    (job_root / "requeue-records").symlink_to(outside, target_is_directory=True)

    result = _run_quarantine(
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
        env=_write_fake_ready_gh(tmp_path / "bin"),
    )

    assert result.returncode == 2
    assert "non-symlink directory" in result.stderr
    assert not list(outside.iterdir())
    assert not list((job_root / "queued").glob("*.json"))


def test_requeue_repeat_finds_terminal_replacement(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    args = (
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
    )
    env = _write_fake_ready_gh(tmp_path / "bin")
    first = _run_quarantine(*args, env=env)
    assert first.returncode == 0, first.stderr
    queued_path = Path(json.loads(first.stdout)["job_path"])
    replacement = json.loads(queued_path.read_text(encoding="utf-8"))
    replacement["queue_status"] = "completed"
    completed_path = job_root / "completed" / queued_path.name
    completed_path.parent.mkdir(parents=True, exist_ok=True)
    completed_path.write_text(
        json.dumps(replacement, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    queued_path.unlink()

    second = _run_quarantine(*args, env=env)

    assert second.returncode == 0, second.stderr
    assert Path(json.loads(second.stdout)["job_path"]) == completed_path
    assert not list((job_root / "queued").glob("*.json"))


def test_concurrent_requeue_creates_at_most_one_replacement(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    args = (
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
    )
    env = _write_fake_ready_gh(tmp_path / "bin")
    start = threading.Barrier(8)

    def run_once() -> subprocess.CompletedProcess[str]:
        start.wait()
        return _run_quarantine(*args, env=env)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: run_once(), range(8)))

    assert any(result.returncode == 0 for result in results)
    assert all(result.returncode in {0, 2} for result in results)
    assert len(list((job_root / "queued").glob("*.json"))) == 1
    assert len(list((job_root / "requeue-records").glob("*.json"))) == 1


def test_claimed_job_routing_is_rechecked_after_queue_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    original_scan = ai_jobs._queued_routing_violations
    worker_called = False

    def scan_then_insert(queue: _QueueState) -> list[dict[str, object]]:
        result = _typed_violations(original_scan(queue))
        _write_expensive_tier_a_job(queue.job_root)
        return result

    def fail_if_called(
        args: SimpleNamespace,
        repo_root: Path,
        job: dict[str, object],
    ) -> tuple[dict[str, object], int]:
        nonlocal worker_called
        worker_called = True
        return {"status": "completed", "returncode": 0, "artifact_dir": None}, 0

    monkeypatch.setattr(ai_jobs, "_queued_routing_violations", scan_then_insert)
    monkeypatch.setattr(ai_jobs, "_run_worker", fail_if_called)

    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 1
    assert payload["status"] == "dispatch-preflight-blocked"
    assert payload["violation"]["reason"] == "tier-a-routing-violation"
    assert worker_called is False
    assert (job_root / "queued" / "legacy-job.json").exists()
    assert not list((job_root / "running").glob("*.json"))


def test_post_scan_symlink_job_is_rejected_before_worker_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    outside_job = tmp_path / "external.json"
    external_payload = _safe_tier_a_job(ai_jobs)
    external_payload["job_id"] = "external-substitute"
    outside_job.write_text(
        json.dumps(external_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_bytes = outside_job.read_bytes()
    original_scan = ai_jobs._queued_routing_violations
    worker_called = False

    def scan_then_insert(queue: _QueueState) -> list[dict[str, object]]:
        result = _typed_violations(original_scan(queue))
        injected = queue.job_root / "queued" / "injected.json"
        injected.symlink_to(outside_job)
        return result

    def fail_if_called(
        args: SimpleNamespace,
        repo_root: Path,
        job: dict[str, object],
    ) -> tuple[dict[str, object], int]:
        nonlocal worker_called
        worker_called = True
        return {"status": "completed", "returncode": 0, "artifact_dir": None}, 0

    monkeypatch.setattr(ai_jobs, "_queued_routing_violations", scan_then_insert)
    monkeypatch.setattr(ai_jobs, "_run_worker", fail_if_called)

    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 1
    assert payload["worker_status"] == "corrupt-queued-job"
    assert worker_called is False
    assert outside_job.read_bytes() == original_bytes
    assert (job_root / "failed" / "injected.json").is_file()


def test_post_claim_running_directory_swap_cannot_substitute_worker_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "safe-tier-a.json"
    ai_jobs._write_job(queued_path, _safe_tier_a_job(ai_jobs))
    outside = tmp_path / "outside-running"
    outside.mkdir()
    detached = tmp_path / "detached-running"
    original_claim = ai_jobs._claim_next_queued_job
    worker_job_ids: list[object] = []
    external_bytes = b""

    def claim_then_swap(queue: _QueueState) -> str | None:
        nonlocal external_bytes
        raw_name: object = original_claim(queue)
        assert isinstance(raw_name, str)
        name = raw_name
        running_dir = queue.job_root / "running"
        running_dir.rename(detached)
        running_dir.symlink_to(outside, target_is_directory=True)
        external_payload = _safe_tier_a_job(ai_jobs)
        external_payload["job_id"] = "external-substitute"
        external_path = outside / name
        external_path.write_text(
            json.dumps(external_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        external_bytes = external_path.read_bytes()
        return name

    def record_worker_job(
        args: SimpleNamespace,
        repo_root: Path,
        job: dict[str, object],
    ) -> tuple[dict[str, object], int]:
        worker_job_ids.append(job["job_id"])
        return {"status": "completed", "returncode": 0, "artifact_dir": None}, 0

    monkeypatch.setattr(ai_jobs, "_claim_next_queued_job", claim_then_swap)
    monkeypatch.setattr(ai_jobs, "_run_worker", record_worker_job)

    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 0
    assert payload["status"] == "completed"
    assert worker_job_ids == ["safe-tier-a"]
    assert (outside / "safe-tier-a.json").read_bytes() == external_bytes
    assert not list(detached.glob("*.json"))
    completed = job_root / "completed" / "safe-tier-a.json"
    assert json.loads(completed.read_text(encoding="utf-8"))["job_id"] == "safe-tier-a"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("revision", "stale-revision"),
        ("file-digest", "selected-files-changed"),
    ],
)
def test_claimed_tier_a_job_revalidates_revision_and_selected_files(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    job = _safe_tier_a_job(ai_jobs)
    if mutation == "revision":
        job["source_revision"] = "0" * 40
    else:
        job["file_sha256"] = {"README.md": "0" * 64}
    queued_path = job_root / "queued" / "safe-tier-a.json"
    ai_jobs._write_job(queued_path, job)

    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 1
    assert payload["status"] == "dispatch-preflight-blocked"
    assert payload["violation"]["reason"] == reason
    assert queued_path.exists()


def test_claimed_tier_a_job_fails_closed_when_issue_revalidation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "safe-tier-a.json"
    ai_jobs._write_job(queued_path, _safe_tier_a_job(ai_jobs, issue="1557"))

    def unavailable(issue: str) -> dict[str, object]:
        raise ai_jobs.AiJobError("unavailable")

    monkeypatch.setattr(ai_jobs, "_github_issue_snapshot", unavailable)
    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 1
    assert payload["violation"]["reason"] == "issue-revalidation-failed"
    assert queued_path.exists()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "print('{\"state\":\"CLOSED\",\"labels\":[] }')\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--json",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert quarantine.returncode == 0, quarantine.stderr
    assert json.loads(quarantine.stdout)["candidates"][0]["reason"] == (
        "issue-revalidation-failed"
    )


def test_claimed_tier_a_job_restores_when_revision_lookup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "safe-tier-a.json"
    ai_jobs._write_job(queued_path, _safe_tier_a_job(ai_jobs))

    def unavailable(repo_root: Path) -> str:
        raise ai_jobs.AiJobError("unavailable")

    monkeypatch.setattr(ai_jobs, "_current_revision", unavailable)
    payload, returncode = ai_jobs._run_next(
        SimpleNamespace(artifact_root=tmp_path / "artifacts"),
        REPO_ROOT,
        job_root,
    )

    assert returncode == 1
    assert payload["violation"]["reason"] == "revision-revalidation-failed"
    assert queued_path.exists()
    assert not list((job_root / "running").glob("*.json"))


def test_dispatch_restore_rejects_concurrently_swapped_queue_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_jobs = _load_ai_jobs_module()
    job_root = tmp_path / "ai-jobs"
    queued_path = job_root / "queued" / "safe-tier-a.json"
    ai_jobs._write_job(queued_path, _safe_tier_a_job(ai_jobs))
    outside = tmp_path / "outside"
    outside.mkdir()

    def swap_before_restore(
        repo_root: Path,
        running_path: Path,
        job: dict[str, object],
    ) -> dict[str, object]:
        queued_path.parent.rmdir()
        queued_path.parent.symlink_to(outside, target_is_directory=True)
        return {
            "job_id": job["job_id"],
            "reason": "forced-test-violation",
        }

    monkeypatch.setattr(ai_jobs, "_claimed_dispatch_violation", swap_before_restore)

    with pytest.raises(ai_jobs.AiJobError, match="could not restore"):
        ai_jobs._run_next(
            SimpleNamespace(artifact_root=tmp_path / "artifacts"),
            REPO_ROOT,
            job_root,
        )

    assert not list(outside.iterdir())
    assert (job_root / "running" / queued_path.name).exists()


def test_requeue_rejects_receipt_missing_required_provenance(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    _write_expensive_tier_a_job(job_root, issue="1557")
    quarantine = _run_quarantine(
        "quarantine",
        "--job-root",
        str(job_root),
        "--apply",
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    receipt_path = job_root / "quarantine-receipts" / "legacy-job.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    del receipt["source_path"]
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _run_quarantine(
        "requeue",
        "--job-root",
        str(job_root),
        "--job-id",
        "legacy-job",
        "--engine",
        "opencode",
        "--profile",
        "flash-free",
        "--apply",
        "--json",
        env=_write_fake_ready_gh(tmp_path / "bin"),
    )

    assert result.returncode == 2
    assert "receipt provenance is invalid" in result.stderr
    assert not list((job_root / "queued").glob("*.json"))
