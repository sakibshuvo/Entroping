"""Deterministic drift report comparison for run reports."""

import json
from collections.abc import Sequence
from pathlib import Path

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.drift import (
    DependencyDriftBaseline,
    DependencyDriftRoute,
    DriftBaseline,
    DriftBaselineTest,
    DriftFinding,
    DriftReport,
    DriftReportSummary,
    DriftValue,
)
from entroping.models.report import RunReport, RunTestReport

_LATENCY_REGRESSION_MIN_INCREASE_MS = 100
_LATENCY_REGRESSION_MIN_PERCENT = 25
DRIFT_REPORT_SCHEMA_VERSION = "entroping.drift-report.v1"


class DriftReportError(ValueError):
    """Raised when a drift baseline or report cannot be handled safely."""


class DriftBaselineNotFoundError(DriftReportError):
    """Raised when drift checking is requested without a local baseline."""


def load_drift_baseline(path: Path) -> DriftBaseline:
    """Load the local drift baseline from JSON."""

    resolved = _resolve_read_path(path)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "Drift baseline must be a JSON object"
        raise DriftReportError(msg)

    raw_tests = data.get("tests")
    if not isinstance(raw_tests, list):
        msg = "Drift baseline must contain a tests list"
        raise DriftReportError(msg)

    tests = tuple(_parse_baseline_test(item) for item in raw_tests)
    return DriftBaseline(
        project=_optional_string(data.get("project")),
        environment=_optional_string(data.get("environment")),
        tests=tests,
    )


def load_dependency_drift_baseline(path: Path) -> DependencyDriftBaseline:
    """Load the reviewed dependency-call drift baseline from JSON."""

    resolved = _resolve_read_path(path)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "Dependency drift baseline must be a JSON object"
        raise DriftReportError(msg)

    raw_routes = data.get("routes")
    if not isinstance(raw_routes, list):
        msg = "Dependency drift baseline must contain a routes list"
        raise DriftReportError(msg)

    return DependencyDriftBaseline(
        source_label=_optional_source_label(data.get("source_label")),
        routes=tuple(_parse_dependency_route(item) for item in raw_routes),
    )


def build_drift_report(
    *,
    current: RunReport,
    baseline: DriftBaseline,
    baseline_path: Path,
) -> DriftReport:
    """Compare current run behavior against a deterministic baseline."""

    baseline_by_path = {test.path: test for test in baseline.tests}
    current_by_path = {test.path: test for test in current.tests}
    findings: list[DriftFinding] = []

    for path in sorted(baseline_by_path):
        baseline_test = baseline_by_path[path]
        current_test = current_by_path.get(path)
        if current_test is None:
            findings.append(_missing_current_test(path, baseline_test))
            continue
        findings.extend(_compare_common_test(path, baseline_test, current_test))

    for path in sorted(set(current_by_path) - set(baseline_by_path)):
        findings.append(_new_current_test(path, current_by_path[path]))

    return DriftReport(
        project=current.project,
        environment=current.environment,
        generated_at=current.generated_at,
        baseline_path=_display_path(baseline_path),
        summary=DriftReportSummary(
            baseline_tests=len(baseline.tests),
            current_tests=len(current.tests),
            findings=len(findings),
            drifted=len(findings),
            missing_baseline=False,
        ),
        findings=tuple(findings),
    )


def append_dependency_drift_findings(
    report: DriftReport,
    *,
    baseline: DependencyDriftBaseline,
    current_routes: Sequence[DependencyDriftRoute],
    baseline_path: Path,
) -> DriftReport:
    """Return a drift report with dependency-call route findings appended."""

    baseline_by_key = {_dependency_route_key(route): route for route in baseline.routes}
    current_by_key = {_dependency_route_key(route): route for route in current_routes}
    findings = list(report.findings)

    for key in sorted(set(baseline_by_key) - set(current_by_key)):
        route = baseline_by_key[key]
        findings.append(
            DriftFinding(
                kind="missing_dependency_route",
                severity="warning",
                path=_dependency_route_path(route),
                message="Baseline dependency route is missing from current traffic observations.",
                baseline=_dependency_route_payload(route),
                current={},
            )
        )

    for key in sorted(set(current_by_key) - set(baseline_by_key)):
        route = current_by_key[key]
        findings.append(
            DriftFinding(
                kind="new_dependency_route",
                severity="warning",
                path=_dependency_route_path(route),
                message="Current traffic observes a dependency route absent from the baseline.",
                baseline={},
                current=_dependency_route_payload(route),
            )
        )

    dependency_path = _display_path(baseline_path)
    return DriftReport(
        project=report.project,
        environment=report.environment,
        generated_at=report.generated_at,
        baseline_path=f"{report.baseline_path}; dependency={dependency_path}",
        summary=DriftReportSummary(
            baseline_tests=report.summary.baseline_tests,
            current_tests=report.summary.current_tests,
            findings=len(findings),
            drifted=len(findings),
            missing_baseline=report.summary.missing_baseline,
        ),
        findings=tuple(findings),
    )


