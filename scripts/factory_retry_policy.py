from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scripts.factory_scheduler_models import WorkerClass

SnapshotSource = Literal["github", "provider-capability", "price", "quota"]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class _StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )


class RecoverySnapshot(_StrictModel):
    source: SnapshotSource
    observed_at: datetime
    expires_at: datetime
    digest: Digest

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        observed = _aware_utc(self.observed_at)
        expires = _aware_utc(self.expires_at)
        if observed >= expires:
            raise ValueError("recovery snapshot expiry must follow observation")
        if expires - observed > timedelta(days=1):
            raise ValueError("recovery snapshot lifetime exceeds one day")
        return self


class RetryPolicy(_StrictModel):
    base_delay_seconds: Annotated[int, Field(ge=1, le=3_600)] = 30
    max_delay_seconds: Annotated[int, Field(ge=1, le=86_400)] = 3_600
    max_attempts: Annotated[int, Field(ge=1, le=20)] = 5
    max_elapsed_seconds: Annotated[int, Field(ge=1, le=604_800)] = 86_400
    jitter_percent: Annotated[int, Field(ge=0, le=50)] = 20
    retry_after_ceiling_seconds: Annotated[int, Field(ge=0, le=86_400)] = 86_400

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("retry base delay exceeds maximum delay")
        if self.max_delay_seconds > self.max_elapsed_seconds:
            raise ValueError("retry maximum delay exceeds elapsed-time ceiling")
        return self


def retry_not_before(
    policy: RetryPolicy,
    *,
    job_id: str,
    attempt_count: int,
    observed_at: datetime,
    retry_after_seconds: int | None,
) -> datetime:
    observed = _aware_utc(observed_at)
    if attempt_count < 1 or attempt_count > 20:
        raise ValueError("retry attempt count is out of bounds")
    exponent = min(attempt_count - 1, 19)
    delay = min(policy.base_delay_seconds * (2**exponent), policy.max_delay_seconds)
    jitter_span = delay * policy.jitter_percent // 100
    if jitter_span:
        material = f"{job_id}\0{attempt_count}".encode()
        offset = int.from_bytes(hashlib.sha256(material).digest()[:8]) % ((2 * jitter_span) + 1)
        delay += offset - jitter_span
    if retry_after_seconds is not None:
        if isinstance(retry_after_seconds, bool) or not 0 <= retry_after_seconds <= 86_400:
            raise ValueError("retry hint is out of bounds")
        hint = min(
            retry_after_seconds,
            policy.retry_after_ceiling_seconds,
            policy.max_delay_seconds,
        )
        delay = max(delay, hint)
    delay = min(max(1, delay), policy.max_delay_seconds)
    try:
        return observed + timedelta(seconds=delay)
    except OverflowError as exc:
        raise ValueError("retry deadline is out of bounds") from exc


def freshness_failure(
    snapshots: tuple[RecoverySnapshot, ...],
    *,
    worker_class: WorkerClass,
    observed_at: datetime,
) -> str | None:
    observed = _aware_utc(observed_at)
    if len(snapshots) > 4:
        return "snapshot-count-invalid"
    indexed: dict[SnapshotSource, RecoverySnapshot] = {}
    for snapshot in snapshots:
        if snapshot.source in indexed:
            return "snapshot-source-duplicate"
        indexed[snapshot.source] = snapshot
    required: tuple[SnapshotSource, ...] = (
        ("github", "provider-capability", "price", "quota")
        if worker_class == "paid"
        else ("github", "provider-capability")
    )
    for source in required:
        required_snapshot = indexed.get(source)
        reason_source = source.replace("provider-capability", "provider")
        if required_snapshot is None:
            return f"{reason_source}-snapshot-missing"
        if _aware_utc(required_snapshot.observed_at) > observed:
            return f"{reason_source}-snapshot-future"
        if _aware_utc(required_snapshot.expires_at) <= observed:
            return f"{reason_source}-snapshot-stale"
    return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
