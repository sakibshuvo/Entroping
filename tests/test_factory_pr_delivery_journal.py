from __future__ import annotations

import dataclasses
import os
import sqlite3
import stat
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_pr_delivery_io import load_delivery_envelope  # noqa: E402, I001
from scripts.factory_pr_delivery_journal import DeliveryJournal  # noqa: E402, I001
from scripts.factory_pr_delivery_journal_cleanup_schema import (  # noqa: E402, I001
    CLEANUP_TRIGGER_IMMUTABLE_IDENTITY,
    CLEANUP_TRIGGER_NO_DELETE,
    CLEANUP_TRIGGER_NO_REWRITE_PROOFS,
)
from scripts.factory_pr_delivery_journal_records import (  # noqa: E402, I001
    DeliveryJournalError,
    read_record,
    read_terminal_receipt,
    validate_record,
)
from scripts.factory_pr_delivery_journal_storage import (  # noqa: E402, I001
    CLEANUP_DDL,
    LIFECYCLE_DDL_V1,
    LIFECYCLE_DDL_V2,
    LIFECYCLE_DDL,
    METADATA_DDL_V1,
    METADATA_DDL_V2,
    METADATA_DDL_V3,
    journal_connection,
)
from scripts.factory_pr_delivery_models import (  # noqa: E402, I001
    DeliveryEnvelope,
    approved_path_digest,
)
from scripts.factory_pr_delivery_receipts import (  # noqa: E402, I001
    DeliveryReceipt,
    encode_delivery_receipt,
    decode_delivery_receipt,
)


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope, DeliveryJournal]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    envelope = load_delivery_envelope(request_path)
    return main, envelope, DeliveryJournal(main)


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _journal_schema_objects(main: Path) -> tuple[tuple[str, str, str, str], ...]:
    with sqlite3.connect(_delivery_database(main)) as connection:
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    return tuple((row[0], row[1], row[2], _canonical_schema(row[3])) for row in rows)


def _canonical_schema(sql: str | None) -> str:
    if sql is None:
        return ""
    normalized = (
        sql.replace('"delivery_lifecycle"', "delivery_lifecycle")
        .replace('"delivery_metadata"', "delivery_metadata")
        .replace('"delivery_cleanup"', "delivery_cleanup")
    )
    return " ".join(normalized.split()).rstrip().rstrip(";")


def _journal_v3_objects() -> tuple[tuple[str, str, str, str], ...]:
    return (
        (
            "table",
            "delivery_cleanup",
            "delivery_cleanup",
            _canonical_schema(CLEANUP_DDL),
        ),
        (
            "table",
            "delivery_lifecycle",
            "delivery_lifecycle",
            _canonical_schema(LIFECYCLE_DDL),
        ),
        (
            "table",
            "delivery_metadata",
            "delivery_metadata",
            _canonical_schema(METADATA_DDL_V3),
        ),
        (
            "trigger",
            "trg_delivery_cleanup_immutable_identity",
            "delivery_cleanup",
            _canonical_schema(CLEANUP_TRIGGER_IMMUTABLE_IDENTITY),
        ),
        (
            "trigger",
            "trg_delivery_cleanup_no_delete",
            "delivery_cleanup",
            _canonical_schema(CLEANUP_TRIGGER_NO_DELETE),
        ),
        (
            "trigger",
            "trg_delivery_cleanup_no_rewrite_proofs",
            "delivery_cleanup",
            _canonical_schema(CLEANUP_TRIGGER_NO_REWRITE_PROOFS),
        )
    )


def _terminal_receipt_payload(
    *,
    request_id: str,
    lifecycle: Literal["merged", "completed"],
    reason: Literal["cleanup-pending", "completed"],
    accepted_local_head: str,
    committed_head: str,
    remote_head: str,
    pr_number: int,
    ci_digest: str,
    merge_head: str,
    timestamp: datetime,
) -> tuple[str, str, DeliveryReceipt]:
    receipt = DeliveryReceipt(
        request_id=request_id,
        lifecycle=lifecycle,
        reason=reason,
        authoritative=True,
        accepted_local_head=accepted_local_head,
        committed_head=committed_head,
        remote_head=remote_head,
        pr_number=pr_number,
        ci_digest=ci_digest,
        merge_head=merge_head,
        created_at=timestamp,
        updated_at=timestamp,
    )
    raw, digest = encode_delivery_receipt(receipt)
    return raw, digest, receipt