def build_missing_baseline_report(*, current: RunReport, baseline_path: Path) -> DriftReport:
    """Build a machine-readable report for the missing-baseline path."""

    message = (
        "Drift baseline not found. Run entroping run --report drift, review "
        "reports/drift-baseline.candidate.json, then copy it to "
        ".entroping/drift-baseline.json only after accepting the behavior."
    )
    finding = DriftFinding(
        kind="missing_baseline",
        severity="warning",
        path="*",
        message=message,
        baseline={},
        current={"tests": current.summary.total},
    )
    return DriftReport(
        project=current.project,
        environment=current.environment,
        generated_at=current.generated_at,
        baseline_path=_display_path(baseline_path),
        summary=DriftReportSummary(
            baseline_tests=0,
            current_tests=current.summary.total,
            findings=1,
            drifted=1,
            missing_baseline=True,
        ),
        findings=(finding,),
    )


def build_reviewed_drift_baseline(current: RunReport) -> DriftBaseline:
    """Build a value-free baseline candidate from the current run report."""

    tests = tuple(_baseline_test_from_run(test) for test in sorted(current.tests, key=_test_key))
    return DriftBaseline(
        project=current.project,
        environment=current.environment,
        tests=tests,
    )


def write_reviewed_drift_baseline_candidate(current: RunReport, path: Path) -> Path:
    """Write a reviewable baseline candidate without approving it as active state."""

    if path.name == "drift-baseline.json":
        msg = (
            "Refusing to write reviewed drift baseline candidate directly to "
            "drift-baseline.json; write a candidate file first."
        )
        raise DriftReportError(msg)

    baseline = build_reviewed_drift_baseline(current)
    try:
        return safe_write_text(
            path,
            json.dumps(drift_baseline_to_dict(baseline), indent=2, sort_keys=True) + "\n",
            artifact="drift baseline candidate",
        )
    except SafeWriteError as exc:
        raise DriftReportError(str(exc)) from exc


def write_drift_report(report: DriftReport, path: Path) -> Path:
    """Write a deterministic machine-readable drift report."""

    try:
        return safe_write_text(
            path,
            json.dumps(drift_report_to_dict(report), indent=2, sort_keys=True) + "\n",
            artifact="drift report",
        )
    except SafeWriteError as exc:
        raise DriftReportError(str(exc)) from exc


def _test_key(test: RunTestReport) -> str:
    return test.path


def _baseline_test_from_run(test: RunTestReport) -> DriftBaselineTest:
    response = {
        "headers": dict(test.response_headers),
        "body_shape": list(test.response_body_shape),
    }
    return DriftBaselineTest(
        path=test.path,
        status=test.status,
        exit_code=test.exit_code,
        rule_ids=test.rule_ids,
        duration_ms=test.duration_ms,
        response_status_code=test.response_status_code,
        response_headers=_optional_response_headers(response),
        response_body_shape=_optional_response_body_shape(response),
    )


def _compare_common_test(
    path: str,
    baseline: DriftBaselineTest,
    current: RunTestReport,
) -> tuple[DriftFinding, ...]:
    findings: list[DriftFinding] = []
    if baseline.status != current.status or baseline.exit_code != current.exit_code:
        findings.append(
            DriftFinding(
                kind="result_changed",
                severity="error",
                path=path,
                message="Current Hurl result differs from the drift baseline.",
                baseline=_result_payload(baseline),
                current=_result_payload(current),
            )
        )
    if baseline.rule_ids != current.rule_ids:
        findings.append(
            DriftFinding(
                kind="assertions_changed",
                severity="warning",
                path=path,
                message="Injected QAnstitution rule IDs differ from the drift baseline.",
                baseline={"rule_ids": list(baseline.rule_ids)},
                current={"rule_ids": list(current.rule_ids)},
            )
        )
    findings.extend(_compare_latency(path, baseline, current))
    findings.extend(_compare_response_fingerprint(path, baseline, current))
    return tuple(findings)


