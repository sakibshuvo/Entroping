from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from factory_status_test_support import initialize_status_period, write_status_policy  # noqa: E402

from scripts.factory_status import collect_factory_status, render_human, render_json  # noqa: E402
from scripts.factory_status_models import FactoryStatusReport  # noqa: E402

FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"


def _healthy_root(root: Path) -> None:
    """Create the minimal fully available local status fixture."""

    now = datetime.now(UTC)
    write_status_policy(root, now)
    (root / ".entroping" / "ai-jobs").mkdir(parents=True)
    policy_dir = root / "docs" / "meta"
    (policy_dir / "factory-retention-policy.example.json").write_bytes(
        (REPO_ROOT / "docs" / "meta" / "factory-retention-policy.example.json").read_bytes()
    )
    _ = initialize_status_period(root, now)
    subject = scheduler(root)
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


def _run_status(
    root: Path, *, json_output: bool = False, columns: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the public CLI in one isolated project root."""

    environment = os.environ.copy()
    if columns is not None:
        environment["COLUMNS"] = str(columns)
    arguments = [sys.executable, str(FACTORYCTL), "status"]
    if json_output:
        arguments.append("--json")
    return subprocess.run(
        arguments,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=10,
    )


def test_status_json_has_strict_complete_schema_and_is_deterministic(tmp_path: Path) -> None:
    """The JSON contract is complete, strict, and stable for one typed snapshot."""

    report = collect_factory_status(tmp_path)
    first = render_json(report)
    second = render_json(report)
    payload = json.loads(first)

    assert first == second
    assert set(payload) == {
        "schema_version",
        "observed_at_utc",
        "state",
        "snapshot_consistency",
        "reason_codes",
        "budget",
        "dispatch_lanes",
        "scheduler",
        "queue",
        "retention",
    }
    assert payload["schema_version"] == "entroping.factory-status.v1"
    assert FactoryStatusReport.model_validate_json(first, strict=True) == report


def test_human_and_json_views_preserve_state_and_trusted_lane_semantics(tmp_path: Path) -> None:
    """Both renderers expose the same typed state and policy/provider lane readiness."""

    _healthy_root(tmp_path)
    report = collect_factory_status(tmp_path)
    payload = json.loads(render_json(report))
    human = render_human(report)

    assert f"Factory status: {payload['state']}" in human
    for lane in payload["dispatch_lanes"]["lanes"]:
        assert f"{lane['policy_lane_id']}:{lane['provider_lane_id']}={lane['status']}" in human


def test_status_cli_wraps_human_output_for_a_48_column_terminal(tmp_path: Path) -> None:
    """The human report remains readable without horizontal overflow in a narrow terminal."""

    _healthy_root(tmp_path)

    result = _run_status(tmp_path, columns=48)

    assert result.returncode == 0, result.stderr
    assert all(len(line) <= 48 for line in result.stdout.splitlines())


def test_status_cli_uses_public_exit_codes_for_healthy_paused_and_unsafe(tmp_path: Path) -> None:
    """The real command maps its three public status states to 0, 1, and 2."""

    healthy = tmp_path / "healthy"
    healthy.mkdir()
    _healthy_root(healthy)
    unsafe = tmp_path / "unsafe"
    database = unsafe / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("not a sqlite database", encoding="utf-8")

    healthy_result = _run_status(healthy, json_output=True)
    paused_result = _run_status(tmp_path, json_output=True)
    unsafe_result = _run_status(unsafe, json_output=True)

    assert healthy_result.returncode == 0, healthy_result.stderr
    assert json.loads(healthy_result.stdout)["state"] == "healthy"
    assert paused_result.returncode == 1, paused_result.stderr
    assert json.loads(paused_result.stdout)["state"] == "paused"
    assert unsafe_result.returncode == 2, unsafe_result.stderr
    assert json.loads(unsafe_result.stdout)["state"] == "unsafe"
