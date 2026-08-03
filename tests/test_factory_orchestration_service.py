from __future__ import annotations

import hashlib
import importlib
import inspect
import sqlite3
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from factory_orchestration_test_support import (
    admission_repository,
    git,
    repository,
    request_payload,
    selection_snapshot,
    update_patch,
)
from factory_scheduler_test_support import dead, owner, scheduler
from factory_scheduler_test_support import request as scheduler_request

from scripts import factory_scheduler_delivery as scheduler_module
from scripts.factory_orchestration_models import OrchestrationRequest
from scripts.factory_scheduler_assignment_transaction import insert_assignment
from scripts.factory_scheduler_execution_models import ExecutionPhase
from scripts.factory_scheduler_lease_transaction import store_lease
from scripts.factory_scheduler_receipts import (
    assignment_id,
    make_decision_id,
    request_digest,
)
from scripts.factory_scheduler_storage import writable_connection
from scripts.factory_scheduler_transaction_control import update_clock
from scripts.factory_scheduler_validation import scheduler_timestamp

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

service = importlib.import_module("scripts.factory_orchestration_service")
gates = importlib.import_module("scripts.factory_orchestration_gates")
journal = importlib.import_module("scripts.factory_orchestration_journal")
models = importlib.import_module("scripts.factory_orchestration_models")
tools = importlib.import_module("scripts.factory_orchestration_tools")


def test_public_orchestration_has_no_authoritative_execution_injection_seam() -> None:
    assert tuple(inspect.signature(service.orchestrate).parameters) == (
        "repo_root",
        "request",
        "proposal",
        "apply",
        "cancelled",
    )


def _authorize(
    main: Path,
    payload: dict[str, object],
    *,
    include_delivery_authority: bool = True,
) -> None:
    subject = scheduler(main)
    lease_owner = owner(1)
    now = datetime.now(UTC)
    issue_number = payload["issue_number"]
    assert isinstance(issue_number, int)
    candidate = scheduler_request(
            worker_class="free-local",
            access_mode="write",
            issue_number=issue_number,
            worktree_id=str(payload["worktree_id"]),
        ).model_copy(
            update={
                "job_id": payload["job_id"],
            }
        )
    if include_delivery_authority:
        worktree = Path(str(payload["worktree_path"]))
        existed = worktree.exists()
        if existed:
            git(main, "worktree", "remove", "--force", str(worktree))
            git(main, "branch", "-D", str(payload["branch"]))
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                scheduler_module,
                "refresh_snapshot",
                lambda **_kwargs: selection_snapshot(),
            )
            assigned = subject._tick_selected(
                request=candidate.model_copy(update={"delivery_authority": None}),
                owner=lease_owner,
                as_of=now,
                lease_seconds=300,
                plan_only=False,
                owner_health=dead,
            )
        if existed:
            git(
                main,
                "worktree",
                "add",
                "-b",
                str(payload["branch"]),
                str(worktree),
                str(payload["base_commit"]),
            )
    else:
        digest = request_digest(candidate)
        legacy_assignment_id = assignment_id(digest)
        legacy_epoch = 1
        with writable_connection(
            main,
            initialized_at=scheduler_timestamp(now),
        ) as connection:
            _ = connection.execute("BEGIN IMMEDIATE")
            store_lease(
                connection,
                lease_owner,
                legacy_epoch,
                now,
                now + timedelta(seconds=300),
            )
            update_clock(connection, now, epoch=legacy_epoch)
            insert_assignment(
                connection,
                request=candidate,
                request_digest=digest,
                assignment_id=legacy_assignment_id,
                decision_id=make_decision_id(
                    request_digest_value=digest,
                    epoch=legacy_epoch,
                    observed_at=now,
                    decision="assigned",
                    reason="capacity-reserved",
                ),
                owner=lease_owner,
                epoch=legacy_epoch,
                created_at=now,
                lease_expires_at=now + timedelta(seconds=300),
            )
            _ = connection.execute("COMMIT")
    if include_delivery_authority:
        assignment_id_value = assigned.assignment_id
        lease_owner_id = assigned.lease_owner_id
        lease_epoch = assigned.lease_epoch
    else:
        assignment_id_value = legacy_assignment_id
        lease_owner_id = lease_owner.owner_id
        lease_epoch = legacy_epoch
    payload["assignment_id"] = assignment_id_value
    payload["scheduler_owner_id"] = lease_owner_id
    payload["scheduler_owner_pid"] = lease_owner.pid
    payload["scheduler_owner_start_token"] = lease_owner.process_start_token
    payload["scheduler_owner_epoch"] = lease_epoch
    assert assignment_id_value is not None and lease_epoch is not None
    if include_delivery_authority:
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
            assignment_id=assignment_id_value,
            owner=lease_owner,
            epoch=lease_epoch,
            expected_phase_version=version,
            target_phase=phase,
            observed_at=now + timedelta(microseconds=version),
            evidence_digest=(
                str(payload["proposal_sha256"])
                if phase == "completed-unsettled"
                else f"{version:x}" * 64
            ),
        )


