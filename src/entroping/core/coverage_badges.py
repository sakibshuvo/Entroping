"""Generate local shields-compatible coverage badge JSON from Entroping reports."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from entroping.core.safe_write import SafeWriteError, safe_write_text

SHIELDS_ENDPOINT_SCHEMA_VERSION = 1


class BadgeReportError(ValueError):
    """Raised when badge reports cannot be generated from local artifacts."""


@dataclass(frozen=True)
class CoverageBadge:
    """One shields endpoint JSON payload and target filename."""

    filename: str
    payload: dict[str, object]


@dataclass(frozen=True)
class CoverageBadgeWriteResult:
    """Written coverage badge artifact paths."""

    output_dir: Path
    artifacts: tuple[Path, ...]


def coverage_badge_payload(*, label: str, covered: int, total: int) -> dict[str, object]:
    """Build one shields endpoint payload for a coverage ratio."""

    if covered < 0 or total < 0 or covered > total:
        msg = "Badge coverage counts must satisfy 0 <= covered <= total"
        raise BadgeReportError(msg)
    if total == 0:
        message = "0/0 (n/a)"
        color = "lightgrey"
    else:
        percentage = round((covered / total) * 100)
        message = f"{covered}/{total} ({percentage}%)"
        color = _coverage_color(percentage)
    return {
        "schemaVersion": SHIELDS_ENDPOINT_SCHEMA_VERSION,
        "label": label,
        "message": message,
        "color": color,
    }


def build_coverage_badges(
    *,
    run_report: Mapping[str, object],
    policy_report: Mapping[str, object],
    openapi_report: Mapping[str, object],
    traceability_report: Mapping[str, object],
) -> tuple[CoverageBadge, ...]:
    """Build policy, OpenAPI, and traceability badges from existing reports."""

    policy_covered, policy_total = _policy_gate_coverage(
        run_report=run_report,
        policy_report=policy_report,
    )
    openapi_covered, openapi_total = _openapi_operation_coverage(openapi_report)
    story_covered, story_total = _story_traceability_coverage(traceability_report)
    return (
        CoverageBadge(
            filename="policy-gates.json",
            payload=coverage_badge_payload(
                label="policy gates",
                covered=policy_covered,
                total=policy_total,
            ),
        ),
        CoverageBadge(
            filename="openapi-operations.json",
            payload=coverage_badge_payload(
                label="openapi ops",
                covered=openapi_covered,
                total=openapi_total,
            ),
        ),
        CoverageBadge(
            filename="story-traceability.json",
            payload=coverage_badge_payload(
                label="story links",
                covered=story_covered,
                total=story_total,
            ),
        ),
    )


def write_coverage_badges(
    *,
    run_json_path: Path,
    policy_json_path: Path,
    openapi_json_path: Path,
    traceability_json_path: Path,
    output_dir: Path,
) -> CoverageBadgeWriteResult:
    """Read local source reports and write deterministic shields endpoint JSON files."""

    run_report = _read_json_object(run_json_path, label="run report")
    policy_report = _read_json_object(policy_json_path, label="policy report")
    openapi_report = _read_json_object(openapi_json_path, label="OpenAPI audit report")
    traceability_report = _read_json_object(
        traceability_json_path,
        label="traceability report",
    )
    badges = build_coverage_badges(
        run_report=run_report,
        policy_report=policy_report,
        openapi_report=openapi_report,
        traceability_report=traceability_report,
    )

    artifacts: list[Path] = []
    for badge in badges:
        destination = output_dir / badge.filename
        try:
            artifacts.append(
                safe_write_text(
                    destination,
                    json.dumps(badge.payload, indent=2, sort_keys=True) + "\n",
                    artifact="coverage badge",
                )
            )
        except SafeWriteError as exc:
            raise BadgeReportError(str(exc)) from exc
    return CoverageBadgeWriteResult(
        output_dir=output_dir,
        artifacts=tuple(artifacts),
    )


def _policy_gate_coverage(
    *,
    run_report: Mapping[str, object],
    policy_report: Mapping[str, object],
) -> tuple[int, int]:
    _require_schema(run_report, expected="entroping.run-report.v1", label="run report")
    _require_schema(
        policy_report,
        expected="entroping.effective-policy-report.v1",
        label="policy report",
    )
    gate_ids = {
        gate_id
        for gate in _mapping_items(policy_report, key="gates", label="policy report")
        for gate_id in (_required_string(gate, key="id", label="policy gate"),)
    }
    applied_rule_ids = {
        rule_id
        for test in _mapping_items(run_report, key="tests", label="run report")
        for rule_id in _string_sequence(test, key="rule_ids", label="run test")
    }
    return (len(gate_ids & applied_rule_ids), len(gate_ids))


def _openapi_operation_coverage(openapi_report: Mapping[str, object]) -> tuple[int, int]:
    _require_schema(
        openapi_report,
        expected="entroping.openapi-audit.v1",
        label="OpenAPI audit report",
    )
    summary = _required_mapping(openapi_report, key="summary", label="OpenAPI audit report")
    covered = _required_nonnegative_int(
        summary,
        key="covered_operations",
        label="OpenAPI audit summary",
    )
    total = _required_nonnegative_int(
        summary,
        key="total_operations",
        label="OpenAPI audit summary",
    )
    if covered > total:
        msg = "OpenAPI audit summary has covered_operations greater than total_operations"
        raise BadgeReportError(msg)
    return (covered, total)


def _story_traceability_coverage(
    traceability_report: Mapping[str, object],
) -> tuple[int, int]:
    _require_schema(
        traceability_report,
        expected="entroping.traceability-report.v1",
        label="traceability report",
    )
    linked_paths = {
        test_path
        for story in _mapping_items(traceability_report, key="stories", label="traceability report")
        for test_path in _string_sequence(story, key="test_paths", label="traceability story")
    }
    missing_paths = {
        test_path
        for finding in _mapping_items(
            traceability_report,
            key="findings",
            label="traceability report",
        )
        if finding.get("kind") == "missing_story_id"
        for test_path in (_required_string(finding, key="test_path", label="traceability finding"),)
    }
    return (len(linked_paths), len(linked_paths | missing_paths))


def _coverage_color(percentage: int) -> str:
    if percentage >= 90:
        return "brightgreen"
    if percentage >= 75:
        return "green"
    if percentage >= 50:
        return "yellow"
    if percentage > 0:
        return "orange"
    return "red"


def _read_json_object(path: Path, *, label: str) -> Mapping[str, object]:
    if not path.exists():
        msg = f"Missing {label}: {path}"
        raise BadgeReportError(msg)
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {label} {path}: {exc.msg}"
        raise BadgeReportError(msg) from exc
    except OSError as exc:
        msg = f"Could not read {label} {path}: {exc}"
        raise BadgeReportError(msg) from exc
    if not isinstance(raw, Mapping):
        msg = f"{label} must be a JSON object: {path}"
        raise BadgeReportError(msg)
    return cast(Mapping[str, object], raw)


def _require_schema(data: Mapping[str, object], *, expected: str, label: str) -> None:
    schema_version = data.get("schema_version")
    if schema_version != expected:
        msg = f"{label} must use schema_version {expected}"
        raise BadgeReportError(msg)


def _mapping_items(
    data: Mapping[str, object],
    *,
    key: str,
    label: str,
) -> tuple[Mapping[str, object], ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"{label} field {key!r} must be an array"
        raise BadgeReportError(msg)
    items: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            msg = f"{label} field {key!r} must contain JSON objects"
            raise BadgeReportError(msg)
        items.append(cast(Mapping[str, object], item))
    return tuple(items)


def _required_mapping(
    data: Mapping[str, object],
    *,
    key: str,
    label: str,
) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        msg = f"{label} field {key!r} must be a JSON object"
        raise BadgeReportError(msg)
    return cast(Mapping[str, object], value)


def _required_string(data: Mapping[str, object], *, key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{label} field {key!r} must be a non-empty string"
        raise BadgeReportError(msg)
    return value.strip()


def _string_sequence(data: Mapping[str, object], *, key: str, label: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"{label} field {key!r} must be an array"
        raise BadgeReportError(msg)
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            msg = f"{label} field {key!r} must contain non-empty strings"
            raise BadgeReportError(msg)
        strings.append(item.strip())
    return tuple(strings)


def _required_nonnegative_int(data: Mapping[str, object], *, key: str, label: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value < 0:
        msg = f"{label} field {key!r} must be a non-negative integer"
        raise BadgeReportError(msg)
    return value
