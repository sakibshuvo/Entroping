from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from factory_orchestration_test_support import (
    private_file,
    repository,
    request_payload,
    selection_snapshot,
    update_patch,
)
from factory_scheduler_test_support import dead, owner, scheduler
from factory_scheduler_test_support import request as scheduler_request

from scripts import factory_scheduler_delivery as scheduler_module
from scripts.factory_scheduler_execution_models import ExecutionPhase

REPO_ROOT = Path(__file__).resolve().parents[1]
FACTORYCTL = REPO_ROOT / "scripts" / "factoryctl.py"


def _authorized_request(main: Path, worktree: Path, base: str, proposal: bytes) -> Path:
    payload = request_payload(main, worktree, base)
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    subject = scheduler(main)
    lease_owner = owner(1)
    now = datetime.now(UTC)
    candidate = scheduler_request(
            worker_class="free-local",
            access_mode="write",
            issue_number=1574,
            worktree_id=str(payload["worktree_id"]),
        ).model_copy(
            update={
                "job_id": payload["job_id"],
            }
        )
    git_remove = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=main,
        check=True,
        capture_output=True,
    )
    assert git_remove.returncode == 0
    subprocess.run(
        ["git", "branch", "-D", str(payload["branch"])],
        cwd=main,
        check=True,
        capture_output=True,
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            scheduler_module,
            "refresh_snapshot",
            lambda **_kwargs: selection_snapshot(),
        )
        assigned = subject._tick_selected(
            request=candidate,
            owner=lease_owner,
            as_of=now,
            lease_seconds=300,
            plan_only=False,
            owner_health=dead,
        )
    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "-b",
            str(payload["branch"]),
            str(worktree),
            str(payload["base_commit"]),
        ],
        cwd=main,
        check=True,
        capture_output=True,
    )
    payload["assignment_id"] = assigned.assignment_id
    payload["scheduler_owner_id"] = assigned.lease_owner_id
    payload["scheduler_owner_pid"] = lease_owner.pid
    payload["scheduler_owner_start_token"] = lease_owner.process_start_token
    payload["scheduler_owner_epoch"] = assigned.lease_epoch
    assert assigned.assignment_id is not None and assigned.lease_epoch is not None
    stored = subject.assignment_for_job_readonly(str(payload["job_id"]))
    assert stored is not None and stored.request.delivery_authority is not None
    delivery = stored.request.delivery_authority
    payload["selector_digest"] = delivery.selector_digest
    payload["selection_digest"] = delivery.selection_digest
    payload["autonomy_tier"] = delivery.autonomy_tier
    payload["verification_lane"] = delivery.verification_lane
    payload["allowed_scopes"] = delivery.allowed_scopes
    payload["allowed_scope_digest"] = delivery.allowed_scope_digest
    phases: tuple[ExecutionPhase, ...] = (
        "dispatch-intent",
        "dispatched",
        "completed-unsettled",
    )
    for version, phase in enumerate(phases, start=1):
        subject.transition_execution(
            assignment_id=assigned.assignment_id,
            owner=lease_owner,
            epoch=assigned.lease_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=now + timedelta(microseconds=version),
            evidence_digest=(
                str(payload["proposal_sha256"])
                if phase == "completed-unsettled"
                else f"{version:x}" * 64
            ),
        )
    proposal_path = Path(str(payload["proposal_path"]))
    request_path = proposal_path.parent / "request.json"
    private_file(proposal_path, proposal)
    private_file(request_path, json.dumps(payload).encode())
    return request_path


def _run(
    main: Path,
    request: Path,
    *extra: str,
    invocation_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FACTORYCTL), "orchestrate", "--request", str(request), *extra],
        cwd=main if invocation_root is None else invocation_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def test_factoryctl_orchestration_defaults_to_plan_only_json(tmp_path: Path) -> None:
    # Given: one scheduler-owned request and exact proposal.
    main, worktree, base = repository(tmp_path)
    request = _authorized_request(main, worktree, base, update_patch())

    # When: the maintainer omits --apply.
    result = _run(main, request, "--json")

    # Then: JSON is plan-only and no orchestration lifecycle is created.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["lifecycle"] == "prepared"
    assert payload["reason"] == "plan-only"
    assert payload["authoritative"] is False
    assert not (main / ".entroping" / "factory-orchestration").exists()


def test_factoryctl_orchestration_from_sibling_uses_primary_scheduler_root(
    tmp_path: Path,
) -> None:
    main, worktree, base = repository(tmp_path)
    request = _authorized_request(main, worktree, base, update_patch())

    result = _run(main, request, "--json", invocation_root=worktree)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["reason"] == "plan-only"
    assert not (worktree / ".entroping/factory-orchestration").exists()


def test_factoryctl_apply_failure_is_value_free_and_exit_one(tmp_path: Path) -> None:
    # Given: a valid patch shape whose context cannot apply.
    main, worktree, base = repository(tmp_path)
    proposal = update_patch().replace(b"Version one.", b"Version missing.")
    request = _authorized_request(main, worktree, base, proposal)

    # When: apply is explicit.
    result = _run(main, request, "--apply", "--json")

    # Then: failure is a value-free receipt with operational exit code one.
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["lifecycle"] == "failed"
    assert payload["reason"] == "patch-check-failed"
    assert "Version missing." not in result.stdout
    assert (main / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"


def test_factoryctl_rejects_insecure_request_without_traceback(tmp_path: Path) -> None:
    # Given: a request path with group-readable permissions.
    main, _worktree, _base = repository(tmp_path)
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    os.chmod(request, 0o600)

    # When: the invalid request reaches the CLI boundary.
    result = _run(main, request, "--json")

    # Then: exit two is sanitized and no traceback is emitted.
    assert result.returncode == 2
    assert "request-invalid" in result.stderr
    assert "Traceback" not in result.stderr


def test_factoryctl_plan_rejects_noncanonical_missing_target_without_mutation(
    tmp_path: Path,
) -> None:
    main, worktree, base = repository(tmp_path)
    proposal = update_patch()
    request = _authorized_request(main, worktree, base, proposal)
    git_result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=main,
        check=True,
        capture_output=True,
    )
    assert git_result.returncode == 0
    payload = json.loads(request.read_text(encoding="utf-8"))
    noncanonical = tmp_path / "wrong-target"
    payload["worktree_path"] = str(noncanonical)
    private_file(request, json.dumps(payload).encode())
    scheduler_db = main / ".entroping/factory-scheduler/scheduler.sqlite3"
    before = scheduler_db.read_bytes()
    before_mtime = scheduler_db.stat().st_mtime_ns

    result = _run(main, request, "--json")

    assert result.returncode == 2
    assert "worktree-mismatch" in result.stderr
    assert not noncanonical.exists()
    assert not (main / ".entroping/factory-orchestration").exists()
    assert scheduler_db.read_bytes() == before
    assert scheduler_db.stat().st_mtime_ns == before_mtime
