from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from scripts import ai_job_fs
from scripts.factory_retention_fs import FsSnapshot, RetentionFsError, read_bounded_regular

JOURNAL_SCHEMA_VERSION = "entroping.factory-retention-journal.v1"
MAX_JOURNAL_BYTES = 8_388_608
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LOG_NAME = re.compile(r"factory-tick\.(?:out|err)\.log(?:\.\d+)?")

type JournalStatus = Literal["moving", "purging", "completed", "rolled_back"]
type OperationState = Literal["pending", "staged", "purged", "restored"]


class RetentionJournalError(RuntimeError):
    pass


@dataclass(slots=True)
class JournalOperation:
    source: PurePosixPath
    trash_name: str
    state: OperationState
    snapshot: FsSnapshot

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source.as_posix(),
            "trash_name": self.trash_name,
            "state": self.state,
            "kind": self.snapshot.kind,
            "byte_size": self.snapshot.byte_size,
            "mtime_ns": self.snapshot.mtime_ns,
            "sha256": self.snapshot.sha256,
        }


@dataclass(slots=True)
class RetentionJournal:
    transaction_id: str
    status: JournalStatus
    created_at: str
    operations: list[JournalOperation]
    completed_at: str | None = None

    def validate_state(self) -> None:
        states = {item.state for item in self.operations}
        if self.status == "moving" and not states <= {"pending", "staged"}:
            raise RetentionJournalError("moving journal has an invalid operation state")
        if self.status == "purging" and not states <= {"staged", "purged"}:
            raise RetentionJournalError("purging journal has an invalid operation state")
        if self.status == "completed" and states != ({"purged"} if states else set()):
            raise RetentionJournalError("completed journal has an invalid operation state")
        if self.status == "rolled_back" and states != ({"restored"} if states else set()):
            raise RetentionJournalError("rolled-back journal has an invalid operation state")
        if self.status in {"completed", "rolled_back"} and self.completed_at is None:
            raise RetentionJournalError("terminal journal is missing its completion time")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "transaction_id": self.transaction_id,
            "status": self.status,
            "created_at": self.created_at,
            "operations": [item.to_payload() for item in self.operations],
        }
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at
        return payload


def read_journal(journal_fd: int, name: str) -> RetentionJournal:
    try:
        raw = read_bounded_regular(journal_fd, name, limit=MAX_JOURNAL_BYTES)
        payload = cast(object, json.loads(raw.decode("utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, RetentionFsError) as exc:
        raise RetentionJournalError("retention journal is unreadable") from exc
    if not isinstance(payload, dict):
        raise RetentionJournalError("retention journal must be a JSON object")
    mapping = cast(dict[str, object], payload)
    allowed = {
        "schema_version",
        "transaction_id",
        "status",
        "created_at",
        "completed_at",
        "operations",
    }
    if set(mapping) - allowed or mapping.get("schema_version") != JOURNAL_SCHEMA_VERSION:
        raise RetentionJournalError("retention journal schema is unsupported")
    journal = RetentionJournal(
        transaction_id=_text(mapping, "transaction_id"),
        status=_status(mapping.get("status")),
        created_at=_text(mapping, "created_at"),
        completed_at=_optional_text(mapping.get("completed_at")),
        operations=_operations(mapping.get("operations")),
    )
    _validate_transaction_id(journal.transaction_id)
    journal.validate_state()
    return journal


def write_journal(
    journal_fd: int,
    journal: RetentionJournal,
    *,
    exclusive: bool = False,
) -> None:
    journal.validate_state()
    ai_job_fs.atomic_write_json(
        journal_fd,
        f"{journal.transaction_id}.json",
        journal.to_payload(),
        exclusive=exclusive,
    )


def managed_source(raw: str) -> PurePosixPath:
    source = PurePosixPath(raw)
    parts = source.parts
    allowed = (
        len(parts) == 4
        and parts[:2] == (".entroping", "ai-jobs")
        and parts[2] in {"completed", "failed"}
        and parts[3].endswith(".json")
    ) or (
        len(parts) == 3 and parts[:2] == (".entroping", "ai-reviews")
    ) or (
        len(parts) == 3
        and parts[:2] == (".entroping", "factory-logs")
        and _LOG_NAME.fullmatch(parts[2]) is not None
    ) or (
        len(parts) == 4
        and parts[:3] == (".entroping", "factory-metrics", "finished-issues")
        and re.fullmatch(r"issue-[1-9][0-9]*", parts[3]) is not None
    ) or (
        len(parts) == 3
        and parts[:2] == (".entroping", "retention-journal")
        and re.fullmatch(r"[0-9a-f]{32}\.json", parts[2]) is not None
    )
    if not allowed or source.as_posix() != raw or any(part in {".", ".."} for part in parts):
        raise RetentionJournalError("retention journal source is outside managed roots")
    return source


def _operations(value: object) -> list[JournalOperation]:
    if not isinstance(value, list):
        raise RetentionJournalError("retention journal operations are invalid")
    operations: list[JournalOperation] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            raise RetentionJournalError("retention journal operation is invalid")
        mapping = cast(dict[str, object], raw)
        expected = {"source", "trash_name", "state", "kind", "byte_size", "mtime_ns", "sha256"}
        if set(mapping) != expected:
            raise RetentionJournalError("retention journal operation fields are invalid")
        operations.append(
            JournalOperation(
                source=managed_source(_text(mapping, "source")),
                trash_name=_trash_name(_text(mapping, "trash_name")),
                state=_operation_state(mapping.get("state")),
                snapshot=_snapshot(mapping),
            )
        )
    return operations


def _snapshot(mapping: dict[str, object]) -> FsSnapshot:
    kind = _text(mapping, "kind")
    if kind not in {"file", "directory"}:
        raise RetentionJournalError("retention operation kind is invalid")
    digest = _text(mapping, "sha256")
    if _DIGEST.fullmatch(digest) is None:
        raise RetentionJournalError("retention operation digest is invalid")
    return FsSnapshot(
        kind=kind,
        byte_size=_integer(mapping, "byte_size"),
        mtime_ns=_integer(mapping, "mtime_ns"),
        sha256=digest,
    )


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise RetentionJournalError(f"retention field is invalid: {key}")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise RetentionJournalError("retention completion time is invalid")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RetentionJournalError(f"retention integer field is invalid: {key}")
    return value


def _trash_name(value: str) -> str:
    if Path(value).name != value:
        raise RetentionJournalError("retention trash name is invalid")
    return value


def _status(value: object) -> JournalStatus:
    if value not in {"moving", "purging", "completed", "rolled_back"}:
        raise RetentionJournalError("retention journal has an unsupported state")
    return cast(JournalStatus, value)


def _operation_state(value: object) -> OperationState:
    if value not in {"pending", "staged", "purged", "restored"}:
        raise RetentionJournalError("retention operation state is invalid")
    return cast(OperationState, value)


def _validate_transaction_id(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise RetentionJournalError("retention transaction id is invalid")
