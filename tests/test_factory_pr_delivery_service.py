from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Never

import pytest

if TYPE_CHECKING:
    def accepted_artifacts(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]: ...

    def raw_git(worktree: Path, *args: str) -> bytes: ...

    def write_delivery_request(path: Path, payload: dict[str, object]) -> None: ...
else:
    from factory_pr_delivery_test_support import (  # noqa: E402
        accepted_artifacts,
        raw_git,
        write_delivery_request,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_github import (  # noqa: E402
    CheckObservation,
    CiObservation,
    IssueObservation,
    MergeResult,
    ProtectionObservation,
    PullRequestObservation,
    RequiredCheck,
    ScriptedGitHubDeliveryPort,
)
from scripts.factory_pr_delivery_github_models import CheckStatus, DeliveryMergeState  # noqa: E402
from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import (  # noqa: E402
    CommitResult,
    DeliveryEnvelope,
    DeliveryGitError,
)
from scripts.factory_pr_delivery_receipts import (  # noqa: E402
    DeliveryReceipt,
    decode_delivery_receipt,
    encode_delivery_receipt,
)
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority  # noqa: E402
from scripts.factory_pr_delivery_service import (  # noqa: E402
    DeliveryService,
    DeliveryServiceError,
)
from scripts.factory_pr_delivery_ssh import DeleteBranchResult, PushResult  # noqa: E402
from scripts.factory_scheduler_queries import (  # noqa: E402
    read_assignment,
    read_execution_for_job,
)
from scripts.factory_scheduler_storage import readonly_connection  # noqa: E402

REPO = "sakibshuvo/Entroping"
HEAD = "b" * 40


def _setup(tmp_path: Path) -> tuple[Path, Path, str, str]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    base = load_delivery_envelope(request_path).orchestration_request.base_commit
    return main, request_path, base, str(payload["pr_body_sha256"])


def _no_body_failures(
    _body: str,
    *
    _args: object,
    **_kwargs: object,
) -> list[str]:
    return []


def _port(
    base: str,
    body_sha: str,
    *,
    existing: bool = False,
    ci_status: CheckStatus = "success",
    merge_state: DeliveryMergeState = "merged",
    merged_head: str | None = HEAD,
) -> ScriptedGitHubDeliveryPort:
    issue = IssueObservation(
        repo=REPO,
        number=1574,
        state="open",
        title="Ship static docs",
        labels=("autonomy:tier-a",),
        body_sha256="1" * 64,
    )


    protection = ProtectionObservation(
        repo=REPO,
        base_ref="main",
        base_sha=base,
        required_checks=(RequiredCheck(context="quality", app_id=1),),
        complete=True,
    )
    pull = PullRequestObservation(
        repo=REPO,
        number=42,
        title="Ship static docs",
        body_sha256=body_sha,
        state="open",
        draft=False,
        head_branch="feat/example",
        head_sha=HEAD,
        base_ref="main",
        base_sha=base,
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        changed_files=("docs/user/guide.md",),
        closing_issue_numbers=(1574,),
    )
    ci = CiObservation(
        repo=REPO,
        base_ref="main",
        base_sha=base,
        head_sha=HEAD,
        protection_digest=protection.digest,
        checks=(
            CheckObservation(context="quality", app_id=1, status=ci_status, head_sha=HEAD),
        ),
        mergeable="MERGEABLE",
        merge_state_status="CLEAN",
        complete=True,
    )
    return ScriptedGitHubDeliveryPort(
        issue=issue,
        pull_requests=(pull,) if existing else (),
        created=pull,
        protection=protection,
        ci=ci,
        merge=MergeResult(
            repo=REPO,
            pr_number=42,
            requested_head=HEAD,
            state=merge_state,
            merged_head=merged_head,
        ),
    )


def _commit_result(base: str) -> CommitResult:
    return CommitResult(
        accepted_local_head=base,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
        accepted_diff_sha256="d" * 64,
        committed_diff_sha256="d" * 64,
        accepted_manifest_sha256="e" * 64,
        committed_manifest_sha256="e" * 64,
        approved_path_sha256="f" * 64,
    )


def _journal_aware_commit(*_args: object, **_kwargs: object) -> CommitResult:
    envelope = _kwargs.get("envelope")
    journal = _kwargs.get("journal")
    if envelope is None:
        if len(_args) < 2:
            raise AssertionError("expected envelope for journal-aware commit")
        envelope = _args[1]
    if not isinstance(envelope, DeliveryEnvelope):
        raise AssertionError("expected DeliveryEnvelope for journal-aware commit")
    if journal is None and len(_args) >= 3 and isinstance(_args[2], DeliveryJournal):
        journal = _args[2]
    if not isinstance(journal, DeliveryJournal):
        raise AssertionError("expected DeliveryJournal for journal-aware commit")
    result = _commit_result(envelope.orchestration_request.base_commit)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=result.committed_head,
        commit_parent=result.commit_parent,
        commit_tree=result.commit_tree,
    )
    _ = journal.committed(envelope)
    return result


