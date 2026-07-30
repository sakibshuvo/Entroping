from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FACTORYCTL), *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def _candidate(
    index: int = 1,
    *,
    worker_class: str = "paid",
) -> tuple[str, ...]:
    values = (
        "--request-id",
        f"request-{index}",
        "--job-id",
        f"review-20260729-job-{index}",
        "--issue",
        "1569",
        "--worktree-id",
        f"wt_{'1' * 64}",
        "--worker-class",
        worker_class,
        "--access-mode",
        "read-only",
    )
    if worker_class == "paid":
        return (*values, "--reservation-id", f"res-{index:032x}")
    return values


def test_factoryctl_help_documents_safe_tick_modes(tmp_path: Path) -> None:
    result = _run(tmp_path, "tick", "--help")

    assert result.returncode == 0
    assert "--apply" in result.stdout
    assert "--authorization-id" in result.stdout
    assert "plan-only" in result.stdout
    assert "does not dispatch providers" in result.stdout


def test_factoryctl_tick_defaults_to_plan_only_without_state(tmp_path: Path) -> None:
    result = _run(tmp_path, "tick", "--json", *_candidate())

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "would-assign"
    assert payload["authoritative"] is False
    assert payload["paid_work_authorized"] is False
    assert not (tmp_path / ".entroping").exists()


def test_factoryctl_accepts_quota_authorization_candidate_in_plan_mode(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    result = _run(
        tmp_path,
        "tick",
        "--json",
        *candidate[:-2],
        "--authorization-id",
        f"auth-{'a' * 32}",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "would-assign"
    assert not (tmp_path / ".entroping").exists()


def test_factoryctl_apply_commits_one_fenced_assignment(tmp_path: Path) -> None:
    common = (
        "--apply",
        "--json",
        "--owner-id",
        "operator-tick-1",
    )
    first = _run(
        tmp_path,
        "tick",
        *common,
        *_candidate(1, worker_class="free-local"),
    )
    second = _run(
        tmp_path,
        "tick",
        "--apply",
        "--json",
        "--owner-id",
        "operator-tick-2",
        *_candidate(2, worker_class="free-local"),
    )

    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["decision"] == "assigned"
    assert second.returncode == 1
    assert json.loads(second.stdout)["reason"] == "lease-held"


def test_factoryctl_rejects_partial_candidate_without_state(tmp_path: Path) -> None:
    result = _run(tmp_path, "tick", "--request-id", "request-1")

    assert result.returncode == 2
    assert "candidate fields must be supplied together" in result.stderr
    assert not (tmp_path / ".entroping").exists()

    authorization_only = _run(
        tmp_path,
        "tick",
        "--authorization-id",
        f"auth-{'a' * 32}",
    )
    assert authorization_only.returncode == 2
    assert "candidate fields must be supplied together" in authorization_only.stderr


def test_factoryctl_idle_tick_is_value_free(tmp_path: Path) -> None:
    result = _run(tmp_path, "tick", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "idle"
    assert payload["request_id"] is None
    assert payload["assignment_id"] is None
    assert payload["paid_work_authorized"] is False
    assert not (tmp_path / ".entroping").exists()
