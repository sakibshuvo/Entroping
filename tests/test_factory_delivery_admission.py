from __future__ import annotations

import json
import shlex
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from factory_orchestration_test_support import admission_repository, git
from factory_scheduler_test_support import dead, owner

from scripts import factory_issue_selector_core, factory_orchestration_tools, factoryctl
from scripts import factory_scheduler_delivery as scheduler_module
from scripts.factory_delivery_admission import (
    DeliveryAdmissionError,
    _DeliveryAdmission,
    selector_policy_digest,
)
from scripts.factory_issue_selector_models import GitHubSnapshot, SnapshotMetadata
from scripts.factory_issue_selector_parser import parse_issue
from scripts.factory_scheduler import FactoryScheduler, FactorySchedulerError
from scripts.factory_scheduler_assignment import plan_or_assign
from scripts.factory_scheduler_models import (
    AssignmentRequest,
    DecisionReceipt,
    DeliveryAuthorityEnvelope,
    LeaseOwner,
    SchedulerLimits,
)
from scripts.factory_scheduler_storage import writable_connection
from scripts.factory_scheduler_tick import HealthCheck, _tick_selected_state, tick_state
from scripts.factory_scheduler_validation import scheduler_timestamp


def _snapshot(*, scope: str = "docs/user/guide.md") -> GitHubSnapshot:
    now = datetime.now(UTC)
    body = (
        "## Outcome\n\nShip docs.\n\n## Scope\n\nStatic docs.\n\n"
        "## Non-goals\n\nNo runtime.\n\n## Acceptance criteria\n\nGate passes.\n\n"
        "## Verification\n\nVerification lane: `tiny-docs`.\n\n"
        "## Autonomy\n\nTier A autonomous lane.\n\n"
        f"## Allowed files\n\n- {scope}\n"
    )
    issue = parse_issue(
        {
            "number": 1574,
            "title": "Ship static docs",
            "state": "open",
            "html_url": "https://github.com/sakibshuvo/Entroping/issues/1574",
            "body": body,
            "labels": [
                {"name": "type:docs"},
                {"name": "priority:p1"},
                {"name": "status:ready"},
                {"name": "autonomy:tier-a"},
            ],
            "assignees": [],
            "milestone": {"title": "Factory"},
        }
    )
    return GitHubSnapshot(
        metadata=SnapshotMetadata(
            repo="sakibshuvo/Entroping",
            fetched_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(seconds=59),
            complete=True,
        ),
        issues=(issue,),
        open_pr_issue_numbers=frozenset(),
    )


def _request() -> AssignmentRequest:
    return AssignmentRequest.model_validate(
        {
            "request_id": "request-1574",
            "job_id": "job-1574",
            "issue_number": 1574,
            "worktree_id": f"wt_{'1' * 64}",
            "worker_class": "free-local",
            "access_mode": "write",
        },
        strict=True,
    )


def _request_for(issue_number: int) -> AssignmentRequest:
    return _request().model_copy(
        update={
            "request_id": f"request-{issue_number}",
            "job_id": f"job-{issue_number}",
            "issue_number": issue_number,
            "worktree_id": f"wt_{issue_number:064x}",
        }
    )


def _authority() -> DeliveryAuthorityEnvelope:
    scopes = ("docs/user/guide.md",)
    return DeliveryAuthorityEnvelope(
        selector_digest="1" * 64,
        selection_digest="2" * 64,
        autonomy_tier="tier-a",
        verification_lane="tiny-docs",
        allowed_scopes=scopes,
        allowed_scope_digest=__import__("hashlib").sha256(
            json.dumps(list(scopes), separators=(",", ":")).encode()
        ).hexdigest(),
    )