def test_journal_storage_creates_schema_v3_on_first_open(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        assert connection.execute(
            "SELECT schema_version FROM delivery_metadata WHERE id = 1"
        ).fetchone() == (3,)
    assert _journal_schema_objects(main) == _journal_v3_objects()


def test_journal_migrates_exact_v1_schema_and_preserves_pushed_row(tmp_path: Path) -> None:
    # Given: a private journal with a valid exact v1 schema and pushed row.
    main, envelope, _ = _subject(tmp_path)
    database = _delivery_database(main)
    state = main / ".entroping" / "factory-pr-delivery"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        os.chmod(state, 0o700)
        connection.execute(METADATA_DDL_V1)
        connection.execute(
            "INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 1)"
        )
        connection.execute(LIFECYCLE_DDL_V1)
        legacy_row = (
            envelope.request.request_id,
            envelope.request.request_digest,
            envelope.envelope_digest,
            envelope.orchestration_request.issue_number,
            envelope.orchestration_request.assignment_id,
            envelope.orchestration_request.worktree_id,
            "pushed",
            "pushed",
            envelope.orchestration_request.base_commit,
            "a" * 40,
            "a" * 40,
            envelope.orchestration_request.base_commit,
            "b" * 40,
            envelope.orchestration_receipt.diff_sha256,
            envelope.orchestration_receipt.result_manifest_sha256,
            approved_path_digest(envelope.orchestration_receipt.approved_paths),
            envelope.request.pr_body_sha256,
            4,
            datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        )
        connection.execute(
            "INSERT INTO delivery_lifecycle("
            "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
            "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,commit_tree,"
            "accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,body_sha256,phase_version,"
            "created_at_utc,updated_at_utc"
            ") VALUES ("
            "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            legacy_row,
        )
        connection.commit()
    os.chmod(database, 0o600)
    with journal_connection(main):
        pass

    # Then: schema migration updates to v3, preserving the pushed row.
    assert _journal_schema_objects(main) == _journal_v3_objects()
    with sqlite3.connect(database) as connection:
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert (
        record.merge_pr_number is None
        and record.merge_head is None
        and record.merge_ci_digest is None
        and record.merge_intent_at is None
        and record.terminal_receipt_json is None
        and record.terminal_receipt_sha256 is None
        and record.terminal_at is None
    )
    with sqlite3.connect(database) as connection:
        cleanup_count = connection.execute(
            "SELECT COUNT(*) FROM delivery_cleanup"
        ).fetchone()
    assert cleanup_count == (0,)
    validate_record(envelope, record)


def test_journal_storage_rejects_drifted_v1_schema_without_mutation(tmp_path: Path) -> None:
    # Given: a private journal whose v1 schema is exact-drifted and non-migratable.
    main, envelope, _ = _subject(tmp_path)
    database = _delivery_database(main)
    state = main / ".entroping" / "factory-pr-delivery"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        os.chmod(state, 0o700)
        connection.execute("CREATE TABLE delivery_metadata(id INTEGER PRIMARY KEY, "
                           "schema_version INTEGER NOT NULL)")
        connection.execute("INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 1)")
        connection.execute(
            "CREATE TABLE delivery_lifecycle("
            "request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
            "envelope_digest TEXT NOT NULL, "
            "issue_number INTEGER NOT NULL, assignment_id TEXT NOT NULL, "
            "worktree_id TEXT NOT NULL, "
            "lifecycle TEXT NOT NULL, reason TEXT NOT NULL, "
            "accepted_local_head TEXT NOT NULL, committed_head TEXT, remote_head TEXT, "
            "commit_parent TEXT, commit_tree TEXT, accepted_diff_sha256 TEXT NOT NULL, "
            "accepted_manifest_sha256 TEXT NOT NULL, approved_path_sha256 TEXT NOT NULL, "
            "body_sha256 TEXT NOT NULL, phase_version INTEGER NOT NULL, "
            "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, extra INTEGER) STRICT"
        )
        connection.commit()
    os.chmod(database, 0o600)
    original_schema = _journal_schema_objects(main)
    with pytest.raises(DeliveryJournalError) as exc_info:
        _ = DeliveryJournal(main).recover(
            envelope,
            local_head=envelope.orchestration_request.base_commit,
            remote_head=envelope.orchestration_request.base_commit,
        )
    assert exc_info.value.code == "journal-invalid"
    assert _journal_schema_objects(main) == original_schema


def test_journal_storage_rejects_drifted_v2_schema_without_mutation(tmp_path: Path) -> None:
    # Given: an exact v2 schema with a drifted extra column.
    main, envelope, _ = _subject(tmp_path)
    database = _delivery_database(main)
    state = main / ".entroping" / "factory-pr-delivery"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        os.chmod(state, 0o700)
        connection.execute(METADATA_DDL_V2)
        connection.execute("INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 2)")
        connection.execute(
            "CREATE TABLE delivery_lifecycle("
            "request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,"
            " envelope_digest TEXT NOT NULL,"
            "issue_number INTEGER NOT NULL, assignment_id TEXT NOT NULL, worktree_id TEXT NOT NULL,"
            "lifecycle TEXT NOT NULL, reason TEXT NOT NULL, accepted_local_head TEXT NOT NULL,"
            "committed_head TEXT, remote_head TEXT, commit_parent TEXT, commit_tree TEXT,"
            "accepted_diff_sha256 TEXT NOT NULL, accepted_manifest_sha256 TEXT NOT NULL,"
            "approved_path_sha256 TEXT NOT NULL, body_sha256 TEXT NOT NULL,"
            " phase_version INTEGER NOT NULL,"
            "created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,"
            "merge_pr_number INTEGER, merge_head TEXT, merge_ci_digest TEXT,"
            "merge_intent_at_utc TEXT, terminal_receipt_json TEXT,"
            "terminal_receipt_sha256 TEXT, terminal_at_utc TEXT, extra INTEGER) STRICT"
        )
        connection.commit()
    os.chmod(database, 0o600)
    original_schema = _journal_schema_objects(main)

    with pytest.raises(DeliveryJournalError) as exc_info:
        _ = DeliveryJournal(main).prepare(envelope)
    assert exc_info.value.code == "journal-invalid"
    assert _journal_schema_objects(main) == original_schema


def test_journal_storage_rejects_drifted_v3_schema_without_mutation(tmp_path: Path) -> None:
    # Given: a valid v3 schema with extra trigger objects that break canonicalization.
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER bogus_cleanup_trigger AFTER UPDATE ON delivery_cleanup "
            "BEGIN SELECT 1; END"
        )
    original_schema = _journal_schema_objects(main)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "journal-invalid"
    assert _journal_schema_objects(main) == original_schema