def _request(main: Path, worktree: Path, base: str) -> tuple[OrchestrationRequest, bytes]:
    payload = request_payload(main, worktree, base)
    proposal = update_patch()
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    _authorize(main, payload)
    return models.OrchestrationRequest.model_validate(payload, strict=True), proposal


def test_orchestrates_reused_worktree_and_replays_exact_receipt(tmp_path: Path) -> None:
    # Given: scheduler-owned work and one exact reusable issue worktree.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)

    # When: the patch and injected narrow acceptance gate run.
    first = service.orchestrate(
        main,
        request,
        proposal,
        apply=True,
    )
    replay = service.orchestrate(
        main,
        request,
        proposal,
        apply=True,
    )

    # Then: acceptance is revision-bound and exact replay performs no work.
    assert first.lifecycle == "accepted"
    assert first == replay
    assert first.result_head == base
    assert first.diff_sha256 is not None
    assert (main / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"

    # Given: live scheduler authority later expires after the receipt is terminal.
    scheduler_db = main / ".entroping" / "factory-scheduler" / "scheduler.sqlite3"
    expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    heartbeat = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    acquired = (datetime.now(UTC) - timedelta(seconds=3)).isoformat()
    with sqlite3.connect(scheduler_db) as connection:
        connection.execute(
            "UPDATE scheduler_lease SET acquired_at_utc = ?, heartbeat_at_utc = ?, "
            "expires_at_utc = ?",
            (acquired, heartbeat, expired),
        )
        connection.execute(
            "UPDATE scheduler_execution_state SET worker_heartbeat_at_utc = ?, "
            "lease_expires_at_utc = ?",
            (heartbeat, expired),
        )

    # When/Then: exact historic replay remains available without live lease authority.
    assert service.orchestrate(main, request, proposal, apply=True) == first
    conflicting = request.model_copy(update={"selector_digest": "f" * 64})
    with pytest.raises(journal.OrchestrationJournalError) as conflict:
        service.orchestrate(main, conflicting, proposal, apply=True)
    assert conflict.value.code == "request-conflict"


def test_orchestration_creates_fresh_worktree_only_through_starter(tmp_path: Path) -> None:
    # Given: main with no issue worktree and a scheduler-owned request.
    main = admission_repository(tmp_path)
    base = git(main, "rev-parse", "HEAD")
    worktree = tmp_path / "Entroping-issue-1574"
    payload = request_payload(main, worktree, base)
    payload["common_git_dir"] = str((main / ".git").resolve())
    proposal = update_patch()
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    _authorize(main, payload)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)
    calls: list[int] = []

    def starter(
        repo: Path,
        requested: OrchestrationRequest,
        *,
        cancelled: Callable[[], bool],
    ) -> None:
        calls.append(requested.issue_number)
        git(repo, "worktree", "add", "-b", requested.branch, requested.worktree_path, base)

    # When: apply is explicitly requested.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(service, "start_issue", starter)
        receipt = service.orchestrate(
            main,
            request,
            proposal,
            apply=True,
        )

    # Then: creation delegates exactly once and acceptance stays in that worktree.
    assert calls == [1574]
    assert receipt.lifecycle == "accepted"
    assert (worktree / "docs/user/guide.md").read_text(encoding="utf-8") == "Version two.\n"
    assert (main / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"


def test_public_apply_uses_production_start_issue_and_tiny_docs_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = admission_repository(tmp_path)
    base = git(main, "rev-parse", "HEAD")
    worktree = tmp_path / "Entroping-issue-1574"
    payload = request_payload(main, worktree, base)
    proposal = update_patch()
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    _authorize(main, payload)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)
    tool_dir = tmp_path / "trusted-tools"
    tool_dir.mkdir(mode=0o700)
    gh = tool_dir / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        "if [[ \"$1 $2\" == \"issue view\" ]]; then "
        "printf '%s\\n' '{\"title\":\"Ship static docs\","
        "\"url\":\"https://example.invalid/1574\",\"state\":\"OPEN\"}'; "
        "exit 0; fi\n"
        "if [[ \"$1 $2\" == \"api rate_limit\" ]]; then printf '0\\n'; exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    uv = tool_dir / "uv"
    uv.write_text(
        "#!/bin/bash\n"
        "if [[ \"$1 $2 $3\" == \"run python -c\" ]]; then "
        "exec /usr/bin/python3 \"${@:3}\"; fi\n"
        "printf '%s\\n' 'Generated bounded issue prompt.'\n",
        encoding="utf-8",
    )
    gh.chmod(0o700)
    uv.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tool_dir}:/usr/bin:/bin")
    monkeypatch.setattr(tools, "_HOMEBREW_DIRS", ())

    receipt = service.orchestrate(main, request, proposal, apply=True)

    assert receipt.lifecycle == "accepted"
    assert receipt.gate_exit_states[0].command_id == "doc-governance-v1"
    assert (worktree / "docs/user/guide.md").read_text(encoding="utf-8") == "Version two.\n"
    assert (worktree / ".entroping/session-prompts/issue-1574.md").is_file()