def test_generic_tick_rejects_caller_supplied_delivery_authority(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    authority = _authority()

    receipt = FactoryScheduler(root).tick(
        request=_request().model_copy(update={"delivery_authority": authority}),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is True
    assert receipt.reason == "selection-required"
    assert not (root / ".entroping").exists()


def test_generic_tick_rejects_free_local_write_without_authority(
    tmp_path: Path,
) -> None:
    root = admission_repository(tmp_path)

    receipt = FactoryScheduler(root).tick(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is True
    assert receipt.reason == "selection-required"
    assert FactoryScheduler(root).snapshot().active_assignment_count == 0
    assert FactoryScheduler(root).snapshot().lease_owner_id is None


def test_path_shadowed_gh_and_git_cannot_mint_live_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    fake_bin = tmp_path / "ambient-bin"
    fake_bin.mkdir()
    marker = tmp_path / "ambient-tools-ran"
    issue = {
        "number": 1574,
        "title": "Ship static docs",
        "state": "open",
        "html_url": "https://github.com/sakibshuvo/Entroping/issues/1574",
        "body": (
            "## Outcome\n\nShip docs.\n\n## Scope\n\nStatic docs.\n\n"
            "## Non-goals\n\nNo runtime.\n\n## Acceptance criteria\n\nGate passes.\n\n"
            "## Verification\n\nVerification lane: `tiny-docs`.\n\n"
            "## Autonomy\n\nTier A autonomous lane.\n\n"
            "## Allowed files\n\n- docs/user/guide.md\n"
        ),
        "labels": [
            {"name": "type:docs"},
            {"name": "priority:p1"},
            {"name": "status:ready"},
            {"name": "autonomy:tier-a"},
        ],
        "assignees": [],
        "milestone": {},
    }
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(marker))}\n"
        "if [ \"$1\" = api ]; then\n"
        f"  printf '%s\\n' {shlex.quote(json.dumps(issue))}\n"
        "else\n"
        "  printf '%s\\n' '[]'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/bin/sh\n"
        f"touch {shlex.quote(str(marker))}\n"
        "case \"$*\" in *'worktree list --porcelain'*) "
        "printf 'worktree %s\\nHEAD deadbeef\\nbranch refs/heads/main\\n' "
        f"{shlex.quote(str(root))};; esac\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    empty_trusted = tmp_path / "trusted-bin"
    empty_trusted.mkdir()
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setattr(
        factory_orchestration_tools,
        "_TRUSTED_TOOL_DIRS",
        (empty_trusted,),
        raising=False,
    )

    receipt = FactoryScheduler(root)._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is True
    assert not marker.exists()
    assert not (root / ".entroping").exists()


def test_selected_plan_writes_nothing_and_apply_mints_envelope(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    subject = FactoryScheduler(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
        planned = subject._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=True,
            owner_health=dead,
        )

        assert planned.decision == "would-assign"
        assert not (root / ".entroping").exists()

        assigned = subject._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
    stored = subject.assignment_for_job_readonly("job-1574")
    assert assigned.decision == "assigned"
    assert stored is not None and stored.request.delivery_authority is not None
    assert stored.request.delivery_authority.allowed_scopes == ("docs/user/guide.md",)


def test_factoryctl_select_live_uses_fresh_snapshot_and_mints_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
    monkeypatch.setattr(factoryctl, "current_lease_owner", lambda _owner: owner(1))

    exit_code = factoryctl.main(
        [
            "tick",
            "--apply",
            "--json",
            "--select-live",
            "--owner-id",
            "owner-1574",
            "--request-id",
            "request-1574",
            "--job-id",
            "job-1574",
            "--issue",
            "1574",
            "--worktree-id",
            f"wt_{'1' * 64}",
            "--worker-class",
            "free-local",
            "--access-mode",
            "write",
        ]
    )

    stored = FactoryScheduler(root).assignment_for_job_readonly("job-1574")
    assert exit_code == 0
    assert stored is not None and stored.request.delivery_authority is not None
    assert not (root / ".entroping/factory-selector-cache.json").exists()


def test_select_live_rejects_read_only_and_incomplete_candidate(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    read_only = _request().model_copy(update={"access_mode": "read-only"})

    receipt = FactoryScheduler(root)._tick_selected(
        request=read_only,
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=True,
        owner_health=dead,
    )
    assert receipt.decision == "blocked"
    assert receipt.authoritative is False
    assert receipt.paid_work_authorized is False
    assert not (root / ".entroping").exists()


def test_selected_admission_rejects_non_markdown_scope_without_state(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            scheduler_module,
            "refresh_snapshot",
            lambda **_kwargs: _snapshot(scope="docs/user/payload.py"),
        )
        receipt = FactoryScheduler(root)._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )

    assert receipt.decision == "blocked"
    assert not (root / ".entroping").exists()


def test_committed_policy_drift_rejects_mismatched_executing_module(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    _ = selector_policy_digest(root)
    policy = root / "scripts/factory_issue_selector_core.py"
    policy.write_bytes(policy.read_bytes() + b"\n# policy revision\n")
    git(root, "add", "scripts/factory_issue_selector_core.py")
    git(root, "commit", "-m", "policy revision")

    with pytest.raises(DeliveryAdmissionError):
        selector_policy_digest(root)


def test_dirty_canonical_main_cannot_mint_delivery_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    policy = root / "scripts/factory_issue_selector_core.py"
    policy.write_bytes(policy.read_bytes() + b"\n# uncommitted policy drift\n")
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())

    receipt = FactoryScheduler(root)._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is True
    assert not (root / ".entroping").exists()


def test_sibling_worktree_loaded_module_drift_cannot_mint_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    sibling = tmp_path / "Entroping-issue-9999"
    git(root, "worktree", "add", "-b", "feat/issue-9999", str(sibling), "main")
    drifted_module = sibling / "scripts/factory_issue_selector_core.py"
    drifted_module.write_bytes(drifted_module.read_bytes() + b"\n# sibling drift\n")
    monkeypatch.setattr(factory_issue_selector_core, "__file__", str(drifted_module))

    with pytest.raises(DeliveryAdmissionError):
        selector_policy_digest(root)


def test_active_delivery_scope_is_immutable_when_remote_issue_scope_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    subject = FactoryScheduler(root)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
    first = subject._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    changed_active = _snapshot(scope="docs/user/other.md").issues[0]
    overlapping_candidate = replace(
        _snapshot().issues[0],
        number=1575,
        url="https://github.com/sakibshuvo/Entroping/issues/1575",
    )
    changed = replace(
        _snapshot(),
        issues=(changed_active, overlapping_candidate),
    )
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: changed)

    second = subject._tick_selected(
        request=_request_for(1575),
        owner=owner(2),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert first.decision == "assigned"
    assert second.decision == "blocked"
    assert second.authoritative is True
    assert subject.snapshot().active_assignment_count == 1


def test_malformed_active_writer_authority_makes_selection_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    subject = FactoryScheduler(root)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
    first = subject._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    database = root / ".entroping/factory-scheduler/scheduler.sqlite3"
    with sqlite3.connect(database) as connection:
        _ = connection.execute(
            "INSERT INTO scheduler_assignments("
            "request_id, request_digest, assignment_id, decision_id, job_id, "
            "issue_number, worktree_id, scope_key, worker_class, access_mode, "
            "reservation_id, authorization_id, delivery_authority_json, "
            "lease_owner_id, lease_owner_pid, lease_owner_start_token, lease_epoch, "
            "created_at_utc, state, completed_at_utc) "
            "SELECT 'legacy-request', ?, ?, ?, 'legacy-job', 1576, ?, '1576:legacy', "
            "'free-local', 'write', NULL, NULL, '{}', lease_owner_id, lease_owner_pid, "
            "lease_owner_start_token, lease_epoch, created_at_utc, 'active', NULL "
            "FROM scheduler_assignments WHERE request_id = 'request-1574'",
            (
                "a" * 64,
                f"assign_{'a' * 64}",
                f"decision_{'b' * 64}",
                f"wt_{'c' * 64}",
            ),
        )
        _ = connection.execute(
            "INSERT INTO scheduler_execution_state "
            "SELECT ?, phase, phase_version, attempt_count, lease_owner_id, "
            "lease_owner_pid, lease_owner_start_token, lease_epoch, lease_expires_at_utc, "
            "phase_changed_at_utc, worker_heartbeat_at_utc, retry_not_before_utc, "
            "failure_code, terminal_outcome, evidence_digest "
            "FROM scheduler_execution_state WHERE assignment_id = ?",
            (f"assign_{'a' * 64}", first.assignment_id),
        )
    changed_active = _snapshot(scope="docs/user/other.md").issues[0]
    candidate = replace(_snapshot().issues[0], number=1575)
    changed = replace(_snapshot(), issues=(changed_active, candidate))
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: changed)

    second = subject._tick_selected(
        request=_request_for(1575),
        owner=owner(2),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )

    assert first.decision == "assigned"
    assert second.decision == "blocked"
    assert second.authoritative is True
    assert subject.snapshot().active_assignment_count == 2


def test_direct_tick_state_rejects_free_local_write_without_live_admission(
    tmp_path: Path,
) -> None:
    root = admission_repository(tmp_path)

    receipt = tick_state(
        root,
        FactoryScheduler(root).limits,
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        health=dead,
    )

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-required"
    assert receipt.authoritative is True
    assert FactoryScheduler(root).snapshot().active_assignment_count == 0
    assert FactoryScheduler(root).snapshot().lease_owner_id is None


def test_transaction_boundary_rejects_free_local_write_without_admission(
    tmp_path: Path,
) -> None:
    root = admission_repository(tmp_path)
    now = datetime.now(UTC)

    with writable_connection(root, initialized_at=scheduler_timestamp(now)) as connection:
        receipt = plan_or_assign(
            connection,
            request=_request(),
            owner=owner(1),
            as_of=now,
            lease_seconds=30,
            limits=FactoryScheduler(root).limits,
            plan_only=False,
            owner_health=dead,
        )

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-required"
    assert receipt.authoritative is True
    assert FactoryScheduler(root).snapshot().active_assignment_count == 0
    assert FactoryScheduler(root).snapshot().lease_owner_id is None


def test_exact_selected_tick_replays_without_refetch(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    subject = FactoryScheduler(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
        first = subject._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )
        patch.setattr(
            scheduler_module,
            "refresh_snapshot",
            lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("exact replay must not refresh")
            ),
        )
        replay = subject._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=False,
            owner_health=dead,
        )

    assert replay.decision == "assigned"
    assert replay.reason == "exact-replay"
    assert replay.assignment_id == first.assignment_id
    assert replay.decision_id == first.decision_id