def _compare_latency(
    path: str,
    baseline: DriftBaselineTest,
    current: RunTestReport,
) -> tuple[DriftFinding, ...]:
    if baseline.duration_ms is None or baseline.duration_ms <= 0:
        return ()

    increase_ms = current.duration_ms - baseline.duration_ms
    if increase_ms < _LATENCY_REGRESSION_MIN_INCREASE_MS:
        return ()

    increase_percent = (increase_ms * 100) // baseline.duration_ms
    if increase_percent < _LATENCY_REGRESSION_MIN_PERCENT:
        return ()

    return (
        DriftFinding(
            kind="latency_regressed",
            severity="warning",
            path=path,
            message="Current duration materially exceeds the drift baseline.",
            baseline={"duration_ms": baseline.duration_ms},
            current={
                "duration_ms": current.duration_ms,
                "increase_ms": increase_ms,
                "increase_percent": increase_percent,
            },
        ),
    )


def _compare_response_fingerprint(
    path: str,
    baseline: DriftBaselineTest,
    current: RunTestReport,
) -> tuple[DriftFinding, ...]:
    if not _has_response_fingerprint(baseline):
        return ()
    if not _has_response_fingerprint(current):
        return (
            DriftFinding(
                kind="response_snapshot_missing",
                severity="warning",
                path=path,
                message="Baseline has structured response data but the current run does not.",
                baseline=_response_payload(baseline),
                current={},
            ),
        )

    findings: list[DriftFinding] = []
    if (
        baseline.response_status_code is not None
        and baseline.response_status_code != current.response_status_code
    ):
        findings.append(
            DriftFinding(
                kind="response_status_changed",
                severity="error",
                path=path,
                message="Response status code differs from the drift baseline.",
                baseline={"response_status_code": baseline.response_status_code},
                current={"response_status_code": current.response_status_code},
            )
        )

    current_headers = dict(current.response_headers)
    for name, baseline_value in baseline.response_headers:
        current_value = current_headers.get(name)
        if current_value == baseline_value:
            continue
        findings.append(
            DriftFinding(
                kind="response_header_changed",
                severity="warning",
                path=path,
                message=f"Response header {name!r} differs from the drift baseline.",
                baseline={"header": name, "value": baseline_value},
                current={"header": name, "value": current_value},
            )
        )

    if baseline.response_body_shape and baseline.response_body_shape != current.response_body_shape:
        findings.append(
            DriftFinding(
                kind="response_body_shape_changed",
                severity="warning",
                path=path,
                message="Response JSON body shape differs from the drift baseline.",
                baseline={"body_shape": list(baseline.response_body_shape)},
                current={"body_shape": list(current.response_body_shape)},
            )
        )

    return tuple(findings)


def _missing_current_test(path: str, baseline: DriftBaselineTest) -> DriftFinding:
    return DriftFinding(
        kind="missing_current_test",
        severity="error",
        path=path,
        message="Baseline test is missing from the current run.",
        baseline=_result_payload(baseline),
        current={},
    )


def _new_current_test(path: str, current: RunTestReport) -> DriftFinding:
    return DriftFinding(
        kind="new_current_test",
        severity="info",
        path=path,
        message="Current run contains a test that is not in the drift baseline.",
        baseline={},
        current=_result_payload(current),
    )


def _result_payload(test: DriftBaselineTest | RunTestReport) -> dict[str, DriftValue]:
    return {
        "status": test.status,
        "exit_code": test.exit_code,
        "rule_ids": list(test.rule_ids),
    }


def _response_payload(test: DriftBaselineTest | RunTestReport) -> dict[str, DriftValue]:
    payload: dict[str, DriftValue] = {}
    if test.response_status_code is not None:
        payload["response_status_code"] = test.response_status_code
    if test.response_headers:
        payload["response_headers"] = [
            f"{name}: {value}" for name, value in test.response_headers
        ]
    if test.response_body_shape:
        payload["response_body_shape"] = list(test.response_body_shape)
    return payload


