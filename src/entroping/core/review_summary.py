"""Provider-neutral review summaries from local Entroping artifacts."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal, Protocol, cast

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from entroping.bridge.story_traceability import (
    StoryTraceabilityReport,
    compile_story_traceability,
)
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.hurl_runner import redact_hurl_output
from entroping.core.safe_write import SafeWriteError, safe_write_text

ReviewStatus = Literal["pass", "attention", "fail"]
FindingSeverity = Literal["error", "warning", "notice"]
ArtifactState = Literal["present", "missing", "disabled"]


class _XmlElement(Protocol):
    text: str | None

    def get(self, key: str) -> str | None: ...

    def findall(self, path: str) -> Sequence[_XmlElement]: ...


class ReviewSummaryError(ValueError):
    """Raised when review-summary artifacts cannot be read safely."""


@dataclass(frozen=True, slots=True)
class ArtifactStatus:
    """Presence state for one input artifact."""

    name: str
    path: Path | None
    state: ArtifactState


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Runtime summary extracted from the JSON run report."""

    project: str
    environment: str
    total: int
    passed: int
    failed: int
    exit_code: int


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """One provider-neutral finding rendered into the review summary."""

    source: str
    severity: FindingSeverity
    path: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Compiled provider-neutral review summary."""

    status: ReviewStatus
    artifacts: tuple[ArtifactStatus, ...]
    run: RunSummary | None
    findings: tuple[ReviewFinding, ...]


@dataclass(frozen=True, slots=True)
class ReviewSummaryResult:
    """Result of writing a review-summary artifact."""

    summary: ReviewSummary
    output_path: Path


def run_review_summary(
    *,
    project_root: Path,
    run_json_path: Path,
    junit_path: Path,
    drift_path: Path,
    include_traceability: bool,
    output_path: Path | None = None,
) -> ReviewSummaryResult:
    """Build and write the provider-neutral review summary Markdown artifact."""

    root = project_root.expanduser().resolve()
    traceability_report = None
    if include_traceability:
        hurl_tests = discover_hurl_tests([root / "tests"]) if (root / "tests").exists() else []
        traceability_report = compile_story_traceability(hurl_tests)

    summary = build_review_summary(
        run_json_path=run_json_path,
        junit_path=junit_path,
        drift_path=drift_path,
        traceability_report=traceability_report,
        project_root=root,
        traceability_enabled=include_traceability,
    )
    destination = output_path or root / "reports" / "review-summary.md"
    try:
        written = safe_write_text(
            destination,
            render_review_summary_markdown(summary),
            artifact="review summary",
            root=root,
        )
    except SafeWriteError as exc:
        msg = str(exc)
        raise ReviewSummaryError(msg) from exc
    return ReviewSummaryResult(summary=summary, output_path=written)


def build_review_summary(
    *,
    run_json_path: Path,
    junit_path: Path,
    drift_path: Path,
    traceability_report: StoryTraceabilityReport | None,
    project_root: Path | None = None,
    traceability_enabled: bool | None = None,
) -> ReviewSummary:
    """Build a provider-neutral summary from existing local report artifacts."""

    root = project_root.expanduser().resolve() if project_root is not None else None
    artifacts: list[ArtifactStatus] = []
    findings: list[ReviewFinding] = []

    run = _load_run_summary(run_json_path, artifacts)
    findings.extend(_findings_from_run_json(run_json_path, root=root))
    findings.extend(_findings_from_junit(junit_path, artifacts, root=root))
    findings.extend(_findings_from_drift(drift_path, artifacts, root=root))

    if traceability_enabled is None:
        traceability_enabled = traceability_report is not None
    if traceability_enabled:
        artifacts.append(ArtifactStatus("Traceability", None, "present"))
    else:
        artifacts.append(ArtifactStatus("Traceability", None, "disabled"))

    if traceability_report is not None:
        findings.extend(_findings_from_traceability(traceability_report, root=root))

    status = _summary_status(run=run, artifacts=artifacts, findings=findings)
    return ReviewSummary(
        status=status,
        artifacts=tuple(artifacts),
        run=run,
        findings=tuple(findings),
    )


def render_review_summary_markdown(summary: ReviewSummary) -> str:
    """Render a safe Markdown review summary for CI logs or PR comments."""

    lines = [
        "# Entroping Review Summary",
        "",
        f"- Status: `{summary.status}`",
    ]
    if summary.run is not None:
        lines.extend(
            [
                f"- Project: `{_inline_code(summary.run.project)}`",
                f"- Environment: `{_inline_code(summary.run.environment)}`",
                f"- Total: `{summary.run.total}`",
                f"- Passed: `{summary.run.passed}`",
                f"- Failed: `{summary.run.failed}`",
                f"- Exit code: `{summary.run.exit_code}`",
            ]
        )

    lines.extend(["", "## Artifacts", ""])
    for artifact in summary.artifacts:
        suffix = ""
        if artifact.path is not None:
            suffix = f" ({_markdown_text(str(artifact.path))})"
        lines.append(f"- {artifact.name}: `{artifact.state}`{suffix}")

    lines.extend(["", "## Findings", ""])
    if not summary.findings:
        lines.append("No review findings were found.")
    else:
        lines.extend(
            [
                "| Source | Severity | Path | Message |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in summary.findings:
            path = finding.path or "n/a"
            lines.append(
                "| "
                f"{_markdown_cell(finding.source)} | "
                f"{_markdown_cell(finding.severity)} | "
                f"{_markdown_cell(path)} | "
                f"{_markdown_cell(finding.message)} |"
            )

    return "\n".join(lines) + "\n"


def _load_run_summary(path: Path, artifacts: list[ArtifactStatus]) -> RunSummary | None:
    artifacts.append(ArtifactStatus("Run JSON", path, _artifact_state(path)))
    if not path.exists():
        return None

    data = _load_json_object(path, artifact="run report")
    raw_summary = data.get("summary")
    if not isinstance(raw_summary, dict):
        msg = f"Run report {path} must contain a summary object"
        raise ReviewSummaryError(msg)
    return RunSummary(
        project=_string_field(data.get("project"), fallback="unknown"),
        environment=_string_field(data.get("environment"), fallback="default"),
        total=_int_field(raw_summary.get("total"), field="summary.total", path=path),
        passed=_int_field(raw_summary.get("passed"), field="summary.passed", path=path),
        failed=_int_field(raw_summary.get("failed"), field="summary.failed", path=path),
        exit_code=_int_field(raw_summary.get("exit_code"), field="summary.exit_code", path=path),
    )


def _findings_from_junit(
    path: Path,
    artifacts: list[ArtifactStatus],
    *,
    root: Path | None,
) -> tuple[ReviewFinding, ...]:
    artifacts.append(ArtifactStatus("JUnit XML", path, _artifact_state(path)))
    if not path.exists():
        return ()

    try:
        root_element = cast(_XmlElement, ElementTree.parse(path).getroot())
    except DefusedXmlException as exc:
        msg = f"Could not parse JUnit report {path}: unsafe XML construct: {exc}"
        raise ReviewSummaryError(msg) from exc
    except ElementTree.ParseError as exc:
        msg = f"Could not parse JUnit report {path}: {exc}"
        raise ReviewSummaryError(msg) from exc
    findings: list[ReviewFinding] = []
    for testcase in root_element.findall(".//testcase"):
        for element_name, title in (
            ("failure", "Hurl failure"),
            ("error", "JUnit error"),
        ):
            for element in testcase.findall(element_name):
                raw_message = (
                    element.text or element.get("message") or testcase.get("name") or title
                )
                message = _redacted_one_line(raw_message)
                findings.append(
                    ReviewFinding(
                        source="JUnit",
                        severity="error",
                        path=_display_path(_junit_test_path(testcase, message), root=root),
                        message=message,
                    )
                )
    return tuple(findings)


def _findings_from_run_json(path: Path, *, root: Path | None) -> tuple[ReviewFinding, ...]:
    if not path.exists():
        return ()

    data = _load_json_object(path, artifact="run report")
    raw_tests = data.get("tests", [])
    if not isinstance(raw_tests, list):
        return ()

    findings: list[ReviewFinding] = []
    for raw_test in raw_tests:
        if not isinstance(raw_test, dict):
            continue
        status = _string_field(raw_test.get("status"), fallback="unknown")
        exit_code = raw_test.get("exit_code")
        exit_code_text = str(exit_code) if isinstance(exit_code, int) else "unknown"
        path_value = _finding_path(raw_test.get("path"))
        if status == "timeout":
            timeout_ms = raw_test.get("timeout_ms")
            timeout_text = (
                str(timeout_ms)
                if isinstance(timeout_ms, int) and timeout_ms >= 0
                else "unknown"
            )
            findings.append(
                ReviewFinding(
                    source="Run JSON",
                    severity="error",
                    path=_display_path(path_value, root=root),
                    message=_redacted_one_line(
                        f"timed out after {timeout_text} ms; "
                        f"final status {status} exit={exit_code_text}"
                    ),
                )
            )
        retry = raw_test.get("retry")
        if not isinstance(retry, dict):
            continue
        retry_count = retry.get("retry_count")
        unstable = retry.get("unstable")
        if not isinstance(retry_count, int) or retry_count <= 0:
            continue
        retry_word = "retry" if retry_count == 1 else "retries"
        if unstable is True:
            severity: FindingSeverity = "warning"
            message = (
                f"unstable after {retry_count} {retry_word}; "
                f"final status {status} exit={exit_code_text}"
            )
        else:
            severity = "notice"
            message = (
                f"retried {retry_count} {retry_word}; "
                f"final status {status} exit={exit_code_text}"
            )
        findings.append(
            ReviewFinding(
                source="Run JSON",
                severity=severity,
                path=_display_path(path_value, root=root),
                message=_redacted_one_line(message),
            )
        )
    return tuple(findings)


def _findings_from_drift(
    path: Path,
    artifacts: list[ArtifactStatus],
    *,
    root: Path | None,
) -> tuple[ReviewFinding, ...]:
    artifacts.append(ArtifactStatus("Drift JSON", path, _artifact_state(path)))
    if not path.exists():
        return ()

    data = _load_json_object(path, artifact="drift report")
    raw_findings = data.get("findings", [])
    if not isinstance(raw_findings, list):
        msg = f"Drift report {path} must contain a findings list"
        raise ReviewSummaryError(msg)

    findings: list[ReviewFinding] = []
    for raw_finding in raw_findings:
        if not isinstance(raw_finding, dict):
            continue
        kind = _string_field(raw_finding.get("kind"), fallback="unknown")
        message = _redacted_one_line(_string_field(raw_finding.get("message"), fallback=kind))
        findings.append(
            ReviewFinding(
                source="Drift",
                severity=_drift_severity(raw_finding.get("severity")),
                path=_display_path(_finding_path(raw_finding.get("path")), root=root),
                message=message,
            )
        )
    return tuple(findings)


def _findings_from_traceability(
    report: StoryTraceabilityReport,
    *,
    root: Path | None,
) -> tuple[ReviewFinding, ...]:
    findings: list[ReviewFinding] = []
    for finding in report.findings:
        path = _display_path(finding.test_path, root=root)
        message = finding.message
        if finding.test_path is not None and path is not None:
            raw_path = str(finding.test_path)
            message = message.replace(raw_path, path)
            message = message.replace(finding.test_path.as_posix(), path)
        findings.append(
            ReviewFinding(
                source="Traceability",
                severity="error" if finding.kind == "missing_story_id" else "warning",
                path=path,
                message=_redacted_one_line(message),
            )
        )
    return tuple(findings)


def _summary_status(
    *,
    run: RunSummary | None,
    artifacts: list[ArtifactStatus],
    findings: list[ReviewFinding],
) -> ReviewStatus:
    if run is not None and (run.failed > 0 or run.exit_code != 0):
        return "fail"
    if any(finding.severity == "error" for finding in findings):
        return "fail"
    if any(finding.severity == "warning" for finding in findings):
        return "attention"
    if all(artifact.state != "present" for artifact in artifacts):
        return "attention"
    return "pass"


def _load_json_object(path: Path, *, artifact: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact} {path}: {exc}"
        raise ReviewSummaryError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{artifact.capitalize()} {path} must be a JSON object"
        raise ReviewSummaryError(msg)
    return data


def _artifact_state(path: Path) -> ArtifactState:
    return "present" if path.exists() else "missing"


def _junit_test_path(testcase: _XmlElement, message: str) -> Path | None:
    for line in message.splitlines():
        if line.startswith("path: "):
            return Path(line.removeprefix("path: ").strip())

    name = testcase.get("name")
    if not name:
        return None
    classname = testcase.get("classname") or ""
    if not classname or classname == ".":
        return Path(name)
    return Path(classname.replace("\\", "/")) / name


def _finding_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if stripped == "*" or stripped.startswith("dependency:"):
        return None
    return Path(stripped)


def _display_path(path: Path | None, *, root: Path | None) -> str | None:
    if path is None:
        return None
    normalized = Path(" ".join(str(path).replace("\\", "/").split()))
    if root is not None:
        try:
            return normalized.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            pass
    return normalized.as_posix()


def _redacted_one_line(value: str) -> str:
    return redact_hurl_output(value)


def _string_field(value: object, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return fallback


def _int_field(value: object, *, field: str, path: Path) -> int:
    if not isinstance(value, int) or value < 0:
        msg = f"Run report {path} field {field} must be a non-negative integer"
        raise ReviewSummaryError(msg)
    return value


def _drift_severity(value: object) -> FindingSeverity:
    if value == "error":
        return "error"
    if value == "warning":
        return "warning"
    return "notice"


def _inline_code(value: str) -> str:
    return value.replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|")
