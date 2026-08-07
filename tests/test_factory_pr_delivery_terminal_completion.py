from __future__ import annotations

import dataclasses
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if TYPE_CHECKING:
    def accepted_artifacts(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]: ...
    def write_delivery_request(path: Path, payload: dict[str, object]) -> None: ...
else:
    from factory_pr_delivery_test_support import (  # noqa: E402
        accepted_artifacts,
        write_delivery_request,
    )

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402
from scripts.factory_pr_delivery_journal_cleanup_records import (  # noqa: E402
    DeliveryCleanupRecord,
)
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_terminal_receipt,
)
from scripts.factory_pr_delivery_models import DeliveryEnvelope, DeliveryGitError  # noqa: E402
from scripts.factory_pr_delivery_receipts import (  # noqa: E402
    DeliveryReceipt,
    encode_delivery_receipt,
)
from scripts.factory_pr_delivery_scheduler import SchedulerCompletionAuthority  # noqa: E402
from scripts.factory_pr_delivery_scheduler_completion import (  # noqa: E402
    DeliverySchedulerCompletionError,
)
from scripts.factory_pr_delivery_ssh import DeleteBranchResult  # noqa: E402
from scripts.factory_pr_delivery_terminal_completion import (  # noqa: E402
    advance_terminal_completion,
)

TERMINAL_MODULE = "scripts.factory_pr_delivery_terminal_completion."
_BASE_INTENT = datetime(2028, 1, 1, tzinfo=UTC)
_BASE_FINISH = datetime(2029, 1, 1, tzinfo=UTC)
_BASE_REMOTE = datetime(2029, 1, 2, tzinfo=UTC)
_BASE_COMPLETION = datetime(2029, 1, 3, tzinfo=UTC)


SeedRecord = tuple[Path, DeliveryEnvelope, DeliveryJournal, DeliveryJournalRecord]
RawRows = tuple[str, str]


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _seed_merged(tmp_path: Path) -> SeedRecord:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    envelope = load_delivery_envelope(request_path)

    subject = DeliveryJournal(main)
    subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    subject.push_intent(envelope)
    pushed = subject.pushed(envelope, remote_head="a" * 40)
    assert pushed.committed_head is not None
    merged_head = pushed.committed_head
    subject.merge_intent(envelope, pr_number=123456, merge_head=merged_head, ci_digest="c" * 64)
    merged = subject.merged(envelope, merged_head=merged_head)
    return main, envelope, subject, merged


def _authority(
    envelope: DeliveryEnvelope, *, phase_version: int = 7
) -> SchedulerCompletionAuthority:
    request = envelope.orchestration_request
    return SchedulerCompletionAuthority(
        owner_id=request.scheduler_owner_id,
        owner_pid=request.scheduler_owner_pid,
        owner_start_token=request.scheduler_owner_start_token,
        epoch=request.scheduler_owner_epoch,
        phase_version=phase_version,
    )


def _seed_cleanup(
    subject: DeliveryJournal,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
    *,
    phase: int,
) -> None:
    if phase >= 1:
        subject.cleanup_intent(envelope, authority=authority, observed_at=_BASE_INTENT)
    if phase >= 2:
        subject.finish_cleaned(envelope, authority=authority, observed_at=_BASE_FINISH)
    if phase >= 3:
        subject.remote_absent(envelope, authority=authority, observed_at=_BASE_REMOTE)
    if phase >= 4:
        subject.scheduler_completion_intent(
            envelope, authority=authority, observed_at=_BASE_COMPLETION
        )


def _seed_phase_five_merged(tmp_path: Path) -> SeedRecord:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=4)
    phase_five = subject.scheduler_completed(envelope, authority=authority)
    return main, envelope, subject, phase_five


