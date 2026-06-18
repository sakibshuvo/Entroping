"""Core workflow for generated-test quality score reports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.test_quality import (
    TestQualityReport,
    compile_test_quality_report,
    render_test_quality_markdown,
)
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.hurl import HurlMetadataSyntaxError

TestQualityOutput = Literal["md", "json"]


class TestQualityReportError(ValueError):
    """Raised when a generated-test quality report cannot be generated."""


@dataclass(frozen=True, slots=True)
class TestQualityReportResult:
    """Result of a successful generated-test quality report workflow."""

    output_path: Path
    report: TestQualityReport


def run_test_quality_report(
    *,
    project_root: Path,
    output: TestQualityOutput,
) -> TestQualityReportResult:
    """Write a local generated-test quality score report."""

    root = project_root.expanduser().resolve()
    try:
        tests_root = root / "tests"
        hurl_tests = tuple(discover_hurl_tests((tests_root,))) if tests_root.exists() else ()
        report = compile_test_quality_report(hurl_tests, project=root.name, root=root)
    except (HurlMetadataSyntaxError, OSError, UnicodeDecodeError, ValueError) as exc:
        raise TestQualityReportError(str(exc)) from exc

    content = _render_report(report, output)
    output_path = root / "reports" / f"test-quality.{output}"
    try:
        safe_write_text(output_path, content, artifact="test quality report", root=root)
    except SafeWriteError as exc:
        raise TestQualityReportError(str(exc)) from exc
    return TestQualityReportResult(output_path=output_path, report=report)


def _render_report(report: TestQualityReport, output: TestQualityOutput) -> str:
    if output == "md":
        return render_test_quality_markdown(report)
    return report.model_dump_json(indent=2) + "\n"