def test_selected_admission_rejects_wildcard_matching_symlink(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    target = root / "foreign.md"
    target.write_text("foreign\n", encoding="utf-8")
    (root / "docs/user/linked.md").symlink_to(target)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            scheduler_module,
            "refresh_snapshot",
            lambda **_kwargs: _snapshot(scope="docs/user/*.md"),
        )
        receipt = FactoryScheduler(root)._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=True,
            owner_health=dead,
        )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is False
    assert not (root / ".entroping").exists()


def test_concurrent_selected_admission_creates_one_assignment(tmp_path: Path) -> None:
    root = admission_repository(tmp_path)
    barrier = threading.Barrier(2)

    def admit(index: int) -> str:
        request = _request().model_copy(
            update={"request_id": f"request-1574-{index}", "job_id": f"job-1574-{index}"}
        )
        barrier.wait()
        try:
            return FactoryScheduler(root)._tick_selected(
                request=request,
                owner=owner(index),
                as_of=None,
                lease_seconds=30,
                plan_only=False,
                owner_health=dead,
            ).decision
        except FactorySchedulerError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor, pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            scheduler_module,
            "refresh_snapshot",
            lambda **_kwargs: _snapshot(),
        )
        outcomes = tuple(executor.map(admit, (1, 2)))

    assert sorted(outcomes) == ["assigned", "blocked"]
    assert FactoryScheduler(root).snapshot().active_assignment_count == 1