def test_journal_storage_rejects_weakened_cleanup_trigger_body(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER trg_delivery_cleanup_no_delete")
        connection.execute(
            "CREATE TRIGGER trg_delivery_cleanup_no_delete AFTER DELETE ON delivery_cleanup "
            "BEGIN SELECT 1; END"
        )
        weakened_schema = _journal_schema_objects(main)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "journal-invalid"
    assert _journal_schema_objects(main) == weakened_schema


def test_journal_storage_rejects_v1_to_v3_failure_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an exact v1 journal and an injected v3 stage failure.
    main, envelope, _ = _subject(tmp_path)
    database = _delivery_database(main)
    state = main / ".entroping" / "factory-pr-delivery"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    lifecycle_columns = (
        "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
        "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,"
        "commit_tree,accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,"
        "body_sha256,phase_version,created_at_utc,updated_at_utc"
    )
    lifecycle_insert = (
        "INSERT INTO delivery_lifecycle("
        "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
        "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,commit_tree,"
        "accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,body_sha256,phase_version,"
        "created_at_utc,updated_at_utc"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    lifecycle_row = (
        envelope.request.request_id,
        envelope.request.request_digest,
        envelope.envelope_digest,
        envelope.orchestration_request.issue_number,
        envelope.orchestration_request.assignment_id,
        envelope.orchestration_request.worktree_id,
        "pushed",
        "pushed",
        envelope.orchestration_request.base_commit,
        "a" * 40,
        "a" * 40,
        envelope.orchestration_request.base_commit,
        "b" * 40,
        envelope.orchestration_receipt.diff_sha256,
        envelope.orchestration_receipt.result_manifest_sha256,
        approved_path_digest(envelope.orchestration_receipt.approved_paths),
        envelope.request.pr_body_sha256,
        4,
        datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )
    select_row = f"SELECT {lifecycle_columns} FROM delivery_lifecycle WHERE request_id = ?"

    with sqlite3.connect(database) as connection:
        os.chmod(state, 0o700)
        connection.execute(METADATA_DDL_V1)
        connection.execute(
            "INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 1)"
        )
        connection.execute(LIFECYCLE_DDL_V1)
        connection.execute(lifecycle_insert, lifecycle_row)
        connection.commit()
        pre_snapshot = connection.execute(select_row, (envelope.request.request_id,)).fetchone()
    os.chmod(database, 0o600)
    pre_schema = _journal_schema_objects(main)
    monkeypatch.setattr(
        "scripts.factory_pr_delivery_journal_migration.CLEANUP_DDL",
        "CREATE TABLE delivery_cleanup(request_id TEXT PRIMARY KEY",
    )
    with pytest.raises(DeliveryJournalError) as exc_info, journal_connection(main):
        pass
    assert exc_info.value.code == "journal-invalid"
    with sqlite3.connect(database) as connection:
        post_snapshot = connection.execute(select_row, (envelope.request.request_id,)).fetchone()
    assert post_snapshot == pre_snapshot
    assert _journal_schema_objects(main) == pre_schema


def test_journal_storage_rejects_v3_orphan_cleanup_rows(tmp_path: Path) -> None:
    # Given: a valid v3 schema with an orphaned cleanup row.
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO delivery_cleanup("
            "request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
            "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
            "scheduler_phase_version, cleanup_intent_at_utc, phase_version) "
            "VALUES ('missing-request', 'issue-9999', '0000000000000000000000000000000000000000', "
            "'owner', 42, 'token', 1, 7, '2000-01-01T00:00:00+00:00', 1)"
        )
        connection.commit()

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "journal-invalid"


def test_journal_storage_migrates_exact_v2_schema_and_preserves_terminal_projection(
    tmp_path: Path,
) -> None:
    # Given: a private journal with a valid exact v2 schema and merged terminal projection.
    main, envelope, _ = _subject(tmp_path)
    database = _delivery_database(main)
    state = main / ".entroping" / "factory-pr-delivery"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    terminal_raw, terminal_digest, _ = _terminal_receipt_payload(
        request_id=envelope.request.request_id,
        lifecycle="merged",
        reason="cleanup-pending",
        accepted_local_head=envelope.orchestration_request.base_commit,
        committed_head="a" * 40,
        remote_head="a" * 40,
        pr_number=987654,
        ci_digest="d" * 64,
        merge_head="a" * 40,
        timestamp=created_at,
    )
    with sqlite3.connect(database) as connection:
        os.chmod(state, 0o700)
        connection.execute(METADATA_DDL_V2)
        connection.execute("INSERT INTO delivery_metadata(id, schema_version) VALUES (1, 2)")
        connection.execute(LIFECYCLE_DDL_V2)
        connection.execute(
            "INSERT INTO delivery_lifecycle("
            "request_id,request_digest,envelope_digest,issue_number,assignment_id,worktree_id,"
            "lifecycle,reason,accepted_local_head,committed_head,remote_head,commit_parent,commit_tree,"
            "accepted_diff_sha256,accepted_manifest_sha256,approved_path_sha256,body_sha256,phase_version,"
            "created_at_utc,updated_at_utc,merge_pr_number,merge_head,merge_ci_digest,merge_intent_at_utc,"
            "terminal_receipt_json,terminal_receipt_sha256,terminal_at_utc"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                envelope.request.request_id,
                envelope.request.request_digest,
                envelope.envelope_digest,
                envelope.orchestration_request.issue_number,
                envelope.orchestration_request.assignment_id,
                envelope.orchestration_request.worktree_id,
                "merged",
                "cleanup-pending",
                envelope.orchestration_request.base_commit,
                "a" * 40,
                "a" * 40,
                envelope.orchestration_request.base_commit,
                "b" * 40,
                envelope.orchestration_receipt.diff_sha256,
                envelope.orchestration_receipt.result_manifest_sha256,
                approved_path_digest(envelope.orchestration_receipt.approved_paths),
                envelope.request.pr_body_sha256,
                9,
                created_at.isoformat(),
                created_at.isoformat(),
                987654,
                "a" * 40,
                "d" * 64,
                created_at.isoformat(),
                terminal_raw,
                terminal_digest,
                created_at.isoformat(),
            ),
        )
        connection.commit()
    os.chmod(database, 0o600)
    with journal_connection(main):
        pass

    # Then: schema migration updates to v3 and terminal projection bytes are preserved.
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT terminal_receipt_json, terminal_receipt_sha256, merge_pr_number, "
            "phase_version FROM delivery_lifecycle WHERE request_id = ?",
            (envelope.request.request_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == terminal_raw
    assert row[1] == terminal_digest
    assert row[2] == 987654
    with sqlite3.connect(database) as connection:
        cleanup_count = connection.execute(
            "SELECT COUNT(*) FROM delivery_cleanup"
        ).fetchone()
    assert cleanup_count == (0,)
    assert _journal_schema_objects(main) == _journal_v3_objects()

def test_journal_storage_reopen_v2_is_idempotent(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    schema_before = _journal_schema_objects(main)
    reopened = DeliveryJournal(main)
    recovered = reopened.prepare(envelope)
    schema_after = _journal_schema_objects(main)

    assert recovered.lifecycle == "prepared"
    assert schema_before == schema_after


def test_journal_records_reads_pushed_v2_projection_with_null_merge_and_terminal_fields(
    tmp_path: Path,
) -> None:
    # Given: a full pushed lifecycle row in the accepted v2 schema.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None

    # Then: the nullable v2 merge/terminal projections remain None.
    with sqlite3.connect(database) as connection:
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert record == pushed
    assert (
        record.merge_pr_number
        is None
        and record.merge_head is None
        and record.merge_ci_digest is None
        and record.merge_intent_at is None
        and record.terminal_receipt_json is None
        and record.terminal_receipt_sha256 is None
        and record.terminal_at is None
    )
    validate_record(envelope, record)


def test_journal_records_reads_merge_intent_projection_with_full_merge_group(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with all required merge fields set.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merge-intent', reason='merge-intent',"
            " merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?"
            " WHERE request_id = ?",
            (
                123456,
                pushed.committed_head,
                "a" * 64,
                pushed.updated_at.isoformat(),
                envelope.request.request_id,
            ),
        )
        connection.commit()
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert record.lifecycle == "merge-intent"
    assert record.reason == "merge-intent"
    assert record.merge_pr_number == 123456
    assert record.merge_head == pushed.committed_head
    assert record.merge_ci_digest == "a" * 64
    assert record.merge_intent_at is not None
    validate_record(envelope, record)


def test_journal_records_persists_merge_intent_projection_atomically(tmp_path: Path) -> None:
    # Given: a pushed lifecycle row without merge metadata.
    main, envelope, subject = _subject(tmp_path)
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
    prior_updated = datetime(
        2030,
        1,
        1,
        12,
        34,
        56,
        tzinfo=timezone(timedelta(hours=3, minutes=30)),
    )

    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle SET updated_at_utc = ? WHERE request_id = ?",
            (prior_updated.isoformat(), envelope.request.request_id),
        )
        connection.commit()
        with_timezone = read_record(connection, envelope.request.request_id)
    assert with_timezone is not None
    pushed = with_timezone
    assert pushed.remote_head is not None

    # When: merge-intent persists with validated PR/merge inputs.
    merged = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head=pushed.remote_head,
        ci_digest="d" * 64,
    )

    # Then: same phase is preserved as +1 and merge metadata plus intent timestamp are durable.
    assert merged.lifecycle == "merge-intent"
    assert merged.reason == "merge-intent"
    assert merged.merge_pr_number == 123456
    assert merged.merge_head == pushed.committed_head
    assert merged.merge_ci_digest == "d" * 64
    assert merged.merge_intent_at == merged.updated_at
    expected_timestamp = pushed.updated_at.astimezone(UTC)
    assert merged.updated_at == expected_timestamp
    assert merged.merge_intent_at == expected_timestamp
    assert merged.updated_at.tzinfo is UTC
    assert merged.updated_at.utcoffset() == timedelta(0)
    assert merged.merge_intent_at.tzinfo is UTC
    assert merged.merge_intent_at.utcoffset() == timedelta(0)
    assert merged.updated_at >= pushed.updated_at
    assert merged.phase_version == pushed.phase_version + 1


def test_journal_records_rejects_duplicate_merge_intent_call_without_change(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row already advanced into merge-intent.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None
    _ = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head=pushed.remote_head,
        ci_digest="d" * 64,
    )

    with sqlite3.connect(database) as connection:
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.merge_intent(
            envelope,
            pr_number=123456,
            merge_head=pushed.remote_head,
            ci_digest="d" * 64,
        )
    assert exc_info.value.code == "request-conflict"

    with sqlite3.connect(database) as connection:
        repeat = read_record(connection, envelope.request.request_id)
    assert repeat == record


@pytest.mark.parametrize(
    "case",
    [
        "pr_number_type",
        "pr_number_zero",
        "pr_number_too_large",
        "merge_head_shape",
        "ci_digest_shape",
        "merge_head_mismatch",
    ],
)
def test_journal_records_merge_intent_rejects_invalid_inputs_and_leaves_row_unchanged(
    tmp_path: Path, case: str
) -> None:
    # Given: a pushed lifecycle row with valid merge intent candidates.
    main, envelope, subject = _subject(tmp_path)
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
    with sqlite3.connect(_delivery_database(main)) as connection:
        before = read_record(connection, envelope.request.request_id)
    assert before is not None
    values: dict[str, dict[str, object]] = {
        "pr_number_type": {"pr_number": True},
        "pr_number_zero": {"pr_number": 0},
        "pr_number_too_large": {"pr_number": 2_147_483_648},
        "merge_head_shape": {"merge_head": "A" * 40},
        "ci_digest_shape": {"ci_digest": "g" * 64},
        "merge_head_mismatch": {"merge_head": "b" * 40},
    }
    kwargs = values[case]
    pr_number = kwargs.get("pr_number", 123456)
    merge_head = kwargs.get("merge_head", pushed.remote_head)
    ci_digest = kwargs.get("ci_digest", "e" * 64)
    assert isinstance(pr_number, int)
    assert isinstance(merge_head, str)
    assert isinstance(ci_digest, str)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.merge_intent(
            envelope,
            pr_number=pr_number,
            merge_head=merge_head,
            ci_digest=ci_digest,
        )
    assert exc_info.value.code == "journal-invalid"

    with sqlite3.connect(_delivery_database(main)) as connection:
        after = read_record(connection, envelope.request.request_id)
    assert after == before


@pytest.mark.parametrize(
    "start",
    ["prepared", "commit-intent", "committed", "push-intent", "merge-intent"],
)
def test_journal_records_rejects_merge_intent_wrong_lifecycle(tmp_path: Path, start: str) -> None:
    # Given: a lifecycle that is not pushed at merge-intent entry.
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    if start == "commit-intent":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
    elif start == "committed":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
        _ = subject.committed(envelope)
    elif start == "push-intent":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
        _ = subject.committed(envelope)
        _ = subject.push_intent(envelope)
    elif start == "merge-intent":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
        _ = subject.committed(envelope)
        _ = subject.push_intent(envelope)
        _ = subject.pushed(envelope, remote_head="a" * 40)
        _ = subject.merge_intent(
            envelope,
            pr_number=123456,
            merge_head="a" * 40,
            ci_digest="e" * 64,
        )
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        before = read_record(connection, envelope.request.request_id)
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.merge_intent(
            envelope,
            pr_number=123456,
            merge_head="a" * 40,
            ci_digest="e" * 64,
        )
    assert exc_info.value.code == "request-conflict"
    with sqlite3.connect(database) as connection:
        after = read_record(connection, envelope.request.request_id)
    assert before == after


def test_journal_records_persists_merged_projection_with_canonical_receipt(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with merge intent persisted.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None
    intent = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head=pushed.committed_head,
        ci_digest="d" * 64,
    )

    merged = subject.merged(envelope, merged_head="a" * 40)
    assert merged.lifecycle == "merged"
    assert merged.reason == "cleanup-pending"
    assert merged.merge_pr_number == 123456
    assert merged.merge_head == pushed.committed_head
    assert merged.merge_ci_digest == "d" * 64
    assert merged.phase_version == intent.phase_version + 1
    assert merged.merge_intent_at is not None
    assert merged.terminal_at == merged.updated_at
    expected_receipt = DeliveryReceipt(
        request_id=envelope.request.request_id,
        lifecycle="merged",
        reason="cleanup-pending",
        authoritative=True,
        accepted_local_head=envelope.orchestration_request.base_commit,
        committed_head=pushed.committed_head,
        remote_head=pushed.remote_head,
        pr_number=123456,
        ci_digest="d" * 64,
        merge_head=pushed.committed_head,
        created_at=merged.merge_intent_at,
        updated_at=merged.terminal_at,
    )
    terminal_raw, terminal_digest = encode_delivery_receipt(expected_receipt)
    assert merged.terminal_receipt_json == terminal_raw
    assert merged.terminal_receipt_sha256 == terminal_digest
    assert read_terminal_receipt(merged) == expected_receipt
    with sqlite3.connect(database) as connection:
        persisted = read_record(connection, envelope.request.request_id)
    assert persisted == merged


def test_journal_records_replays_merged_projection_exactly_and_idempotently(
    tmp_path: Path,
) -> None:
    # Given: a merged lifecycle row with a persisted terminal projection.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
        ci_digest="d" * 64,
    )
    first = subject.merged(envelope, merged_head="a" * 40)
    with sqlite3.connect(database) as connection:
        before = read_record(connection, envelope.request.request_id)
    assert before == first

    second = subject.merged(envelope, merged_head="a" * 40)
    with sqlite3.connect(database) as connection:
        after = read_record(connection, envelope.request.request_id)
    assert second == before == after
    assert second.terminal_receipt_json == first.terminal_receipt_json
    assert second.terminal_receipt_sha256 == first.terminal_receipt_sha256
    assert second.terminal_at == first.terminal_at
    assert second.updated_at == first.updated_at
    assert second.phase_version == first.phase_version