def test_plan_mode_reads_authority_without_mutating_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    observed: list[str] = []

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )

    original_issue = port.observe_issue

    def observe_issue(repo: str, issue_number: int) -> IssueObservation:
        observed.append("gh:observe-issue")
        return original_issue(repo, issue_number)

    original_protection = port.observe_protection

    def observe_protection(
        repo: str, *, base_ref: str, base_sha: str
    ) -> ProtectionObservation:
        observed.append("gh:observe-protection")
        return original_protection(repo, base_ref=base_ref, base_sha=base_sha)

    original_pull_requests = port.observe_pull_requests

    def observe_pull_requests(
        repo: str, issue_number: int, head_branch: str
    ) -> tuple[PullRequestObservation, ...]:
        observed.append("gh:observe-prs")
        return original_pull_requests(repo, issue_number, head_branch)

    monkeypatch.setattr(port, "observe_issue", observe_issue)
    monkeypatch.setattr(port, "observe_protection", observe_protection)
    monkeypatch.setattr(port, "observe_pull_requests", observe_pull_requests)
    expected = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

    def service_now() -> datetime:
        observed.append("now")
        return expected

    receipt = DeliveryService(
        main,
        github=port,
        now=service_now,
    ).deliver(request_path, apply=False)

    assert observed == ["now", "gh:observe-issue", "gh:observe-protection", "gh:observe-prs"]

    assert receipt.lifecycle == "planned"
    assert receipt.reason == "plan-only"
    assert receipt.authoritative is False
    assert receipt.created_at == expected
    assert receipt.updated_at == expected
    assert [call.operation for call in port.calls] == [
        "observe-issue",
        "observe-protection",
        "observe-prs",
    ]


def test_apply_reaches_merged_receipt_once_gates_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    envelope = load_delivery_envelope(request_path)
    calls = {"scheduler": 0, "merge": 0}

    def validate_scheduler(*_args: object, **_kwargs: object) -> None:
        calls["scheduler"] += 1

    original_merge = port.merge_pull_request

    def fake_merge(repo: str, *, pr_number: int, head_sha: str) -> MergeResult:
        calls["merge"] += 1
        record = DeliveryJournal(main).read(envelope)
        if record is None or record.lifecycle != "merge-intent":
            raise AssertionError("merge must run after merge-intent persisted")
        return original_merge(repo, pr_number=pr_number, head_sha=head_sha)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.validate_scheduler_authority",
        validate_scheduler,
    )
    monkeypatch.setattr(port, "merge_pull_request", fake_merge)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        _journal_aware_commit,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit",
        lambda *_args, **_kwargs: PushResult("pushed", HEAD),
    )

    receipt = DeliveryService(
        main,
        github=port,
        now=lambda: datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    ).deliver(request_path, apply=True)

    terminal_record = DeliveryJournal(main).read(envelope)
    assert terminal_record is not None
    terminal = read_terminal_receipt(terminal_record)
    assert terminal is not None
    assert terminal == receipt
    assert receipt.lifecycle == "merged"
    assert receipt.reason == "cleanup-pending"
    assert receipt.committed_head == HEAD
    assert receipt.remote_head == HEAD
    assert receipt.pr_number == 42
    assert [call.operation for call in port.calls].count("create-pr") == 1
    assert [call.operation for call in port.calls].count("merge-pr") == 1
    assert calls["scheduler"] == 1
    assert calls["merge"] == 1


