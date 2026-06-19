"""Core workflow for local test-pyramid evidence reports."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.test_pyramid import (
    TestPyramidArtifactEvidence,
    TestPyramidReport,
    compile_test_pyramid_report,
    render_test_pyramid_markdown,
)
from entroping.core.evidence_index import LocalEvidenceArtifact, build_local_evidence_index
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

TestPyramidOutput = Literal["md", "json"]
_MAX_COVERAGE_ARTIFACT_BYTES = 10 * 1024 * 1024
_PERCENT_RE = re.compile(r"^\d+(?:\.\d+)?%?$")


class TestPyramidReportError(ValueError):
    """Raised when a test-pyramid report cannot be generated."""

    __test__ = False


@dataclass(frozen=True, slots=True)
class TestPyramidReportResult:
    """Result of a successful test-pyramid report workflow."""

    output_path: Path
    report: TestPyramidReport


def run_test_pyramid_report(
    *,
    project_root: Path,
    output: TestPyramidOutput,
) -> TestPyramidReportResult:
    """Write a local value-free test-pyramid evidence report."""

    if output not in {"md", "json"}:
        msg = f"Unsupported test-pyramid output: {output}"
        raise TestPyramidReportError(msg)

    root = project_root.expanduser().resolve()
    try:
        evidence_artifacts = tuple(build_local_evidence_index(project_root=root))
    except (OSError, ValueError) as exc:
        raise TestPyramidReportError(str(exc)) from exc

    report = compile_test_pyramid_report(
        _test_pyramid_artifacts(evidence_artifacts, root=root),
        project=root.name,
    )
    content = _render_report(report, output)
    output_path = root / "reports" / f"test-pyramid.{output}"
    try:
        safe_write_text(output_path, content, artifact="test pyramid report", root=root)
    except SafeWriteError as exc:
        raise TestPyramidReportError(str(exc)) from exc
    return TestPyramidReportResult(output_path=output_path, report=report)


def _test_pyramid_artifacts(
    evidence_artifacts: tuple[LocalEvidenceArtifact, ...],
    *,
    root: Path,
) -> tuple[TestPyramidArtifactEvidence, ...]:
    selected = {
        artifact.id: _artifact_from_evidence_index(artifact) for artifact in evidence_artifacts
    }
    selected["coverage-json"] = _coverage_artifact(root=root)
    return tuple(selected.values())


def _artifact_from_evidence_index(
    artifact: LocalEvidenceArtifact,
) -> TestPyramidArtifactEvidence:
    return TestPyramidArtifactEvidence(
        id=artifact.id,
        label=artifact.label,
        path=artifact.path,
        state=artifact.state,
        schema_version=artifact.schema_version,
        summary=artifact.summary,
    )


def _coverage_artifact(*, root: Path) -> TestPyramidArtifactEvidence:
    definition = TestPyramidArtifactEvidence(
        id="coverage-json",
        label="Coverage JSON",
        path="reports/coverage.json",
        state="missing",
        schema_version="coverage.py.json",
        summary="missing",
    )
    path = root / "reports" / "coverage.json"
    unsafe_summary = _unsafe_artifact_summary(path, root=root)
    if unsafe_summary is not None:
        return definition.model_copy(
            update={"state": "unsafe", "schema_version": None, "summary": unsafe_summary}
        )
    if not path.exists():
        return definition
    if not path.is_file():
        return definition.model_copy(
            update={"state": "unsafe", "schema_version": None, "summary": "not a file"}
        )

    document, load_error = _load_coverage_json(path)
    if document is None:
        return definition.model_copy(
            update={"state": "invalid", "schema_version": None, "summary": load_error}
        )
    summary = _coverage_summary(document)
    if summary is None:
        return definition.model_copy(
            update={
                "state": "invalid",
                "schema_version": None,
                "summary": "coverage totals missing",
            }
        )
    return definition.model_copy(update={"state": "present", "summary": summary})


def _unsafe_artifact_summary(path: Path, *, root: Path) -> str | None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError:
        return "path outside project"
    if symlink_path is not None:
        return "symlinked path component"
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return "path outside project"
    return None


def _load_coverage_json(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        if path.stat().st_size > _MAX_COVERAGE_ARTIFACT_BYTES:
            return None, "artifact too large"
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "unreadable"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid JSON"
    return (document, "") if isinstance(document, dict) else (None, "invalid JSON")


def _coverage_summary(document: dict[str, object]) -> str | None:
    totals = document.get("totals")
    if not isinstance(totals, dict):
        return None
    display = totals.get("percent_covered_display")
    if isinstance(display, str) and _PERCENT_RE.fullmatch(display):
        return f"coverage {_normalize_percent(display)}"
    percent = totals.get("percent_covered")
    if isinstance(percent, int | float) and percent >= 0:
        return f"coverage {_normalize_percent(f'{percent:g}')}"
    return None


def _normalize_percent(value: str) -> str:
    return value if value.endswith("%") else f"{value}%"


def _render_report(report: TestPyramidReport, output: TestPyramidOutput) -> str:
    if output == "md":
        return render_test_pyramid_markdown(report)
    return report.model_dump_json(indent=2) + "\n"
