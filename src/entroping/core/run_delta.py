"""Deterministic run-to-run delta reports."""

from dataclasses import dataclass
from html import escape
from pathlib import PurePosixPath, PureWindowsPath
from typing import cast

from entroping.models.report import RunReport, RunTestReport

RUN_DELTA_REPORT_SCHEMA_VERSION = "entroping.run-delta-report.v1"


class RunDeltaError(ValueError):
    """Raised when run reports cannot be compared safely."""


@dataclass(frozen=True)
class RunFailureDelta:
    """Failure status difference for one Hurl test path."""

    path: str
    base_status: str | None
    current_status: str | None
    base_exit_code: int | None
    current_exit_code: int | None
    base_rule_ids: tuple[str, ...]
    current_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class RunLatencyDelta:
    """Duration difference for one Hurl test path."""

    path: str
    base_duration_ms: int
    current_duration_ms: int
    delta_ms: int


@dataclass(frozen=True)
class RunPolicyGateDelta:
    """Rule-ID difference for one Hurl test path."""

    path: str
    added_rule_ids: tuple[str, ...]
    resolved_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class RunDeltaReport:
    """A schema-versioned comparison between two run reports."""

    base_project: str
    current_project: str
    base_environment: str
    current_environment: str
    base_generated_at: str
    current_generated_at: str
    base_total: int
    current_total: int
    added_failures: tuple[RunFailureDelta, ...]
    resolved_failures: tuple[RunFailureDelta, ...]
    changed_failures: tuple[RunFailureDelta, ...]
    unchanged_failures: tuple[RunFailureDelta, ...]
    latency_deltas: tuple[RunLatencyDelta, ...]
    policy_gate_deltas: tuple[RunPolicyGateDelta, ...]

    @property
    def passed(self) -> bool:
        """Return whether the current run introduced no new or changed failures."""

        return not self.added_failures and not self.changed_failures


def build_run_delta_report(*, base: RunReport, current: RunReport) -> RunDeltaReport:
    """Compare two deterministic run reports without inspecting raw output bodies."""

    base_tests = _index_tests(base.tests, side="base")
    current_tests = _index_tests(current.tests, side="current")
    paths = tuple(sorted(set(base_tests) | set(current_tests)))

    added_failures: list[RunFailureDelta] = []
    resolved_failures: list[RunFailureDelta] = []
    changed_failures: list[RunFailureDelta] = []
    unchanged_failures: list[RunFailureDelta] = []
    latency_deltas: list[RunLatencyDelta] = []
    policy_gate_deltas: list[RunPolicyGateDelta] = []

    for path in paths:
        base_test = base_tests.get(path)
        current_test = current_tests.get(path)
        if base_test is not None and current_test is not None:
            duration_delta = current_test.duration_ms - base_test.duration_ms
            if duration_delta != 0:
                latency_deltas.append(
                    RunLatencyDelta(
                        path=path,
                        base_duration_ms=base_test.duration_ms,
                        current_duration_ms=current_test.duration_ms,
                        delta_ms=duration_delta,
                    )
                )

        policy_delta = _build_policy_delta(path, base_test, current_test)
        if policy_delta is not None:
            policy_gate_deltas.append(policy_delta)

        base_failed = base_test is not None and not base_test.passed
        current_failed = current_test is not None and not current_test.passed
        if current_failed and not base_failed:
            added_failures.append(_failure_delta(path, base_test, current_test))
        elif base_failed and not current_failed:
            resolved_failures.append(_failure_delta(path, base_test, current_test))
        elif base_failed and current_failed:
            base_existing = cast(RunTestReport, base_test)
            current_existing = cast(RunTestReport, current_test)
            delta = _failure_delta(path, base_existing, current_existing)
            if _failure_signature(base_existing) != _failure_signature(current_existing):
                changed_failures.append(delta)
            else:
                unchanged_failures.append(delta)

    return RunDeltaReport(
        base_project=base.project,
        current_project=current.project,
        base_environment=base.environment,
        current_environment=current.environment,
        base_generated_at=base.generated_at,
        current_generated_at=current.generated_at,
        base_total=base.summary.total,
        current_total=current.summary.total,
        added_failures=tuple(added_failures),
        resolved_failures=tuple(resolved_failures),
        changed_failures=tuple(changed_failures),
        unchanged_failures=tuple(unchanged_failures),
        latency_deltas=tuple(latency_deltas),
        policy_gate_deltas=tuple(policy_gate_deltas),
    )


