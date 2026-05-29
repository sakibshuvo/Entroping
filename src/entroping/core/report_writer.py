"""Report writers for deterministic Entroping runs."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree  # nosec B405

from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlSuiteResult, redact_hurl_output
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

    resolved = _prepare_output_path(path)
    resolved.write_text(
        json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolved


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

    resolved = _prepare_output_path(path)
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
    tree.write(resolved, encoding="utf-8", xml_declaration=True)
    return resolved


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

    resolved = _prepare_output_path(path)
    resolved.write_text(render_bug_report(report), encoding="utf-8")
    return resolved


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


def _display_path(path: Path, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _prepare_output_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        msg = f"Refusing to write report through symlinked path: {expanded}"
        raise ReportWriterError(msg)
    resolved = expanded.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
