from __future__ import annotations

import os
import sqlite3
import stat
import sys
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402
from scripts.factory_pr_delivery_journal import (  # noqa: E402
    DeliveryJournal,
    DeliveryJournalError,
)


def _subject(tmp_path: Path):
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    envelope = load_delivery_envelope(request_path)
    return main, envelope, DeliveryJournal(main)


def test_journal_persists_value_free_exact_lifecycle(tmp_path: Path) -> None:
    # Given: an immutable delivery envelope.
    main, envelope, subject = _subject(tmp_path)

    # When: every mutation intent and observation is persisted in order.
    prepared = subject.prepare(envelope)
    intent = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    committed = subject.committed(envelope)
    push_intent = subject.push_intent(envelope)
    pushed = subject.pushed(envelope, remote_head="a" * 40)

    # Then: meanings are monotonic, replay-stable, private, and body-free.
    assert [
        prepared.lifecycle,
        intent.lifecycle,
        committed.lifecycle,
        push_intent.lifecycle,
        pushed.lifecycle,
    ] == [
        "prepared",
        "commit-intent",
        "committed",
        "push-intent",
        "pushed",
    ]
    assert subject.prepare(envelope) == pushed
    state = main / ".entroping/factory-pr-delivery"
    database = state / "delivery.sqlite3"
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert envelope.pr_body.encode() not in database.read_bytes()


def test_journal_crash_recovery_advances_only_on_exact_evidence(tmp_path: Path) -> None:
    # Given: a persisted commit intent interrupted before its observation.
    _main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )

    # When: recovery observes the exact planned revision.
    recovered = subject.recover(
        envelope,
        local_head="a" * 40,
        remote_head=envelope.orchestration_request.base_commit,
    )

    # Then: it advances to committed without creating a second intent.
    assert recovered.lifecycle == "committed"
    assert recovered.committed_head == "a" * 40


def test_journal_nonexact_recovery_becomes_uncertain(tmp_path: Path) -> None:
    # Given: a push intent whose observed remote differs from both base and commit.
    _main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)

    # When: recovery cannot prove accepted or not-yet-applied state.
    uncertain = subject.recover(envelope, local_head="a" * 40, remote_head="c" * 40)

    # Then: ambiguity is durable and blocks replay.
    assert uncertain.lifecycle == "uncertain"
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "uncertain-recovery-required"


@pytest.mark.parametrize("abuse", ["sidecar", "trigger", "mode", "symlink"])
def test_journal_storage_abuse_fails_closed(tmp_path: Path, abuse: str) -> None:
    # Given: a valid journal followed by one out-of-band storage mutation.
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    state = main / ".entroping/factory-pr-delivery"
    database = state / "delivery.sqlite3"
    if abuse == "sidecar":
        (state / "delivery.sqlite3-wal").write_bytes(b"hostile")
        os.chmod(state / "delivery.sqlite3-wal", 0o600)
    elif abuse == "trigger":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TRIGGER attacker AFTER UPDATE ON delivery_lifecycle BEGIN SELECT 1; END"
            )
    elif abuse == "mode":
        os.chmod(database, 0o644)
    else:
        database.unlink()
        target = tmp_path / "foreign.sqlite3"
        target.write_bytes(b"foreign")
        database.symlink_to(target)

    # When/Then: no lifecycle SQL runs through the corrupted storage surface.
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "journal-invalid"
