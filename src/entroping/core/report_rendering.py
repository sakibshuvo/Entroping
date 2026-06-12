"""Human and CI report rendering helpers."""

from html import escape
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree  # nosec B405

from entroping.models.report import (
    KnownFailureEvidence,
    RunAttemptEvidence,
    RunReport,
    RunTestReport,
)


def render_junit_report(report: RunReport) -> bytes:
    """Render a CI-consumable JUnit XML report."""

    testsuite = ElementTree.Element(
        "testsuite",
        {
            "name": f"Entroping {report.project}",
            "tests": str(report.summary.total),
            "failures": str(report.summary.failed),
            "errors": "0",
            "time": f"{sum(test.duration_ms for test in report.tests) / 1000:.3f}",
        },
    )

    for test in report.tests:
        testcase = ElementTree.SubElement(
            testsuite,
            "testcase",
            {
                "classname": str(Path(test.path).parent),
                "name": Path(test.path).name,
                "time": f"{test.duration_ms / 1000:.3f}",
            },
        )
        if not test.passed:
            failure = ElementTree.SubElement(
                testcase,
                "failure",
                {
                    "message": test.status,
                    "type": _failure_type(test),
                },
            )
            failure.text = _failure_text(test)
        if _has_test_properties(test):
            properties = ElementTree.SubElement(testcase, "properties")
            if test.timeout_ms > 0:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.timeout_ms",
                        "value": str(test.timeout_ms),
                    },
                )
            if test.operation_id is not None:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.operation_id",
                        "value": test.operation_id,
                    },
                )
            if test.source is not None:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.source",
                        "value": test.source,
                    },
                )
            if test.negative_category is not None:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.negative_category",
                        "value": test.negative_category,
                    },
                )
            if test.severity is not None:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.severity",
                        "value": test.severity,
                    },
                )
            for known_failure in test.known_failures:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": f"entroping.known_failure.{known_failure.rule_id}",
                        "value": _known_failure_summary(known_failure),
                    },
                )
            if test.safety is not None:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.safety.protected_environment",
                        "value": str(test.safety.protected_environment).lower(),
                    },
                )
                if test.safety.safety is not None:
                    ElementTree.SubElement(
                        properties,
                        "property",
                        {
                            "name": "entroping.safety",
                            "value": test.safety.safety,
                        },
                    )
                if test.safety.methods:
                    ElementTree.SubElement(
                        properties,
                        "property",
                        {
                            "name": "entroping.safety.methods",
                            "value": ",".join(test.safety.methods),
                        },
                    )
                if test.safety.blocked_reason is not None:
                    ElementTree.SubElement(
                        properties,
                        "property",
                        {
                            "name": "entroping.safety.blocked_reason",
                            "value": test.safety.blocked_reason,
                        },
                    )
            if test.retry.retry_count > 0 or test.retry.unstable:
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.retry_count",
                        "value": str(test.retry.retry_count),
                    },
                )
                ElementTree.SubElement(
                    properties,
                    "property",
                    {
                        "name": "entroping.unstable",
                        "value": str(test.retry.unstable).lower(),
                    },
                )
                for attempt in test.retry.attempts:
                    ElementTree.SubElement(
                        properties,
                        "property",
                        {
                            "name": f"entroping.attempt.{attempt.attempt}",
                            "value": _attempt_summary(
                                status=attempt.status,
                                exit_code=attempt.exit_code,
                                duration_ms=attempt.duration_ms,
                            ),
                        },
                    )

    tree = ElementTree.ElementTree(testsuite)
    ElementTree.indent(tree, space="  ")
    buffer = BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def render_html_report(report: RunReport) -> str:
    rows = "\n".join(_html_test_row(test) for test in report.tests)
    summary = (
        f"{report.summary.passed} passed, {report.summary.failed} failed, "
        f"{report.summary.total} total"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Entroping {escape(report.project)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 2rem; color: #161616; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d8d8d8; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f4f4f4; }}
    .passed {{ color: #137333; font-weight: 600; }}
    .failed, .timeout, .error, .blocked {{ color: #b3261e; font-weight: 600; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 0.75rem; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Entroping Run Report</h1>
  <dl>
    <dt>Project</dt><dd>{escape(report.project)}</dd>
    <dt>Environment</dt><dd>{escape(report.environment)}</dd>
    <dt>Generated</dt><dd>{escape(report.generated_at)}</dd>
    <dt>Summary</dt><dd>{escape(summary)}</dd>
  </dl>
  <table>
    <thead>
      <tr><th>Test</th><th>Status</th><th>Duration</th><th>Timeout</th><th>Operation</th><th>Rules</th><th>Output</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""


def render_bug_report(report: RunReport) -> str:
    """Render a Markdown bug handoff from the latest failing run."""

    failing = [test for test in report.tests if not test.passed]
    if not failing:
        return "No failing Entroping run is available for bug report generation.\n"

    primary = failing[0]
    sections = [
        "# Entroping Failure Report",
        "",
        f"- Project: {report.project}",
        f"- Environment: {report.environment}",
        f"- Test: {primary.path}",
        f"- Status: {primary.status}",
        f"- Exit code: {primary.exit_code}",
        f"- Rule IDs: {', '.join(primary.rule_ids) if primary.rule_ids else 'none'}",
        "",
        "## Reproduce",
        "",
        "```bash",
        "entroping run --tag <tag> --report json --report junit",
        "```",
        "",
        "## Output",
        "",
        "```text",
        _failure_text(primary).strip(),
        "```",
        "",
    ]
    return "\n".join(sections)


def _html_test_row(test: RunTestReport) -> str:
    output = _html_output(test)
    return (
        "      <tr>"
        f"<td>{escape(test.path)}</td>"
        f'<td class="{escape(test.status)}">{escape(test.status)}</td>'
        f"<td>{test.duration_ms} ms</td>"
        f"<td>{test.timeout_ms} ms</td>"
        f"<td>{escape(test.operation_id or 'none')}</td>"
        f"<td>{escape(', '.join(test.rule_ids) if test.rule_ids else 'none')}</td>"
        f"<td>{output}</td>"
        "</tr>"
    )


def _html_output(test: RunTestReport) -> str:
    parts: list[str] = []
    if test.known_failures:
        items = "".join(
            f"<li>{escape(_known_failure_summary(known_failure))}</li>"
            for known_failure in test.known_failures
        )
        parts.append(f"<strong>Known failures</strong><ul>{items}</ul>")
    if test.safety is not None:
        parts.append(f"<strong>Safety</strong><p>{escape(_safety_summary(test))}</p>")
    metadata_summary = _metadata_summary(test)
    if metadata_summary != "none":
        parts.append(f"<strong>Metadata</strong><p>{escape(metadata_summary)}</p>")
    if test.retry.retry_count > 0 or test.retry.unstable:
        items = "".join(_html_attempt_item(attempt) for attempt in test.retry.attempts)
        parts.append(
            "<strong>Retry evidence</strong>"
            f"<p>retry_count: {test.retry.retry_count}; "
            f"unstable: {str(test.retry.unstable).lower()}</p>"
            f"<ul>{items}</ul>"
        )
    if test.stdout:
        parts.append(f"<strong>stdout</strong><pre>{escape(test.stdout)}</pre>")
    if test.stderr:
        parts.append(f"<strong>stderr</strong><pre>{escape(test.stderr)}</pre>")
    return "".join(parts) if parts else "&nbsp;"


def _html_attempt_item(attempt: RunAttemptEvidence) -> str:
    summary = _attempt_summary(
        status=attempt.status,
        exit_code=attempt.exit_code,
        duration_ms=attempt.duration_ms,
    )
    return f"<li>attempt {attempt.attempt}: {escape(summary)}</li>"


def _failure_text(test: RunTestReport) -> str:
    parts = [
        f"path: {test.path}",
        f"status: {test.status}",
        f"exit_code: {test.exit_code}",
        f"timeout_ms: {test.timeout_ms}",
        f"operation_id: {test.operation_id or 'none'}",
        f"source: {test.source or 'none'}",
        f"negative_category: {test.negative_category or 'none'}",
        f"severity: {test.severity or 'none'}",
        f"rule_ids: {', '.join(test.rule_ids) if test.rule_ids else 'none'}",
    ]
    if test.safety is not None:
        parts.append(f"safety: {_safety_summary(test)}")
    if test.known_failures:
        parts.append(
            "known_failures: "
            + "; ".join(
                _known_failure_summary(known_failure) for known_failure in test.known_failures
            )
        )
    if test.retry.retry_count > 0 or test.retry.unstable:
        parts.append(
            "retry: "
            f"count={test.retry.retry_count}; "
            f"unstable={str(test.retry.unstable).lower()}; "
            + "; ".join(
                f"attempt {attempt.attempt} "
                + _attempt_summary(
                    status=attempt.status,
                    exit_code=attempt.exit_code,
                    duration_ms=attempt.duration_ms,
                )
                for attempt in test.retry.attempts
            )
        )
    if test.stdout:
        parts.extend(("", "stdout:", test.stdout))
    if test.stderr:
        parts.extend(("", "stderr:", test.stderr))
    return "\n".join(parts)


def _known_failure_summary(known_failure: KnownFailureEvidence) -> str:
    return f"{known_failure.issue_id} expires {known_failure.expires}: {known_failure.reason}"


def _has_test_properties(test: RunTestReport) -> bool:
    return (
        test.timeout_ms > 0
        or test.operation_id is not None
        or test.source is not None
        or test.negative_category is not None
        or test.severity is not None
        or bool(test.known_failures)
        or test.safety is not None
        or test.retry.retry_count > 0
        or test.retry.unstable
    )


def _failure_type(test: RunTestReport) -> str:
    if test.status == "blocked":
        return "entroping.run.blocked"
    return "entroping.hurl.timeout" if test.status == "timeout" else "entroping.hurl"


def _attempt_summary(*, status: str, exit_code: int, duration_ms: int) -> str:
    return f"{status} exit={exit_code} duration_ms={duration_ms}"


def _safety_summary(test: RunTestReport) -> str:
    if test.safety is None:
        return "none"
    safety = test.safety.safety or "unspecified"
    source = test.safety.safety_source or "none"
    methods = ",".join(test.safety.methods) if test.safety.methods else "none"
    blocked = test.safety.blocked_reason or "not blocked"
    protected = str(test.safety.protected_environment).lower()
    return (
        f"protected_environment={protected}; safety={safety}; source={source}; "
        f"methods={methods}; reason={blocked}"
    )


def _metadata_summary(test: RunTestReport) -> str:
    values = {
        "source": test.source,
        "negative_category": test.negative_category,
        "severity": test.severity,
    }
    present = [f"{key}={value}" for key, value in values.items() if value is not None]
    return "; ".join(present) if present else "none"