def _has_response_fingerprint(test: DriftBaselineTest | RunTestReport) -> bool:
    return (
        test.response_status_code is not None
        or bool(test.response_headers)
        or bool(test.response_body_shape)
    )


def _parse_baseline_test(item: object) -> DriftBaselineTest:
    if not isinstance(item, dict):
        msg = "Each drift baseline test must be a JSON object"
        raise DriftReportError(msg)

    path = _required_string(item.get("path"), "path")
    status = _required_string(item.get("status"), f"{path}.status")
    exit_code = item.get("exit_code")
    if type(exit_code) is not int:
        msg = f"Drift baseline test {path!r} must have an integer exit_code"
        raise DriftReportError(msg)

    raw_rule_ids = item.get("rule_ids", [])
    if not isinstance(raw_rule_ids, list) or not all(
        isinstance(rule_id, str) for rule_id in raw_rule_ids
    ):
        msg = f"Drift baseline test {path!r} must have a string rule_ids list"
        raise DriftReportError(msg)

    return DriftBaselineTest(
        path=path,
        status=status,
        exit_code=exit_code,
        rule_ids=tuple(raw_rule_ids),
        duration_ms=_optional_duration_ms(item.get("duration_ms"), path),
        response_status_code=_optional_response_status(item.get("response"), path),
        response_headers=_optional_response_headers(item.get("response")),
        response_body_shape=_optional_response_body_shape(item.get("response")),
    )


def _parse_dependency_route(item: object) -> DependencyDriftRoute:
    if not isinstance(item, dict):
        msg = "Each dependency drift route must be a JSON object"
        raise DriftReportError(msg)

    destination_host = _dependency_host(item.get("destination_host"))
    method = _dependency_method(item.get("method"))
    path_template = _dependency_path_template(item.get("path_template"))
    return DependencyDriftRoute(
        destination_host=destination_host,
        method=method,
        path_template=path_template,
    )