def test_journal_initial_lifecycle_uses_explicit_timestamp_and_replays_merged(
    tmp_path: Path,
) -> None:
    main, envelope, subject = _subject(tmp_path)
    observed_at = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    prepared = subject.prepare(envelope, observed_at=observed_at)
    intent = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
        observed_at=observed_at,
    )
    committed = subject.committed(envelope, observed_at=observed_at)
    push_intent = subject.push_intent(envelope, observed_at=observed_at)
    pushed = subject.pushed(
        envelope, remote_head="a" * 40, observed_at=observed_at
    )
    merge_intent = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head="a" * 40,
        ci_digest="d" * 64,
        observed_at=observed_at,
    )
    merged = subject.merged(envelope, merged_head="a" * 40, observed_at=observed_at)

    assert all(
        record.updated_at == observed_at
        for record in (prepared, intent, committed, push_intent, pushed, merge_intent, merged)
    )
    assert merge_intent.merge_intent_at == observed_at
    terminal = read_terminal_receipt(merged)
    assert terminal is not None
    assert terminal.created_at == observed_at
    assert terminal.updated_at == observed_at
    assert subject.merged(
        envelope, merged_head="a" * 40, observed_at=datetime(2026, 8, 4, 12, 1)
    ) == merged


def test_journal_records_rejects_merged_head_mismatch_and_preserves_merge_intent(
    tmp_path: Path,
) -> None:
    # Given: a merge-intent lifecycle row and a different merged head.
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    _ = subject.pushed(envelope, remote_head="a" * 40)
    _ = subject.merge_intent(
        envelope,
        pr_number=123456,
        merge_head="a" * 40,
        ci_digest="d" * 64,
    )
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        before = read_record(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.merged(envelope, merged_head="b" * 40)
    assert exc_info.value.code == "journal-invalid"
    with sqlite3.connect(database) as connection:
        after = read_record(connection, envelope.request.request_id)
    assert before == after


def test_journal_records_rejects_merged_without_merge_intent_and_preserves_row(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row without merge intent.
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    _ = subject.pushed(envelope, remote_head="a" * 40)

    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        before = read_record(connection, envelope.request.request_id)

    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.merged(envelope, merged_head="a" * 40)
    assert exc_info.value.code == "request-conflict"
    with sqlite3.connect(database) as connection:
        after = read_record(connection, envelope.request.request_id)
    assert before == after


def test_journal_records_reads_merged_projection_with_full_terminal_group(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with a full merge group and full terminal group.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None
    terminal_raw, terminal_digest, terminal_receipt = _terminal_receipt_payload(
        request_id=envelope.request.request_id,
        lifecycle="merged",
        reason="cleanup-pending",
        accepted_local_head=envelope.orchestration_request.base_commit,
        committed_head=pushed.committed_head,
        remote_head=pushed.remote_head,
        pr_number=123456,
        ci_digest="a" * 64,
        merge_head=pushed.committed_head,
        timestamp=pushed.updated_at,
    )

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merged', reason='cleanup-pending',"
            " merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?,"
            " terminal_receipt_json=?, terminal_receipt_sha256=?, terminal_at_utc=?"
            " WHERE request_id = ?",
            (
                123456,
                pushed.committed_head,
                "a" * 64,
                pushed.updated_at.isoformat(),
                terminal_raw,
                terminal_digest,
                pushed.updated_at.isoformat(),
                envelope.request.request_id,
            ),
        )
        connection.commit()
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert record.lifecycle == "merged"
    assert record.reason == "cleanup-pending"
    assert record.merge_pr_number == 123456
    assert read_terminal_receipt(record) == terminal_receipt
    validate_record(envelope, record)


def test_journal_records_rejects_partial_merge_group(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with a partial merge intent group.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    _ = subject.pushed(envelope, remote_head="a" * 40)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merge-intent', reason='merge-intent', merge_pr_number=?"
            " WHERE request_id = ?",
            (123456, envelope.request.request_id),
        )
        connection.commit()
        with pytest.raises(DeliveryJournalError):
            read_record(connection, envelope.request.request_id)


@pytest.mark.parametrize(
    "failure",
    [
        "authoritative_false",
        "invalid_terminal_pair",
        "request_id_mismatch",
        "accepted_local_head_mismatch",
        "remote_head_mismatch",
        "pr_number_mismatch",
        "ci_digest_mismatch",
        "committed_and_merge_head_mismatch",
        "merge_intent_created_at_mismatch",
        "terminal_updated_at_mismatch",
        "terminal_at_utc_mismatch",
        "digest_corrupt",
    ],
)
def test_journal_records_rejects_terminal_receipt_decode_or_binding_failure(
    tmp_path: Path, failure: str
) -> None:
    # Given: a pushed lifecycle row with a full terminal group whose terminal row is wrong.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None

    terminal_raw, terminal_digest, terminal_receipt = _terminal_receipt_payload(
        request_id=envelope.request.request_id,
        lifecycle="merged",
        reason="cleanup-pending",
        accepted_local_head=envelope.orchestration_request.base_commit,
        committed_head=pushed.committed_head,
        remote_head=pushed.remote_head,
        pr_number=123456,
        ci_digest="a" * 64,
        merge_head=pushed.committed_head,
        timestamp=pushed.updated_at,
    )
    terminal_merge_intent_at = pushed.updated_at
    terminal_at_utc = pushed.updated_at
    if failure == "digest_corrupt":
        terminal_digest = "b" * 64
    elif failure == "authoritative_false":
        terminal_receipt = terminal_receipt.model_copy(update={"authoritative": False})
    elif failure == "invalid_terminal_pair":
        terminal_receipt = terminal_receipt.model_copy(
            update={"lifecycle": "completed", "reason": "cleanup-pending"}
        )
    elif failure == "request_id_mismatch":
        terminal_receipt = terminal_receipt.model_copy(
            update={"request_id": "delivery_" + "2" * 64}
        )
    elif failure == "accepted_local_head_mismatch":
        terminal_receipt = terminal_receipt.model_copy(
            update={"accepted_local_head": "b" * 40}
        )
    elif failure == "committed_and_merge_head_mismatch":
        mismatched_head = "b" * 40
        terminal_receipt = terminal_receipt.model_copy(
            update={"committed_head": mismatched_head, "merge_head": mismatched_head}
        )
    elif failure == "remote_head_mismatch":
        terminal_receipt = terminal_receipt.model_copy(update={"remote_head": "b" * 40})
    elif failure == "pr_number_mismatch":
        terminal_receipt = terminal_receipt.model_copy(update={"pr_number": 654321})
    elif failure == "ci_digest_mismatch":
        terminal_receipt = terminal_receipt.model_copy(update={"ci_digest": "b" * 64})
    elif failure == "merge_intent_created_at_mismatch":
        terminal_merge_intent_at = pushed.updated_at.replace(
            year=pushed.updated_at.year + 1
        )
    elif failure == "terminal_updated_at_mismatch":
        terminal_receipt = terminal_receipt.model_copy(
            update={"updated_at": pushed.updated_at.replace(year=pushed.updated_at.year + 1)}
        )
    elif failure == "terminal_at_utc_mismatch":
        terminal_at_utc = pushed.updated_at.replace(year=pushed.updated_at.year + 1)

    if failure != "digest_corrupt":
        terminal_raw, terminal_digest = encode_delivery_receipt(terminal_receipt)
        assert decode_delivery_receipt(terminal_raw, terminal_digest) == terminal_receipt

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merged', reason='cleanup-pending',"
            " merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?,"
            " terminal_receipt_json=?, terminal_receipt_sha256=?, terminal_at_utc=?"
            " WHERE request_id = ?",
            (
                123456,
                pushed.committed_head,
                "a" * 64,
                terminal_merge_intent_at.isoformat(),
                terminal_raw,
                terminal_digest,
                terminal_at_utc.isoformat(),
                envelope.request.request_id,
            ),
        )
        connection.commit()
        with pytest.raises(DeliveryJournalError):
            read_record(connection, envelope.request.request_id)


def test_journal_records_rejects_partial_terminal_group_only_at_public_api_boundary(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with a full merge group.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
    _ = subject.prepare(envelope)
    _ = subject.commit_intent(
        envelope,
        committed_head="a" * 40,
        commit_parent=envelope.orchestration_request.base_commit,
        commit_tree="b" * 40,
    )
    _ = subject.committed(envelope)
    _ = subject.push_intent(envelope)
    _ = subject.pushed(envelope, remote_head="a" * 40)

    with sqlite3.connect(database) as connection:
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    partial = dataclasses.replace(
        record,
        terminal_receipt_json="{}",
        terminal_receipt_sha256=None,
        terminal_at=None,
    )
    with pytest.raises(DeliveryJournalError):
        _ = read_terminal_receipt(partial)


def test_journal_records_reads_completed_projection_with_canonical_receipt(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with a completed terminal receipt.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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
    assert pushed.remote_head is not None
    terminal_raw, terminal_digest, terminal_receipt = _terminal_receipt_payload(
        request_id=envelope.request.request_id,
        lifecycle="completed",
        reason="completed",
        accepted_local_head=envelope.orchestration_request.base_commit,
        committed_head=pushed.committed_head,
        remote_head=pushed.remote_head,
        pr_number=123456,
        ci_digest="a" * 64,
        merge_head=pushed.committed_head,
        timestamp=pushed.updated_at,
    )

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merged', reason='cleanup-pending',"
            " merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?,"
            " terminal_receipt_json=?, terminal_receipt_sha256=?, terminal_at_utc=?"
            " WHERE request_id = ?",
            (
                123456,
                pushed.committed_head,
                "a" * 64,
                pushed.updated_at.isoformat(),
                terminal_raw,
                terminal_digest,
                pushed.updated_at.isoformat(),
                envelope.request.request_id,
            ),
        )
        connection.commit()
        record = read_record(connection, envelope.request.request_id)
    assert record is not None
    assert read_terminal_receipt(record) == terminal_receipt
    validate_record(envelope, record)


def test_journal_records_rejects_partial_terminal_group(
    tmp_path: Path,
) -> None:
    # Given: a pushed lifecycle row with merge-complete plus partial terminal group.
    main, envelope, subject = _subject(tmp_path)
    database = _delivery_database(main)
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

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='merged', reason='cleanup-pending',"
            " merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?,"
            " terminal_receipt_json=?"
            " WHERE request_id = ?",
            (
                123456,
                pushed.committed_head,
                "a" * 64,
                pushed.updated_at.isoformat(),
                "{}",
                envelope.request.request_id,
            ),
        )
        connection.commit()
        with pytest.raises(DeliveryJournalError):
            read_record(connection, envelope.request.request_id)


@pytest.mark.parametrize("lifecycle", ["prepared", "commit-intent", "committed", "push-intent"])
def test_journal_records_rejects_remote_head_for_pre_merge_lifecycles(
    tmp_path: Path, lifecycle: str
) -> None:
    # Given: a pre-merge lifecycle row with an unexpected remote head.
    main, envelope, subject = _subject(tmp_path)
    _ = subject.prepare(envelope)
    if lifecycle == "commit-intent":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
    elif lifecycle == "committed":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
        _ = subject.committed(envelope)
    elif lifecycle == "push-intent":
        _ = subject.commit_intent(
            envelope,
            committed_head="a" * 40,
            commit_parent=envelope.orchestration_request.base_commit,
            commit_tree="b" * 40,
        )
        _ = subject.committed(envelope)
        _ = subject.push_intent(envelope)

    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle SET remote_head = ? WHERE request_id = ?",
            ("a" * 40, envelope.request.request_id),
        )
        connection.commit()
        with pytest.raises(DeliveryJournalError):
            read_record(connection, envelope.request.request_id)


