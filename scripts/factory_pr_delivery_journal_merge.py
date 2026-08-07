"""SQLite writer for durable merge-intent journal transitions."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal_records import (
    DeliveryJournalError,
    DeliveryJournalRecord,
    read_record,
    read_terminal_receipt,
    validate_record,
)
from scripts.factory_pr_delivery_journal_storage import journal_connection
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_pr_delivery_receipts import DeliveryReceipt, encode_delivery_receipt

_DIGEST = re.compile(r"^[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"^[a-f0-9]{40}\Z")
_MAX_PR_NUMBER = 2_147_483_647


def persist_merge_intent(
    root: Path,
    envelope: DeliveryEnvelope,
    *,
    pr_number: int,
    merge_head: str,
    ci_digest: str,
    observed_at: datetime | None = None,
) -> DeliveryJournalRecord:
    _validate_merge_inputs(pr_number=pr_number, merge_head=merge_head, ci_digest=ci_digest)
    with journal_connection(root) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            record = read_record(connection, envelope.request.request_id)
            if record is None or record.lifecycle != "pushed":
                raise DeliveryJournalError("request-conflict")
            validate_record(envelope, record)
            if record.remote_head != record.committed_head:
                raise DeliveryJournalError("journal-invalid")
            if (
                merge_head != record.committed_head
                or merge_head != record.remote_head
            ):
                raise DeliveryJournalError("journal-invalid")

            merged_at = _timestamp(observed_at, prior=record.updated_at)

            changed = connection.execute(
                "UPDATE delivery_lifecycle SET "
                "lifecycle='merge-intent', reason='merge-intent', "
                "merge_pr_number=?, merge_head=?, merge_ci_digest=?, merge_intent_at_utc=?, "
                "terminal_receipt_json=NULL, terminal_receipt_sha256=NULL, terminal_at_utc=NULL, "
                "updated_at_utc=?, phase_version = phase_version + 1 "
                "WHERE request_id = ? AND lifecycle = 'pushed' AND phase_version = ?",
                (
                    pr_number,
                    merge_head,
                    ci_digest,
                    merged_at.isoformat(),
                    merged_at.isoformat(),
                    record.request_id,
                    record.phase_version,
                ),
            ).rowcount
            if changed != 1:
                raise DeliveryJournalError("request-conflict")

            updated = read_record(connection, record.request_id)
            if updated is None:
                raise DeliveryJournalError("journal-invalid")
            validate_record(envelope, updated)
            connection.execute("COMMIT")
            return updated
        except DeliveryJournalError:
            connection.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
            raise DeliveryJournalError("journal-invalid") from None


def persist_merged_receipt(
    root: Path,
    envelope: DeliveryEnvelope,
    *,
    merged_head: str,
    observed_at: datetime | None = None,
) -> DeliveryJournalRecord:
    _validate_merged_head(merged_head)
    with journal_connection(root) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            record = read_record(connection, envelope.request.request_id)
            if record is None:
                raise DeliveryJournalError("request-conflict")

            if record.lifecycle == "merged":
                validate_record(envelope, record)
                if merged_head != record.merge_head:
                    raise DeliveryJournalError("journal-invalid")
                terminal = read_and_validate_terminal_receipt(record)
                if merged_head != terminal.merge_head:
                    raise DeliveryJournalError("journal-invalid")
                if terminal.created_at != record.merge_intent_at:
                    raise DeliveryJournalError("journal-invalid")
                connection.execute("COMMIT")
                return record

            if record.lifecycle != "merge-intent":
                raise DeliveryJournalError("request-conflict")
            validate_record(envelope, record)

            if (
                merged_head != record.merge_head
                or merged_head != record.committed_head
                or merged_head != record.remote_head
            ):
                raise DeliveryJournalError("journal-invalid")
            if record.merge_intent_at is None:
                raise DeliveryJournalError("journal-invalid")

            terminal_at = _timestamp(observed_at, prior=record.updated_at)
            if (
                record.merge_pr_number is None
                or record.merge_ci_digest is None
                or record.merge_head is None
            ):
                raise DeliveryJournalError("journal-invalid")
            terminal_receipt = DeliveryReceipt(
                request_id=record.request_id,
                lifecycle="merged",
                reason="cleanup-pending",
                authoritative=True,
                accepted_local_head=record.accepted_local_head,
                committed_head=record.committed_head,
                remote_head=record.remote_head,
                pr_number=record.merge_pr_number,
                ci_digest=record.merge_ci_digest,
                merge_head=record.merge_head,
                created_at=record.merge_intent_at.astimezone(UTC),
                updated_at=terminal_at,
            )
            terminal_raw, terminal_digest = encode_delivery_receipt(terminal_receipt)

            changed = connection.execute(
                "UPDATE delivery_lifecycle SET "
                "lifecycle='merged', reason='cleanup-pending', "
                "terminal_receipt_json=?, terminal_receipt_sha256=?, terminal_at_utc=?, "
                "updated_at_utc=?, phase_version = phase_version + 1 "
                "WHERE request_id = ? AND lifecycle = 'merge-intent' AND phase_version = ?",
                (
                    terminal_raw,
                    terminal_digest,
                    terminal_at.isoformat(),
                    terminal_at.isoformat(),
                    record.request_id,
                    record.phase_version,
                ),
            ).rowcount
            if changed != 1:
                raise DeliveryJournalError("request-conflict")

            updated = read_record(connection, record.request_id)
            if updated is None:
                raise DeliveryJournalError("journal-invalid")
            validate_record(envelope, updated)
            if read_and_validate_terminal_receipt(updated) != terminal_receipt:
                raise DeliveryJournalError("journal-invalid")
            connection.execute("COMMIT")
            return updated
        except DeliveryJournalError:
            connection.execute("ROLLBACK")
            raise
        except (TypeError, ValueError, sqlite3.DatabaseError):
            connection.execute("ROLLBACK")
            raise DeliveryJournalError("journal-invalid") from None


def _validate_merge_inputs(*, pr_number: int, merge_head: str, ci_digest: str) -> None:
    if not isinstance(merge_head, str) or not isinstance(ci_digest, str):
        raise DeliveryJournalError("journal-invalid")
    if type(pr_number) is not int or not 1 <= pr_number <= _MAX_PR_NUMBER:
        raise DeliveryJournalError("journal-invalid")
    if not _COMMIT.fullmatch(merge_head) or not _DIGEST.fullmatch(ci_digest):
        raise DeliveryJournalError("journal-invalid")


def _validate_merged_head(merged_head: str) -> None:
    if not isinstance(merged_head, str) or not _COMMIT.fullmatch(merged_head):
        raise DeliveryJournalError("journal-invalid")


def _timestamp(observed_at: datetime | None, *, prior: datetime) -> datetime:
    if observed_at is None:
        candidate = datetime.now(UTC)
    elif not isinstance(observed_at, datetime):
        raise DeliveryJournalError("journal-invalid")
    else:
        try:
            if observed_at.utcoffset() is None:
                raise DeliveryJournalError("journal-invalid")
            candidate = observed_at.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            raise DeliveryJournalError("journal-invalid") from None
    return max(candidate, prior.astimezone(UTC))


def read_and_validate_terminal_receipt(record: DeliveryJournalRecord) -> DeliveryReceipt:
    receipt = read_terminal_receipt(record)
    if receipt is None:
        raise DeliveryJournalError("journal-invalid")
    terminal_raw, terminal_digest = encode_delivery_receipt(receipt)
    if (
        terminal_raw != record.terminal_receipt_json
        or terminal_digest != record.terminal_receipt_sha256
    ):
        raise DeliveryJournalError("journal-invalid")
    return receipt
