from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_pr_delivery_test_support import (  # noqa: E402
    accepted_artifacts,
    write_delivery_request,
)

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
)
from scripts.factory_pr_delivery_journal_scheduler_completed import (  # noqa: E402
    _SCHEDULER_COMPLETED_UPDATE,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope  # noqa: E402
from scripts.factory_pr_delivery_scheduler import (  # noqa: E402
    SchedulerCompletionAuthority,
)


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path)


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


def _authority(
    envelope: DeliveryEnvelope, phase_version: int = 7
) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    return SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=phase_version,
    )


def _mutate_authority(
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    case: str,
) -> SchedulerCompletionAuthority:
    if case == "owner_id":
        return SchedulerCompletionAuthority(
            owner_id="other-" + authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "owner_pid":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid + 1,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "owner_start_token":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token="task-" + authority.owner_start_token,
            epoch=authority.epoch,
            phase_version=authority.phase_version,
        )
    if case == "epoch":
        return SchedulerCompletionAuthority(
            owner_id=authority.owner_id,
            owner_pid=authority.owner_pid,
            owner_start_token=authority.owner_start_token,
            epoch=authority.epoch + 1,
            phase_version=authority.phase_version,
        )
    return SchedulerCompletionAuthority(
        owner_id=authority.owner_id,
        owner_pid=authority.owner_pid,
        owner_start_token=authority.owner_start_token,
        epoch=authority.epoch,
        phase_version=authority.phase_version + 1,
    )


def _seed_prefix(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    subject.cleanup_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2028, 1, 1, tzinfo=UTC),
    )
    subject.finish_cleaned(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 1, tzinfo=UTC),
    )
    subject.remote_absent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 2, tzinfo=UTC),
    )
    subject.scheduler_completion_intent(
        envelope,
        authority=authority,
        observed_at=datetime(2029, 1, 3, tzinfo=UTC),
    )


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


def _terminal_row(
    connection: sqlite3.Connection, request_id: str
) -> tuple[object, ...] | None:
    row: tuple[object, ...] | None = connection.execute(
        "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
        "FROM delivery_lifecycle WHERE request_id = ?",
        (request_id,),
    ).fetchone()
    return row


def test_journal_scheduler_completed_persists_phase_five_and_keeps_identity(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
        assert before_cleanup is not None

    record = subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)
        assert after_cleanup is not None

    assert before_cleanup[11] == str(datetime(2029, 1, 3, tzinfo=UTC).isoformat())
    assert after_cleanup[0] == envelope.request.request_id
    assert after_cleanup[1] == envelope.orchestration_request.branch
    assert after_cleanup[2] == merged.committed_head
    assert after_cleanup[3] == authority.owner_id
    assert after_cleanup[4] == authority.owner_pid
    assert after_cleanup[5] == authority.owner_start_token
    assert after_cleanup[6] == authority.epoch
    assert after_cleanup[7] == authority.phase_version
    assert after_cleanup[13] == 5
    assert after_cleanup[12] == before_cleanup[11]
    assert after_cleanup[11] == before_cleanup[11]
    assert after_cleanup[9] is not None
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert record.cleanup.scheduler_completed_at is not None
    assert record.cleanup.scheduler_completed_at == record.cleanup.scheduler_completion_at


def test_journal_scheduler_completed_update_uses_stored_completion_timestamp() -> None:
    assert _SCHEDULER_COMPLETED_UPDATE == (
        "UPDATE delivery_cleanup "
        "SET scheduler_completed_at_utc = scheduler_completion_at_utc, "
        "phase_version = phase_version + 1 "
        "WHERE request_id = ? "
        "AND phase_version = 4 "
        "AND scheduler_completion_at_utc IS NOT NULL "
        "AND scheduler_completed_at_utc IS NULL"
    )
    assert _SCHEDULER_COMPLETED_UPDATE.count("?") == 1


