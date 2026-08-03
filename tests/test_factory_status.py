from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pytest import MonkeyPatch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_scheduler_test_support import (  # noqa: E402
    complete_free_assignment,
    dead,
    owner,
    request,
    scheduler,
)

from scripts import factory_status_database  # noqa: E402
from scripts.factory_budget_ledger import BudgetPeriodConfig, FactoryBudgetLedger  # noqa: E402
from scripts.factory_budget_reservation_models import UsageEnvelope  # noqa: E402
from scripts.factory_quota_models import (  # noqa: E402
    DispatchAuthorizationRequest,
    QuotaObservation,
    QuotaRequirement,
    QuotaWindow,
    TopUpAttestation,
)
from scripts.factory_status import collect_factory_status, render_human  # noqa: E402
from scripts.factory_status_filesystem import collect_queue as status_collect_queue  # noqa: E402
from scripts.factory_status_models import QueueStatus  # noqa: E402


def _database(path: Path, marker: str) -> None:
    connection = sqlite3.connect(path, autocommit=True)
    try:
        _ = connection.execute("CREATE TABLE marker (value TEXT NOT NULL) STRICT")
        _ = connection.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
    finally:
        connection.close()
    path.chmod(0o600)


def test_status_database_remains_bound_to_opened_descriptor_during_path_swap(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Replacing the pathname during open cannot change the observed database."""

    path = tmp_path / "state.sqlite3"
    replacement = tmp_path / "replacement.sqlite3"
    _database(path, "original")
    _database(replacement, "replacement")
    connect = sqlite3.connect

    def swap_before_connect(
        database: str,
        *,
        uri: bool,
        autocommit: bool,
        timeout: float,
        factory: type[sqlite3.Connection],
    ) -> sqlite3.Connection:
        os.replace(replacement, path)
        return connect(database, uri=uri, autocommit=autocommit, timeout=timeout, factory=factory)

    monkeypatch.setattr("scripts.factory_status_database.sqlite3.connect", swap_before_connect)

    connection, state = factory_status_database.open_status_database(tmp_path, path, [])

    assert state == "available"
    assert connection is not None
    try:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("original",)
    finally:
        connection.close()


def test_status_database_rejects_hot_journal_before_immutable_read(tmp_path: Path) -> None:
    """A live journal is not a stable immutable snapshot."""

    path = tmp_path / "state.sqlite3"
    _database(path, "original")
    journal = path.with_name(f"{path.name}-journal")
    journal.write_bytes(b"hot journal")
    journal.chmod(0o600)

    connection, state = factory_status_database.open_status_database(tmp_path, path, [])

    assert connection is None
    assert state == "unsafe"


def test_quota_evidence_for_one_provider_route_never_readies_another(tmp_path: Path) -> None:
    """Quota authority is keyed by the registered provider lane, not provider alone."""

    now = datetime.now(UTC)
    _write_quota_policy(tmp_path, now)
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    ledger.initialize_period(
        BudgetPeriodConfig(
            starts_on=date(now.year, now.month, 1),
            cash_cap_microcents=10_000,
            emergency_reserve_microcents=1_000,
            currency="USD",
            policy_id="status-policy",
            policy_revision=1,
            reserve_idempotency_key="status-period",
        )
    )
    observation = QuotaObservation(
        observation_id="status-observation",
        quota_id="deepseek-five-hour",
        provider_id="deepseek",
        provider_lane_id="deepseek-api/direct",
        policy_id="status-policy",
        policy_revision=1,
        unit="requests",
        source_kind="provider-usage-export",
        source_id="status-provider-export",
        observed_at=now - timedelta(minutes=1),
        recorded_at=now - timedelta(seconds=30),
        expires_at=now + timedelta(minutes=10),
        window=QuotaWindow(
            kind="rolling",
            starts_at=now - timedelta(hours=5),
            ends_at=now + timedelta(minutes=10),
            cycle_id=None,
        ),
        used_units=1,
        known=True,
        evidence_digest="a" * 64,
    )
    _ = ledger.authorize_dispatch(
        DispatchAuthorizationRequest(
            idempotency_key="status-authorize",
            job_id="status-job",
            provider_lane_id="deepseek-api/direct",
            provider_id="deepseek",
            cost_policy_lane_id="deepseek-included",
            policy_id="status-policy",
            policy_revision=1,
            billing_mode="included_quota",
            work_purpose="essential",
            usage_envelope=UsageEnvelope(requests=1),
            cash_reservation=None,
            quota_requirements=(
                QuotaRequirement(
                    quota_id="deepseek-five-hour",
                    unit="requests",
                    limit=100,
                    observation=observation,
                ),
            ),
            top_up_attestation=TopUpAttestation(
                attestation_id="status-top-up",
                provider_id="deepseek",
                provider_lane_id="deepseek-api/direct",
                policy_id="status-policy",
                policy_revision=1,
                mode="disabled",
                source_kind="provider-policy-export",
                source_id="status-policy-export",
                evidence_digest="b" * 64,
                observed_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=10),
            ),
            decision_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )

    report = collect_factory_status(tmp_path)

    assert report.dispatch_lanes.ready_routes == 1
    assert tuple(row.provider_lane_id for row in report.dispatch_lanes.lanes) == (
        "deepseek-api/direct",
        "opencode/native-deepseek",
    )
    assert tuple(row.status for row in report.dispatch_lanes.lanes) == ("available", "unavailable")
    assert report.dispatch_lanes.lanes[1].quotas[0].reason_code == "quota-unavailable"
    assert "deepseek-five-hour:unavailable:quota-unavailable" in render_human(report)


def test_malformed_policy_is_unsafe_not_an_unconfigured_pause(tmp_path: Path) -> None:
    """A present but invalid authority file is a security failure."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    (policy_dir / "factory-cost-policy.example.json").write_text("{", encoding="utf-8")
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.budget.status == "unsafe"
    assert "budget-policy-unsafe" in report.reason_codes


def test_symlinked_policy_authority_is_unsafe(tmp_path: Path) -> None:
    """A policy path must be a regular tracked authority document."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    target = tmp_path / "policy-target.json"
    target.write_text("{}", encoding="utf-8")
    os.symlink(target, policy_dir / "factory-cost-policy.example.json")
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert "budget-policy-unsafe" in report.reason_codes


def test_scheduler_execution_lease_mismatch_is_unsafe(tmp_path: Path) -> None:
    """Execution ownership that does not match the singleton lease is ambiguous authority."""

    now = datetime.now(UTC)
    subject = scheduler(tmp_path)
    _ = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=now,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database, autocommit=True)
    try:
        _ = connection.execute("UPDATE scheduler_execution_state SET lease_epoch = lease_epoch + 1")
    finally:
        connection.close()

    report = collect_factory_status(tmp_path)

    assert report.scheduler.status == "unsafe"
    assert "scheduler-concurrency-unsafe" in report.reason_codes


@pytest.mark.parametrize(
    ("offset", "reason"),
    (
        (timedelta(minutes=1), "scheduler-retry-waiting"),
        (timedelta(minutes=-1), "scheduler-retry-stale"),
    ),
)
def test_scheduler_retry_timing_pauses_status(
    tmp_path: Path, offset: timedelta, reason: str
) -> None:
    """Future and stale retry authority are distinguishable paused states."""

    now = datetime.now(UTC)
    subject = scheduler(tmp_path)
    _ = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=now,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    database = tmp_path / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    connection = sqlite3.connect(database, autocommit=True)
    try:
        _ = connection.execute(
            "UPDATE scheduler_execution_state SET phase = 'retry-wait', retry_not_before_utc = ?",
            ((now + offset).isoformat(),),
        )
    finally:
        connection.close()

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"
    assert reason in report.reason_codes


def test_fully_configured_status_is_healthy(tmp_path: Path) -> None:
    """All trusted status sections produce the successful public exit state."""

    now = datetime.now(UTC)
    _write_policy(tmp_path, now, quota_backed=False)
    (tmp_path / ".entroping" / "ai-jobs").mkdir(parents=True)
    retention_dir = tmp_path / "docs" / "meta"
    (retention_dir / "factory-retention-policy.example.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "factory-retention-policy.example.json").read_bytes()
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
            reserve_idempotency_key="status-period",
        )
    )
    subject = scheduler(tmp_path)
    assigned = subject.tick(
        request=request(worker_class="free-local"),
        owner=owner(1),
        as_of=now,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    complete_free_assignment(
        subject,
        assignment_id=assigned.assignment_id,
        lease_owner=owner(1),
        epoch=assigned.lease_epoch,
        completed_at=now + timedelta(seconds=1),
    )

    report = collect_factory_status(tmp_path)

    assert report.state == "healthy"
    assert report.dispatch_lanes.ready_routes == report.dispatch_lanes.active_routes


def test_queue_payload_file_is_never_opened(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Queue status may inspect metadata but must not open untrusted payload content."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    payload = queued / "job.json"
    payload.write_text("secret-canary", encoding="utf-8")
    open_file = os.open

    def reject_payload(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *args: int
    ) -> int:
        if os.fsdecode(path) == str(payload):
            raise AssertionError("status attempted to read queue payload")
        return open_file(path, *args)

    monkeypatch.setattr("scripts.factory_status_filesystem.os.open", reject_payload)

    report = collect_factory_status(tmp_path)

    assert report.queue.queued == 1


def test_status_never_invokes_provider_or_test_execution(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Status is a local projection and cannot trigger network or subprocess work."""

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("status attempted network access")

    def reject_process(*args: object, **kwargs: object) -> None:
        raise AssertionError("status attempted subprocess execution")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(subprocess, "run", reject_process)

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"


@pytest.mark.parametrize("kind", ("hardlink", "special"))
def test_queue_rejects_unsafe_non_payload_entries(tmp_path: Path, kind: str) -> None:
    """Hardlinks and special entries are invalid queue metadata boundaries."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    candidate = queued / "job.json"
    if kind == "hardlink":
        source = tmp_path / "source.json"
        source.write_text("payload", encoding="utf-8")
        os.link(source, candidate)
    else:
        os.mkfifo(candidate)

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.queue.status == "unsafe"


def test_retention_pressure_pauses_status(tmp_path: Path) -> None:
    """A managed retention root above its trusted ceiling is a paused state."""

    policy_dir = tmp_path / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    policy = json.loads(
        (REPO_ROOT / "docs" / "meta" / "factory-retention-policy.example.json").read_text(
            encoding="utf-8"
        )
    )
    policy["class_policies"][4]["byte_ceiling"] = 1
    (policy_dir / "factory-retention-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    journal = tmp_path / ".entroping" / "retention-journal"
    journal.mkdir(parents=True)
    (journal / "entry.json").write_bytes(b"xx")

    report = collect_factory_status(tmp_path)

    assert report.state == "paused"
    assert "retention-pressure" in report.reason_codes


def test_changed_metadata_between_collections_is_unsafe(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A moving status snapshot cannot be represented as stable authority."""

    queued = tmp_path / ".entroping" / "ai-jobs" / "queued"
    queued.mkdir(parents=True)
    job = queued / "job.json"
    job.write_text("first", encoding="utf-8")
    collect_queue = status_collect_queue
    calls = 0

    def move_after_first_queue(
        root: Path, fingerprints: list[tuple[str, int, int, int]]
    ) -> tuple[QueueStatus, tuple[str, ...]]:
        nonlocal calls
        result = collect_queue(root, fingerprints)
        calls += 1
        if calls == 1:
            job.write_text("second", encoding="utf-8")
        return result

    monkeypatch.setattr("scripts.factory_status.collect_queue", move_after_first_queue)

    report = collect_factory_status(tmp_path)

    assert report.state == "unsafe"
    assert report.snapshot_consistency == "changed"


def _write_quota_policy(root: Path, now: datetime) -> None:
    _write_policy(root, now, quota_backed=True)


def _write_policy(root: Path, now: datetime, *, quota_backed: bool) -> None:
    policy_dir = root / "docs" / "meta"
    policy_dir.mkdir(parents=True)
    policy = {
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
        "provider_quotas": (
            [
                {
                    "id": "deepseek-five-hour",
                    "provider_id": "deepseek",
                    "unit": "requests",
                    "limit": 100,
                    "window": {"kind": "rolling", "duration_seconds": 18_000},
                }
            ]
            if quota_backed
            else []
        ),
        "automatic_top_up": {"mode": "disabled"},
        "automation_lanes": (
            [
                {
                    "id": "deepseek-included",
                    "provider_id": "deepseek",
                    "billing_mode": "included_quota",
                    "enabled": True,
                    "quota_ids": ["deepseek-five-hour"],
                }
            ]
            if quota_backed
            else [
                {
                    "id": "deepseek-metered",
                    "provider_id": "deepseek",
                    "model_id": "deepseek/deepseek-v4-pro",
                    "billing_mode": "metered",
                    "enabled": True,
                    "price_snapshot_ids": ["deepseek-price"],
                    "quota_ids": [],
                }
            ]
        ),
    }
    (policy_dir / "factory-cost-policy.example.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (policy_dir / "provider-capability-registry.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "provider-capability-registry.json").read_bytes()
    )