def _assert_real_delivery_receipts(
    receipts: list[DeliveryReceipt], head: str, clock_values: tuple[datetime, ...]
) -> None:
    assert [(item.lifecycle, item.reason) for item in receipts[:6]] == [
        ("merged", "cleanup-pending")
    ] * 6
    assert [(item.lifecycle, item.reason) for item in receipts[6:]] == [
        ("completed", "completed")
    ] * 2
    assert receipts[0].committed_head == head
    assert receipts[0].remote_head == head
    assert receipts[0].created_at == clock_values[0]
    assert receipts[0].updated_at == clock_values[0]
    assert encode_delivery_receipt(receipts[6]) == encode_delivery_receipt(receipts[7])


def _assert_real_delivery_effects(
    worktree: Path, main: Path, base: str, head: str, pushes: int, deletes: int,
    finishes: int, clock_calls: list[datetime], remote: dict[str, str],
    port: ScriptedGitHubDeliveryPort,
) -> None:
    assert raw_git(worktree, "rev-list", "--count", f"{base}..{head}").decode().strip() == "1"
    assert raw_git(worktree, "status", "--porcelain") == b""
    assert raw_git(main, "rev-parse", "HEAD").decode().strip() == base
    assert (pushes, deletes, finishes, len(clock_calls), remote) == (1, 1, 1, 5, {})
    operations = [call.operation for call in port.calls]
    assert [operations.count(item) for item in ("create-pr", "observe-ci", "merge-pr")] == [1, 1, 1]


