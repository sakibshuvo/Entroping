from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_JOBS = REPO_ROOT / "scripts" / "ai_jobs.py"


class _AuditViolation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", strict=True)

    reason: str


class _AuditResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", strict=True)

    violation_count: int
    violations: list[_AuditViolation]


def _run_ai_jobs(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AI_JOBS), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_submit_rejects_unknown_paid_model_before_writing_job(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"

    result = _run_ai_jobs(
        "submit",
        "--mode",
        "review",
        "--engine",
        "deepseek-api",
        "--model",
        "deepseek-v9-unregistered",
        "--autonomy-tier",
        "tier-b",
        "--file",
        "README.md",
        "--job-root",
        str(job_root),
    )

    assert result.returncode == 2
    assert "unknown paid provider/model combination" in result.stderr
    assert not job_root.exists()


def test_audit_rejects_tampered_paid_route_outside_tier_a(tmp_path: Path) -> None:
    job_root = tmp_path / "ai-jobs"
    queued = job_root / "queued"
    queued.mkdir(parents=True)
    _ = (queued / "tampered.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.ai-job.v1",
                "job_id": "tampered",
                "queue_status": "queued",
                "engine": "deepseek-api",
                "mode": "review",
                "profile": "custom",
                "model": "deepseek-v9-unregistered",
                "autonomy_tier": "tier_b",
                "provider_lane": "deepseek-api/direct",
                "provider_host": "repo-local DeepSeek worker",
                "billing_path": "paid direct DeepSeek API",
            }
        ),
        encoding="utf-8",
    )

    result = _run_ai_jobs(
        "audit-routing",
        "--job-root",
        str(job_root),
        "--json",
    )

    assert result.returncode == 1
    payload = _AuditResult.model_validate_json(result.stdout)
    assert payload.violation_count == 1
    assert payload.violations[0].reason == "provider-route-violation"
