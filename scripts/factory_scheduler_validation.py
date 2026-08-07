from __future__ import annotations

from datetime import UTC, datetime

MAX_LEASE_EPOCH = 9_223_372_036_854_775_807
MAX_LEASE_SECONDS = 3_600


class FactorySchedulerError(RuntimeError):
    pass


def validate_lease_seconds(value: int) -> None:
    if type(value) is not int or not 1 <= value <= MAX_LEASE_SECONDS:
        raise FactorySchedulerError(
            f"lease seconds must be an integer from 1 through {MAX_LEASE_SECONDS}"
        )


def validate_lease_epoch(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_LEASE_EPOCH:
        raise FactorySchedulerError(
            f"lease epoch must be an integer from 1 through {MAX_LEASE_EPOCH}"
        )
    return value


def validate_phase_version(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_LEASE_EPOCH:
        raise FactorySchedulerError("phase version must be a positive bounded integer")
    return value


def aware_utc(value: datetime) -> datetime:
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduler timestamps must be timezone-aware")
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("scheduler timestamp is outside the UTC range") from exc


def scheduler_timestamp(value: datetime) -> str:
    return aware_utc(value).isoformat()
