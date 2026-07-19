"""Offline governance policy for experimental report commands."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from entroping.core.bounded_read import BoundedReadError, read_text_bounded

EXPERIMENTAL_REPORT_GROWTH_POLICY_SCHEMA_VERSION: Final = (
    "entroping.experimental-report-growth-policy.v1"
)
EXPERIMENTAL_REPORT_GROWTH_POLICY_MAX_BYTES: Final = 256 * 1024

type AdoptionState = Literal["missing", "partial", "validated"]
type ExperimentalDisposition = Literal[
    "retain-experimental",
    "consolidate",
    "retire",
    "promote",
]
type CommandName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9-]*$"),
]
type NonEmptyText = Annotated[
    str,
    StringConstraints(pattern=r"^\S(?:.*\S)?$"),
]
type ReviewDateText = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
]


@dataclass(frozen=True, slots=True)
class ExperimentalReportPolicyError(Exception):
    """Actionable failure at the experimental-report policy boundary."""

    field: str
    detail: str
    path: Path | None = None

    def __str__(self) -> str:
        location = f"{self.path}: " if self.path is not None else ""
        return f"{location}{self.field}: {self.detail}"


class _DuplicateJsonMemberError(ValueError):
    def __init__(self, member: str) -> None:
        self.member = member
        super().__init__(f"duplicate JSON member: {member}")


class ExperimentalReportAdoptionEvidence(BaseModel):
    """Evidence state and review pointer for one experimental command."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: AdoptionState
    pointer: NonEmptyText


class ExperimentalReportPolicyEntry(BaseModel):
    """Governance decision for one experimental report command."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command: CommandName
    owner: NonEmptyText
    adoption_evidence: ExperimentalReportAdoptionEvidence
    disposition: ExperimentalDisposition
    review_on: ReviewDateText

    @field_validator("review_on")
    @classmethod
    def validate_review_date(cls, value: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(value)
        except ValueError:
            raise PydanticCustomError(
                "review_on",
                "review_on must be an ISO calendar date (YYYY-MM-DD)",
            ) from None
        return value

    @model_validator(mode="after")
    def validate_promotion_evidence(self) -> Self:
        if (
            self.disposition == "promote"
            and self.adoption_evidence.state != "validated"
        ):
            raise PydanticCustomError(
                "promotion_evidence",
                (
                    "command '{command}': disposition 'promote' requires "
                    "adoption_evidence.state 'validated'"
                ),
                {"command": self.command},
            )
        return self


class ExperimentalReportGrowthPolicy(BaseModel):
    """Versioned ordered policy for the complete experimental report panel."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["entroping.experimental-report-growth-policy.v1"]
    entries: tuple[ExperimentalReportPolicyEntry, ...]

    @model_validator(mode="after")
    def validate_unique_commands(self) -> Self:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.command in seen:
                raise PydanticCustomError(
                    "duplicate_command",
                    "entries.command: duplicate command '{command}'",
                    {"command": entry.command},
                )
            seen.add(entry.command)
        return self


def load_experimental_report_growth_policy(
    path: Path,
) -> ExperimentalReportGrowthPolicy:
    """Load a local policy without imports, network calls, or runtime mutation."""

    try:
        document = read_text_bounded(
            path,
            max_bytes=EXPERIMENTAL_REPORT_GROWTH_POLICY_MAX_BYTES,
            label="experimental report growth policy",
        )
    except BoundedReadError as exc:
        raise ExperimentalReportPolicyError(
            field="path",
            detail=str(exc),
            path=path,
        ) from None

    _require_unambiguous_json(document, path)
    try:
        return ExperimentalReportGrowthPolicy.model_validate_json(document)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = _format_error_location(first_error["loc"])
        detail = first_error["msg"]
        raise ExperimentalReportPolicyError(
            field=location,
            detail=detail,
            path=path,
        ) from None


def _require_unambiguous_json(document: str, path: Path) -> None:
    try:
        json.loads(
            document,
            object_pairs_hook=_object_without_duplicate_members,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except _DuplicateJsonMemberError as exc:
        raise ExperimentalReportPolicyError(
            field="document",
            detail=str(exc),
            path=path,
        ) from None
    except (ValueError, RecursionError):
        raise ExperimentalReportPolicyError(
            field="document",
            detail="invalid JSON",
            path=path,
        ) from None


def _reject_nonstandard_json_constant(constant: str) -> object:
    raise ValueError(f"nonstandard JSON constant: {constant}")


def _object_without_duplicate_members(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document_object: dict[str, object] = {}
    for member, value in pairs:
        if member in document_object:
            raise _DuplicateJsonMemberError(member)
        document_object[member] = value
    return document_object


def validate_experimental_report_growth_policy(
    policy: ExperimentalReportGrowthPolicy,
    live_commands: tuple[str, ...],
) -> None:
    """Require policy commands to match the live experimental panel exactly."""

    policy_commands = tuple(entry.command for entry in policy.entries)
    _require_unique_live_commands(live_commands)
    _require_no_missing_commands(policy_commands, live_commands)
    _require_no_stale_commands(policy_commands, live_commands)
    _require_matching_command_order(policy_commands, live_commands)


def _require_unique_live_commands(live_commands: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for command in live_commands:
        if command in seen:
            raise ExperimentalReportPolicyError(
                field="live_commands",
                detail=f"duplicate live command: {command}",
            )
        seen.add(command)


def _require_no_missing_commands(
    policy_commands: tuple[str, ...],
    live_commands: tuple[str, ...],
) -> None:
    policy_set = frozenset(policy_commands)
    missing = tuple(command for command in live_commands if command not in policy_set)
    if missing:
        raise ExperimentalReportPolicyError(
            field="entries.command",
            detail=f"missing live command(s): {', '.join(missing)}",
        )


def _require_no_stale_commands(
    policy_commands: tuple[str, ...],
    live_commands: tuple[str, ...],
) -> None:
    live_set = frozenset(live_commands)
    stale = tuple(command for command in policy_commands if command not in live_set)
    if stale:
        raise ExperimentalReportPolicyError(
            field="entries.command",
            detail=f"stale command(s): {', '.join(stale)}",
        )


def _require_matching_command_order(
    policy_commands: tuple[str, ...],
    live_commands: tuple[str, ...],
) -> None:
    if policy_commands != live_commands:
        mismatch_index = next(
            index
            for index, (expected, actual) in enumerate(
                zip(live_commands, policy_commands, strict=True),
            )
            if expected != actual
        )
        raise ExperimentalReportPolicyError(
            field="entries.command",
            detail=(
                f"order mismatch at position {mismatch_index + 1}: expected "
                f"{live_commands[mismatch_index]!r}, found {policy_commands[mismatch_index]!r}"
            ),
        )


def _format_error_location(location: tuple[int | str, ...]) -> str:
    rendered = ""
    for part in location:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}" if rendered else part
    return rendered or "policy"
