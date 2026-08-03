from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from factory_scheduler_test_support import dead, owner, request, scheduler

from scripts.factory_budget_ledger import (  # noqa: E402
    BudgetPeriodConfig,
    FactoryBudgetLedger,
    LedgerEntryInput,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"


def _status_policy(
    now: datetime, *, enabled: bool, quota_backed: bool = False
) -> dict[str, object]:
    return {
        "schema_version": "entroping.factory-cost-policy.v1",
        "policy_id": "status-policy",
        "policy_revision": 1,
        "currency": "USD",
        "monetary_unit": "microcent",
        "valid_from": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=1)).isoformat(),
        "unknown_cost_behavior": "deny_paid_dispatch",
        "unknown_quota_behavior": "deny_affected_paid_lane",
        "cash": {
            "calendar_month_timezone": "UTC",
            "calendar_month_cap_microcents": 10_000,
            "emergency_reserve_microcents": 1_000,
            "thresholds": {
                "stop_experiments_basis_points": 8000,
                "subscription_only_basis_points": 9000,
                "stop_paid_dispatch_basis_points": 10000,
            },
        },
        "subscriptions": [],
        "price_snapshots": []
        if quota_backed
        else [
            {
                "id": "deepseek-price",
                "provider_id": "deepseek",
                "model_id": "deepseek/deepseek-v4-pro",
                "unit": "input_token",
                "quantity": 1,
                "price_microcents": 1,
                "observed_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        "provider_quotas": [
            {
                "id": "deepseek-five-hour",
                "provider_id": "deepseek",
                "unit": "requests",
                "limit": 100,
                "window": {"kind": "rolling", "duration_seconds": 18_000},
            }
        ]
        if quota_backed
        else [],
        "automatic_top_up": {"mode": "disabled"},
        "automation_lanes": [
            {
                "id": "deepseek-included" if quota_backed else "deepseek-metered",
                "provider_id": "deepseek",
                "billing_mode": "included_quota" if quota_backed else "metered",
                "enabled": enabled,
                **(
                    {"quota_ids": ["deepseek-five-hour"]}
                    if quota_backed
                    else {
                        "model_id": "deepseek/deepseek-v4-pro",
                        "price_snapshot_ids": ["deepseek-price"],
                        "quota_ids": [],
                    }
                ),
            }
        ],
    }


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


def test_factoryctl_status_empty_state_is_paused_and_creates_nothing(
    tmp_path: Path,
) -> None:
    # Given: an otherwise empty project root and its recursive pre-command manifest.
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))

    # When: the maintainer requests the factory status projection.
    result = _run(tmp_path, "status", "--json")

    # Then: it reports a stable paused status without creating factory state.
    after = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.factory-status.v1"
    assert payload["state"] == "paused"
    assert payload["snapshot_consistency"] == "stable"
    assert before == after
    assert not (tmp_path / ".entroping").exists()


def test_factoryctl_status_counts_metadata_without_reading_queue_payload(
    tmp_path: Path,
) -> None:
    # Given: one queue metadata entry whose payload contains a disclosure canary.
    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    canary = "sk-status-secret-canary-must-not-render"
    (queued / "job.json").write_text(canary, encoding="utf-8")

    # When: both public status views are requested.
    json_result = _run(tmp_path, "status", "--json")
    human_result = _run(tmp_path, "status")

    # Then: metadata counts agree and neither view exposes the payload.
    assert json_result.returncode == 1, json_result.stderr
    assert human_result.returncode == 1, human_result.stderr
    payload = json.loads(json_result.stdout)
    assert payload["queue"]["queued"] == 1
    assert payload["state"] == "paused"
    assert "Factory status: paused" in human_result.stdout
    assert canary not in json_result.stdout
    assert canary not in human_result.stdout
    assert "\x1b" not in human_result.stdout


