"""Repository-only guard for the tracked experimental report policy."""

from __future__ import annotations

import re
from datetime import date
from typing import TypedDict, cast

SCHEMA_VERSION = "entroping.experimental-report-growth-policy.v1"
_ADOPTION_STATES = frozenset({"missing", "partial", "validated"})
_DISPOSITIONS = frozenset(
    {"retain-experimental", "consolidate", "retire", "promote"}
)
_COMMAND_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


class AdoptionEvidence(TypedDict):
    """Review evidence recorded for one experimental command."""

    state: str
    pointer: str


class PolicyEntry(TypedDict):
    """One repository governance record."""

    command: str
    owner: str
    adoption_evidence: AdoptionEvidence
    disposition: str
    review_on: str


class PolicyValidationError(ValueError):
    """Actionable tracked-policy validation failure."""


def policy_entry(
    command: str,
    *,
    adoption_state: str = "missing",
    disposition: str = "retain-experimental",
) -> PolicyEntry:
    """Build one minimal policy entry for drift-focused tests."""

    return {
        "command": command,
        "owner": "qa-brain",
        "adoption_evidence": {
            "state": adoption_state,
            "pointer": "https://github.com/sakibshuvo/Entroping/issues/306",
        },
        "disposition": disposition,
        "review_on": "2026-08-31",
    }


def validate_experimental_report_growth_policy(
    document: object,
    live_commands: tuple[str, ...],
) -> tuple[PolicyEntry, ...]:
    """Validate the tracked policy and its exact resolved panel membership."""

    root = _mapping(document, "policy")
    _require_keys(root, {"schema_version", "entries"}, "policy")
    if root["schema_version"] != SCHEMA_VERSION:
        raise PolicyValidationError(f"schema_version must be {SCHEMA_VERSION!r}")
    raw_entries = root["entries"]
    if type(raw_entries) is not list:
        raise PolicyValidationError("entries must be an array")
    entries = tuple(
        _validate_entry(value, index)
        for index, value in enumerate(cast(list[object], raw_entries))
    )

    policy_commands = tuple(entry["command"] for entry in entries)
    if len(set(policy_commands)) != len(policy_commands):
        raise PolicyValidationError("entries.command contains a duplicate command")
    if len(set(live_commands)) != len(live_commands):
        raise PolicyValidationError("live commands contain a duplicate command")

    policy_set = frozenset(policy_commands)
    live_set = frozenset(live_commands)
    missing = tuple(command for command in live_commands if command not in policy_set)
    if missing:
        raise PolicyValidationError(f"missing live command(s): {', '.join(missing)}")
    stale = tuple(command for command in policy_commands if command not in live_set)
    if stale:
        raise PolicyValidationError(f"stale command(s): {', '.join(stale)}")
    if policy_commands != live_commands:
        mismatch = next(
            index
            for index, (expected, actual) in enumerate(
                zip(live_commands, policy_commands, strict=True)
            )
            if expected != actual
        )
        raise PolicyValidationError(
            "order mismatch at position "
            f"{mismatch + 1}: expected {live_commands[mismatch]!r}, "
            f"found {policy_commands[mismatch]!r}"
        )
    return entries


def _validate_entry(value: object, index: int) -> PolicyEntry:
    entry = _mapping(value, f"entries[{index}]")
    _require_keys(
        entry,
        {"command", "owner", "adoption_evidence", "disposition", "review_on"},
        f"entries[{index}]",
    )
    command = _nonempty_text(entry["command"], f"entries[{index}].command")
    if _COMMAND_PATTERN.fullmatch(command) is None:
        raise PolicyValidationError(f"entries[{index}].command is invalid")
    owner = _nonempty_text(entry["owner"], f"entries[{index}].owner")

    evidence = _mapping(
        entry["adoption_evidence"], f"entries[{index}].adoption_evidence"
    )
    _require_keys(
        evidence,
        {"state", "pointer"},
        f"entries[{index}].adoption_evidence",
    )
    state = _nonempty_text(
        evidence["state"], f"entries[{index}].adoption_evidence.state"
    )
    if state not in _ADOPTION_STATES:
        raise PolicyValidationError(
            f"entries[{index}].adoption_evidence.state is invalid"
        )
    pointer = _nonempty_text(
        evidence["pointer"], f"entries[{index}].adoption_evidence.pointer"
    )

    disposition = _nonempty_text(
        entry["disposition"], f"entries[{index}].disposition"
    )
    if disposition not in _DISPOSITIONS:
        raise PolicyValidationError(f"entries[{index}].disposition is invalid")
    if disposition == "promote" and state != "validated":
        raise PolicyValidationError(
            f"{command}: promote requires validated adoption evidence"
        )

    review_on = _nonempty_text(entry["review_on"], f"entries[{index}].review_on")
    try:
        parsed_review_on = date.fromisoformat(review_on)
    except ValueError:
        raise PolicyValidationError(
            f"entries[{index}].review_on must be an ISO calendar date"
        ) from None
    if parsed_review_on.isoformat() != review_on:
        raise PolicyValidationError(
            f"entries[{index}].review_on must use YYYY-MM-DD"
        )

    return {
        "command": command,
        "owner": owner,
        "adoption_evidence": {"state": state, "pointer": pointer},
        "disposition": disposition,
        "review_on": review_on,
    }


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PolicyValidationError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _nonempty_text(value: object, field: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise PolicyValidationError(f"{field} must be non-empty trimmed text")
    return value


def _require_keys(
    value: dict[str, object],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PolicyValidationError(
            f"{field} fields mismatch; missing={missing!r}, extra={extra!r}"
        )
