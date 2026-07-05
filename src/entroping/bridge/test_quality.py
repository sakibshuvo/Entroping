"""Compile deterministic quality reports for generated Hurl tests."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.hurl_source import read_hurl_source_text
from entroping.models.hurl import HurlTest

TEST_QUALITY_REPORT_SCHEMA_VERSION = "entroping.test-quality-report.v1"

TestQualityCategory = Literal[
    "assertion-strength",
    "brittle-selector",
    "missing-negative-path",
    "weak-auth-coverage",
    "shallow-schema-check",
    "overfitted-example",
    "policy-alignment",
    "missing-generated-tests",
]
TestQualitySeverity = Literal["high", "medium", "low"]
TestQualityStatus = Literal["pass", "warn", "fail", "missing"]

_GENERATED_SOURCES = frozenset({"architect", "openapi", "traffic"})
_ASSERTION_SECTION = "[Asserts]"
_ASSERTION_PREFIXES = (
    "body",
    "certificate",
    "cookie",
    "header",
    "jsonpath",
    "regex",
    "variable",
    "xpath",
)
_TYPE_OR_EXISTENCE_ASSERTION_RE = re.compile(
    r"\b(exists|not exists|isBoolean|isCollection|isDate|isFloat|isInteger|isNumber|isString)\b"
)
_BRITTLE_JSONPATH_RE = re.compile(r"jsonpath\s+\"[^\"]*\[\d+\][^\"]*\"")
_OVERFITTED_EQUALITY_RE = re.compile(
    r"==\s+\"(?:[A-Za-z]+[_-])?\d[\w.-]*\"|==\s+\"[\w.-]*[_-]\d[\w.-]*\""
)
_NUMERIC_PATH_SEGMENT_RE = re.compile(r"/\d+(?:/|$)")
_UUID_PATH_SEGMENT_RE = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:/|$)"
)


class TestQualityFinding(BaseModel):
    """One deterministic generated-test quality finding."""

    model_config = ConfigDict(extra="forbid")

    category: TestQualityCategory
    severity: TestQualitySeverity
    path: str | None
    message: str
    evidence: str
    deduction: int = Field(ge=0, le=100)


class TestQualityTestReport(BaseModel):
    """Quality score and findings for one generated Hurl file."""

    model_config = ConfigDict(extra="forbid")

    path: str
    source: str
    operation_id: str | None
    negative_category: str | None = None
    security: str | None = None
    tags: tuple[str, ...]
    score: int = Field(ge=0, le=100)
    findings: tuple[TestQualityFinding, ...]


class TestQualitySummary(BaseModel):
    """Aggregate generated-test quality score counts."""

    model_config = ConfigDict(extra="forbid")

    total_tests: int = Field(ge=0)
    generated_tests: int = Field(ge=0)
    manual_tests: int = Field(ge=0)
    score: int = Field(ge=0, le=100)
    status: TestQualityStatus
    findings: int = Field(ge=0)


class TestQualityReport(BaseModel):
    """Machine-readable static quality score for generated Hurl tests."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.test-quality-report.v1"] = (
        "entroping.test-quality-report.v1"
    )
    project: str
    summary: TestQualitySummary
    findings: tuple[TestQualityFinding, ...]
    tests: tuple[TestQualityTestReport, ...]


def compile_test_quality_report(
    hurl_tests: tuple[HurlTest, ...],
    *,
    project: str,
    root: Path,
) -> TestQualityReport:
    """Compile a deterministic static score for generated Hurl tests.

    The report reads committed Hurl source locally but never emits raw request
    targets, assertion values, headers, bodies, or provider output.
    """

    resolved_root = root.expanduser().resolve()
    generated: list[TestQualityTestReport] = []
    for hurl_test in hurl_tests:
        if not _is_generated_test(hurl_test, root=resolved_root):
            continue
        content = read_hurl_source_text(hurl_test.path)
        generated.append(_score_test(hurl_test, content=content, root=resolved_root))

    corpus_findings = _corpus_findings(tuple(generated))
    if not generated:
        summary = TestQualitySummary(
            total_tests=len(hurl_tests),
            generated_tests=0,
            manual_tests=len(hurl_tests),
            score=0,
            status="missing",
            findings=len(corpus_findings),
        )
        return TestQualityReport(
            project=project,
            summary=summary,
            findings=corpus_findings,
            tests=(),
        )

    test_score = round(sum(test.score for test in generated) / len(generated))
    score = max(0, test_score - sum(finding.deduction for finding in corpus_findings))
    findings_count = sum(len(test.findings) for test in generated) + len(corpus_findings)
    return TestQualityReport(
        project=project,
        summary=TestQualitySummary(
            total_tests=len(hurl_tests),
            generated_tests=len(generated),
            manual_tests=len(hurl_tests) - len(generated),
            score=score,
            status=_status_for_score(score),
            findings=findings_count,
        ),
        findings=corpus_findings,
        tests=tuple(generated),
    )