def test_post_create_validation_failure_is_uncertain(tmp_path: Path) -> None:
    # Given: a canonical missing target whose starter creates the wrong branch.
    main = admission_repository(tmp_path)
    base = git(main, "rev-parse", "HEAD")
    worktree = tmp_path / "Entroping-issue-1574"
    payload = request_payload(main, worktree, base)
    proposal = update_patch()
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    _authorize(main, payload)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)

    def wrong_starter(
        repo: Path,
        requested: OrchestrationRequest,
        *,
        cancelled: Callable[[], bool],
    ) -> None:
        git(repo, "worktree", "add", "-b", "feat/wrong", requested.worktree_path, base)

    # When/Then: post-create mismatch cannot be downgraded to a fixed failure.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(service, "start_issue", wrong_starter)
        with pytest.raises(service.OrchestrationServiceError) as uncertain:
            service.orchestrate(
                main,
                request,
                proposal,
                apply=True,
            )
    assert uncertain.value.code == "uncertain-recovery-required"
    with pytest.raises(journal.OrchestrationJournalError) as replay:
        journal.OrchestrationJournal(main).prepare(request)
    assert replay.value.code == "uncertain-recovery-required"


def test_plan_only_creates_no_journal_or_worktree(tmp_path: Path) -> None:
    # Given: one reusable scheduler-owned worktree.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)

    # When: orchestration runs in its default plan-only mode.
    receipt = service.orchestrate(main, request, proposal, apply=False)

    # Then: it reports a non-authoritative plan and creates no orchestration state.
    assert receipt.reason == "plan-only"
    assert receipt.authoritative is False
    assert not (main / ".entroping" / "factory-orchestration").exists()
    assert (worktree / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"


def test_plan_rejects_noncanonical_missing_target_without_mutation(tmp_path: Path) -> None:
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    git(main, "worktree", "remove", "--force", str(worktree))
    noncanonical = tmp_path / "wrong-target"
    request = request.model_copy(update={"worktree_path": str(noncanonical)})
    scheduler_db = main / ".entroping/factory-scheduler/scheduler.sqlite3"
    before = scheduler_db.read_bytes()
    before_mtime = scheduler_db.stat().st_mtime_ns

    with pytest.raises(service.OrchestrationServiceError) as denied:
        service.orchestrate(main, request, proposal, apply=False)

    assert denied.value.code == "worktree-mismatch"
    assert not noncanonical.exists()
    assert not (main / ".entroping/factory-orchestration").exists()
    assert scheduler_db.read_bytes() == before
    assert scheduler_db.stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scheduler_owner_pid", 99999),
        ("scheduler_owner_start_token", f"proc_{9:064x}"),
        ("scheduler_owner_epoch", 99),
    ),
)
def test_plan_rejects_scheduler_authority_drift(tmp_path: Path, field: str, value: object) -> None:
    # Given: an otherwise valid request whose live scheduler identity has drifted.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    request = request.model_copy(update={field: value})

    # When/Then: even plan mode refuses stale one-writer authority.
    with pytest.raises(service.OrchestrationServiceError) as denied:
        service.orchestrate(main, request, proposal, apply=False)
    assert denied.value.code == "authority-mismatch"


