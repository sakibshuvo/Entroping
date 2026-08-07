"""Replay and journal preflight helpers for delivery apply path."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from scripts.factory_pr_delivery_journal import DeliveryJournal
from scripts.factory_pr_delivery_journal_records import DeliveryJournalError, read_terminal_receipt
from scripts.factory_pr_delivery_models import DeliveryEnvelope
from scripts.factory_pr_delivery_receipts import DeliveryReceipt
from scripts.factory_pr_delivery_terminal_completion import advance_terminal_completion

__all__ = ["prepare_delivery_apply"]


def prepare_delivery_apply(
    root: Path, envelope: DeliveryEnvelope, *, now: Callable[[], datetime]
) -> tuple[DeliveryJournal, DeliveryReceipt | None]:
    """Prepare journal state and perform terminal replay if already completed."""

    journal = DeliveryJournal(root)
    record = journal.read(envelope)
    if record is not None:
        terminal = read_terminal_receipt(record)
        if terminal is not None:
            return journal, advance_terminal_completion(root, envelope, now=now)
        if record.lifecycle == "merge-intent":
            committed_head = record.committed_head
            remote_head = record.remote_head
            if committed_head is None or remote_head is None:
                raise DeliveryJournalError("journal-invalid")
            journal.recover(envelope, local_head=committed_head, remote_head=remote_head)
            raise RuntimeError("uncertain-recovery-required")
    return journal, None