def test_journal_records_rejects_uncertain_without_merge_with_complete_terminal_group(
    tmp_path: Path,
) -> None:
    # Given: a non-merge uncertainty row carrying a full terminal group.
    main, envelope, subject = _subject(tmp_path)
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
    database = _delivery_database(main)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE delivery_lifecycle"
            " SET lifecycle='uncertain', reason='interrupted', remote_head=NULL,"
            " merge_pr_number=NULL, merge_head=NULL,"
            " merge_ci_digest=NULL, merge_intent_at_utc=NULL,"
            " terminal_receipt_json='{}', terminal_receipt_sha256=?, terminal_at_utc=?"
            " WHERE request_id = ?",
            (
                "c" * 64,
                pushed.updated_at.isoformat(),
                envelope.request.request_id,
            ),
        )
        connection.commit()
        with pytest.raises(DeliveryJournalError):
            read_record(connection, envelope.request.request_id)


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
        # Deliberately non-private: the test asserts that journal reuse fails closed.
        os.chmod(database, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    else:
        database.unlink()
        target = tmp_path / "foreign.sqlite3"
        target.write_bytes(b"foreign")
        database.symlink_to(target)

    # When/Then: no lifecycle SQL runs through the corrupted storage surface.
    with pytest.raises(DeliveryJournalError) as exc_info:
        subject.prepare(envelope)
    assert exc_info.value.code == "journal-invalid"
