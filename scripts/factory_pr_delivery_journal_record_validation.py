"""Validation helpers for durable journal row projection."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Protocol

type JournalLifecycle = Literal[
    "prepared",
    "commit-intent",
    "committed",
    "push-intent",
    "pushed",
    "merge-intent",
    "merged",
    "uncertain",
]
type JournalReason = Literal[
    "none",
    "committed",
    "pushed",
    "interrupted",
    "merge-intent",
    "cleanup-pending",
]

_REQUEST_ID = re.compile(r"delivery_[a-f0-9]{64}\Z")
_ASSIGNMENT_ID = re.compile(r"assign_[a-f0-9]{64}\Z")
_WORKTREE_ID = re.compile(r"wt_[a-f0-9]{64}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}\Z")


class JournalRecordShape(Protocol):
    @property
    def request_id(self) -> str: ...
    @property
    def request_digest(self) -> str: ...
    @property
    def envelope_digest(self) -> str: ...
    @property
    def issue_number(self) -> int: ...
    @property
    def assignment_id(self) -> str: ...
    @property
    def worktree_id(self) -> str: ...
    @property
    def lifecycle(self) -> JournalLifecycle: ...
    @property
    def reason(self) -> JournalReason: ...
    @property
    def accepted_local_head(self) -> str: ...
    @property
    def committed_head(self) -> str | None: ...
    @property
    def remote_head(self) -> str | None: ...
    @property
    def commit_parent(self) -> str | None: ...
    @property
    def commit_tree(self) -> str | None: ...
    @property
    def accepted_diff_sha256(self) -> str: ...
    @property
    def accepted_manifest_sha256(self) -> str: ...
    @property
    def approved_path_sha256(self) -> str: ...
    @property
    def body_sha256(self) -> str: ...
    @property
    def phase_version(self) -> int: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def updated_at(self) -> datetime: ...
    @property
    def merge_pr_number(self) -> int | None: ...
    @property
    def merge_head(self) -> str | None: ...
    @property
    def merge_ci_digest(self) -> str | None: ...
    @property
    def merge_intent_at(self) -> datetime | None: ...
    @property
    def terminal_receipt_json(self) -> str | None: ...
    @property
    def terminal_receipt_sha256(self) -> str | None: ...
    @property
    def terminal_at(self) -> datetime | None: ...


def validate_journal_record_shape(record: JournalRecordShape) -> None:
    if (
        record.lifecycle
        not in {
            "prepared",
            "commit-intent",
            "committed",
            "push-intent",
            "pushed",
            "merge-intent",
            "merged",
            "uncertain",
        }
        or record.reason
        not in {
            "none",
            "committed",
            "pushed",
            "interrupted",
            "merge-intent",
            "cleanup-pending",
        }
    ):
        raise ValueError

    if (
        not _REQUEST_ID.fullmatch(record.request_id)
        or not _DIGEST.fullmatch(record.request_digest)
        or not _DIGEST.fullmatch(record.envelope_digest)
        or not _ASSIGNMENT_ID.fullmatch(record.assignment_id)
        or not _WORKTREE_ID.fullmatch(record.worktree_id)
        or not _COMMIT.fullmatch(record.accepted_local_head)
        or not _DIGEST.fullmatch(record.accepted_diff_sha256)
        or not _DIGEST.fullmatch(record.accepted_manifest_sha256)
        or not _DIGEST.fullmatch(record.approved_path_sha256)
        or not _DIGEST.fullmatch(record.body_sha256)
        or (
            record.merge_pr_number is not None
            and (type(record.merge_pr_number) is not int or record.merge_pr_number < 1)
        )
        or (record.merge_head is not None and not _COMMIT.fullmatch(record.merge_head))
        or (record.merge_ci_digest is not None and not _DIGEST.fullmatch(record.merge_ci_digest))
        or (
            record.terminal_receipt_sha256 is not None
            and not _DIGEST.fullmatch(record.terminal_receipt_sha256)
        )
        or (
            record.terminal_receipt_json is not None
            and not isinstance(record.terminal_receipt_json, str)
        )
        or record.issue_number < 1
        or record.phase_version < 1
        or record.created_at.tzinfo is None
        or record.created_at.utcoffset() is None
        or record.updated_at.tzinfo is None
        or record.updated_at.utcoffset() is None
        or record.updated_at < record.created_at
    ):
        raise ValueError

    if (
        record.merge_intent_at is not None
        and (record.merge_intent_at.tzinfo is None or record.merge_intent_at.utcoffset() is None)
    ):
        raise ValueError
    if record.terminal_at is not None and (
        record.terminal_at.tzinfo is None or record.terminal_at.utcoffset() is None
    ):
        raise ValueError

    for commit in (
        record.committed_head,
        record.remote_head,
        record.commit_parent,
        record.commit_tree,
    ):
        if commit is not None and not _COMMIT.fullmatch(commit):
            raise ValueError

    commit_values = (record.committed_head, record.commit_parent, record.commit_tree)
    committed = record.lifecycle in {
        "commit-intent",
        "committed",
        "push-intent",
        "pushed",
        "merge-intent",
        "merged",
    }
    if (committed or any(value is not None for value in commit_values)) and not all(
        value is not None for value in commit_values
    ):
        raise ValueError
    if record.commit_parent is not None and record.commit_parent != record.accepted_local_head:
        raise ValueError

    merge_fields = (
        record.merge_pr_number,
        record.merge_head,
        record.merge_ci_digest,
        record.merge_intent_at,
    )
    terminal_fields = (
        record.terminal_receipt_json,
        record.terminal_receipt_sha256,
        record.terminal_at,
    )
    merge_present = any(field is not None for field in merge_fields)
    merge_complete = all(field is not None for field in merge_fields)
    terminal_present = any(field is not None for field in terminal_fields)
    terminal_complete = all(field is not None for field in terminal_fields)
    if merge_present != merge_complete or terminal_present != terminal_complete:
        raise ValueError

    expected_reason: dict[JournalLifecycle, JournalReason] = {
        "prepared": "none",
        "commit-intent": "none",
        "committed": "committed",
        "push-intent": "committed",
        "pushed": "pushed",
        "merge-intent": "merge-intent",
        "merged": "cleanup-pending",
    }
    if record.lifecycle != "uncertain" and record.reason != expected_reason[record.lifecycle]:
        raise ValueError

    pre_merge = record.lifecycle in {
        "prepared",
        "commit-intent",
        "committed",
        "push-intent",
        "pushed",
    }
    if (
        record.lifecycle in {"prepared", "commit-intent", "committed", "push-intent"}
        and record.remote_head is not None
    ):
        raise ValueError
    if pre_merge and (merge_present or terminal_present):
        raise ValueError

    if record.lifecycle == "merge-intent":
        if not merge_complete or terminal_present:
            raise ValueError
        if record.remote_head != record.committed_head:
            raise ValueError
        if record.merge_head != record.committed_head:
            raise ValueError

    elif record.lifecycle == "merged":
        if not merge_complete or not terminal_complete:
            raise ValueError
        if record.remote_head != record.committed_head:
            raise ValueError
        if record.merge_head != record.committed_head:
            raise ValueError

    elif record.lifecycle == "uncertain":
        if not merge_complete:
            if (
                record.reason != "interrupted"
                or record.remote_head is not None
                or terminal_present
            ):
                raise ValueError
            return
        if record.reason not in {"interrupted", "cleanup-pending"}:
            raise ValueError
        if record.remote_head != record.committed_head:
            raise ValueError

    if record.lifecycle == "pushed" and record.remote_head != record.committed_head:
        raise ValueError