def test_apply_real_git_commit_reaches_merged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    envelope = load_delivery_envelope(request_path)
    worktree = envelope.worktree_path
    pushes = 0

    def fake_push(
        worktree_arg: Path, *, branch: str, committed_head: str
    ) -> PushResult:
        nonlocal pushes
        assert worktree_arg == worktree
        assert branch == envelope.orchestration_request.branch
        assert raw_git(worktree_arg, "rev-parse", "HEAD").decode().strip() == committed_head
        assert port.created is not None
        pushes += 1
        port.created = port.created.model_copy(update={"head_sha": committed_head})
        port.ci = port.ci.model_copy(
            update={
                "head_sha": committed_head,
                "checks": tuple(
                    check.model_copy(update={"head_sha": committed_head})
                    for check in port.ci.checks
                ),
            }
        )
        port.merge = port.merge.model_copy(
            update={"requested_head": committed_head, "merged_head": committed_head}
        )
        return PushResult("pushed", committed_head)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )
    monkeypatch.setattr("scripts.factory_pr_delivery_service.push_exact_commit", fake_push)

    clock_values = (
        datetime(2026, 8, 3, 12, 10, tzinfo=UTC),
        datetime(2026, 8, 3, 12, 20, tzinfo=UTC),
        datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
        datetime(2026, 8, 3, 12, 40, tzinfo=UTC),
        datetime(2026, 8, 3, 12, 50, tzinfo=UTC),
    )
    clock_calls: list[datetime] = []

    def now() -> datetime:
        if len(clock_calls) == len(clock_values):
            raise AssertionError("unexpected clock access")
        value = clock_values[len(clock_calls)]
        clock_calls.append(value)
        return value

    remote: dict[str, str] = {}
    deletes = 0
    finishes = 0

    def fake_delete(
        worktree_arg: Path, *, branch: str, expected_head: str
    ) -> DeleteBranchResult:
        nonlocal deletes
        assert worktree_arg == worktree
        assert branch == envelope.orchestration_request.branch
        assert remote == {branch: expected_head}
        deletes += 1
        del remote[branch]
        return DeleteBranchResult("deleted", None)

    def fake_finish(
        root: Path, current_envelope: DeliveryEnvelope, record: DeliveryJournalRecord
    ) -> None:
        nonlocal finishes
        assert root == main
        assert current_envelope == envelope
        assert record.lifecycle == "merged"
        assert record.cleanup is not None
        assert record.cleanup.finish_cleanup_at is None
        assert record.cleanup.remote_absent_at is None
        terminal = read_terminal_receipt(record)
        assert terminal is not None
        assert terminal.lifecycle == "merged"
        assert terminal.reason == "cleanup-pending"
        assert remote == {
            envelope.orchestration_request.branch: record.cleanup.expected_remote_head
        }
        finishes += 1

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_terminal_completion.delete_remote_branch", fake_delete
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_terminal_completion.run_strict_finish_issue", fake_finish
    )

    def deliver() -> DeliveryReceipt:
        return DeliveryService(main, github=port, now=now).deliver(request_path, apply=True)

    def raw_rows() -> tuple[str, str]:
        database = main / ".entroping/factory-pr-delivery/delivery.sqlite3"
        with sqlite3.connect(database) as connection:
            lifecycle = connection.execute(
                "SELECT * FROM delivery_lifecycle WHERE request_id = ?",
                (envelope.request.request_id,),
            ).fetchone()
            cleanup = connection.execute(
                "SELECT * FROM delivery_cleanup WHERE request_id = ?",
                (envelope.request.request_id,),
            ).fetchone()
        assert lifecycle is not None
        assert cleanup is not None
        return repr(tuple(lifecycle)), repr(tuple(cleanup))

    receipts = [deliver()]
    head = raw_git(worktree, "rev-parse", "HEAD").decode().strip()
    remote[envelope.orchestration_request.branch] = head
    receipts.extend(deliver() for _ in range(6))
    before_replay = raw_rows()
    receipts.append(deliver())
    assert raw_rows() == before_replay

    _assert_real_delivery_receipts(receipts, head, clock_values)
    _assert_real_delivery_effects(
        worktree, main, base, head, pushes, deletes, finishes, clock_calls, remote, port
    )
    record = DeliveryJournal(main).read(envelope)
    assert record is not None
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert record.cleanup.remote_absent_at is not None
    assert record.cleanup.finish_cleanup_at is not None
    assert record.cleanup.scheduler_completed_at is not None
    with readonly_connection(main) as connection:
        assignment = read_assignment(
            connection, job_id=envelope.orchestration_request.job_id
        )
        execution = read_execution_for_job(
            connection, job_id=envelope.orchestration_request.job_id
        )
    assert assignment is not None
    assert execution is not None
    assert assignment.state == "completed"
    assert execution.phase == "completed"
    assert execution.terminal_outcome == "completed"


def test_apply_stops_after_push_when_required_ci_is_not_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha, ci_status="pending")
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        _journal_aware_commit,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit",
        lambda *_args, **_kwargs: PushResult("pushed", HEAD),
    )

    receipt = DeliveryService(
        main,
        github=port,
        now=lambda: datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    ).deliver(request_path, apply=True)

    assert receipt.lifecycle == "pushed"
    assert receipt.reason == "ci-pending"
    assert not any(call.operation == "merge-pr" for call in port.calls)


