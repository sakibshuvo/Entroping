"""Strict schema parsing for aggregate-PR finish evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Never

from finish_issue_aggregate_support import AggregateEvidenceError

SCHEMA = "entroping.aggregate-pr-finish-evidence.v1"
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class AggregateEntry:
    issue_number: int
    source_branch: str
    source_commit: str
    integrated_commit: str
    patch_id: str


@dataclass(frozen=True, slots=True)
class AggregateManifest:
    schema_version: str
    repository: str
    aggregate_pr_number: int
    aggregate_merge_commit: str
    entries: tuple[AggregateEntry, ...]


def unique_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Reject duplicate keys at every JSON object level."""
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise AggregateEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value: str) -> Never:
    """Reject NaN and infinities at the JSON boundary."""
    raise AggregateEvidenceError("non-finite JSON value")


def parse_manifest(payload: bytes) -> AggregateManifest:
    """Parse one bounded manifest with an exact schema and types."""
    try:
        value = json.loads(payload, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
        return _parse_root(value)
    except (
        AggregateEvidenceError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        RecursionError,
    ) as exc:
        raise AggregateEvidenceError("manifest schema is invalid") from exc


def _parse_root(value: JsonValue) -> AggregateManifest:
    if not isinstance(value, dict):
        raise AggregateEvidenceError("manifest schema is invalid")
    _require_keys(
        value,
        {
            "schema_version",
            "repository",
            "aggregate_pr_number",
            "aggregate_merge_commit",
            "entries",
        },
    )
    schema = value["schema_version"]
    repository = value["repository"]
    pr_number = value["aggregate_pr_number"]
    merge_commit = value["aggregate_merge_commit"]
    raw_entries = value["entries"]
    if (
        schema != SCHEMA
        or not isinstance(repository, str)
        or len(repository.encode()) > 255
        or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None
        or type(pr_number) is not int
        or not 1 <= pr_number <= 2_147_483_647
        or not isinstance(merge_commit, str)
        or re.fullmatch(r"[a-f0-9]{40}", merge_commit) is None
        or not isinstance(raw_entries, list)
        or not 1 <= len(raw_entries) <= 256
    ):
        raise AggregateEvidenceError("manifest schema is invalid")
    entries = tuple(_parse_entry(item) for item in raw_entries)
    manifest = AggregateManifest(schema, repository, pr_number, merge_commit, entries)
    _reject_duplicates(manifest)
    return manifest


def _parse_entry(value: JsonValue) -> AggregateEntry:
    if not isinstance(value, dict):
        raise AggregateEvidenceError("manifest schema is invalid")
    _require_keys(
        value,
        {"issue_number", "source_branch", "source_commit", "integrated_commit", "patch_id"},
    )
    issue = value["issue_number"]
    branch = value["source_branch"]
    source = value["source_commit"]
    integrated = value["integrated_commit"]
    patch_id = value["patch_id"]
    if type(issue) is not int or not 1 <= issue <= 2_147_483_647:
        raise AggregateEvidenceError("manifest schema is invalid")
    if (
        not isinstance(branch, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,159}", branch) is None
    ):
        raise AggregateEvidenceError("manifest schema is invalid")
    if not isinstance(source, str) or not isinstance(integrated, str) or not isinstance(
        patch_id, str
    ):
        raise AggregateEvidenceError("manifest schema is invalid")
    if any(
        re.fullmatch(r"[a-f0-9]{40}", item) is None
        for item in (source, integrated, patch_id)
    ):
        raise AggregateEvidenceError("manifest schema is invalid")
    return AggregateEntry(issue, branch, source, integrated, patch_id)


def _require_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise AggregateEvidenceError("manifest schema is invalid")


def _reject_duplicates(manifest: AggregateManifest) -> None:
    fields = (
        tuple(entry.issue_number for entry in manifest.entries),
        tuple(entry.source_branch for entry in manifest.entries),
        tuple(entry.source_commit for entry in manifest.entries),
        tuple(entry.integrated_commit for entry in manifest.entries),
    )
    if any(len(items) != len(set(items)) for items in fields):
        raise AggregateEvidenceError("manifest contains duplicate mappings")
