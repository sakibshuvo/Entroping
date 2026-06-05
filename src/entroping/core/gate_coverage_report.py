"""Core workflow for QAnstitution policy gate coverage reports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.gate_coverage import (
    GateCoverageReport,
    compile_gate_coverage_report,
    render_gate_coverage_markdown,
)
from entroping.bridge.policy_to_hurl import GateCompilationError
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.hurl import HurlMetadataSyntaxError

GateCoverageOutput = Literal["md", "json"]


class GateCoverageReportError(ValueError):
    """Raised when a policy gate coverage report cannot be generated."""


@dataclass(frozen=True, slots=True)
class GateCoverageReportResult:
    """Result of a successful policy gate coverage workflow."""

    output_path: Path
    report: GateCoverageReport


def run_gate_coverage_report(
    *,
    project_root: Path,
    output: GateCoverageOutput,
) -> GateCoverageReportResult:
    """Write local evidence showing which Hurl tests match each policy gate."""

    root = project_root.expanduser().resolve()
    try:
        evidence = load_qanstitution_evidence(root / "qanstitution.yaml")
        tests_root = root / "tests"
        hurl_tests = tuple(discover_hurl_tests((tests_root,))) if tests_root.exists() else ()
        report = compile_gate_coverage_report(evidence, hurl_tests, root=root)
    except (
        GateCompilationError,
        HurlMetadataSyntaxError,
        OSError,
        QanstitutionLoadError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise GateCoverageReportError(str(exc)) from exc

    content = _render_report(report, output)
    output_path = root / "reports" / f"gate-coverage.{output}"
    try:
        safe_write_text(output_path, content, artifact="gate coverage report", root=root)
    except SafeWriteError as exc:
        raise GateCoverageReportError(str(exc)) from exc
    return GateCoverageReportResult(output_path=output_path, report=report)


def _render_report(report: GateCoverageReport, output: GateCoverageOutput) -> str:
    if output == "md":
        return render_gate_coverage_markdown(report)
    return report.model_dump_json(indent=2) + "\n"