def test_apply_replays_pushed_journal_without_second_commit_or_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, _body_sha = _setup(tmp_path)
    envelope = load_delivery_envelope(request_path)
    journal = DeliveryJournal(main)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=HEAD)

    def fail_commit(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("replay must not create a second commit")

    def fail_push(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("replay must not push a second time")

    monkeypatch.setattr("scripts.factory_pr_delivery_service.commit_exact_diff", fail_commit)
    monkeypatch.setattr("scripts.factory_pr_delivery_service.push_exact_commit", fail_push)
    result, pushed = DeliveryService(main, github=_port(base, "1" * 64))._apply_git(
        envelope,
        now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        journal=journal,
    )

    assert result.committed_head == HEAD
    assert pushed.state == "replay"
    assert pushed.remote_head == HEAD


def test_apply_returns_exact_same_terminal_receipt_on_duplicate_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)
    envelope = load_delivery_envelope(request_path)
    request = envelope.orchestration_request
    calls = {
        "commit": 0,
        "push": 0,
        "merge": 0,
        "authority": 0,
    }
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )

    original_merge = port.merge_pull_request

    def fake_merge(repo: str, *, pr_number: int, head_sha: str) -> MergeResult:
        calls["merge"] += 1
        return original_merge(repo, pr_number=pr_number, head_sha=head_sha)

    monkeypatch.setattr(port, "merge_pull_request", fake_merge)
    authority = SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=7,
    )
    def fake_validate_authority(
        *_args: object, **_kwargs: object
    ) -> SchedulerCompletionAuthority:
        calls["authority"] += 1
        return authority

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_terminal_completion.validate_scheduler_authority",
        fake_validate_authority,
    )

    def fake_commit_exact_diff(*_args: object, **_kwargs: object) -> CommitResult:
        calls["commit"] += 1
        return _journal_aware_commit(*_args, **_kwargs)

    def fake_push_exact_commit(*_args: object, **_kwargs: object) -> PushResult:
        calls["push"] += 1
        return PushResult("pushed", HEAD)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        fake_commit_exact_diff,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit", fake_push_exact_commit
    )

    service = DeliveryService(
        main,
        github=port,
        now=lambda: datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )
    first = service.deliver(request_path, apply=True)
    first_count = len(port.calls)
    second = service.deliver(request_path, apply=True)
    terminal_record = DeliveryJournal(main).read(envelope)
    assert terminal_record is not None
    terminal = read_terminal_receipt(terminal_record)
    assert terminal is not None
    first_raw, first_digest = encode_delivery_receipt(first)
    second_raw, second_digest = encode_delivery_receipt(second)
    assert first_raw == second_raw
    assert first_digest == second_digest
    assert terminal == first
    assert terminal.model_dump(mode="json") == first.model_dump(mode="json")
    terminal_record = DeliveryJournal(main).read(envelope)
    assert terminal_record is not None
    assert terminal_record.terminal_receipt_json == first_raw
    assert terminal_record.terminal_receipt_sha256 == first_digest
    assert terminal_record.cleanup is not None
    assert terminal_record.cleanup.phase_version == 1
    assert calls["commit"] == 1
    assert calls["push"] == 1
    assert calls["merge"] == 1
    assert calls["authority"] == 1
    assert len(port.calls) == first_count
    assert [call.operation for call in port.calls].count("create-pr") == 1
    assert [call.operation for call in port.calls].count("merge-pr") == 1


def test_apply_replay_hits_preseeded_terminal_with_authority_and_no_mutating_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.factory_pr_delivery_terminal_completion import (
        advance_terminal_completion as _real_advance_terminal_completion,
    )

    main, request_path, base, _body_sha = _setup(tmp_path)
    envelope = load_delivery_envelope(request_path)
    request = envelope.orchestration_request
    journal = DeliveryJournal(main)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=HEAD)
    _ = journal.merge_intent(
        envelope,
        pr_number=42,
        merge_head=HEAD,
        ci_digest="c" * 64,
    )
    terminal_record = journal.merged(envelope, merged_head=HEAD)
    terminal = read_terminal_receipt(terminal_record)
    assert terminal is not None
    port = _port(base, "1" * 64)

    calls = {
        "coordinator": 0,
        "authority": 0,
    }
    first_raw, first_digest = encode_delivery_receipt(terminal)
    authority = SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=7,
    )

    def fake_validate_authority(
        *_args: object, **_kwargs: object
    ) -> SchedulerCompletionAuthority:
        calls["authority"] += 1
        return authority

    def fake_advance_terminal_completion(
        root: Path,
        loaded_envelope: DeliveryEnvelope,
        *,
        now: Callable[[], datetime],
    ) -> DeliveryReceipt:
        calls["coordinator"] += 1
        assert root == main
        assert loaded_envelope == envelope
        assert callable(now)
        return _real_advance_terminal_completion(root, loaded_envelope, now=now)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_terminal_completion.validate_scheduler_authority",
        fake_validate_authority,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_replay.advance_terminal_completion",
        fake_advance_terminal_completion,
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("terminal replay should not call GitHub")

    monkeypatch.setattr(port, "observe_issue", fail_if_called)
    monkeypatch.setattr(port, "observe_pull_requests", fail_if_called)
    monkeypatch.setattr(port, "observe_ci", fail_if_called)
    monkeypatch.setattr(port, "observe_protection", fail_if_called)
    monkeypatch.setattr(port, "merge_pull_request", fail_if_called)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )

    receipt = DeliveryService(main, github=port).deliver(request_path, apply=True)
    assert calls["coordinator"] == 1
    assert calls["authority"] == 1
    assert receipt == terminal
    after_raw, after_digest = encode_delivery_receipt(receipt)
    assert after_raw == first_raw
    assert after_digest == first_digest
    assert not port.calls