def _raw_rows(main: Path, request_id: str) -> RawRows:
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.row_factory = sqlite3.Row
        lifecycle = connection.execute(
            "SELECT * FROM delivery_lifecycle WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        cleanup = connection.execute(
            "SELECT * FROM delivery_cleanup WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    assert lifecycle is not None
    assert cleanup is not None
    return repr(tuple(lifecycle)), repr(tuple(cleanup))


def _read_journal(main: Path, envelope: DeliveryEnvelope) -> DeliveryJournalRecord:
    record = DeliveryJournal(main).read(envelope)
    assert record is not None
    return record


def _cleanup(main: Path, envelope: DeliveryEnvelope) -> DeliveryCleanupRecord:
    cleanup = _read_journal(main, envelope).cleanup
    assert cleanup is not None
    return cleanup


def _assert_cleanup_identity(
    cleanup: DeliveryCleanupRecord,
    envelope: DeliveryEnvelope,
    authority: SchedulerCompletionAuthority,
) -> None:
    assert cleanup is not None
    assert (
        cleanup.remote_branch,
        cleanup.scheduler_owner_id,
        cleanup.scheduler_owner_pid,
        cleanup.scheduler_owner_start_token,
        cleanup.scheduler_owner_epoch,
        cleanup.scheduler_phase_version,
    ) == (
        envelope.orchestration_request.branch,
        authority.owner_id,
        authority.owner_pid,
        authority.owner_start_token,
        authority.epoch,
        authority.phase_version,
    )


def _seed_completed_terminal(
    main: Path,
    envelope: DeliveryEnvelope,
    merged: DeliveryJournalRecord,
    *,
    at: datetime,
) -> DeliveryReceipt:
    completed = _terminal_from(merged).model_copy(
        update={"lifecycle": "completed", "reason": "completed", "updated_at": at}
    )
    raw, digest = encode_delivery_receipt(completed)
    with sqlite3.connect(_delivery_database(main)) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle "
            "SET terminal_receipt_json = ?, terminal_receipt_sha256 = ?, "
            "terminal_at_utc = ?, updated_at_utc = ? "
            "WHERE request_id = ?",
            (raw, digest, at.isoformat(), at.isoformat(), envelope.request.request_id),
        )
    return completed


def _terminal_from(record: DeliveryJournalRecord) -> DeliveryReceipt:
    terminal = read_terminal_receipt(record)
    assert terminal is not None
    return terminal


def _forbid(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("forbidden")


def _forbid_clock() -> datetime:
    raise AssertionError("forbidden")


def _patch_forbidden_terminal_adapters(
    monkeypatch: pytest.MonkeyPatch, *, keep: tuple[str, ...] = ()
) -> None:
    allowed = {TERMINAL_MODULE + name for name in keep}
    for name in (
        "validate_scheduler_authority",
        "delete_remote_branch",
        "run_strict_finish_issue",
        "complete_scheduler_completion",
    ):
        path = TERMINAL_MODULE + name
        if path not in allowed:
            monkeypatch.setattr(path, _forbid)


def test_phase0_validates_live_authority_and_persists_phase1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, _subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    calls: list[tuple[Path, str]] = []
    observed = datetime(2030, 1, 1, tzinfo=UTC)
    bad_root = main.with_name("wrong-root")
    bad_root.mkdir()

    with pytest.raises(DeliveryJournalError) as exc:
        advance_terminal_completion(bad_root, envelope, now=_forbid_clock)
    assert exc.value.code == "journal-invalid"
    assert calls == []

    def _validate(root: Path, env: DeliveryEnvelope) -> SchedulerCompletionAuthority:
        calls.append((root, env.request.request_id))
        return authority

    monkeypatch.setattr(
        TERMINAL_MODULE + "validate_scheduler_authority", _validate
    )
    _patch_forbidden_terminal_adapters(monkeypatch, keep=("validate_scheduler_authority",))

    merged_terminal = _terminal_from(merged)
    returned = advance_terminal_completion(main, envelope, now=lambda: observed)
    assert returned == merged_terminal
    assert calls == [(main, envelope.request.request_id)]
    cleanup = _cleanup(main, envelope)
    _assert_cleanup_identity(cleanup, envelope, authority)
    assert cleanup.expected_remote_head == merged.committed_head
    assert cleanup.cleanup_intent_at == observed
    assert cleanup.phase_version == 1


def test_cleanup_effect_order_is_finish_then_remote_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=1)
    finish_at = datetime(2030, 2, 1, tzinfo=UTC)
    remote_at = datetime(2030, 3, 1, tzinfo=UTC)
    effects: list[str] = []

    def _validate(_root: Path, _env: DeliveryEnvelope) -> SchedulerCompletionAuthority:
        return authority

    def _finish(
        _root: Path, _env: DeliveryEnvelope, record: DeliveryJournalRecord
    ) -> None:
        assert record.cleanup is not None
        assert record.cleanup.phase_version == 1
        assert record.cleanup.finish_cleanup_at is None
        assert record.cleanup.remote_absent_at is None
        effects.append("finish")

    def _delete(
        _worktree: Path, *, branch: str, expected_head: str
    ) -> DeleteBranchResult:
        current = _cleanup(main, envelope)
        assert current.phase_version == 2
        assert current.finish_cleanup_at == finish_at
        assert current.remote_absent_at is None
        assert branch == envelope.orchestration_request.branch
        assert expected_head == merged.committed_head
        effects.append("delete")
        return DeleteBranchResult("deleted", None)

    monkeypatch.setattr(TERMINAL_MODULE + "validate_scheduler_authority", _validate)
    monkeypatch.setattr(TERMINAL_MODULE + "run_strict_finish_issue", _finish)
    monkeypatch.setattr(TERMINAL_MODULE + "delete_remote_branch", _delete)
    _patch_forbidden_terminal_adapters(
        monkeypatch,
        keep=(
            "validate_scheduler_authority",
            "run_strict_finish_issue",
            "delete_remote_branch",
        ),
    )

    first = advance_terminal_completion(main, envelope, now=lambda: finish_at)
    assert first == _terminal_from(merged)
    phase_two = _cleanup(main, envelope)
    assert effects == ["finish"]
    assert phase_two.phase_version == 2
    assert phase_two.finish_cleanup_at == finish_at
    assert phase_two.remote_absent_at is None

    second = advance_terminal_completion(main, envelope, now=lambda: remote_at)
    assert second == _terminal_from(merged)
    phase_three = _cleanup(main, envelope)
    assert effects == ["finish", "delete"]
    assert phase_three.phase_version == 3
    assert phase_three.finish_cleanup_at == finish_at
    assert phase_three.remote_absent_at == remote_at


