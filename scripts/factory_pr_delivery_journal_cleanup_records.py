"""Strict value-free read projection for cleanup intent and proofs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from pydantic import Field, ValidationError, model_validator

from scripts.factory_orchestration_models import Branch, Commit
from scripts.factory_pr_delivery_models import RequestId, StrictModel
from scripts.factory_scheduler_execution_models import PhaseVersion
from scripts.factory_scheduler_models import Identifier, PositiveEpoch, ProcessToken

__all__ = ["DeliveryCleanupRecord", "read_cleanup_record"]

_PositivePid = Annotated[int, Field(ge=1, le=2_147_483_647)]


class DeliveryCleanupRecord(StrictModel):
    request_id: RequestId
    remote_branch: Branch
    expected_remote_head: Commit
    scheduler_owner_id: Identifier
    scheduler_owner_pid: _PositivePid
    scheduler_owner_start_token: ProcessToken
    scheduler_owner_epoch: PositiveEpoch
    scheduler_phase_version: PhaseVersion
    cleanup_intent_at: datetime
    remote_absent_at: datetime | None
    finish_cleanup_at: datetime | None
    scheduler_completion_at: datetime | None
    scheduler_completed_at: datetime | None
    phase_version: PhaseVersion

    @model_validator(mode="after")
    def validate_projection(self) -> DeliveryCleanupRecord:
        timeline = [
            self.cleanup_intent_at,
            self.finish_cleanup_at,
            self.remote_absent_at,
            self.scheduler_completion_at,
            self.scheduler_completed_at,
        ]
        optional_prefix = timeline[1:]
        found_null = False
        for value in optional_prefix:
            if value is None:
                found_null = True
            elif found_null:
                raise ValueError("cleanup proof must be an ordered optional prefix")
        for value in timeline:
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("cleanup timestamp must be timezone-aware")
        for previous, current in zip(timeline, timeline[1:], strict=False):
            if previous is not None and current is not None and current < previous:
                raise ValueError("cleanup proof timestamps must be monotonic")
        if (
            self.scheduler_completed_at is not None
            and self.scheduler_completed_at != self.scheduler_completion_at
        ):
            raise ValueError("scheduler completion and completed timestamp must match")
        populated = sum(
            value is not None
            for value in (
                self.remote_absent_at,
                self.finish_cleanup_at,
                self.scheduler_completion_at,
                self.scheduler_completed_at,
            )
        )
        if self.phase_version != 1 + populated:
            raise ValueError("invalid cleanup proof phase")
        return self


def read_cleanup_record(row: Sequence[object]) -> DeliveryCleanupRecord:
    if len(row) != 14:
        raise ValueError("invalid cleanup row")
    try:
        return DeliveryCleanupRecord.model_validate(
            {
                "request_id": _as_text(row[0], "request_id"),
                "remote_branch": _as_text(row[1], "remote_branch"),
                "expected_remote_head": _as_text(row[2], "expected_remote_head"),
                "scheduler_owner_id": _as_text(row[3], "scheduler_owner_id"),
                "scheduler_owner_pid": _as_int(row[4], "scheduler_owner_pid"),
                "scheduler_owner_start_token": _as_text(
                    row[5], "scheduler_owner_start_token"
                ),
                "scheduler_owner_epoch": _as_int(row[6], "scheduler_owner_epoch"),
                "scheduler_phase_version": _as_int(row[7], "scheduler_phase_version"),
                "cleanup_intent_at": _as_aware_datetime(
                    row[8], "cleanup_intent_at_utc"
                ),
                "remote_absent_at": _as_optional_aware_datetime(
                    row[9], "remote_absent_at_utc"
                ),
                "finish_cleanup_at": _as_optional_aware_datetime(
                    row[10], "finish_cleanup_at_utc"
                ),
                "scheduler_completion_at": _as_optional_aware_datetime(
                    row[11], "scheduler_completion_at_utc"
                ),
                "scheduler_completed_at": _as_optional_aware_datetime(
                    row[12], "scheduler_completed_at_utc"
                ),
                "phase_version": _as_int(row[13], "phase_version"),
            }
        )
    except ValidationError:
        raise ValueError("invalid cleanup row") from None


def _as_text(value: object, _field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{_field} must be text")
    return value


def _as_int(value: object, _field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{_field} must be integer")
    return value


def _as_optional_aware_datetime(value: object, _field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{_field} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{_field} must be aware")
    return parsed


def _as_aware_datetime(value: object, _field: str) -> datetime:
    parsed = _as_optional_aware_datetime(value, _field)
    if parsed is None:
        raise ValueError(f"{_field} is required")
    return parsed
