"""HTML output-boundary tests for deterministic run reports."""

from pathlib import Path

from report_writer_test_helpers import _execution_copy

import entroping.core.report_rendering as report_rendering
import entroping.core.report_writer as report_writer
from entroping.core.hurl_runner import HurlFileResult, HurlSuiteResult
from entroping.models.report import RunSafetyEvidence, RunTestReport


def test_html_report_includes_safety_summary_and_none_fallback(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                ),
            ),
        ),
        project_root=tmp_path,
        safety_evidence_by_source_path={
            source.resolve(): RunSafetyEvidence(
                protected_environment=True,
                safety=None,
                safety_source=None,
                methods=("PATCH",),
                blocked_reason=(
                    "mutating method PATCH requires safety metadata in protected environments"
                ),
            )
        },
    )
    output = tmp_path / "reports" / "run-latest.html"

    report_writer.write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<strong>Safety</strong>" in html
    assert "protected_environment=true; safety=unspecified; source=none;" in html
    assert (
        report_rendering._safety_summary(
            RunTestReport(
                path="tests/no-safety.hurl",
                execution_path=".entroping/run/no-safety.hurl",
                status="passed",
                exit_code=0,
                duration_ms=0,
                rule_ids=(),
                stdout="",
                stderr="",
            )
        )
        == "none"
    )


def test_html_report_includes_suite_scheduling_summary(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "checkout.hurl"
    execution = tmp_path / ".entroping" / "run-1" / "checkout.hurl"
    report = report_writer.build_run_report(
        project="checkout-api",
        environment="prod",
        execution_copies=[_execution_copy(source, execution)],
        suite=HurlSuiteResult(
            results=(
                HurlFileResult(
                    path=execution,
                    command=("entroping", "run", "preflight"),
                    status="blocked",
                    exit_code=1,
                    stdout="",
                    stderr="Protected run blocked before Hurl execution",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    duration_ms=0,
                ),
            ),
            selected_count=2,
        ),
        project_root=tmp_path,
    )
    output = tmp_path / "reports" / "run-latest.html"

    report_writer.write_html_report(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<dt>Selected</dt><dd>2</dd>" in html
    assert "<dt>Executed</dt><dd>1</dd>" in html
    assert "<dt>Not scheduled</dt><dd>1</dd>" in html