def test_journal_scheduler_completed_replay_is_byte_exact_no_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    _ = subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)

    def _should_not_persist(
        _connection: sqlite3.Connection,
        *,
        request_id: str,
    ) -> int:
        raise AssertionError("_persist_scheduler_completed called during replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_completed._persist_scheduler_completed",
        _should_not_persist,
    )

    record = subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert before_cleanup is not None
    assert isinstance(before_cleanup[12], str)
    assert record.cleanup.scheduler_completed_at == datetime.fromisoformat(before_cleanup[12])


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_journal_scheduler_completed_requires_valid_prefix(
    tmp_path: Path,
    phase: int,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    if phase >= 1:
        _ = subject.cleanup_intent(
            envelope,
            authority=authority,
            observed_at=datetime(2028, 1, 1, tzinfo=UTC),
        )
    if phase >= 2:
        _ = subject.finish_cleaned(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 1, tzinfo=UTC),
        )
    if phase >= 3:
        _ = subject.remote_absent(
            envelope,
            authority=authority,
            observed_at=datetime(2029, 1, 2, tzinfo=UTC),
        )
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "request-conflict"
    assert before == after


def test_journal_scheduler_completed_replay_with_phase_five_from_db_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _ = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    first = subject.scheduler_completed(envelope, authority=authority)
    assert first.cleanup is not None
    assert first.cleanup.phase_version == 5
    assert first.cleanup.scheduler_completed_at is not None

    def _should_not_persist(
        _connection: sqlite3.Connection,
        *,
        request_id: str,
    ) -> int:
        raise AssertionError("_persist_scheduler_completed called during replay")

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_completed._persist_scheduler_completed",
        _should_not_persist,
    )

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)
    record = subject.scheduler_completed(envelope, authority=authority)
    monkeypatch.undo()

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert before is not None
    assert before == after
    assert record.cleanup is not None
    assert record.cleanup.phase_version == 5
    assert record.cleanup.scheduler_completion_at is not None
    assert record.cleanup.scheduler_completed_at is not None
    assert (
        record.cleanup.scheduler_completion_at == record.cleanup.scheduler_completed_at
    )


@pytest.mark.parametrize(
    "case", ["owner_id", "owner_pid", "owner_start_token", "epoch", "phase_version"]
)
def test_journal_scheduler_completed_rejects_authority_tuple_mismatch(
    tmp_path: Path,
    case: str,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(
            envelope,
            authority=_mutate_authority(envelope, authority, case),
        )

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before == after


def test_journal_scheduler_completed_wrong_lifecycle_is_request_conflict(
    tmp_path: Path,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle SET lifecycle = 'uncertain', reason = 'interrupted' "
            "WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        connection.commit()
        before = _lifecycle_row(connection, envelope.request.request_id)
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = _lifecycle_row(connection, envelope.request.request_id)
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "request-conflict"
    assert before == after
    assert before_cleanup == after_cleanup


def test_journal_scheduler_completed_missing_cleanup_request_conflict(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        before_terminal = _terminal_row(connection, envelope.request.request_id)
    assert before_cleanup is None

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "request-conflict"
    assert before_cleanup is None
    assert after_cleanup is None
    assert before_lifecycle == after_lifecycle
    assert before_terminal == after_terminal
    assert merged.lifecycle == "merged"


def test_journal_scheduler_completed_rejects_malformed_phase_and_terminal_data(
    tmp_path: Path,
) -> None:
    main, envelope, subject, merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_lifecycle SET terminal_receipt_json = '{}' "
            "WHERE request_id = ?",
            (envelope.request.request_id,),
        )
        connection.commit()
        corrupted_terminal = _terminal_row(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_terminal = _terminal_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert corrupted_terminal == after_terminal

    assert merged.lifecycle == "merged"


def test_journal_scheduler_completed_cas_rolls_back_real_partial_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    seam_reached = False
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        assert before_cleanup is not None

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completed_at_utc = scheduler_completion_at_utc, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (request_id,),
        )
        state = connection.execute(
            "SELECT scheduler_completed_at_utc, phase_version "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        expected = before_cleanup[11] if before_cleanup is not None else None
        if state is None or state[0] != expected or state[1] != 5:
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 0

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_completed._persist_scheduler_completed",
        _fake_update,
    )
    import scripts.factory_pr_delivery_journal_scheduler_completed as scheduler_completed_module

    assert scheduler_completed_module._persist_scheduler_completed is _fake_update
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)

    assert seam_reached
    assert exc_info.value.code == "request-conflict"
    assert before_cleanup == after_cleanup


def test_journal_scheduler_completed_rejects_parent_mutation_on_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    assert before_cleanup is not None
    assert before_lifecycle is not None
    changed_digest = "a" * 64
    if before_lifecycle[1] == changed_digest:
        changed_digest = "b" * 64
    seam_reached = False

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
    ) -> int:
        nonlocal seam_reached
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completed_at_utc = scheduler_completion_at_utc, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (request_id,),
        )
        connection.execute(
            "UPDATE delivery_lifecycle SET request_digest = ? WHERE request_id = ?",
            (changed_digest, request_id),
        )
        state = connection.execute(
            "SELECT cleanup.scheduler_completed_at_utc, "
            "cleanup.phase_version, lifecycle.request_digest "
            "FROM delivery_cleanup AS cleanup "
            "JOIN delivery_lifecycle AS lifecycle ON "
            "lifecycle.request_id = cleanup.request_id "
            "WHERE cleanup.request_id = ?",
            (request_id,),
        ).fetchone()
        if (
            state is None
            or state[0] != before_cleanup[11]
            or state[1] != 5
            or state[2] != changed_digest
        ):
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 1

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_completed._persist_scheduler_completed",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert exc_info.value.code == "journal-invalid"
    assert seam_reached
    assert before_cleanup == after_cleanup
    assert before_lifecycle == after_lifecycle