def _optional_duration_ms(value: object, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        msg = f"Drift baseline test {path!r} duration_ms must be a non-negative integer"
        raise DriftReportError(msg)
    return value


def _optional_response_status(response: object, path: str) -> int | None:
    if response is None:
        return None
    if not isinstance(response, dict):
        msg = f"Drift baseline test {path!r} response must be a JSON object"
        raise DriftReportError(msg)
    status_code = response.get("status_code")
    if status_code is None:
        return None
    if type(status_code) is not int:
        msg = f"Drift baseline test {path!r} response.status_code must be an integer"
        raise DriftReportError(msg)
    return status_code


def _optional_response_headers(response: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(response, dict):
        return ()
    raw_headers = response.get("headers")
    if not isinstance(raw_headers, dict):
        return ()

    headers: dict[str, str] = {}
    for raw_name, raw_value in raw_headers.items():
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            continue
        name = raw_name.strip().lower()
        value = raw_value.strip()
        if (
            name in {"cache-control", "content-type", "vary"}
            and value
            and "[REDACTED]" not in value
        ):
            headers[name] = value
    return tuple(sorted(headers.items()))


def _optional_response_body_shape(response: object) -> tuple[str, ...]:
    if not isinstance(response, dict):
        return ()
    raw_shape = response.get("body_shape")
    if not isinstance(raw_shape, list):
        return ()
    shape = {
        item
        for item in raw_shape
        if isinstance(item, str) and item.strip() and not _has_control_character(item)
    }
    return tuple(sorted(shape, key=_body_shape_sort_key))


def _body_shape_sort_key(item: str) -> tuple[int, str]:
    return (0 if item.startswith("$:") else 1, item)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or _has_control_character(value):
        msg = f"Drift baseline field {field!r} must be a non-empty string"
        raise DriftReportError(msg)
    return value


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        msg = "Optional drift baseline project/environment fields must be strings"
        raise DriftReportError(msg)
    return value


def _optional_source_label(value: object) -> str:
    if value is None:
        return "client"
    if not isinstance(value, str) or not value.strip() or _has_control_character(value):
        msg = "Dependency drift baseline source_label must be a non-empty string"
        raise DriftReportError(msg)
    return " ".join(value.split())


def _dependency_host(value: object) -> str:
    host = _required_string(value, "destination_host").strip().lower()
    if any(part in host for part in ("/", "\\", "@", "?", "#")) or any(
        character.isspace() for character in host
    ):
        msg = "Dependency drift baseline destination_host is not a safe host"
        raise DriftReportError(msg)
    return host


def _dependency_method(value: object) -> str:
    method = _required_string(value, "method").strip().upper()
    if any(character.isspace() for character in method):
        msg = "Dependency drift baseline method is not a safe method"
        raise DriftReportError(msg)
    return method


def _dependency_path_template(value: object) -> str:
    path_template = _required_string(value, "path_template").strip()
    if (
        not path_template.startswith("/")
        or "?" in path_template
        or "#" in path_template
        or "\\" in path_template
    ):
        msg = "Dependency drift baseline path_template must be a safe absolute path template"
        raise DriftReportError(msg)
    return path_template


def _dependency_route_key(route: DependencyDriftRoute) -> tuple[str, str, str]:
    return (route.destination_host, route.method, route.path_template)


def _dependency_route_path(route: DependencyDriftRoute) -> str:
    return f"dependency:{route.destination_host} {route.method} {route.path_template}"


def _dependency_route_payload(route: DependencyDriftRoute) -> dict[str, DriftValue]:
    return {
        "destination_host": route.destination_host,
        "method": route.method,
        "path_template": route.path_template,
    }


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\t" for character in value)


def _resolve_read_path(path: Path) -> Path:
    expanded = path.expanduser()
    _reject_symlink_path_components(expanded, action="read baseline")
    if not expanded.exists():
        msg = f"Drift baseline not found: {_display_path(expanded)}"
        raise DriftBaselineNotFoundError(msg)
    if not expanded.is_file():
        msg = f"Drift baseline path is not a file: {_display_path(expanded)}"
        raise DriftReportError(msg)
    return expanded.resolve()


def _reject_symlink_path_components(path: Path, *, action: str) -> None:
    symlink_component = first_symlink_path_component(path)
    if symlink_component is not None:
        msg = (
            f"Refusing to {action} through symlinked path component: "
            f"{symlink_component}"
        )
        raise DriftReportError(msg)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def drift_report_to_dict(report: DriftReport) -> dict[str, object]:
    """Return the versioned JSON-serializable drift report payload."""

    return {
        "schema_version": DRIFT_REPORT_SCHEMA_VERSION,
        "project": report.project,
        "environment": report.environment,
        "generated_at": report.generated_at,
        "baseline_path": report.baseline_path,
        "summary": {
            "baseline_tests": report.summary.baseline_tests,
            "current_tests": report.summary.current_tests,
            "findings": report.summary.findings,
            "drifted": report.summary.drifted,
            "missing_baseline": report.summary.missing_baseline,
        },
        "findings": [_finding_to_dict(finding) for finding in report.findings],
    }


def drift_baseline_to_dict(baseline: DriftBaseline) -> dict[str, object]:
    """Return the JSON-serializable drift baseline payload."""

    return {
        "project": baseline.project,
        "environment": baseline.environment,
        "tests": [_drift_baseline_test_to_dict(test) for test in baseline.tests],
    }


def _drift_baseline_test_to_dict(test: DriftBaselineTest) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": test.path,
        "status": test.status,
        "exit_code": test.exit_code,
        "duration_ms": test.duration_ms,
        "rule_ids": list(test.rule_ids),
    }
    response = _drift_baseline_response_to_dict(test)
    if response is not None:
        payload["response"] = response
    return payload


def _drift_baseline_response_to_dict(test: DriftBaselineTest) -> dict[str, object] | None:
    if (
        test.response_status_code is None
        and not test.response_headers
        and not test.response_body_shape
    ):
        return None

    response: dict[str, object] = {}
    if test.response_status_code is not None:
        response["status_code"] = test.response_status_code
    if test.response_headers:
        response["headers"] = dict(test.response_headers)
    if test.response_body_shape:
        response["body_shape"] = list(test.response_body_shape)
    return response


def _finding_to_dict(finding: DriftFinding) -> dict[str, object]:
    return {
        "kind": finding.kind,
        "severity": finding.severity,
        "path": finding.path,
        "message": finding.message,
        "baseline": dict(finding.baseline),
        "current": dict(finding.current),
    }