def render_test_quality_markdown(report: TestQualityReport) -> str:
    """Render a value-safe generated-test quality score."""

    lines = [
        "# Entroping Generated-Test Quality Score",
        "",
        "Static local evidence for reviewing AI- or compiler-generated Hurl tests. "
        + "This score does not execute Hurl, call model providers, upload artifacts, "
        + "or replace QAnstitution/Hurl pass-fail authority.",
        "",
        "## Summary",
        "",
        f"- Project: {_escape_markdown_text(report.project)}",
        f"- Status: {_escape_markdown_text(report.summary.status)}",
        f"- Score: {report.summary.score}",
        f"- Generated tests: {report.summary.generated_tests}",
        f"- Manual tests skipped: {report.summary.manual_tests}",
        f"- Findings: {report.summary.findings}",
        "",
    ]
    if report.findings:
        lines.extend(
            [
                "## Corpus Findings",
                "",
                "| Category | Severity | Evidence | Deduction |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in report.findings:
            lines.append(_finding_row(finding))
        lines.append("")

    lines.extend(
        [
            "## Generated Tests",
            "",
            "| Test | Source | Operation ID | Tags | Score | Findings |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for test in report.tests:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(test.path),
                    _escape_markdown_cell(test.source),
                    _escape_markdown_cell(test.operation_id or ""),
                    _escape_markdown_cell(", ".join(test.tags)),
                    str(test.score),
                    str(len(test.findings)),
                ]
            )
            + " |"
        )
    if not report.tests:
        lines.append("|  |  |  |  | 0 | 0 |")
    lines.append("")

    for test in report.tests:
        if not test.findings:
            continue
        lines.extend(
            [
                f"## {_escape_markdown_text(test.path)}",
                "",
                "| Category | Severity | Evidence | Deduction |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in test.findings:
            lines.append(_finding_row(finding))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _score_test(hurl_test: HurlTest, *, content: str, root: Path) -> TestQualityTestReport:
    path = _display_path(hurl_test.path, root=root)
    findings: list[TestQualityFinding] = []
    assertion_lines = _assertion_lines(content)

    if len(assertion_lines) < 2:
        findings.append(
            _finding(
                "assertion-strength",
                "medium",
                path=path,
                message="Generated test has fewer than two response assertions.",
                evidence="assertion count",
                deduction=20,
            )
        )
    if any(_BRITTLE_JSONPATH_RE.search(line) for line in assertion_lines):
        findings.append(
            _finding(
                "brittle-selector",
                "low",
                path=path,
                message="Generated test uses positional JSONPath selectors.",
                evidence="positional JSONPath selector",
                deduction=10,
            )
        )
    if assertion_lines and not any(
        _TYPE_OR_EXISTENCE_ASSERTION_RE.search(line) for line in assertion_lines
    ):
        findings.append(
            _finding(
                "shallow-schema-check",
                "medium",
                path=path,
                message="Generated test lacks type or existence assertions.",
                evidence="assertion operator mix",
                deduction=10,
            )
        )
    if _has_overfitted_example(hurl_test, content=content):
        findings.append(
            _finding(
                "overfitted-example",
                "medium",
                path=path,
                message="Generated test appears tied to one concrete example value.",
                evidence="literal equality or identifier-shaped path",
                deduction=10,
            )
        )
    if hurl_test.metadata.operation_id is None:
        findings.append(
            _finding(
                "policy-alignment",
                "medium",
                path=path,
                message="Generated test is missing operation_id traceability metadata.",
                evidence="metadata",
                deduction=10,
            )
        )

    return TestQualityTestReport(
        path=path,
        source=hurl_test.metadata.meta.get("source", "unknown"),
        operation_id=hurl_test.metadata.operation_id,
        negative_category=hurl_test.metadata.meta.get("negative_category"),
        security=hurl_test.metadata.meta.get("security"),
        tags=tuple(sorted(hurl_test.tags)),
        score=max(0, 100 - sum(finding.deduction for finding in findings)),
        findings=tuple(findings),
    )


def _corpus_findings(
    generated: tuple[TestQualityTestReport, ...],
) -> tuple[TestQualityFinding, ...]:
    if not generated:
        return (
            _finding(
                "missing-generated-tests",
                "high",
                path=None,
                message="No generated Hurl tests were discovered.",
                evidence="tests/generated or generated metadata",
                deduction=100,
            ),
        )

    findings: list[TestQualityFinding] = []
    if not any(_has_negative_evidence(test) for test in generated):
        findings.append(
            _finding(
                "missing-negative-path",
                "medium",
                path=None,
                message="Generated-test corpus has no negative-path metadata.",
                evidence="generated corpus metadata",
                deduction=10,
            )
        )
    if not any(_has_auth_evidence(test) for test in generated):
        findings.append(
            _finding(
                "weak-auth-coverage",
                "medium",
                path=None,
                message="Generated-test corpus has no auth or security coverage metadata.",
                evidence="generated corpus metadata",
                deduction=10,
            )
        )
    return tuple(findings)


def _finding(
    category: TestQualityCategory,
    severity: TestQualitySeverity,
    *,
    path: str | None,
    message: str,
    evidence: str,
    deduction: int,
) -> TestQualityFinding:
    return TestQualityFinding(
        category=category,
        severity=severity,
        path=path,
        message=message,
        evidence=evidence,
        deduction=deduction,
    )


def _is_generated_test(hurl_test: HurlTest, *, root: Path) -> bool:
    source = hurl_test.metadata.meta.get("source")
    if source in _GENERATED_SOURCES:
        return True
    if "generated" in hurl_test.tags:
        return True
    try:
        relative = hurl_test.path.expanduser().resolve().relative_to(root)
    except ValueError:
        return False
    return len(relative.parts) >= 2 and relative.parts[:2] == ("tests", "generated")


def _assertion_lines(content: str) -> tuple[str, ...]:
    in_asserts = False
    assertions: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == _ASSERTION_SECTION:
            in_asserts = True
            continue
        if in_asserts and stripped.startswith("[") and stripped.endswith("]"):
            in_asserts = False
            continue
        if not in_asserts or not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(_ASSERTION_PREFIXES):
            assertions.append(stripped)
    return tuple(assertions)


def _has_overfitted_example(hurl_test: HurlTest, *, content: str) -> bool:
    if _OVERFITTED_EQUALITY_RE.search(content) is not None:
        return True
    return any(
        _NUMERIC_PATH_SEGMENT_RE.search(exchange.path) is not None
        or _UUID_PATH_SEGMENT_RE.search(exchange.path) is not None
        for exchange in hurl_test.exchanges
    )


def _has_negative_evidence(test: TestQualityTestReport) -> bool:
    return test.negative_category is not None


def _has_auth_evidence(test: TestQualityTestReport) -> bool:
    return test.security is not None or bool(
        {"security", "auth", "invalid-auth"}.intersection(test.tags)
    )


def _status_for_score(score: int) -> TestQualityStatus:
    if score >= 85:
        return "pass"
    if score >= 60:
        return "warn"
    return "fail"


def _display_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return f"<outside-project>/{resolved.name}"


def _finding_row(finding: TestQualityFinding) -> str:
    values = [
        finding.category,
        finding.severity,
        finding.evidence,
        str(finding.deduction),
    ]
    return "| " + " | ".join(_escape_markdown_cell(value) for value in values) + " |"


def _escape_markdown_cell(value: str) -> str:
    return _escape_markdown_text(value).replace("|", "\\|")


def _escape_markdown_text(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace("`", "\\`")