@pytest.mark.parametrize(
    "state", [DeleteBranchResult("deleted", None), DeleteBranchResult("absent", None)]
)
def test_phase2_deleted_and_absent_results_in_phase3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: DeleteBranchResult,
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=2)
    observed = datetime(2030, 3, 1, tzinfo=UTC)
    delete_calls: list[tuple[str, str]] = []

    def _validate(_root: Path, _env: DeliveryEnvelope) -> SchedulerCompletionAuthority:
        return authority

    def _delete(
        _worktree: Path, *, branch: str, expected_head: str
    ) -> DeleteBranchResult:
        delete_calls.append((branch, expected_head))
        return state

    monkeypatch.setattr(TERMINAL_MODULE + "validate_scheduler_authority", _validate)
    monkeypatch.setattr(TERMINAL_MODULE + "delete_remote_branch", _delete)
    _patch_forbidden_terminal_adapters(
        monkeypatch, keep=("validate_scheduler_authority", "delete_remote_branch")
    )
    merged_terminal = _terminal_from(merged)
    returned = advance_terminal_completion(main, envelope, now=lambda: observed)
    assert returned == merged_terminal

    assert delete_calls == [(envelope.orchestration_request.branch, merged.committed_head)]
    cleanup = _cleanup(main, envelope)
    _assert_cleanup_identity(cleanup, envelope, authority)
    assert cleanup.remote_absent_at == observed
    assert cleanup.finish_cleanup_at == _BASE_FINISH
    assert cleanup.phase_version == 3


