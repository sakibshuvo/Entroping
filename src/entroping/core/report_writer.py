"""Report writers for deterministic Entroping runs."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree  # nosec B405

from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlSuiteResult, redact_hurl_output
from entroping.core.safe_write import SafeWriteError, safe_write_bytes, safe_write_text
from entroping.models.report import RunReport, RunReportSummary, RunTestReport


class ReportWriterError(ValueError):
    """Raised when a run report cannot be built or written safely."""


def build_run_report(
    *,
    project: str,
    environment: str,
    execution_copies: Sequence[HurlExecutionCopy],
    suite: HurlSuiteResult,
    project_root: Path,
) -> RunReport:
    """Build a serializable report from Hurl execution copies and results."""

    if len(execution_copies) != len(suite.results):
        msg = "Execution copy count does not match Hurl result count"
        raise ReportWriterError(msg)

    root = project_root.expanduser().resolve()
    tests: list[RunTestReport] = []
    for execution_copy, result in zip(execution_copies, suite.results, strict=True):
        tests.append(
            RunTestReport(
                path=_display_path(execution_copy.source_path, root),
                execution_path=_display_path(execution_copy.execution_path, root),
                status=result.status,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                rule_ids=tuple(gate.rule_id for gate in execution_copy.injected_gates),
                stdout=redact_hurl_output(result.stdout),
                stderr=redact_hurl_output(result.stderr),
            )
        )

    return RunReport(
        project=project,
        environment=environment or "default",
        generated_at=datetime.now(UTC).isoformat(),
        summary=RunReportSummary(
            total=suite.total,
            passed=suite.passed,
            failed=suite.failed,
            exit_code=suite.exit_code,
        ),
        tests=tuple(tests),
    )


def write_json_report(report: RunReport, path: Path) -> Path:
    """Write a redacted JSON run report."""

    return _write_report_text(
        path,
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        artifact="path",
    )


def load_run_report(path: Path) -> RunReport:
    """Load a previously written JSON run report."""

    data = json.loads(path.read_text(encoding="utf-8"))
    summary_data = data["summary"]
    tests = tuple(
        RunTestReport(
            path=item["path"],
            execution_path=item["execution_path"],
            status=item["status"],
            exit_code=item["exit_code"],
            duration_ms=item["duration_ms"],
            rule_ids=tuple(item["rule_ids"]),
            stdout=item["stdout"],
            stderr=item["stderr"],
        )
        for item in data["tests"]
    )
    return RunReport(
        project=data["project"],
        environment=data["environment"],
        generated_at=data["generated_at"],
        summary=RunReportSummary(
            total=summary_data["total"],
            passed=summary_data["passed"],
            failed=summary_data["failed"],
            exit_code=summary_data["exit_code"],
        ),
        tests=tests,
    )


def write_junit_report(report: RunReport, path: Path) -> Path:
    """Write a CI-consumable JUnit XML report."""

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
                    "type": "entroping.hurl",
                },
            )
            failure.text = _failure_text(test)

    tree = ElementTree.ElementTree(testsuite)
    ElementTree.indent(tree, space="  ")
    buffer = BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return _write_report_bytes(path, buffer.getvalue(), artifact="path")


def write_html_report(report: RunReport, path: Path) -> Path:
    """Write a dependency-free human-readable HTML report."""

    return _write_report_text(path, _render_html_report(report), artifact="path")


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


def write_bug_report(report: RunReport, path: Path) -> Path:
    """Write a Markdown bug handoff with the same path safety as other reports."""

    return _write_report_text(path, render_bug_report(report), artifact="path")


def _report_to_dict(report: RunReport) -> dict[str, object]:
    return {
        "project": report.project,
        "environment": report.environment,
        "generated_at": report.generated_at,
        "summary": {
            "total": report.summary.total,
            "passed": report.summary.passed,
            "failed": report.summary.failed,
            "exit_code": report.summary.exit_code,
        },
        "tests": [
            {
                "path": test.path,
                "execution_path": test.execution_path,
                "status": test.status,
                "exit_code": test.exit_code,
                "duration_ms": test.duration_ms,
                "rule_ids": list(test.rule_ids),
                "stdout": test.stdout,
                "stderr": test.stderr,
            }
            for test in report.tests
        ],
    }


def _failure_text(test: RunTestReport) -> str:
    parts = [
        f"path: {test.path}",
        f"status: {test.status}",
        f"exit_code: {test.exit_code}",
        f"rule_ids: {', '.join(test.rule_ids) if test.rule_ids else 'none'}",
    ]
    if test.stdout:
        parts.extend(("", "stdout:", test.stdout))
    if test.stderr:
        parts.extend(("", "stderr:", test.stderr))
    return "\n".join(parts)


def _render_html_report(report: RunReport) -> str:
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
    .failed, .timeout, .error {{ color: #b3261e; font-weight: 600; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 0.75rem; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Entroping Run Report</h1>
  <dl>
    <dt>Project</dt><dd>{escape(report.project)}</dd>
    <dt>Environment</dt><dd>{escape(report.environment)}</dd>
    <dt>Generated</dt><dd>{escape(report.generated_at)}</dd>
    <dt>Summary</dt><dd>{summary}</dd>
  </dl>
  <table>
    <thead>
      <tr><th>Test</th><th>Status</th><th>Duration</th><th>Rules</th><th>Output</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""


def _html_test_row(test: RunTestReport) -> str:
    output = _html_output(test)
    return (
        "      <tr>"
        f"<td>{escape(test.path)}</td>"
        f'<td class="{escape(test.status)}">{escape(test.status)}</td>'
        f"<td>{test.duration_ms} ms</td>"
        f"<td>{escape(', '.join(test.rule_ids) if test.rule_ids else 'none')}</td>"
        f"<td>{output}</td>"
        "</tr>"
    )


def _html_output(test: RunTestReport) -> str:
    parts: list[str] = []
    if test.stdout:
        parts.append(f"<strong>stdout</strong><pre>{escape(test.stdout)}</pre>")
    if test.stderr:
        parts.append(f"<strong>stderr</strong><pre>{escape(test.stderr)}</pre>")
    return "".join(parts) if parts else "&nbsp;"


def _display_path(path: Path, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _write_report_text(path: Path, content: str, *, artifact: str) -> Path:
    try:
        return safe_write_text(path, content, artifact=artifact)
    except SafeWriteError as exc:
        raise ReportWriterError(str(exc)) from exc


def _write_report_bytes(path: Path, content: bytes, *, artifact: str) -> Path:
    try:
        return safe_write_bytes(path, content, artifact=artifact)
    except SafeWriteError as exc:
        raise ReportWriterError(str(exc)) from exc
