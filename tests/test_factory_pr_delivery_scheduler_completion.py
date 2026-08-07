from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_pr_delivery_test_support import (  # noqa: E402
    accepted_artifacts,
    write_delivery_request,
)

from scripts.factory_orchestration_models import OrchestrationRequest  # noqa: E402
from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_cleanup_records import DeliveryCleanupRecord  # noqa: E402
from scripts.factory_pr_delivery_journal_records import DeliveryJournalRecord  # noqa: E402
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_scheduler import (  # noqa: E402
    SchedulerCompletionAuthority,
    validate_scheduler_authority,
)
from scripts.factory_pr_delivery_scheduler_completion import (  # noqa: E402
    DeliverySchedulerCompletionError,
    _complete_scheduler,
    _read_scheduler_state,
    _SchedulerSnapshot,
    complete_scheduler_completion,
)
from scripts.factory_scheduler_storage import readonly_connection, writable_connection  # noqa: E402

_BASE = datetime(2028, 1, 1, tzinfo=UTC)
_BASE_FINISH = datetime(2029, 1, 1, tzinfo=UTC)
_BASE_REMOTE = datetime(2029, 1, 2, tzinfo=UTC)


def _completion_base() -> datetime:
    return datetime(2030, 1, 1, tzinfo=UTC)


def _completion_at(offset: int) -> datetime:
    return _completion_base() + timedelta(minutes=1, seconds=offset)


def _parse_utc_timestamp(value: str | None) -> datetime:
    if value is None:
        raise AssertionError("expected UTC timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


def test_complete_scheduler_completion_symlink_root_is_fixed_invalid_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope = _subject(tmp_path)
    loop = tmp_path / "root-loop"
    loop.symlink_to(loop)
    delivery_database = _delivery_database(main)
    before_delivery_exists = delivery_database.exists()
    before_scheduler = _scheduler_rows(main, envelope)

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(loop, envelope)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert delivery_database.exists() is before_delivery_exists
    assert _scheduler_rows(main, envelope) == before_scheduler


def test_complete_scheduler_completion_missing_caller_root_is_fixed_invalid_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope = _subject(tmp_path)
    missing = tmp_path / "missing-caller-root"
    delivery_database = _delivery_database(main)
    before_delivery_exists = delivery_database.exists()
    before_scheduler = _scheduler_rows(main, envelope)

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(missing, envelope)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert not missing.exists()
    assert delivery_database.exists() is before_delivery_exists
    assert _scheduler_rows(main, envelope) == before_scheduler


def test_complete_scheduler_completion_missing_envelope_root_is_fixed_invalid_without_mutation(
    tmp_path: Path,
) -> None:
    main, envelope = _subject(tmp_path)
    missing = tmp_path / "missing-envelope-root"
    missing_envelope = envelope.model_copy(update={"main_root": missing})
    delivery_database = _delivery_database(main)
    before_delivery_exists = delivery_database.exists()
    before_scheduler = _scheduler_rows(main, envelope)

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, missing_envelope)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert not missing.exists()
    assert delivery_database.exists() is before_delivery_exists
    assert _scheduler_rows(main, envelope) == before_scheduler


def _seed_merged_record(
    tmp_path: Path,
) -> tuple[Path, DeliveryEnvelope, DeliveryJournal, DeliveryJournalRecord]:
    main, envelope = _subject(tmp_path)
    subject = DeliveryJournal(main)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    pushed = subject.pushed(envelope, remote_head="a" * 40)
    assert pushed.committed_head is not None
    _ = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head=pushed.committed_head,
        ci_digest="c" * 64,
    )
    merged = subject.merged(envelope, merged_head=pushed.committed_head)
    return main, envelope, subject, merged


def _seed_cleanup_prefix(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=_BASE,
    )
    subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=_BASE_FINISH,
    )
    subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=_BASE_REMOTE,
    )


def _seed_cleanup_phase2(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=_BASE,
    )
    subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=_BASE_FINISH,
    )