def test_journal_scheduler_completed_rejects_identity_mutation_when_triggered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, envelope, subject, _merged = _seed_merged_record(tmp_path)
    authority = _authority(envelope)
    _seed_prefix(subject, envelope, authority)
    seam_reached = False

    with sqlite3.connect(_delivery_database(main)) as connection:
        before_cleanup = _cleanup_row(connection, envelope.request.request_id)
        before_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        before_lifecycle = _lifecycle_row(connection, envelope.request.request_id)
    assert before_trigger is not None
    assert before_cleanup is not None

    def _fake_update(
        connection: sqlite3.Connection,
        *,
        request_id: str,
    ) -> int:
        nonlocal seam_reached
        connection.execute("DROP TRIGGER trg_delivery_cleanup_immutable_identity")
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completed_at_utc = scheduler_completion_at_utc, "
            "phase_version = phase_version + 1 "
            "WHERE request_id = ?",
            (request_id,),
        )
        state = connection.execute(
            "SELECT scheduler_completed_at_utc, phase_version, remote_branch "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        assert state is not None
        if (
            state[0] != before_cleanup[11]
            or state[1] != 5
        ):
            raise AssertionError("partial write did not apply")
        connection.execute(
            "UPDATE delivery_cleanup SET remote_branch = ? WHERE request_id = ?",
            ("mutated-branch", request_id),
        )
        state = connection.execute(
            "SELECT scheduler_completed_at_utc, phase_version, remote_branch "
            "FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        assert state is not None
        if (
            state[0] != before_cleanup[11]
            or state[1] != 5
            or state[2] != "mutated-branch"
        ):
            raise AssertionError("partial write did not apply")
        seam_reached = True
        return 1

    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_scheduler_completed._persist_scheduler_completed",
        _fake_update,
    )

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.scheduler_completed(envelope, authority=authority)

    with sqlite3.connect(_delivery_database(main)) as connection:
        after_cleanup = _cleanup_row(connection, envelope.request.request_id)
        after_trigger = connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE type = 'trigger' AND name = 'trg_delivery_cleanup_immutable_identity'",
        ).fetchone()
        after_lifecycle = _lifecycle_row(connection, envelope.request.request_id)

    assert seam_reached
    assert exc_info.value.code == "journal-invalid"
    assert before_cleanup == after_cleanup
    assert before_trigger == after_trigger
    assert before_lifecycle == after_lifecycle
