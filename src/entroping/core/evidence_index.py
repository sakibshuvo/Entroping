"""Read-only local evidence artifact index for Studio and future viewers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.bridge.capture_summary import CAPTURE_SUMMARY_SCHEMA_VERSION
from entroping.bridge.effective_policy import EFFECTIVE_POLICY_SCHEMA_VERSION
from entroping.bridge.gate_coverage import GATE_COVERAGE_REPORT_SCHEMA_VERSION
from entroping.bridge.gate_injection_explain import GATE_INJECTION_REPORT_SCHEMA_VERSION
from entroping.core.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.drift_report import DRIFT_REPORT_SCHEMA_VERSION
from entroping.core.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.failure_bundle import FAILURE_BUNDLE_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_artifact_manifest import REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION
from entroping.core.run_workflow import RUN_PLAN_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION

EvidenceArtifactState = Literal["present", "missing", "invalid", "unsafe"]
_ArtifactKind = Literal["json", "markdown", "xml", "html", "sarif"]
_SummaryBuilder = Callable[[dict[str, object]], str]
_MAX_JSON_ARTIFACT_BYTES: Final = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LocalEvidenceArtifact:
    """Value-free status for one canonical local evidence artifact."""

    id: str
    label: str
    path: str
    state: EvidenceArtifactState
    schema_version: str | None
    summary: str


@dataclass(frozen=True, slots=True)
class _EvidenceArtifactDefinition:
    id: str
    label: str
    path: Path
    kind: _ArtifactKind
    schema_version: str | None
    summary_builder: _SummaryBuilder | None = None


def build_local_evidence_index(*, project_root: Path) -> tuple[LocalEvidenceArtifact, ...]:
    """Return value-free status rows for canonical local report artifacts."""

    root = project_root.expanduser().resolve()
    return tuple(_artifact_status(definition, root=root) for definition in _artifact_definitions())


def _artifact_definitions() -> tuple[_EvidenceArtifactDefinition, ...]:
    return (
        _EvidenceArtifactDefinition(
            id="run-json",
            label="Run JSON",
            path=Path("reports") / "run-latest.json",
            kind="json",
            schema_version=RUN_REPORT_SCHEMA_VERSION,
            summary_builder=_run_summary,
        ),
        _EvidenceArtifactDefinition(
            id="run-plan-json",
            label="Run Plan",
            path=Path("reports") / "run-plan.json",
            kind="json",
            schema_version=RUN_PLAN_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="junit-xml",
            label="JUnit XML",
            path=Path("reports") / "junit.xml",
            kind="xml",
            schema_version="junit.xml",
        ),
        _EvidenceArtifactDefinition(
            id="run-html",
            label="Run HTML",
            path=Path("reports") / "run-latest.html",
            kind="html",
            schema_version="entroping.run-report.html",
        ),
        _EvidenceArtifactDefinition(
            id="drift-json",
            label="Drift JSON",
            path=Path("reports") / "drift.json",
            kind="json",
            schema_version=DRIFT_REPORT_SCHEMA_VERSION,
            summary_builder=_drift_summary,
        ),
        _EvidenceArtifactDefinition(
            id="bug-md",
            label="Bug Markdown",
            path=Path("reports") / "bug.md",
            kind="markdown",
            schema_version="entroping.bug.md",
        ),
        _EvidenceArtifactDefinition(
            id="failure-bundle-manifest-json",
            label="Failure Bundle Manifest",
            path=Path("reports") / "failure-bundle" / "manifest.json",
            kind="json",
            schema_version=FAILURE_BUNDLE_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="capture-summary-json",
            label="Capture Summary JSON",
            path=Path("reports") / "capture-summary.json",
            kind="json",
            schema_version=CAPTURE_SUMMARY_SCHEMA_VERSION,
            summary_builder=_capture_summary,
        ),
        _EvidenceArtifactDefinition(
            id="capture-summary-md",
            label="Capture Summary Markdown",
            path=Path("reports") / "capture-summary.md",
            kind="markdown",
            schema_version="entroping.capture-summary.md",
        ),
        _EvidenceArtifactDefinition(
            id="effective-policy-json",
            label="Effective Policy JSON",
            path=Path("reports") / "effective-policy.json",
            kind="json",
            schema_version=EFFECTIVE_POLICY_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="effective-policy-md",
            label="Effective Policy Markdown",
            path=Path("reports") / "effective-policy.md",
            kind="markdown",
            schema_version="entroping.effective-policy.md",
        ),
        _EvidenceArtifactDefinition(
            id="gate-coverage-json",
            label="Gate Coverage JSON",
            path=Path("reports") / "gate-coverage.json",
            kind="json",
            schema_version=GATE_COVERAGE_REPORT_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="gate-coverage-md",
            label="Gate Coverage Markdown",
            path=Path("reports") / "gate-coverage.md",
            kind="markdown",
            schema_version="entroping.gate-coverage.md",
        ),
        _EvidenceArtifactDefinition(
            id="gate-injection-json",
            label="Gate Injection JSON",
            path=Path("reports") / "gate-injection.json",
            kind="json",
            schema_version=GATE_INJECTION_REPORT_SCHEMA_VERSION,
        ),
        _EvidenceArtifactDefinition(
            id="gate-injection-md",
            label="Gate Injection Markdown",
            path=Path("reports") / "gate-injection.md",
            kind="markdown",
            schema_version="entroping.gate-injection.md",
        ),
        _EvidenceArtifactDefinition(
            id="artifact-manifest-json",
            label="Artifact Manifest",
            path=Path("reports") / "artifact-manifest.json",
            kind="json",
            schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
            summary_builder=_artifact_manifest_summary,
        ),
        _EvidenceArtifactDefinition(
            id="evidence-bundle-json",
            label="Evidence Bundle",
            path=Path("reports") / "evidence-bundle.json",
            kind="json",
            schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="runtime-card-md",
            label="Runtime Card Markdown",
            path=Path("reports") / "runtime-card.md",
            kind="markdown",
            schema_version="entroping.runtime-card.md",
        ),
        _EvidenceArtifactDefinition(
            id="runtime-card-json",
            label="Runtime Card JSON",
            path=Path("reports") / "runtime-card.json",
            kind="json",
            schema_version=RUNTIME_CARD_SCHEMA_VERSION,
            summary_builder=_status_summary,
        ),
        _EvidenceArtifactDefinition(
            id="agent-bundle-md",
            label="Agent Bundle Markdown",
            path=Path("reports") / "agent-bundle.md",
            kind="markdown",
            schema_version="entroping.agent-review-bundle.md",
        ),
        _EvidenceArtifactDefinition(
            id="agent-bundle-json",
            label="Agent Bundle JSON",
            path=Path("reports") / "agent-bundle.json",
            kind="json",
            schema_version=AGENT_REVIEW_BUNDLE_SCHEMA_VERSION,
            summary_builder=_agent_bundle_summary,
        ),
        _EvidenceArtifactDefinition(
            id="sarif",
            label="SARIF",
            path=Path("reports") / "entroping.sarif",
            kind="sarif",
            schema_version="SARIF 2.1.0",
        ),
        _EvidenceArtifactDefinition(
            id="review-summary-md",
            label="Review Summary",
            path=Path("reports") / "review-summary.md",
            kind="markdown",
            schema_version="entroping.review-summary.md",
        ),
    )


def _artifact_status(
    definition: _EvidenceArtifactDefinition,
    *,
    root: Path,
) -> LocalEvidenceArtifact:
    candidate = root / definition.path
    unsafe_summary = _unsafe_summary(candidate, root=root)
    if unsafe_summary is not None:
        return _status(definition, "unsafe", None, unsafe_summary)
    if not candidate.exists():
        return _status(definition, "missing", None, "missing")
    if not candidate.is_file():
        return _status(definition, "unsafe", None, "not a file")
    if definition.kind == "json":
        return _json_status(definition, candidate)
    if definition.kind == "sarif":
        return _sarif_status(definition, candidate)
    return _status(definition, "present", definition.schema_version, f"{definition.label} present")


def _unsafe_summary(path: Path, *, root: Path) -> str | None:
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


def _json_status(definition: _EvidenceArtifactDefinition, path: Path) -> LocalEvidenceArtifact:
    document, load_error = _load_json_object(path)
    if document is None:
        return _status(definition, "invalid", None, load_error)
    if document.get("schema_version") != definition.schema_version:
        return _status(definition, "invalid", None, "schema mismatch")
    summary = _metadata_summary(definition, document)
    return _status(definition, "present", definition.schema_version, summary)


def _sarif_status(definition: _EvidenceArtifactDefinition, path: Path) -> LocalEvidenceArtifact:
    document, load_error = _load_json_object(path)
    if document is None:
        return _status(definition, "invalid", None, load_error)
    if document.get("version") != "2.1.0":
        return _status(definition, "invalid", None, "schema mismatch")
    return _status(definition, "present", definition.schema_version, "SARIF 2.1.0")


def _load_json_object(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        if path.stat().st_size > _MAX_JSON_ARTIFACT_BYTES:
            return None, "artifact too large"
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "unreadable"
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid JSON"
    return (document, "") if isinstance(document, dict) else (None, "invalid JSON")


def _metadata_summary(
    definition: _EvidenceArtifactDefinition,
    document: dict[str, object],
) -> str:
    if definition.summary_builder is None:
        return f"{definition.label} present"
    return definition.summary_builder(document)


def _run_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    total = _int_field(summary, "total")
    passed = _int_field(summary, "passed")
    failed = _int_field(summary, "failed")
    if total is None or passed is None or failed is None:
        return "run summary available"
    return f"{total} total, {passed} passed, {failed} failed"


def _drift_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    findings = _int_field(summary, "findings")
    drifted = _int_field(summary, "drifted")
    if findings is None or drifted is None:
        return "drift summary available"
    return f"{findings} findings, {drifted} drifted"


def _capture_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    total = _int_field(summary, "total_records")
    redacted = _int_field(summary, "redacted_records")
    unredacted = _int_field(summary, "unredacted_records")
    if total is None or redacted is None or unredacted is None:
        return "capture summary available"
    return f"{redacted}/{total} records redacted, {unredacted} unredacted"


def _artifact_manifest_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    present = _int_field(summary, "total_present")
    missing = _int_field(summary, "total_missing")
    audit = _object_field(document, "audit")
    verification = _object_field(audit, "verification")
    audit_status = _allowed_status(
        verification.get("status"),
        allowed=("verified", "broken"),
        fallback="unknown",
    )
    if present is None or missing is None:
        return f"audit {audit_status}"
    return f"{present} present, {missing} missing, audit {audit_status}"


def _status_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    return _allowed_status(
        summary.get("status"),
        allowed=("ready", "not_ready", "pass", "attention", "fail"),
        fallback="unknown",
    )


def _agent_bundle_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    status = _allowed_status(
        summary.get("status"),
        allowed=("pass", "attention", "fail"),
        fallback="unknown",
    )
    manifests = _int_field(summary, "manifests")
    findings = _int_field(summary, "findings")
    if manifests is None or findings is None:
        return status
    return f"{status}, {manifests} manifests, {findings} findings"


def _object_field(document: dict[str, object], field: str) -> dict[str, object]:
    value = document.get(field)
    return value if isinstance(value, dict) else {}


def _int_field(document: dict[str, object], field: str) -> int | None:
    value = document.get(field)
    return value if isinstance(value, int) and value >= 0 else None


def _allowed_status(
    value: object,
    *,
    allowed: tuple[str, ...],
    fallback: str,
) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def _status(
    definition: _EvidenceArtifactDefinition,
    state: EvidenceArtifactState,
    schema_version: str | None,
    summary: str,
) -> LocalEvidenceArtifact:
    return LocalEvidenceArtifact(
        id=definition.id,
        label=definition.label,
        path=definition.path.as_posix(),
        state=state,
        schema_version=schema_version,
        summary=summary,
    )