def _seed_scheduler_completion(
    main: Path,
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    observed: datetime,
) -> datetime:
    authority = validate_scheduler_authority(main, envelope)
    request = envelope.orchestration_request
    target_lease = (observed + timedelta(days=1)).astimezone(UTC)
    with writable_connection(main, initialized_at=observed.isoformat()) as connection:
        current = connection.execute(
            "SELECT lease_expires_at_utc FROM scheduler_execution_state WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
        if current is None:
            raise AssertionError("missing scheduler execution row")
        current_lease = _parse_utc_timestamp(current[0])
        if current_lease < target_lease:
            connection.execute(
                "UPDATE scheduler_execution_state SET lease_expires_at_utc = ? "
                "WHERE assignment_id = ?",
                (target_lease.isoformat(), request.assignment_id),
            )
            updated = connection.execute(
                "SELECT lease_expires_at_utc FROM scheduler_execution_state "
                "WHERE assignment_id = ?",
                (request.assignment_id,),
            ).fetchone()
            if updated is None:
                raise AssertionError("missing scheduler execution row after lease update")
            if _parse_utc_timestamp(updated[0]) != target_lease:
                raise AssertionError("lease extension not applied")
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=observed,
    )
    return observed


def test_complete_scheduler_completion_preserves_expired_worker_heartbeat(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = validate_scheduler_authority(main, envelope)
    completion_at = _completion_at(20)
    _seed_cleanup_prefix(subject, envelope, authority)
    _ = subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=completion_at,
    )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
    with readonly_connection(main) as connection:
        before_assignment = connection.execute(
            "SELECT state, completed_at_utc FROM scheduler_assignments WHERE assignment_id = ?",
            (envelope.orchestration_request.assignment_id,),
        ).fetchone()
        before_execution = connection.execute(
            "SELECT phase, phase_version, worker_heartbeat_at_utc, lease_expires_at_utc, "
            "terminal_outcome, evidence_digest FROM scheduler_execution_state "
            "WHERE assignment_id = ?",
            (envelope.orchestration_request.assignment_id,),
        ).fetchone()

    record = complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
    with readonly_connection(main) as connection:
        after_assignment = connection.execute(
            "SELECT state, completed_at_utc FROM scheduler_assignments WHERE assignment_id = ?",
            (envelope.orchestration_request.assignment_id,),
        ).fetchone()
        after_execution = connection.execute(
            "SELECT phase, phase_version, worker_heartbeat_at_utc, lease_expires_at_utc, "
            "terminal_outcome, evidence_digest FROM scheduler_execution_state "
            "WHERE assignment_id = ?",
            (envelope.orchestration_request.assignment_id,),
        ).fetchone()

    assert before_assignment is not None
    assert before_execution is not None
    assert after_assignment is not None
    assert after_execution is not None
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert after_assignment[0] == "completed"
    assert _parse_utc_timestamp(after_assignment[1]) == completion_at
    assert after_execution == (
        "completed",
        before_execution[1] + 1,
        before_execution[2],
        before_execution[3],
        "completed",
        before_execution[5],
    )
    assert _parse_utc_timestamp(before_execution[2]) < _parse_utc_timestamp(
        before_execution[3]
    ) < completion_at
    assert record.cleanup is not None
    assert record.cleanup.scheduler_completion_at == completion_at