@pytest.mark.parametrize("scenario", ("authority_drift", "naive_clock", "backward_clock"))
def test_phase1_guard_and_clock_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=1)
    before = _raw_rows(main, envelope.request.request_id)

    if scenario == "authority_drift":
        drifted = dataclasses.replace(
            authority, owner_id=f"{authority.owner_id}-mismatch"
        )
        monkeypatch.setattr(
            TERMINAL_MODULE + "validate_scheduler_authority",
            lambda _root, _env: drifted,
        )
        monkeypatch.setattr(
            TERMINAL_MODULE + "run_strict_finish_issue", _forbid
        )
        with pytest.raises(DeliveryGitError, match="authority-mismatch"):
            advance_terminal_completion(main, envelope, now=_forbid_clock)
        after = _raw_rows(main, envelope.request.request_id)
        assert before == after

    elif scenario == "naive_clock":
        monkeypatch.setattr(
            TERMINAL_MODULE + "validate_scheduler_authority",
            lambda _root, _env: authority,
        )
        monkeypatch.setattr(
            TERMINAL_MODULE + "run_strict_finish_issue", _forbid
        )
        with pytest.raises(DeliveryJournalError) as exc:
            advance_terminal_completion(main, envelope, now=lambda: datetime(2030, 1, 1))
        assert exc.value.code == "journal-invalid"
        after = _raw_rows(main, envelope.request.request_id)
        assert before == after

    else:
        finish_calls: dict[str, bool] = {}

        def _finish(
            root: Path, env: DeliveryEnvelope, record: DeliveryJournalRecord
        ) -> None:
            finish_calls["called"] = True
            assert root == main
            assert env == envelope
            assert record.request_id == merged.request_id
            assert record.cleanup is not None
            assert record.cleanup.phase_version == 1

        monkeypatch.setattr(
            TERMINAL_MODULE + "validate_scheduler_authority",
            lambda _root, _env: authority,
        )
        monkeypatch.setattr(
            TERMINAL_MODULE + "run_strict_finish_issue", _finish
        )
        _ = advance_terminal_completion(
            main, envelope, now=lambda: datetime(2027, 1, 1, tzinfo=UTC)
        )
        assert finish_calls["called"]
        cleanup = _cleanup(main, envelope)
        _assert_cleanup_identity(cleanup, envelope, authority)
        assert cleanup.finish_cleanup_at == _BASE_INTENT
        assert cleanup.remote_absent_at is None
        assert cleanup.phase_version == 2


def test_phase1_calls_strict_finish_and_persists_phase2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=1)
    finish_calls: list[tuple[Path, str, str]] = []
    observed = datetime(2030, 4, 1, tzinfo=UTC)

    def _validate(_root: Path, _env: DeliveryEnvelope) -> SchedulerCompletionAuthority:
        return authority

    def _finish(root: Path, env: DeliveryEnvelope, record: DeliveryJournalRecord) -> None:
        finish_calls.append((root, env.request.request_id, record.request_id))

    monkeypatch.setattr(TERMINAL_MODULE + "validate_scheduler_authority", _validate)
    monkeypatch.setattr(TERMINAL_MODULE + "run_strict_finish_issue", _finish)
    _patch_forbidden_terminal_adapters(
        monkeypatch, keep=("validate_scheduler_authority", "run_strict_finish_issue")
    )

    merged_terminal = _terminal_from(merged)
    returned = advance_terminal_completion(main, envelope, now=lambda: observed)
    assert returned == merged_terminal
    assert len(finish_calls) == 1
    assert finish_calls[0] == (main, envelope.request.request_id, envelope.request.request_id)
    cleanup = _cleanup(main, envelope)
    _assert_cleanup_identity(cleanup, envelope, authority)
    assert cleanup.finish_cleanup_at == observed
    assert cleanup.remote_absent_at is None
    assert cleanup.phase_version == 2


def test_phase3_persists_phase4_with_clamped_previous_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, _merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=3)
    calls: list[tuple[datetime, SchedulerCompletionAuthority]] = []
    original = DeliveryJournal.scheduler_completion_intent

    def _validate(_root: Path, _env: DeliveryEnvelope) -> SchedulerCompletionAuthority:
        return authority

    def _scheduler_completion_intent(
        self: DeliveryJournal,
        env: DeliveryEnvelope,
        *,
        authority: SchedulerCompletionAuthority,
        observed_at: datetime,
    ) -> DeliveryJournalRecord:
        calls.append((observed_at, authority))
        return original(
            self, env, authority=authority, observed_at=observed_at
        )

    monkeypatch.setattr(TERMINAL_MODULE + "validate_scheduler_authority", _validate)
    monkeypatch.setattr(
        DeliveryJournal, "scheduler_completion_intent", _scheduler_completion_intent
    )
    _patch_forbidden_terminal_adapters(
        monkeypatch, keep=("validate_scheduler_authority",)
    )

    _ = advance_terminal_completion(main, envelope, now=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    assert calls == [(_BASE_REMOTE, authority)]
    cleanup = _cleanup(main, envelope)
    _assert_cleanup_identity(cleanup, envelope, authority)
    assert cleanup.scheduler_completion_at == _BASE_REMOTE
    assert cleanup.phase_version == 4


@pytest.mark.parametrize("uncertain", (False, True))
def test_phase4_completion_success_and_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uncertain: bool
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=4)
    complete_calls: list[bool] = []

    def _complete(_root: Path, _env: DeliveryEnvelope) -> None:
        assert _root == main
        assert _env == envelope
        complete_calls.append(True)
        if uncertain:
            raise DeliverySchedulerCompletionError("scheduler-completion-uncertain")

    monkeypatch.setattr(TERMINAL_MODULE + "complete_scheduler_completion", _complete)
    _patch_forbidden_terminal_adapters(
        monkeypatch, keep=("complete_scheduler_completion",)
    )
    before = _raw_rows(main, envelope.request.request_id)

    if uncertain:
        with pytest.raises(DeliverySchedulerCompletionError) as exc:
            advance_terminal_completion(main, envelope, now=_forbid_clock)
        assert exc.value.code == "scheduler-completion-uncertain"
        after = _raw_rows(main, envelope.request.request_id)
        assert after == before
    else:
        merged_terminal = _terminal_from(merged)
        returned = advance_terminal_completion(main, envelope, now=_forbid_clock)
        assert returned.lifecycle == "merged"
        assert returned.reason == "cleanup-pending"
        assert (
            returned.request_id,
            returned.authoritative,
            returned.committed_head,
            returned.merge_head,
        ) == (
            merged_terminal.request_id,
            merged_terminal.authoritative,
            merged_terminal.committed_head,
            merged_terminal.merge_head,
        )

        cleanup = _cleanup(main, envelope)
        _assert_cleanup_identity(cleanup, envelope, authority)
        assert cleanup.phase_version == 5

    assert complete_calls == [True]


