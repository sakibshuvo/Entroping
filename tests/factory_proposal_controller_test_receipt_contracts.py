from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal, Self, TypeGuard, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

RECEIPT_SCHEMA_VERSION: Final[int] = 1
MAX_RECEIPT_BYTES: Final[int] = 4_096
MAX_FIELD_LENGTH: Final[int] = 96
MAX_LIST_ITEMS: Final[int] = 16
MAX_SUMMARIZED_PATHS: Final[int] = 640
MAX_SUMMARIZED_FILES: Final[int] = 512
MAX_SUMMARIZED_FILE_BYTES: Final[int] = 1_000_000
MAX_SUMMARIZED_BYTES: Final[int] = 2_000_000
MAX_PROVIDER_CALLS: Final[int] = 16
MAX_DURATION_MS: Final[int] = 60_000
type CrashPoint = Literal["none", "purge"]
type InvariantClass = Literal[
    "no-provider",
    "no-source-mutation",
    "no-worker",
    "offline",
]
type ReturnClass = Literal[
    "assigned",
    "blocked",
    "bounded-complete",
    "exit-1",
    "fail-closed",
    "input-invalid",
    "one-capacity-winner",
    "recovered",
    "replay-conflict",
    "retry-scheduled",
    "settled-replay",
    "uncertain",
    "would-assign",
    "would-recover",
]
type DenialReason = Literal["budget", "quota", "capacity-full", "lease-held"]
CRASH_POINTS: Final[frozenset[str]] = frozenset(get_args(CrashPoint.__value__))
ALLOWED_INVARIANTS: Final[frozenset[str]] = frozenset(get_args(InvariantClass.__value__))
ALLOWED_RETURNS: Final[frozenset[str]] = frozenset(get_args(ReturnClass.__value__))
ALLOWED_PATHS: Final[frozenset[str]] = frozenset({".entroping", "fake-worker", "provider-model"})
FORBIDDEN_TEXT: Final[tuple[str, ...]] = (
    "secret",
    "token",
    "credential",
    "password",
    "api-key",
    "provider-output",
)
DENIAL_REASONS: Final[frozenset[str]] = frozenset(get_args(DenialReason.__value__))
type BoundedCount = Annotated[int, Field(strict=True, ge=0, le=MAX_SUMMARIZED_FILES)]
type BoundedBytes = Annotated[int, Field(strict=True, ge=0, le=MAX_SUMMARIZED_BYTES)]
type ProviderCount = Annotated[int, Field(strict=True, ge=0, le=MAX_PROVIDER_CALLS)]
type Duration = Annotated[int, Field(strict=True, ge=0, le=MAX_DURATION_MS)]


class ReceiptDurations(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    compose: Duration
    verify: Duration


class ReceiptPayload(BaseModel):
    """Strict, versioned serialized evidence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    scenario: Annotated[str, Field(pattern=r"^[a-z0-9-]{1,80}$", strict=True)]
    crash_point: CrashPoint
    return_class: ReturnClass
    state_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
    fake_call_count: ProviderCount
    provider_call_count: ProviderCount
    changed_paths: Annotated[
        tuple[Literal[".entroping", "fake-worker", "provider-model"], ...],
        Field(max_length=MAX_LIST_ITEMS),
    ]
    file_total: BoundedCount
    byte_total: BoundedBytes
    durations_ms: ReceiptDurations
    invariants: Annotated[tuple[InvariantClass, ...], Field(max_length=MAX_LIST_ITEMS)]

    @model_validator(mode="after")
    def unique_categories(self) -> Self:
        if len(set(self.changed_paths)) != len(self.changed_paths):
            raise ValueError("changed path categories must be unique")
        if len(set(self.invariants)) != len(self.invariants):
            raise ValueError("invariants must be unique")
        return self


@dataclass(frozen=True, slots=True)
class CompositionOutcome:
    decision: Literal["assigned", "blocked"]
    assignment_id: str | None
    denial_reason: DenialReason | None

    @classmethod
    def accepted(cls, assignment_id: str) -> CompositionOutcome:
        if not assignment_id:
            raise AssertionError("accepted composition requires an assignment identifier")
        return cls("assigned", assignment_id, None)

    @classmethod
    def denied(cls, reason: str) -> CompositionOutcome:
        if not _is_denial_reason(reason):
            raise AssertionError("composition denial reason is not categorical")
        return cls("blocked", None, reason)


@dataclass(frozen=True, slots=True)
class StateSummary:
    digest: str
    file_total: int
    byte_total: int
    category_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ScenarioReceipt:
    scenario: str
    crash_point: CrashPoint
    return_class: ReturnClass
    state_digest: str
    fake_call_count: int
    provider_call_count: int
    changed_paths: tuple[str, ...]
    file_total: int
    byte_total: int
    invariants: tuple[InvariantClass, ...]
    path: Path


def _is_denial_reason(value: str) -> TypeGuard[DenialReason]:
    return value in DENIAL_REASONS