def _cleanup_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
        "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
        "scheduler_phase_version, cleanup_intent_at_utc, remote_absent_at_utc, "
        "finish_cleanup_at_utc, scheduler_completion_at_utc, "
        "scheduler_completed_at_utc, phase_version "
        "FROM delivery_cleanup WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _terminal_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _lifecycle_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT request_id, request_digest, envelope_digest, issue_number, "
        "assignment_id, worktree_id, lifecycle, reason, accepted_local_head, "
        "committed_head, remote_head, commit_parent, commit_tree, "
        "accepted_diff_sha256, accepted_manifest_sha256, approved_path_sha256, "
        "body_sha256, phase_version, created_at_utc, updated_at_utc, "
        "merge_pr_number, merge_head, merge_ci_digest, merge_intent_at_utc, "
        "terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def _scheduler_rows(
    main: Path, envelope: DeliveryEnvelope
) -> tuple[tuple[object, ...] | None, tuple[object, ...] | None]:
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment = connection.execute(
            "SELECT state, completed_at_utc FROM scheduler_assignments "
            "WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
        execution = connection.execute(
            "SELECT phase, phase_version, terminal_outcome, evidence_digest "
            "FROM scheduler_execution_state WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
    return assignment, execution


def _raw_scheduler_rows(main: Path, envelope: DeliveryEnvelope) -> tuple[str, str]:
    request = envelope.orchestration_request
    with readonly_connection(main) as connection:
        assignment: tuple[object, ...] | None = connection.execute(
            "SELECT * FROM scheduler_assignments WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
        execution: tuple[object, ...] | None = connection.execute(
            "SELECT * FROM scheduler_execution_state WHERE assignment_id = ?",
            (request.assignment_id,),
        ).fetchone()
    if assignment is None or execution is None:
        raise AssertionError("missing scheduler rows")
    return repr(assignment), repr(execution)


def _set_cleanup_phase5(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...]:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT scheduler_completion_at_utc, phase_version "
        "FROM delivery_cleanup WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    if row is None or row[0] is None:
        raise AssertionError("missing completion timestamp")
    connection.execute(
        "UPDATE delivery_cleanup "
        "SET scheduler_completed_at_utc = ?, phase_version = 5 "
        "WHERE request_id = ?",
        (row[0], request_id),
    )
    return row


def _mutate_snapshot_for_case(
    snapshot: _SchedulerSnapshot,
    field: str,
) -> _SchedulerSnapshot:
    assignment = snapshot.assignment
    request = assignment.request
    execution = snapshot.execution
    if field == "owner_id":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={"lease_owner_id": f"other-{assignment.lease_owner_id}"},
            ),
        )
    if field == "owner_pid":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={"lease_owner_pid": assignment.lease_owner_pid + 1},
            ),
        )
    if field == "owner_start_token":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "lease_owner_start_token": f"proc_{'c' * 64}",
                },
            ),
        )
    if field == "owner_epoch":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={"lease_epoch": assignment.lease_epoch + 1},
            ),
        )
    if field == "proposal_evidence":
        return replace(
            snapshot,
            execution=execution.model_copy(update={"evidence_digest": "c" * 64}),
        )
    if field == "phase_version":
        return replace(
            snapshot,
            execution=execution.model_copy(
                update={"phase_version": execution.phase_version + 1}
            ),
        )
    if field == "request_id":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={"request_id": "r" + "a" * 63},
                    ),
                },
            ),
        )
    if field == "assignment_id":
        return replace(
            snapshot,
            assignment=assignment.model_copy(update={"assignment_id": "assign_" + "b" * 64}),
        )
    if field == "issue_number":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={"issue_number": request.issue_number + 1}
                    )
                },
            ),
        )
    if field == "job_id":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={"request": request.model_copy(update={"job_id": "other_job"})},
            ),
        )
    if field == "worktree_id":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={"worktree_id": "wt_" + "b" * 64},
                    ),
                },
            ),
        )
    authority = request.delivery_authority
    if authority is None:
        raise AssertionError("expected delivery authority in test fixtures")
    if field == "selector_digest":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={
                            "delivery_authority": authority.model_copy(
                                update={"selector_digest": "a" * 64}
                            )
                        },
                    ),
                },
            ),
        )
    if field == "selection_digest":
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={
                            "delivery_authority": authority.model_copy(
                                update={"selection_digest": "b" * 64}
                            )
                        },
                    ),
                },
            ),
        )
    if field == "lane":
        lane = (
            "docs-guardrail"
            if authority.verification_lane != "docs-guardrail"
            else "tiny-docs"
        )
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={
                            "delivery_authority": authority.model_copy(
                                update={"verification_lane": lane}
                            )
                        },
                    ),
                },
            ),
        )
    if field == "scopes/digest":
        digest = "0" * 64 if authority.allowed_scope_digest != "0" * 64 else "f" * 64
        return replace(
            snapshot,
            assignment=assignment.model_copy(
                update={
                    "request": request.model_copy(
                        update={
                            "delivery_authority": authority.model_copy(
                                update={"allowed_scope_digest": digest},
                            ),
                        },
                    ),
                },
            ),
        )
    raise AssertionError(f"unsupported mismatch case: {field}")


