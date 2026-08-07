from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factory_pr_delivery_test_support import accepted_artifacts, write_delivery_request

from scripts.factory_pr_delivery_io import load_delivery_envelope
from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_models import DeliveryEnvelope


def _delivery_database(main: Path) -> Path:
    return main / ".entroping/factory-pr-delivery/delivery.sqlite3"


def _subject(tmp_path: Path) -> tuple[Path, DeliveryEnvelope, DeliveryJournal]:
    main, _worktree, payload = accepted_artifacts(tmp_path)
    request_path = tmp_path / "private/delivery-request.json"
    write_delivery_request(request_path, payload)
    return main, load_delivery_envelope(request_path), DeliveryJournal(main)


def _write_cleanup_row(connection: sqlite3.Connection, *, request_id: str) -> None:
    connection.execute(
        "INSERT INTO delivery_cleanup("
        "request_id, remote_branch, expected_remote_head, scheduler_owner_id, "
        "scheduler_owner_pid, scheduler_owner_start_token, scheduler_owner_epoch, "
        "scheduler_phase_version, cleanup_intent_at_utc, phase_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            request_id,
            "feature/canonical",
            "a" * 40,
            "owner-id",
            42,
            "owner-token",
            1,
            7,
            datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            1,
        ),
    )


def test_journal_cleanup_schema_rejects_identity_mutation(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(connection, request_id=envelope.request.request_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup SET remote_branch = ? WHERE request_id = ?",
                ("feature/other", envelope.request.request_id),
            )


def test_journal_cleanup_schema_rejects_proof_rewrite_and_clear(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(connection, request_id=envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_cleanup SET finish_cleanup_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (datetime(2026, 1, 2, tzinfo=UTC).isoformat(), 2, envelope.request.request_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup SET finish_cleanup_at_utc = ?, phase_version = ? "
                "WHERE request_id = ?",
                (
                    datetime(2026, 1, 2, 12, tzinfo=UTC).isoformat(),
                    2,
                    envelope.request.request_id,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup SET finish_cleanup_at_utc = ?, phase_version = ? "
                "WHERE request_id = ?",
                (None, 1, envelope.request.request_id),
            )


def test_journal_cleanup_schema_rejects_prefix_and_phase_constraints(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(connection, request_id=envelope.request.request_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup "
                "SET remote_absent_at_utc = ?, phase_version = ? "
                "WHERE request_id = ?",
                (datetime(2026, 1, 2, tzinfo=UTC).isoformat(), 2, envelope.request.request_id),
            )

        connection.execute(
            "UPDATE delivery_cleanup "
            "SET finish_cleanup_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (datetime(2026, 1, 2, tzinfo=UTC).isoformat(), 2, envelope.request.request_id),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup "
                "SET scheduler_completion_at_utc = ?, phase_version = ? "
                "WHERE request_id = ?",
                (
                    datetime(2026, 1, 3, tzinfo=UTC).isoformat(),
                    3,
                    envelope.request.request_id,
                ),
            )


def test_journal_cleanup_schema_rejects_scheduler_completion_equality_violation(
    tmp_path: Path,
) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(connection, request_id=envelope.request.request_id)
        connection.execute(
            "UPDATE delivery_cleanup SET finish_cleanup_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (
                datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
                2,
                envelope.request.request_id,
            ),
        )
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET remote_absent_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (datetime(2026, 1, 3, tzinfo=UTC).isoformat(), 3, envelope.request.request_id),
        )
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completion_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (datetime(2026, 1, 4, tzinfo=UTC).isoformat(), 4, envelope.request.request_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE delivery_cleanup "
                "SET scheduler_completed_at_utc = ?, phase_version = ? "
                "WHERE request_id = ?",
                (datetime(2026, 1, 5, tzinfo=UTC).isoformat(), 5, envelope.request.request_id),
            )
        completion_at = datetime(2026, 1, 4, tzinfo=UTC).isoformat()
        connection.execute(
            "UPDATE delivery_cleanup "
            "SET scheduler_completed_at_utc = ?, phase_version = ? "
            "WHERE request_id = ?",
            (completion_at, 5, envelope.request.request_id),
        )


def test_journal_cleanup_schema_rejects_row_deletion(tmp_path: Path) -> None:
    main, envelope, subject = _subject(tmp_path)
    subject.prepare(envelope)
    with sqlite3.connect(_delivery_database(main)) as connection:
        _write_cleanup_row(connection, request_id=envelope.request.request_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM delivery_cleanup WHERE request_id = ?",
                (envelope.request.request_id,),
            )