def test_factoryctl_status_rejects_symlinked_queue_entry_without_disclosure(
    tmp_path: Path,
) -> None:
    # Given: a queue root containing a symlink named with a disclosure canary.
    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    secret_name = "token-secret-canary"
    os.symlink(tmp_path / "missing", queued / secret_name)

    # When: the status projection scans the queue metadata boundary.
    result = _run(tmp_path, "status", "--json")

    # Then: the unsafe state is sanitized and carries no untrusted filename.
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "unsafe"
    assert payload["queue"]["invalid"] == 1
    assert secret_name not in result.stdout


def test_factoryctl_status_preserves_existing_database_bytes_mtime_and_manifest(
    tmp_path: Path,
) -> None:
    # Given: initialized scheduler state and a complete pre-command read-only manifest.
    subject = scheduler(tmp_path)
    _ = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=datetime.now(UTC),
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    before_manifest = tuple(
        sorted(
            (
                path.relative_to(tmp_path).as_posix(),
                path.stat(follow_symlinks=False).st_size,
                path.stat(follow_symlinks=False).st_mtime_ns,
            )
            for path in tmp_path.rglob("*")
        )
    )
    before_bytes = database.read_bytes()
    before_mtime_ns = database.stat().st_mtime_ns

    # When: status reads the initialized state through its no-create path.
    result = _run(tmp_path, "status", "--json")

    # Then: the projection is paused for unrelated missing authority, not mutated.
    after_manifest = tuple(
        sorted(
            (
                path.relative_to(tmp_path).as_posix(),
                path.stat(follow_symlinks=False).st_size,
                path.stat(follow_symlinks=False).st_mtime_ns,
            )
            for path in tmp_path.rglob("*")
        )
    )
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["scheduler"]["status"] == "available"
    assert database.read_bytes() == before_bytes
    assert database.stat().st_mtime_ns == before_mtime_ns
    assert after_manifest == before_manifest


def test_factoryctl_status_reports_corrupt_scheduler_database_as_unsafe(
    tmp_path: Path,
) -> None:
    # Given: a scheduler database path that cannot be a safe SQLite state store.
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("not a sqlite database", encoding="utf-8")

    # When: status opens the existing state through the no-create read path.
    result = _run(tmp_path, "status", "--json")

    # Then: the unsafe state is sanitized and carries no database contents.
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == "unsafe"
    assert "scheduler-unsafe" in payload["reason_codes"]
    assert "not a sqlite database" not in result.stdout


def test_factoryctl_status_requires_enabled_policy_lane_for_route_readiness(
    tmp_path: Path,
) -> None:
    # Given: valid tracked policy and capability files with every lane disabled.
    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    now = datetime.now(UTC)
    policy = _status_policy(now, enabled=False)
    (policy_dir / "factory-cost-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    # When: the status projection resolves route readiness.
    result = _run(tmp_path, "status", "--json")

    # Then: disabled authority cannot be represented as a ready dispatch route.
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dispatch_lanes"]["status"] == "unavailable"
    assert payload["dispatch_lanes"]["ready_routes"] == 0


def test_factoryctl_status_pauses_at_configured_cash_threshold(tmp_path: Path) -> None:
    # Given: a current policy and a period whose spend is exactly the policy threshold.
    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    now = datetime.now(UTC)
    policy = _status_policy(now, enabled=True)
    (policy_dir / "factory-cost-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(now.year, now.month, 1),
            cash_cap_microcents=10_000,
            emergency_reserve_microcents=1_000,
            currency="USD",
            policy_id="status-policy",
            policy_revision=1,
            reserve_idempotency_key="status-reserve",
        )
    )
    ledger.record_entry(
        LedgerEntryInput(
            idempotency_key="status-threshold",
            kind="manual_adjustment",
            direction="debit",
            amount_microcents=8_000,
            occurred_at=now,
            currency="USD",
            source_id="status-test",
        )
    )

    # When: the status projection reads exact stop-experiments spend.
    result = _run(tmp_path, "status", "--json")

    # Then: configured basis points pause the budget authority.
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["budget"]["status"] == "unavailable"
    assert "budget-threshold" in payload["reason_codes"]