def test_orchestration_rejects_legacy_assignment_without_delivery_authority(
    tmp_path: Path,
) -> None:
    main, worktree, base = repository(tmp_path)
    payload = request_payload(main, worktree, base)
    proposal = update_patch()
    payload["proposal_sha256"] = hashlib.sha256(proposal).hexdigest()
    _authorize(main, payload, include_delivery_authority=False)
    request = models.OrchestrationRequest.model_validate(payload, strict=True)

    with pytest.raises(service.OrchestrationServiceError) as denied:
        service.orchestrate(main, request, proposal, apply=False)

    assert denied.value.code == "authority-mismatch"


def test_plan_rejects_proposal_digest_and_scope_drift(tmp_path: Path) -> None:
    # Given: scheduler-owned work and an immutable proposal contract.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)

    # When/Then: bytes different from the authorized digest are rejected.
    with pytest.raises(service.OrchestrationServiceError) as digest:
        service.orchestrate(main, request, proposal + b"\n", apply=False)
    assert digest.value.code == "proposal-drift"

    # When/Then: a proposal outside the exact selector scope is rejected pre-mutation.
    denied = request.model_copy(
        update={
            "allowed_scopes": ("tests/**",),
            "allowed_scope_digest": hashlib.sha256(b'["tests/**"]').hexdigest(),
        }
    )
    with pytest.raises(service.OrchestrationServiceError) as scope:
        service.orchestrate(main, denied, proposal, apply=False)
    assert scope.value.code == "scope-denied"


def test_plan_rejects_main_advancing_after_request(tmp_path: Path) -> None:
    # Given: an authorized request whose issue worktree remains at the old base.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    (main / "later.txt").write_text("later\n", encoding="utf-8")
    git(main, "add", "later.txt")
    git(main, "commit", "-m", "advance main")

    # When/Then: plan refuses stale local main authority before mutation.
    with pytest.raises(service.OrchestrationServiceError) as stale:
        service.orchestrate(main, request, proposal, apply=False)
    assert stale.value.code == "stale-base"


def test_plan_uses_canonical_primary_root_from_sibling_invocation(tmp_path: Path) -> None:
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)

    receipt = service.orchestrate(worktree, request, proposal, apply=False)

    assert receipt.reason == "plan-only"
    assert not (worktree / ".entroping/factory-orchestration").exists()