def _set_scheduler_exact_completion(
    main: Path,
    envelope: DeliveryEnvelope,
    *,
    completed_at: datetime,
    scheduler_phase_version: int,
) -> None:
    request = envelope.orchestration_request
    with writable_connection(main, initialized_at=completed_at.isoformat()) as connection:
        connection.execute(
            "UPDATE scheduler_assignments "
            "SET state = 'completed', completed_at_utc = ? "
            "WHERE assignment_id = ?",
            (completed_at.isoformat(), request.assignment_id),
        )
        connection.execute(
            "UPDATE scheduler_execution_state "
            "SET phase = 'completed', phase_version = ?, phase_changed_at_utc = ?, "
            "terminal_outcome = 'completed' "
            "WHERE assignment_id = ?",
            (
                scheduler_phase_version + 1,
                completed_at.isoformat(),
                request.assignment_id,
            ),
        )


def test_complete_scheduler_completion_rejects_stale_completed_phase_timestamp(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(10)
    _seed_scheduler_completion(main, subject, envelope, completion_at)
    _set_scheduler_exact_completion(
        main,
        envelope,
        completed_at=completion_at,
        scheduler_phase_version=4,
    )
    stale_phase_changed = completion_at - timedelta(minutes=1)
    with writable_connection(main, initialized_at=completion_at.isoformat()) as connection:
        connection.execute(
            "UPDATE scheduler_execution_state SET phase_changed_at_utc = ? "
            "WHERE assignment_id = ?",
            (
                stale_phase_changed.isoformat(),
                envelope.orchestration_request.assignment_id,
            ),
        )
    with readonly_connection(main) as connection:
        phase_changed: tuple[object, ...] | None = connection.execute(
            "SELECT phase_changed_at_utc FROM scheduler_execution_state "
            "WHERE assignment_id = ?",
            (envelope.orchestration_request.assignment_id,),
        ).fetchone()
    if phase_changed is None or not isinstance(phase_changed[0], str):
        raise AssertionError("missing scheduler phase timestamp")
    assert _parse_utc_timestamp(phase_changed[0]) == stale_phase_changed
    before_scheduler = _raw_scheduler_rows(main, envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "scheduler-completion-invalid"
    assert before_scheduler == _raw_scheduler_rows(main, envelope)
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle


def test_complete_scheduler_completion_first_completion_mutates_scheduler_only(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    _seed_scheduler_completion(main, subject, envelope, _completion_at(1))

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    before_scheduler = _scheduler_rows(main, envelope)
    assert before_cleanup is not None
    assert before_cleanup[13] == 4
    assert before_cleanup[12] is None

    record = complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    after_scheduler = _scheduler_rows(main, envelope)

    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_terminal == (
        merged.terminal_receipt_json,
        merged.terminal_receipt_sha256,
        merged.terminal_at.isoformat() if merged.terminal_at is not None else None,
    )

    assert before_scheduler != after_scheduler
    assert after_scheduler[0] is not None
    assert after_scheduler[1] is not None
    assert before_scheduler[1] is not None
    assert isinstance(after_scheduler[0][1], str)
    assert isinstance(before_scheduler[1][1], int)
    assert _parse_utc_timestamp(after_scheduler[0][1]) == _completion_at(1)
    assert after_scheduler[1] == (
        "completed",
        before_scheduler[1][1] + 1,
        "completed",
        envelope.orchestration_request.proposal_sha256,
    )
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 4
    assert record.cleanup.scheduler_completion_at == _completion_at(1)
    assert record.cleanup.scheduler_completed_at is None


def test_complete_scheduler_completion_replay_phase4_exact_completion_no_scheduler_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(2)
    _seed_scheduler_completion(main, subject, envelope, completion_at)
    _set_scheduler_exact_completion(
        main,
        envelope,
        completed_at=completion_at,
        scheduler_phase_version=4,
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    before_scheduler = _scheduler_rows(main, envelope)

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion unexpectedly called")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    record = complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    after_scheduler = _scheduler_rows(main, envelope)

    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_scheduler == after_scheduler
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 4
    assert record.cleanup.scheduler_completion_at == completion_at
    assert record.cleanup.scheduler_completed_at is None


def test_complete_scheduler_completion_response_loss_after_real_completion_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(3)
    _seed_scheduler_completion(main, subject, envelope, completion_at)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    before_scheduler = _scheduler_rows(main, envelope)

    original_complete = _complete_scheduler
    seam_reached = False

    def _fake_complete(
        root: Path,
        request: OrchestrationRequest,
        cleanup: DeliveryCleanupRecord,
    ) -> None:
        nonlocal seam_reached
        original_complete(root=root, request=request, cleanup=cleanup)
        seam_reached = True
        raise RuntimeError("simulated transport loss")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _fake_complete,
    )
    record = complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    after_scheduler = _scheduler_rows(main, envelope)

    assert seam_reached
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert after_scheduler[0] is not None
    assert after_scheduler[1] is not None
    assert before_scheduler[1] is not None
    assert isinstance(after_scheduler[0][1], str)
    assert isinstance(before_scheduler[1][1], int)
    assert _parse_utc_timestamp(after_scheduler[0][1]) == completion_at
    assert after_scheduler[1] == (
        "completed",
        before_scheduler[1][1] + 1,
        "completed",
        envelope.orchestration_request.proposal_sha256,
    )
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 4
    assert record.cleanup.scheduler_completion_at == completion_at
    assert record.cleanup.scheduler_completed_at is None


def test_complete_scheduler_completion_post_call_mismatch_is_uncertain_then_exact_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(4)
    _seed_scheduler_completion(main, subject, envelope, completion_at)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    before_scheduler = _scheduler_rows(main, envelope)

    original_complete = _complete_scheduler
    seam_reached = False

    def _fake_complete(
        root: Path,
        request: OrchestrationRequest,
        cleanup: DeliveryCleanupRecord,
    ) -> None:
        nonlocal seam_reached
        original_complete(root=root, request=request, cleanup=cleanup)
        with writable_connection(main, initialized_at=completion_at.isoformat()) as connection:
            row = connection.execute(
                "SELECT completed_at_utc FROM scheduler_assignments WHERE assignment_id = ?",
                (envelope.orchestration_request.assignment_id,),
            ).fetchone()
            if row is None:
                raise AssertionError("missing assignment row")
            next_stamp = (completion_at + timedelta(minutes=1)).isoformat()
            connection.execute(
                "UPDATE scheduler_assignments SET completed_at_utc = ? WHERE assignment_id = ?",
                (next_stamp, envelope.orchestration_request.assignment_id),
            )
            mutated = connection.execute(
                "SELECT completed_at_utc FROM scheduler_assignments WHERE assignment_id = ?",
                (envelope.orchestration_request.assignment_id,),
            ).fetchone()
        if mutated is None or mutated[0] != next_stamp:
            raise AssertionError("completion mismatch not applied")
        seam_reached = True

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _fake_complete,
    )
    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    after_scheduler = _scheduler_rows(main, envelope)

    assert seam_reached
    assert exc_info.value.code == "scheduler-completion-uncertain"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_scheduler != after_scheduler

    _set_scheduler_exact_completion(
        main,
        envelope,
        completed_at=completion_at,
        scheduler_phase_version=4,
    )

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion should not be retried on exact replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    exact = complete_scheduler_completion(main, envelope)

    assert exact.cleanup is not None
    assert exact.cleanup.phase_version == 4
    assert exact.cleanup.scheduler_completion_at == completion_at
    assert exact.cleanup.scheduler_completed_at is None
    with sqlite3.connect(_delivery_database(main)) as connection:
        replay_cleanup = _cleanup_row(connection, envelope.request.request_id)
        replay_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        replay_terminal = _terminal_row(connection, envelope.request.request_id)
    assert replay_cleanup == before_cleanup
    assert replay_lifecycle == after_lifecycle
    assert replay_terminal == after_terminal


def test_complete_scheduler_completion_missing_remote_absence_rejects_before_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = validate_scheduler_authority(main, envelope)
    _seed_cleanup_phase2(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion called for invalid phase")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert before_cleanup is not None
    assert before_cleanup[9] is None
    assert before_cleanup[10] is not None


def test_complete_scheduler_completion_wrong_lifecycle_rejects_no_scheduler_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(5)
    _seed_scheduler_completion(main, subject, envelope, completion_at)

    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle SET lifecycle = 'uncertain', reason = 'interrupted' "
            "WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion called despite lifecycle mismatch")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle


def test_complete_scheduler_completion_corrupted_terminal_rejects_and_preserves_rows(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    _seed_scheduler_completion(main, subject, envelope, _completion_at(6))

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = '{}' WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        corrupted_terminal = _terminal_row(connection, envelope.request.request_id)

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
    assert exc_info.value.code == "scheduler-completion-invalid"
    assert before_cleanup == after_cleanup
    assert after_terminal == corrupted_terminal


def test_complete_scheduler_completion_naive_timestamp_rejects_and_preserves_state(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(7)
    _seed_scheduler_completion(main, subject, envelope, completion_at)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        if before_cleanup is None:
            raise AssertionError("missing cleanup row")
        if before_cleanup[13] != 4:
            raise AssertionError("expected scheduler-completion phase-4")
        connection.execute("DROP TRIGGER trg_delivery_cleanup_no_rewrite_proofs")
        completion_naive = completion_at.replace(tzinfo=None).isoformat()
        connection.execute(
            "UPDATE delivery_cleanup SET scheduler_completion_at_utc = ? "
            "WHERE request_id = ?",
            (completion_naive, envelope.request.request_id),
        )
        mutated_cleanup = _cleanup_row(connection, envelope.request.request_id)

    assert mutated_cleanup is not None
    assert mutated_cleanup[11] == completion_naive
    assert mutated_cleanup == (
        before_cleanup[0],
        before_cleanup[1],
        before_cleanup[2],
        before_cleanup[3],
        before_cleanup[4],
        before_cleanup[5],
        before_cleanup[6],
        before_cleanup[7],
        before_cleanup[8],
        before_cleanup[9],
        before_cleanup[10],
        completion_naive,
        before_cleanup[12],
        before_cleanup[13],
    )

    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "scheduler-completion-invalid"
    assert mutated_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle


def test_complete_scheduler_completion_phase_five_replay_is_no_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    completion_at = _completion_at(8)
    _seed_scheduler_completion(main, subject, envelope, completion_at)
    _set_scheduler_exact_completion(
        main,
        envelope,
        completed_at=completion_at,
        scheduler_phase_version=4,
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        _set_cleanup_phase5(connection, envelope.request.request_id)
        before = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    before_scheduler = _scheduler_rows(main, envelope)

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion should not run for phase-5 replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    record = complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    after_scheduler = _scheduler_rows(main, envelope)

    assert before == after
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_scheduler == after_scheduler
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert record.cleanup.scheduler_completed_at == completion_at


@pytest.mark.parametrize(
    "case",
    [
        "owner_id",
        "owner_pid",
        "owner_start_token",
        "owner_epoch",
        "proposal_evidence",
        "request_id",
        "assignment_id",
        "issue_number",
        "job_id",
        "worktree_id",
        "selector_digest",
        "selection_digest",
        "lane",
        "scopes/digest",
        "phase_version",
    ],
)
def test_complete_scheduler_completion_binding_mismatch_is_invalid_no_scheduler_call(
    tmp_path: Path,
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    _seed_scheduler_completion(main, subject, envelope, _completion_at(9))

    baseline = _read_scheduler_state(main, envelope.orchestration_request)
    mutated = _mutate_snapshot_for_case(baseline, case)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_scheduler = _scheduler_rows(main, envelope)

    seam_reached = False

    def _fake_read_state(
        *_args: object,
        **_kwargs: object,
    ) -> _SchedulerSnapshot:
        nonlocal seam_reached
        seam_reached = True
        return mutated

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._read_scheduler_state",
        _fake_read_state,
    )

    def _forbid_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scheduler completion called despite binding mismatch")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_scheduler_completion._complete_scheduler",
        _forbid_call,
    )
    with pytest.raises(DeliverySchedulerCompletionError) as exc_info:
        complete_scheduler_completion(main, envelope)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_scheduler = _scheduler_rows(main, envelope)

    assert seam_reached
    assert exc_info.value.code == "scheduler-completion-invalid"
    assert before_cleanup == after_cleanup
    assert before_terminal == after_terminal
    assert before_lifecycle == after_lifecycle
    assert before_scheduler == after_scheduler