@pytest.mark.parametrize(
    "case",
    ("stale", "incomplete", "issue-mismatch", "tier-b", "non-docs-lane"),
)
def test_selected_plan_rejects_invalid_live_selection_without_state(
    tmp_path: Path,
    case: str,
) -> None:
    root = admission_repository(tmp_path)
    snapshot = _snapshot()
    issue = snapshot.issues[0]
    now = datetime.now(UTC)
    if case == "stale":
        snapshot = replace(
            snapshot,
            metadata=replace(
                snapshot.metadata,
                fetched_at=now - timedelta(seconds=60),
                expires_at=now - timedelta(seconds=1),
            ),
        )
    elif case == "incomplete":
        snapshot = replace(snapshot, metadata=replace(snapshot.metadata, complete=False))
    elif case == "issue-mismatch":
        snapshot = replace(snapshot, issues=(replace(issue, number=1575),))
    elif case == "tier-b":
        snapshot = replace(
            snapshot,
            issues=(replace(issue, autonomy_labels=("autonomy:tier-b",)),),
        )
    else:
        snapshot = replace(
            snapshot,
            issues=(replace(issue, verification_lanes=("normal-code",)),),
        )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: snapshot)
        receipt = FactoryScheduler(root)._tick_selected(
            request=_request(),
            owner=owner(1),
            as_of=None,
            lease_seconds=30,
            plan_only=True,
            owner_health=dead,
        )

    assert receipt.decision == "blocked"
    assert receipt.authoritative is False
    assert receipt.paid_work_authorized is False
    assert not (root / ".entroping").exists()