def run_delta_report_to_dict(report: RunDeltaReport) -> dict[str, object]:
    """Return the JSON-serializable run-delta report payload."""

    return {
        "schema_version": RUN_DELTA_REPORT_SCHEMA_VERSION,
        "status": "pass" if report.passed else "fail",
        "base": {
            "project": report.base_project,
            "environment": report.base_environment,
            "generated_at": report.base_generated_at,
            "total": report.base_total,
        },
        "current": {
            "project": report.current_project,
            "environment": report.current_environment,
            "generated_at": report.current_generated_at,
            "total": report.current_total,
        },
        "summary": {
            "base_total": report.base_total,
            "current_total": report.current_total,
            "added_failures": len(report.added_failures),
            "resolved_failures": len(report.resolved_failures),
            "changed_failures": len(report.changed_failures),
            "unchanged_failures": len(report.unchanged_failures),
            "latency_deltas": len(report.latency_deltas),
            "policy_gate_deltas": len(report.policy_gate_deltas),
        },
        "added_failures": [_failure_delta_to_dict(item) for item in report.added_failures],
        "resolved_failures": [_failure_delta_to_dict(item) for item in report.resolved_failures],
        "changed_failures": [_failure_delta_to_dict(item) for item in report.changed_failures],
        "unchanged_failures": [
            _failure_delta_to_dict(item) for item in report.unchanged_failures
        ],
        "latency_deltas": [_latency_delta_to_dict(item) for item in report.latency_deltas],
        "policy_gate_deltas": [
            _policy_gate_delta_to_dict(item) for item in report.policy_gate_deltas
        ],
    }


def render_run_delta_markdown(report: RunDeltaReport) -> str:
    """Render a provider-neutral Markdown summary suitable for PR comments."""

    lines = [
        "# Entroping Run Delta",
        "",
        f"Status: **{'pass' if report.passed else 'fail'}**",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Base tests | {report.base_total} |",
        f"| Current tests | {report.current_total} |",
        f"| Added failures | {len(report.added_failures)} |",
        f"| Resolved failures | {len(report.resolved_failures)} |",
        f"| Changed failures | {len(report.changed_failures)} |",
        f"| Unchanged failures | {len(report.unchanged_failures)} |",
        f"| Latency deltas | {len(report.latency_deltas)} |",
        f"| Policy gate deltas | {len(report.policy_gate_deltas)} |",
        "",
    ]
    _append_failure_section(lines, "Added Failures", report.added_failures)
    _append_failure_section(lines, "Resolved Failures", report.resolved_failures)
    _append_failure_section(lines, "Changed Failures", report.changed_failures)
    _append_failure_section(lines, "Unchanged Failures", report.unchanged_failures)
    _append_latency_section(lines, report.latency_deltas)
    _append_policy_section(lines, report.policy_gate_deltas)
    return "\n".join(lines).rstrip() + "\n"


def _index_tests(tests: tuple[RunTestReport, ...], *, side: str) -> dict[str, RunTestReport]:
    indexed: dict[str, RunTestReport] = {}
    for test in tests:
        path = test.path.strip()
        if _is_unsafe_test_path(path):
            msg = f"{side} report contains unsafe test path"
            raise RunDeltaError(msg)
        if path in indexed:
            msg = f"{side} report contains duplicate test path: {path}"
            raise RunDeltaError(msg)
        indexed[path] = test
    return indexed


def _failure_delta(
    path: str,
    base_test: RunTestReport | None,
    current_test: RunTestReport | None,
) -> RunFailureDelta:
    return RunFailureDelta(
        path=path,
        base_status=base_test.status if base_test is not None else None,
        current_status=current_test.status if current_test is not None else None,
        base_exit_code=base_test.exit_code if base_test is not None else None,
        current_exit_code=current_test.exit_code if current_test is not None else None,
        base_rule_ids=base_test.rule_ids if base_test is not None else (),
        current_rule_ids=current_test.rule_ids if current_test is not None else (),
    )