def test_plan_rejects_untracked_main_checkout_state(tmp_path: Path) -> None:
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    (main / "untracked.txt").write_text("drift\n", encoding="utf-8")

    with pytest.raises(service.OrchestrationServiceError) as stale:
        service.orchestrate(main, request, proposal, apply=False)

    assert stale.value.code == "stale-base"


def test_gate_drift_and_mid_gate_cancellation_never_accept(tmp_path: Path) -> None:
    # Given: a gate that creates untracked worktree drift.
    main, worktree, base = repository(tmp_path / "drift")
    request, proposal = _request(main, worktree, base)
    mutating = gates.GateCommand(
        "mutating-gate",
        "mutating-gate-v1",
        (sys.executable, "-c", "from pathlib import Path; Path('gate.txt').write_text('x')"),
        2,
        1024,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "commands_for_lane", lambda *_args, **_kwargs: (mutating,))

    # When: gate truth no longer matches the applied proposal.
    with pytest.raises(service.OrchestrationServiceError) as drift:
        service.orchestrate(
            main,
            request,
            proposal,
            apply=True,
        )

    # Then: acceptance is denied and main remains untouched.
    assert drift.value.code == "uncertain-recovery-required"
    assert (main / "docs/user/guide.md").read_text(encoding="utf-8") == "Version one.\n"
    monkeypatch.undo()

    # Given: a separate long-running gate cancelled after it starts.
    main2, worktree2, base2 = repository(tmp_path / "cancel")
    request2, proposal2 = _request(main2, worktree2, base2)
    started = time.monotonic()
    slow = gates.GateCommand(
        "slow-gate",
        "slow-gate-v1",
        (sys.executable, "-c", "import time; time.sleep(60)"),
        10,
        1024,
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(service, "commands_for_lane", lambda *_args, **_kwargs: (slow,))
        cancelled = service.orchestrate(
            main2,
            request2,
            proposal2,
            apply=True,
            cancelled=lambda: time.monotonic() - started >= 0.05,
        )
    assert cancelled.lifecycle == "cancelled"
    assert cancelled.reason == "cancelled"


def test_authority_loss_after_apply_is_journaled_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: scheduler authority that disappears only after exact patch apply.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    original = service.validate_scheduler_authority
    calls = 0

    def drifting_authority(root: Path, requested: OrchestrationRequest) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise service.OrchestrationServiceError("authority-mismatch")
        original(root, requested)

    monkeypatch.setattr(service, "validate_scheduler_authority", drifting_authority)

    # When/Then: applied work is never left active or represented as failed.
    with pytest.raises(service.OrchestrationServiceError) as uncertain:
        service.orchestrate(
            main,
            request,
            proposal,
            apply=True,
        )
    assert uncertain.value.code == "uncertain-recovery-required"
    with pytest.raises(journal.OrchestrationJournalError) as replay:
        journal.OrchestrationJournal(main).prepare(request)
    assert replay.value.code == "uncertain-recovery-required"


def test_first_gate_main_drift_prevents_second_gate(tmp_path: Path) -> None:
    # Given: two gates where the first writes into the protected main checkout.
    main, worktree, base = repository(tmp_path)
    request, proposal = _request(main, worktree, base)
    marker = worktree / "second-ran"
    first = gates.GateCommand(
        "main-drift",
        "main-drift-v1",
        (
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(main / 'gate-main.txt')!r}).write_text('x')",
        ),
        2,
        1024,
    )
    second = gates.GateCommand(
        "must-not-run",
        "must-not-run-v1",
        (
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('x')",
        ),
        2,
        1024,
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        service,
        "commands_for_lane",
        lambda *_args, **_kwargs: (first, second),
    )

    # When/Then: integrity is checked after gate one and halts the sequence.
    with pytest.raises(service.OrchestrationServiceError) as uncertain:
        service.orchestrate(
            main,
            request,
            proposal,
            apply=True,
        )
    assert uncertain.value.code == "uncertain-recovery-required"
    assert not marker.exists()
    monkeypatch.undo()