def test_apply_terminal_coordinator_runtime_error_maps_to_service_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, _body_sha = _setup(tmp_path)
    envelope = load_delivery_envelope(request_path)
    journal = DeliveryJournal(main)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=HEAD)
    _ = journal.merge_intent(
        envelope,
        pr_number=42,
        merge_head=HEAD,
        ci_digest="c" * 64,
    )
    _ = journal.merged(envelope, merged_head=HEAD)

    port = _port(base, "1" * 64)

    def fake_advance_terminal_completion(*_args: object, **_kwargs: object) -> DeliveryReceipt:
        raise DeliveryGitError("authority-mismatch")

    def fail(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("terminal replay should not call GitHub")

    calls = {"coordinator": 0}

    def fake_advance_terminal_completion_with_count(
        *_args: object, **_kwargs: object
    ) -> DeliveryReceipt:
        calls["coordinator"] += 1
        return fake_advance_terminal_completion(*_args, **_kwargs)

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_replay.advance_terminal_completion",
        fake_advance_terminal_completion_with_count,
    )
    monkeypatch.setattr(port, "observe_issue", fail)
    monkeypatch.setattr(port, "observe_protection", fail)
    monkeypatch.setattr(port, "observe_pull_requests", fail)
    monkeypatch.setattr(port, "observe_ci", fail)
    monkeypatch.setattr(port, "merge_pull_request", fail)
    monkeypatch.setattr(port, "create_pull_request", fail)
    monkeypatch.setattr(port, "update_pull_request", fail)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )

    with pytest.raises(DeliveryServiceError, match="^authority-mismatch$"):
        DeliveryService(main, github=port).deliver(request_path, apply=True)
    assert calls["coordinator"] == 1
    assert not port.calls


def test_apply_merge_intent_replay_rejects_with_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    envelope = load_delivery_envelope(request_path)
    journal = DeliveryJournal(main)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=HEAD)
    _ = journal.merge_intent(envelope, pr_number=42, merge_head=HEAD, ci_digest="c" * 64)
    port = _port(base, body_sha)
    with pytest.raises(
        DeliveryServiceError,
        match="uncertain-recovery-required",
    ):
        DeliveryService(main, github=port).deliver(request_path, apply=True)
    record = DeliveryJournal(main).read(envelope)
    assert record is not None
    assert record.lifecycle == "uncertain"


def test_apply_preflight_journal_error_maps_to_service_error_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha)

    def fail_once(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight journal errors should prevent any I/O side effects")

    def _read_for_test(*_args: object, **_kwargs: object) -> None:
        raise DeliveryJournalError("journal-invalid")

    monkeypatch.setattr("scripts.factory_pr_delivery_service.DeliveryJournal.read", _read_for_test)
    monkeypatch.setattr(port, "observe_issue", fail_once)
    monkeypatch.setattr(port, "observe_protection", fail_once)
    monkeypatch.setattr(port, "observe_pull_requests", fail_once)
    monkeypatch.setattr(port, "observe_ci", fail_once)
    monkeypatch.setattr(port, "merge_pull_request", fail_once)
    monkeypatch.setattr(port, "create_pull_request", fail_once)
    monkeypatch.setattr(port, "update_pull_request", fail_once)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.validate_scheduler_authority",
        fail_once,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body",
        _no_body_failures,
    )

    with pytest.raises(DeliveryServiceError, match="^journal-invalid$") as exc_info:
        DeliveryService(main, github=port).deliver(request_path, apply=True)
    assert exc_info.value.code == "journal-invalid"
    assert not port.calls