def test_phase5_first_write_preserves_terminal_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, phase_five = _seed_phase_five_merged(tmp_path)
    before = _read_journal(main, envelope)
    assert before.cleanup is not None
    before_cleanup = before.cleanup
    before_cleanup_raw = _raw_rows(main, envelope.request.request_id)[1]
    merged_terminal = _terminal_from(phase_five)
    _patch_forbidden_terminal_adapters(monkeypatch)
    returned = advance_terminal_completion(main, envelope, now=_forbid_clock)

    assert returned.lifecycle == "completed"
    assert returned.reason == "completed"
    assert returned.request_id == merged_terminal.request_id
    assert (
        returned.model_dump(exclude={"lifecycle", "reason", "updated_at"})
        == merged_terminal.model_dump(exclude={"lifecycle", "reason", "updated_at"})
    )
    assert returned.updated_at == before_cleanup.scheduler_completed_at

    after = _read_journal(main, envelope)
    assert after.cleanup == before_cleanup
    assert after.phase_version == before.phase_version + 1
    with sqlite3.connect(_delivery_database(main)) as connection:
        terminal = connection.execute(
            "SELECT terminal_receipt_json, terminal_receipt_sha256, terminal_at_utc "
            "FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()
    assert terminal is not None
    terminal_raw, terminal_sha = encode_delivery_receipt(returned)
    assert terminal == (terminal_raw, terminal_sha, returned.updated_at.isoformat())

    after_cleanup_raw = _raw_rows(main, envelope.request.request_id)[1]
    assert after_cleanup_raw == before_cleanup_raw


def test_phase5_replay_is_byte_exact_no_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, _phase_five = _seed_phase_five_merged(tmp_path)
    completed = subject.completed(envelope)
    completed_terminal = _terminal_from(completed)
    before = _raw_rows(main, envelope.request.request_id)

    def _forbid_completed(
        _self: DeliveryJournal,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        raise AssertionError("completed should not be called on phase5 replay")

    monkeypatch.setattr(DeliveryJournal, "completed", _forbid_completed)
    _patch_forbidden_terminal_adapters(monkeypatch)

    returned = advance_terminal_completion(main, envelope, now=_forbid_clock)
    assert returned == completed_terminal
    after = _raw_rows(main, envelope.request.request_id)
    assert before == after


def test_completed_terminal_with_cleanup_phase4_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, envelope, subject, merged = _seed_merged(tmp_path)
    authority = _authority(envelope)
    _seed_cleanup(subject, envelope, authority, phase=4)
    _ = _seed_completed_terminal(main, envelope, merged, at=_BASE_COMPLETION)
    before = _raw_rows(main, envelope.request.request_id)
    _patch_forbidden_terminal_adapters(monkeypatch)

    with pytest.raises(DeliveryJournalError) as exc:
        advance_terminal_completion(main, envelope, now=_forbid_clock)
    assert exc.value.code == "journal-invalid"
    after = _raw_rows(main, envelope.request.request_id)
    assert before == after
