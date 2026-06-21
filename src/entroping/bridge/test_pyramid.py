"""Compile local test-pyramid evidence summaries."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TEST_PYRAMID_REPORT_SCHEMA_VERSION = "entroping.test-pyramid-report.v1"

ArtifactState = Literal["present", "missing", "invalid", "unsafe"]
LayerStatus = Literal["present", "missing", "incomplete", "invalid", "unsafe"]
RuntimeGovernanceStatus = Literal["complete", "incomplete"]

_RUNTIME_GOVERNANCE_ARTIFACTS = frozenset(
    {
        "run-json",
        "junit-xml",
        "gate-coverage-json",
    }
)
_INLINE_CODE_RUN_RE = re.compile(r"`+")


class TestPyramidArtifactEvidence(BaseModel):
    """Value-free status for one local evidence artifact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    path: str
    state: ArtifactState
    schema_version: str | None = None
    summary: str


class TestPyramidLayer(BaseModel):
    """One classified test-pyramid evidence layer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    status: LayerStatus
    summary: str
    artifacts: tuple[TestPyramidArtifactEvidence, ...]


class TestPyramidFinding(BaseModel):
    """Missing or unsafe runtime-governance proof."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["high"]
    layer_id: str
    artifact_id: str
    state: ArtifactState
    message: str


class TestPyramidSummary(BaseModel):
    """Aggregate test-pyramid evidence status."""

    model_config = ConfigDict(extra="forbid")

    total_layers: int = Field(ge=0)
    present_layers: int = Field(ge=0)
    attention_layers: int = Field(ge=0)
    findings: int = Field(ge=0)
    runtime_governance_status: RuntimeGovernanceStatus