def test_apply_merge_returns_ambiguous_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, request_path, base, body_sha = _setup(tmp_path)
    port = _port(base, body_sha, merge_state="uncertain", merged_head=None)
    calls = {"merge": 0}
    original_merge = port.merge_pull_request

    def fake_merge(repo: str, *, pr_number: int, head_sha: str) -> MergeResult:
        calls["merge"] += 1
        return original_merge(repo, pr_number=pr_number, head_sha=head_sha)

    monkeypatch.setattr(port, "merge_pull_request", fake_merge)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service_support.validate_body", _no_body_failures
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.commit_exact_diff",
        _journal_aware_commit,
    )
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_service.push_exact_commit",
        lambda *_args, **_kwargs: PushResult("pushed", HEAD),
    )

    envelope = load_delivery_envelope(request_path)
    journal = DeliveryJournal(main)
    _ = journal.prepare(envelope)
    _ = journal.commit_intent(
        envelope,
        committed_head=HEAD,
        commit_parent=base,
        commit_tree="c" * 40,
    )
    _ = journal.committed(envelope)
    _ = journal.push_intent(envelope)
    _ = journal.pushed(envelope, remote_head=HEAD)

    with pytest.raises(
        DeliveryServiceError, match="uncertain-recovery-required"
    ):
        DeliveryService(main, github=port).deliver(request_path, apply=True)
    with pytest.raises(
        DeliveryServiceError, match="uncertain-recovery-required"
    ):
        DeliveryService(main, github=port).deliver(request_path, apply=True)
    assert calls["merge"] == 1
    record = DeliveryJournal(main).read(envelope)
    assert record is not None
    assert record.lifecycle == "uncertain"


def test_delivery_receipt_rejects_incomplete_merged_projection() -> None:
    with pytest.raises(ValueError):
        DeliveryReceipt(
            request_id="delivery_" + "1" * 64,
            lifecycle="merged",
            reason="cleanup-pending",
            authoritative=True,
            accepted_local_head="a" * 40,
            created_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        )


def _codec_receipt_payload(*, lifecycle: str = "merged") -> DeliveryReceipt:
    if lifecycle == "merged":
        return DeliveryReceipt(
            request_id="delivery_" + "1" * 64,
            lifecycle="merged",
            reason="cleanup-pending",
            authoritative=True,
            accepted_local_head="a" * 40,
            committed_head="b" * 40,
            remote_head="b" * 40,
            pr_number=42,
            ci_digest="c" * 64,
            merge_head="b" * 40,
            created_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        )
    return DeliveryReceipt(
        request_id="delivery_" + "1" * 64,
        lifecycle="uncertain",
        reason="uncertain",
        authoritative=True,
        accepted_local_head="a" * 40,
        created_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )


def test_delivery_receipt_codec_round_trips_merged_and_uncertain() -> None:
    for lifecycle in ("merged", "uncertain"):
        receipt = _codec_receipt_payload(lifecycle=lifecycle)
        raw, digest = encode_delivery_receipt(receipt)
        expected_raw = json.dumps(
            receipt.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        assert raw == expected_raw
        assert digest == hashlib.sha256(raw.encode("utf-8")).hexdigest()
        restored = decode_delivery_receipt(raw, digest)
        assert restored == receipt


def test_delivery_receipt_decode_rejects_duplicate_keys() -> None:
    payload, digest = encode_delivery_receipt(_codec_receipt_payload())
    corrupted = payload[:-1] + ',"pr_number":42}'
    with pytest.raises(ValueError):
        decode_delivery_receipt(corrupted, digest)


def test_delivery_receipt_decode_rejects_non_finite_numbers() -> None:
    receipt = _codec_receipt_payload()
    payload_obj = json.loads(receipt.model_dump_json())
    payload_obj["pr_number"] = float("nan")
    payload = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="receipt encoding has non-finite number"):
        decode_delivery_receipt(payload, digest)


