from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeGuard, get_args

RECEIPT_SCHEMA_VERSION: Final[int] = 1
MAX_RECEIPT_BYTES: Final[int] = 4_096
MAX_FIELD_LENGTH: Final[int] = 96
MAX_LIST_ITEMS: Final[int] = 16
MAX_SUMMARIZED_PATHS: Final[int] = 640
MAX_SUMMARIZED_FILES: Final[int] = 512
MAX_SUMMARIZED_FILE_BYTES: Final[int] = 1_000_000
MAX_SUMMARIZED_BYTES: Final[int] = 2_000_000
MAX_PROVIDER_CALLS: Final[int] = 16
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