def _failure_signature(test: RunTestReport) -> tuple[str, int, tuple[str, ...]]:
    return (test.status, test.exit_code, tuple(sorted(test.rule_ids)))


def _build_policy_delta(
    path: str,
    base_test: RunTestReport | None,
    current_test: RunTestReport | None,
) -> RunPolicyGateDelta | None:
    base_rules = set(base_test.rule_ids if base_test is not None else ())
    current_rules = set(current_test.rule_ids if current_test is not None else ())
    added = tuple(sorted(current_rules - base_rules))
    resolved = tuple(sorted(base_rules - current_rules))
    if not added and not resolved:
        return None
    return RunPolicyGateDelta(path=path, added_rule_ids=added, resolved_rule_ids=resolved)


def _failure_delta_to_dict(delta: RunFailureDelta) -> dict[str, object]:
    return {
        "path": delta.path,
        "base_status": delta.base_status,
        "current_status": delta.current_status,
        "base_exit_code": delta.base_exit_code,
        "current_exit_code": delta.current_exit_code,
        "base_rule_ids": list(delta.base_rule_ids),
        "current_rule_ids": list(delta.current_rule_ids),
    }


def _latency_delta_to_dict(delta: RunLatencyDelta) -> dict[str, object]:
    return {
        "path": delta.path,
        "base_duration_ms": delta.base_duration_ms,
        "current_duration_ms": delta.current_duration_ms,
        "delta_ms": delta.delta_ms,
    }


def _policy_gate_delta_to_dict(delta: RunPolicyGateDelta) -> dict[str, object]:
    return {
        "path": delta.path,
        "added_rule_ids": list(delta.added_rule_ids),
        "resolved_rule_ids": list(delta.resolved_rule_ids),
    }


def _append_failure_section(
    lines: list[str],
    title: str,
    items: tuple[RunFailureDelta, ...],
) -> None:
    lines.append(f"## {title}")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.extend(
        (
            "",
            "| Test | Base | Current | Base rules | Current rules |",
            "| --- | --- | --- | --- | --- |",
        )
    )
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(item.path),
                    _status_cell(item.base_status, item.base_exit_code),
                    _status_cell(item.current_status, item.current_exit_code),
                    _rule_ids_cell(item.base_rule_ids),
                    _rule_ids_cell(item.current_rule_ids),
                )
            )
            + " |"
        )
    lines.append("")


def _append_latency_section(lines: list[str], items: tuple[RunLatencyDelta, ...]) -> None:
    lines.append("## Latency Deltas")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.extend(
        (
            "",
            "| Test | Base ms | Current ms | Delta ms |",
            "| --- | ---: | ---: | ---: |",
        )
    )
    for item in items:
        lines.append(
            f"| {_markdown_cell(item.path)} | {item.base_duration_ms} | "
            f"{item.current_duration_ms} | {item.delta_ms:+d} |"
        )
    lines.append("")


def _append_policy_section(lines: list[str], items: tuple[RunPolicyGateDelta, ...]) -> None:
    lines.append("## Policy Gate Deltas")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.extend(
        (
            "",
            "| Test | Added rules | Resolved rules |",
            "| --- | --- | --- |",
        )
    )
    for item in items:
        lines.append(
            f"| {_markdown_cell(item.path)} | {_rule_ids_cell(item.added_rule_ids)} | "
            f"{_rule_ids_cell(item.resolved_rule_ids)} |"
        )
    lines.append("")


def _status_cell(status: str | None, exit_code: int | None) -> str:
    if status is None:
        return "missing"
    return _markdown_cell(f"{status} ({exit_code})")


def _rule_ids_cell(rule_ids: tuple[str, ...]) -> str:
    if not rule_ids:
        return "-"
    return _markdown_cell(", ".join(rule_ids))


def _markdown_cell(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|")


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _is_unsafe_test_path(value: str) -> bool:
    if not value or _has_control_character(value):
        return True
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    return (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    )