def test_delivery_receipt_decode_rejects_oversize_input() -> None:
    payload = _codec_receipt_payload()
    raw_payload = payload.model_dump(mode="json")
    raw_payload["padding"] = "x" * 16385
    oversized = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError, match="receipt encoding exceeds 16KiB"):
        decode_delivery_receipt(oversized, hashlib.sha256(oversized.encode()).hexdigest())


def test_delivery_receipt_decode_rejects_excessive_depth() -> None:
    deep: dict[str, object] = {"marker": "leaf"}
    for _ in range(20):
        deep = {"inner": deep}
    payload = {
        "schema_version": "entroping.factory-pr-delivery-receipt.v1",
        "request_id": "delivery_" + "1" * 64,
        "lifecycle": "merged",
        "reason": "cleanup-pending",
        "authoritative": True,
        "accepted_local_head": "a" * 40,
        "committed_head": "b" * 40,
        "remote_head": "b" * 40,
        "pr_number": 42,
        "ci_digest": "c" * 64,
        "merge_head": "b" * 40,
        "created_at": "2026-08-04T12:00:00+00:00",
        "updated_at": "2026-08-04T12:00:00+00:00",
        "deep": deep,
    }
    oversized_depth = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError, match="receipt encoding exceeds depth limit"):
        decode_delivery_receipt(
            oversized_depth, hashlib.sha256(oversized_depth.encode()).hexdigest()
        )


def test_delivery_receipt_decode_rejects_excessive_nodes() -> None:
    payload = {
        "schema_version": "entroping.factory-pr-delivery-receipt.v1",
        "request_id": "delivery_" + "1" * 64,
        "lifecycle": "merged",
        "reason": "cleanup-pending",
        "authoritative": True,
        "accepted_local_head": "a" * 40,
        "committed_head": "b" * 40,
        "remote_head": "b" * 40,
        "pr_number": 42,
        "ci_digest": "c" * 64,
        "merge_head": "b" * 40,
        "created_at": "2026-08-04T12:00:00+00:00",
        "updated_at": "2026-08-04T12:00:00+00:00",
        "overflow": list(range(600)),
    }
    oversized_nodes = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError, match="receipt encoding exceeds node limit"):
        decode_delivery_receipt(
            oversized_nodes, hashlib.sha256(oversized_nodes.encode()).hexdigest()
        )


def test_delivery_receipt_decode_rejects_coercible_wrong_types() -> None:
    payload, digest = encode_receipt_for_projection_test("merged")
    payload_obj = json.loads(payload)
    payload_obj["pr_number"] = "42"
    adjusted = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError, match="receipt projection is invalid"):
        decode_delivery_receipt(adjusted, hashlib.sha256(adjusted.encode()).hexdigest())


def encode_receipt_for_projection_test(lifecycle: str) -> tuple[str, str]:
    receipt = _codec_receipt_payload(lifecycle=lifecycle)
    raw, digest = encode_delivery_receipt(receipt)
    return raw, digest


def test_delivery_receipt_decode_rejects_digest_mismatch() -> None:
    payload, digest = encode_delivery_receipt(_codec_receipt_payload())
    bad_digest = "0" + digest[1:]
    with pytest.raises(ValueError):
        decode_delivery_receipt(payload, bad_digest)


def test_delivery_receipt_decode_rejects_unknown_fields() -> None:
    raw, digest = encode_delivery_receipt(_codec_receipt_payload())
    payload_obj = json.loads(raw)
    payload_obj["unexpected"] = "value"
    raw_with_unknown = json.dumps(
        payload_obj, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(raw_with_unknown.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError):
        decode_delivery_receipt(raw_with_unknown, digest)


def test_delivery_receipt_decode_rejects_noncanonical_json() -> None:
    raw, digest = encode_delivery_receipt(_codec_receipt_payload())
    payload_obj = json.loads(raw)
    payload_obj["pr_number"] = 42
    noncanonical = json.dumps(payload_obj)
    bad_digest = hashlib.sha256(noncanonical.encode("utf-8")).hexdigest()
    with pytest.raises(ValueError):
        decode_delivery_receipt(noncanonical, bad_digest)
