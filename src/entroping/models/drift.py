"""Pure models for deterministic drift reports."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

DriftFindingKind = Literal[
    "missing_baseline",
    "missing_current_test",
    "new_current_test",
    "result_changed",
    "assertions_changed",
    "response_snapshot_missing",
    "response_status_changed",
    "response_header_changed",
    "response_body_shape_changed",
    "latency_regressed",
]
DriftSeverity = Literal["info", "warning", "error"]
DriftValue = str | int | list[str] | None


@dataclass(frozen=True)
class DriftBaselineTest:
    """Small baseline row for one governed Hurl test."""

    path: str
    status: str
    exit_code: int
    rule_ids: tuple[str, ...]
    duration_ms: int | None = None
    response_status_code: int | None = None
    response_headers: tuple[tuple[str, str], ...] = ()
    response_body_shape: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriftBaseline:
    """Loaded deterministic drift baseline."""

    project: str
    environment: str
    tests: tuple[DriftBaselineTest, ...]


@dataclass(frozen=True)
class DriftFinding:
    """One deterministic drift finding."""

    kind: DriftFindingKind
    severity: DriftSeverity
    path: str
    message: str
    baseline: Mapping[str, DriftValue]
    current: Mapping[str, DriftValue]


@dataclass(frozen=True)
class DriftReportSummary:
    """Aggregate drift-report summary."""

    baseline_tests: int
    current_tests: int
    findings: int
    drifted: int
    missing_baseline: bool


@dataclass(frozen=True)
class DriftReport:
    """Serializable deterministic drift report."""

    project: str
    environment: str
    generated_at: str
    baseline_path: str
    summary: DriftReportSummary
    findings: tuple[DriftFinding, ...]