def test_transaction_state_drift_blocks_without_assignment_or_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
    original_tick_state = _tick_selected_state

    def drift_then_tick(
        project_root: Path,
        limits: SchedulerLimits,
        *,
        request: AssignmentRequest,
        owner: LeaseOwner,
        as_of: datetime | None,
        lease_seconds: int,
        plan_only: bool,
        health: HealthCheck,
        delivery_admission: _DeliveryAdmission,
    ) -> DecisionReceipt:
        tree = git(root, "rev-parse", "HEAD^{tree}")
        commit = git(root, "commit-tree", tree, "-p", "HEAD", input_bytes=b"drift\n")
        git(root, "branch", "feat/issue-1575", commit)
        return original_tick_state(
            project_root,
            limits,
            request=request,
            owner=owner,
            as_of=as_of,
            lease_seconds=lease_seconds,
            plan_only=plan_only,
            health=health,
            delivery_admission=delivery_admission,
        )

    monkeypatch.setattr(scheduler_module, "_tick_selected_state", drift_then_tick)

    receipt = FactoryScheduler(root)._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    state = FactoryScheduler(root).snapshot()

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-changed"
    assert receipt.authoritative is True
    assert state.active_assignment_count == 0
    assert state.lease_owner_id is None


def test_factoryctl_failed_live_plan_is_value_free_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = admission_repository(tmp_path)
    stale = replace(
        _snapshot(),
        metadata=replace(_snapshot().metadata, complete=False),
    )
    monkeypatch.chdir(root)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: stale)

    exit_code = factoryctl.main(
        [
            "tick",
            "--json",
            "--select-live",
            "--request-id",
            "request-1574",
            "--job-id",
            "job-1574",
            "--issue",
            "1574",
            "--worktree-id",
            f"wt_{'1' * 64}",
            "--worker-class",
            "free-local",
            "--access-mode",
            "write",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["decision"] == "blocked"
    assert output["authoritative"] is False
    assert output["paid_work_authorized"] is False
    assert output["assignment_id"] is None
    assert not (root / ".entroping").exists()


def test_transaction_policy_drift_blocks_without_assignment_or_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = admission_repository(tmp_path)
    monkeypatch.setattr(scheduler_module, "refresh_snapshot", lambda **_kwargs: _snapshot())
    original_tick_state = _tick_selected_state

    def drift_then_tick(
        project_root: Path,
        limits: SchedulerLimits,
        *,
        request: AssignmentRequest,
        owner: LeaseOwner,
        as_of: datetime | None,
        lease_seconds: int,
        plan_only: bool,
        health: HealthCheck,
        delivery_admission: _DeliveryAdmission,
    ) -> DecisionReceipt:
        policy = root / "scripts/factory_issue_selector_core.py"
        policy.write_bytes(policy.read_bytes() + b"\n# changed during admission\n")
        git(root, "add", "scripts/factory_issue_selector_core.py")
        git(root, "commit", "-m", "policy drift")
        return original_tick_state(
            project_root,
            limits,
            request=request,
            owner=owner,
            as_of=as_of,
            lease_seconds=lease_seconds,
            plan_only=plan_only,
            health=health,
            delivery_admission=delivery_admission,
        )

    monkeypatch.setattr(scheduler_module, "_tick_selected_state", drift_then_tick)

    receipt = FactoryScheduler(root)._tick_selected(
        request=_request(),
        owner=owner(1),
        as_of=None,
        lease_seconds=30,
        plan_only=False,
        owner_health=dead,
    )
    state = FactoryScheduler(root).snapshot()

    assert receipt.decision == "blocked"
    assert receipt.reason == "selection-changed"
    assert state.active_assignment_count == 0
    assert state.lease_owner_id is None