class TestPyramidReport(BaseModel):
    """Machine-readable local test-pyramid evidence report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.test-pyramid-report.v1"] = (
        "entroping.test-pyramid-report.v1"
    )
    project: str
    summary: TestPyramidSummary
    layers: tuple[TestPyramidLayer, ...]
    findings: tuple[TestPyramidFinding, ...]


def compile_test_pyramid_report(
    artifacts: tuple[TestPyramidArtifactEvidence, ...],
    *,
    project: str,
) -> TestPyramidReport:
    """Classify local evidence artifacts into a test-pyramid summary."""

    by_id = {artifact.id: artifact for artifact in artifacts}
    layers = tuple(
        _layer(layer_id, label, artifact_ids, by_id=by_id)
        for layer_id, label, artifact_ids in _layer_definitions(by_id=by_id)
    )
    findings = tuple(
        _runtime_finding(layer.id, artifact)
        for layer in layers
        for artifact in layer.artifacts
        if artifact.id in _RUNTIME_GOVERNANCE_ARTIFACTS and artifact.state != "present"
    )
    present_layers = sum(1 for layer in layers if layer.status == "present")
    summary = TestPyramidSummary(
        total_layers=len(layers),
        present_layers=present_layers,
        attention_layers=len(layers) - present_layers,
        findings=len(findings),
        runtime_governance_status="complete" if not findings else "incomplete",
    )
    return TestPyramidReport(
        project=project,
        summary=summary,
        layers=layers,
        findings=findings,
    )


def render_test_pyramid_markdown(report: TestPyramidReport) -> str:
    """Render a value-free Markdown test-pyramid evidence summary."""

    lines = [
        "# Entroping Test Pyramid Evidence",
        "",
        f"- Project: {_inline_code(report.project)}",
        f"- Runtime governance: {_inline_code(report.summary.runtime_governance_status)}",
        f"- Layers present: {report.summary.present_layers}/{report.summary.total_layers}",
        f"- Findings: {report.summary.findings}",
        "",
        "## Layers",
        "",
        "| Layer | Status | Summary |",
        "| --- | --- | --- |",
    ]
    for layer in report.layers:
        lines.append(
            "| "
            f"{_escape_markdown(layer.label)} | {_inline_code(layer.status)} | "
            f"{_escape_markdown(layer.summary)} |"
        )

    lines.extend(["", "## Missing Runtime Governance Proof", ""])
    if report.findings:
        lines.extend(
            [
                "| Artifact | State | Finding |",
                "| --- | --- | --- |",
            ]
        )
        for finding in report.findings:
            lines.append(
                "| "
                f"{_inline_code(finding.artifact_id)} | "
                f"{_inline_code(finding.state)} | {_escape_markdown(finding.message)} |"
            )
    else:
        lines.append("No missing runtime-governance proof detected from local artifacts.")

    lines.extend(["", "## Artifact Evidence", ""])
    for layer in report.layers:
        lines.extend([f"### {_escape_markdown(layer.label)}", ""])
        for artifact in layer.artifacts:
            schema = artifact.schema_version or "none"
            lines.append(
                "- "
                f"{_inline_code(artifact.id)}: {_inline_code(artifact.state)}; "
                f"schema {_inline_code(schema)}; "
                f"{_escape_markdown(artifact.summary)}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _layer_definitions(
    *,
    by_id: dict[str, TestPyramidArtifactEvidence] | None = None,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    definitions = (
        ("code-coverage", "Code Coverage", ("coverage-json",)),
        ("runtime-api-proof", "Runtime API Proof", ("run-json", "junit-xml")),
        ("policy-governance", "Policy Governance", ("gate-coverage-json",)),
        ("drift-contract", "Drift And Contract Evidence", ("drift-json",)),
        ("static-security", "Static And Security Evidence", ("sarif",)),
        ("generated-test-quality", "Generated-Test Quality", ("test-quality-json",)),
    )
    if by_id is not None and "external-test-evidence-json" in by_id:
        return definitions + (
            (
                "external-test-evidence",
                "External Test Evidence",
                ("external-test-evidence-json",),
            ),
        )
    return definitions


def _artifact_definitions() -> dict[str, tuple[str, str, str | None]]:
    return {
        "coverage-json": ("Coverage JSON", "reports/coverage.json", "coverage.py.json"),
        "run-json": ("Run JSON", "reports/run-latest.json", "entroping.run-report.v1"),
        "junit-xml": ("JUnit XML", "reports/junit.xml", "junit.xml"),
        "gate-coverage-json": (
            "Gate Coverage JSON",
            "reports/gate-coverage.json",
            "entroping.gate-coverage-report.v1",
        ),
        "drift-json": ("Drift JSON", "reports/drift.json", "entroping.drift-report.v1"),
        "sarif": ("SARIF", "reports/entroping.sarif", "SARIF 2.1.0"),
        "test-quality-json": (
            "Generated-Test Quality JSON",
            "reports/test-quality.json",
            "entroping.test-quality-report.v1",
        ),
        "external-test-evidence-json": (
            "External Test Evidence JSON",
            "reports/external-test-evidence.json",
            "entroping.external-test-evidence.v1",
        ),
    }


def _layer(
    layer_id: str,
    label: str,
    artifact_ids: tuple[str, ...],
    *,
    by_id: dict[str, TestPyramidArtifactEvidence],
) -> TestPyramidLayer:
    artifacts = tuple(
        by_id.get(artifact_id) or _missing_artifact(artifact_id)
        for artifact_id in artifact_ids
    )
    status = _layer_status(artifacts)
    return TestPyramidLayer(
        id=layer_id,
        label=label,
        status=status,
        summary=_layer_summary(status),
        artifacts=artifacts,
    )


def _missing_artifact(artifact_id: str) -> TestPyramidArtifactEvidence:
    label, path, schema_version = _artifact_definitions().get(
        artifact_id,
        (artifact_id, "", None),
    )
    return TestPyramidArtifactEvidence(
        id=artifact_id,
        label=label,
        path=path,
        state="missing",
        schema_version=schema_version,
        summary="missing",
    )


def _layer_status(artifacts: tuple[TestPyramidArtifactEvidence, ...]) -> LayerStatus:
    states = {artifact.state for artifact in artifacts}
    if states == {"present"}:
        return "present"
    if "unsafe" in states:
        return "unsafe"
    if "invalid" in states:
        return "invalid"
    if "present" in states:
        return "incomplete"
    return "missing"


def _layer_summary(status: LayerStatus) -> str:
    if status == "present":
        return "all required evidence present"
    if status == "incomplete":
        return "some required evidence missing"
    if status == "invalid":
        return "invalid evidence needs review"
    if status == "unsafe":
        return "unsafe evidence path needs review"
    return "required evidence missing"


def _runtime_finding(layer_id: str, artifact: TestPyramidArtifactEvidence) -> TestPyramidFinding:
    return TestPyramidFinding(
        severity="high",
        layer_id=layer_id,
        artifact_id=artifact.id,
        state=artifact.state,
        message=(
            f"Runtime governance proof is {artifact.state} "
            f"for {artifact.label} evidence."
        ),
    )


def _escape_markdown(value: str) -> str:
    normalized = _normalize_markdown_text(value)
    return (
        normalized.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("#", "\\#")
    )


def _inline_code(value: str) -> str:
    normalized = _normalize_markdown_text(value)
    longest_run = max(
        (len(match.group(0)) for match in _INLINE_CODE_RUN_RE.finditer(normalized)),
        default=0,
    )
    fence = "`" * (longest_run + 1)
    if normalized.startswith("`") or normalized.endswith("`"):
        normalized = f" {normalized} "
    return f"{fence}{normalized}{fence}"


def _normalize_markdown_text(value: str) -> str:
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