def test_factoryctl_status_blocks_route_with_missing_quota_authority(tmp_path: Path) -> None:
    # Given: an enabled included-quota route without any recorded quota evidence.
    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    now = datetime.now(UTC)
    policy = _status_policy(now, enabled=True, quota_backed=True)
    (policy_dir / "factory-cost-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    # When: status evaluates dispatch readiness.
    result = _run(tmp_path, "status", "--json")

    # Then: missing quota evidence denies the affected paid route.
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dispatch_lanes"]["status"] == "unavailable"
    assert payload["dispatch_lanes"]["quota_status"] == "unavailable"


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


def _recovery_args(assignment_id: str, epoch: int) -> tuple[str, ...]:
    observed = datetime.now(UTC) - timedelta(seconds=1)
    expires = observed + timedelta(minutes=5)
    common = (
        "--request-id",
        "recover-cli-1",
        "--assignment-id",
        assignment_id,
        "--expected-epoch",
        str(epoch),
        "--dispatch-state",
        "not-dispatched",
        "--settlement-state",
        "not-required",
        "--failure-class",
        "transient",
        "--failure-code",
        "worker-interrupted",
    )
    snapshots = tuple(
        value
        for index, source in enumerate(("github", "provider-capability"), start=1)
        for value in (
            "--snapshot",
            f"{source},{observed.isoformat()},{expires.isoformat()},{index:x}" + "0" * 63,
        )
    )
    return (*common, *snapshots)


def test_factoryctl_recover_is_plan_first_value_free_and_apply_is_explicit(
    tmp_path: Path,
) -> None:
    subject = scheduler(tmp_path)
    assigned_at = datetime.now(UTC) - timedelta(seconds=2)
    assigned = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=assigned_at,
        lease_seconds=1,
        plan_only=False,
        owner_health=dead,
    )
    assert assigned.assignment_id is not None
    assert assigned.lease_epoch is not None
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    before = database.read_bytes()
    recovery_args = _recovery_args(assigned.assignment_id, assigned.lease_epoch)

    plan = _run(
        tmp_path,
        "recover",
        "--json",
        *recovery_args,
    )

    assert plan.returncode == 0, plan.stderr
    planned = json.loads(plan.stdout)
    assert planned["decision"] == "would-recover"
    assert planned["authoritative"] is False
    assert planned["paid_work_authorized"] is False
    assert "failure_code" not in planned
    assert "snapshots" not in planned
    assert database.read_bytes() == before

    missing_owner = _run(
        tmp_path,
        "recover",
        "--apply",
        *recovery_args,
    )
    assert missing_owner.returncode == 2
    assert "--apply requires --owner-id" in missing_owner.stderr

    applied = _run(
        tmp_path,
        "recover",
        "--apply",
        "--json",
        "--owner-id",
        "recovery-operator",
        *recovery_args,
    )
    assert applied.returncode == 0, applied.stderr
    receipt = json.loads(applied.stdout)
    assert receipt["decision"] == "retry-scheduled"
    assert receipt["authoritative"] is True
    assert receipt["paid_work_authorized"] is False

    replay = _run(
        tmp_path,
        "recover",
        "--apply",
        "--json",
        "--owner-id",
        "recovery-operator",
        *recovery_args,
    )
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout) == receipt


def test_factoryctl_recover_rejects_malformed_snapshot_without_state_change(
    tmp_path: Path,
) -> None:
    result = _run(
        tmp_path,
        "recover",
        "--request-id",
        "recover-cli-1",
        "--assignment-id",
        f"assign_{'a' * 64}",
        "--expected-epoch",
        "1",
        "--dispatch-state",
        "not-dispatched",
        "--settlement-state",
        "not-required",
        "--failure-class",
        "transient",
        "--failure-code",
        "worker-interrupted",
        "--snapshot",
        "not,a,valid,snapshot,shape",
    )

    assert result.returncode == 2
    assert "snapshot must be SOURCE,OBSERVED,EXPIRES,DIGEST" in result.stderr
    assert not (tmp_path / ".entroping").exists()
