"""PR runtime evidence cards from local deterministic artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.bridge.capture_summary import CAPTURE_SUMMARY_SCHEMA_VERSION
from entroping.core.agent_bundle import AGENT_REVIEW_BUNDLE_SCHEMA_VERSION
from entroping.core.drift_report import DRIFT_REPORT_SCHEMA_VERSION
from entroping.core.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_artifact_manifest import REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.secrets import contains_secret_like_value, redact_secret_like_values

RUNTIME_CARD_SCHEMA_VERSION: Final = "entroping.runtime-card.v1"
_MAX_RUNTIME_CARD_ARTIFACT_BYTES: Final = 100 * 1024 * 1024
_ASCII_CONTROL_CHAR_TRANSLATION: Final = {code: " " for code in range(32)}

RuntimeCardOutput = Literal["md", "json"]
RuntimeCardStatus = Literal["pass", "attention", "fail"]
RuntimeCardSeverity = Literal["error", "warning", "notice"]
RuntimeCardArtifactState = Literal["present", "missing"]
RuntimeCardDriftStatus = Literal["none", "drift", "missing_baseline", "unknown"]
RuntimeCardRedactionStatus = Literal["verified", "attention", "missing"]
RuntimeCardAgentStatus = Literal["pass", "attention", "fail", "missing"]
RuntimeCardPilotReadinessStatus = Literal["ready", "not_ready", "missing", "invalid", "unsafe"]

_DEFAULT_JSON_OUTPUT: Final = Path("reports") / "runtime-card.json"
_DEFAULT_MARKDOWN_OUTPUT: Final = Path("reports") / "runtime-card.md"


@dataclass(frozen=True, slots=True)
class _ArtifactDefinition:
    name: str
    path: Path
    schema_version: str
    required: bool = False


_RUN_ARTIFACT: Final = _ArtifactDefinition(
    name="Run JSON",
    path=Path("reports") / "run-latest.json",
    schema_version=RUN_REPORT_SCHEMA_VERSION,
    required=True,
)
_DRIFT_ARTIFACT: Final = _ArtifactDefinition(
    name="Drift JSON",
    path=Path("reports") / "drift.json",
    schema_version=DRIFT_REPORT_SCHEMA_VERSION,
)
_CAPTURE_ARTIFACT: Final = _ArtifactDefinition(
    name="Capture Summary",
    path=Path("reports") / "capture-summary.json",
    schema_version=CAPTURE_SUMMARY_SCHEMA_VERSION,
)
_ARTIFACT_MANIFEST: Final = _ArtifactDefinition(
    name="Artifact Manifest",
    path=Path("reports") / "artifact-manifest.json",
    schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
)
_EVIDENCE_BUNDLE: Final = _ArtifactDefinition(
    name="Evidence Bundle",
    path=Path("reports") / "evidence-bundle.json",
    schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
)
_AGENT_BUNDLE: Final = _ArtifactDefinition(
    name="Agent Bundle",
    path=Path("reports") / "agent-bundle.json",
    schema_version=AGENT_REVIEW_BUNDLE_SCHEMA_VERSION,
)
_ARTIFACTS: Final = (
    _RUN_ARTIFACT,
    _DRIFT_ARTIFACT,
    _CAPTURE_ARTIFACT,
    _ARTIFACT_MANIFEST,
    _EVIDENCE_BUNDLE,
    _AGENT_BUNDLE,
)


class RuntimeCardError(ValueError):
    """Raised when a runtime card cannot be generated safely."""


class RuntimeCardArtifact(BaseModel):
    """Presence and schema evidence for one local artifact."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    state: RuntimeCardArtifactState
    schema_version: str | None


class RuntimeCardRunEvidence(BaseModel):
    """Deterministic run evidence summarized from the run report."""

    model_config = ConfigDict(extra="forbid")

    project: str
    environment: str
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    exit_code: int
    failed_tests: int = Field(ge=0)
    failed_gate_ids: tuple[str, ...] = ()


class RuntimeCardDriftEvidence(BaseModel):
    """Drift evidence summarized from the drift report."""

    model_config = ConfigDict(extra="forbid")

    status: RuntimeCardDriftStatus
    findings: int = Field(ge=0)
    drifted: int = Field(ge=0)
    missing_baseline: bool


class RuntimeCardRedactionEvidence(BaseModel):
    """Counts-only redaction confidence evidence."""

    model_config = ConfigDict(extra="forbid")

    status: RuntimeCardRedactionStatus
    total_records: int = Field(ge=0)
    redacted_records: int = Field(ge=0)
    unredacted_records: int = Field(ge=0)
    low_confidence_categories: tuple[str, ...] = ()


class RuntimeCardReleaseEvidence(BaseModel):
    """Release-review anchors from sanitized local evidence."""

    model_config = ConfigDict(extra="forbid")

    artifact_manifest_audit_status: str
    evidence_bundle_status: str
    evidence_links: tuple[str, ...] = ()


class RuntimeCardPilotReadiness(BaseModel):
    """Design-partner pilot readiness from sanitized evidence-bundle metadata."""

    model_config = ConfigDict(extra="forbid")

    status: RuntimeCardPilotReadinessStatus
    path: str
    missing_artifacts: int = Field(ge=0)
    invalid_artifacts: int = Field(ge=0)
    checksum_mismatches: int = Field(ge=0)
    diagnostics: int = Field(ge=0)
    manifest_audit_status: str


class RuntimeCardAgentProvenance(BaseModel):
    """Value-free AI-agent provenance evidence."""

    model_config = ConfigDict(extra="forbid")

    status: RuntimeCardAgentStatus
    configured_roles: int = Field(ge=0)
    manifests: int = Field(ge=0)
    findings: int = Field(ge=0)


class RuntimeCardFinding(BaseModel):
    """One value-free runtime-card finding."""

    model_config = ConfigDict(extra="forbid")

    severity: RuntimeCardSeverity
    code: str
    path: str | None = None
    message: str


class RuntimeCardSummary(BaseModel):
    """Top-level runtime-card status and counts."""

    model_config = ConfigDict(extra="forbid")

    status: RuntimeCardStatus
    findings: int = Field(ge=0)
    evidence_links: int = Field(ge=0)


class RuntimeCardReport(BaseModel):
    """Schema-versioned PR runtime evidence card."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.runtime-card.v1"] = RUNTIME_CARD_SCHEMA_VERSION
    summary: RuntimeCardSummary
    run: RuntimeCardRunEvidence | None
    drift: RuntimeCardDriftEvidence
    redaction: RuntimeCardRedactionEvidence
    release: RuntimeCardReleaseEvidence
    pilot_readiness: RuntimeCardPilotReadiness
    agent_provenance: RuntimeCardAgentProvenance
    artifacts: tuple[RuntimeCardArtifact, ...]
    findings: tuple[RuntimeCardFinding, ...]


@dataclass(frozen=True, slots=True)
class RuntimeCardResult:
    """Result of writing one runtime-card artifact."""

    output_path: Path
    card: RuntimeCardReport


def run_runtime_card_report(
    *,
    project_root: Path,
    output: RuntimeCardOutput = "md",
    output_path: Path | None = None,
) -> RuntimeCardResult:
    """Write a value-free PR runtime evidence card from local artifacts."""

    root = project_root.expanduser().resolve()
    if output not in {"md", "json"}:
        msg = f"Unsupported runtime card output: {output}"
        raise RuntimeCardError(msg)
    destination = output_path or (
        _DEFAULT_JSON_OUTPUT if output == "json" else _DEFAULT_MARKDOWN_OUTPUT
    )
    card = build_runtime_card(project_root=root)
    content = (
        json.dumps(card.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        if output == "json"
        else render_runtime_card_markdown(card)
    )
    if _contains_unredacted_secret_like_value(content):
        msg = "runtime card metadata contains secret-like content"
        raise RuntimeCardError(msg)
    try:
        written = safe_write_text(destination, content, artifact="runtime card", root=root)
    except SafeWriteError as exc:
        raise RuntimeCardError(str(exc)) from exc
    return RuntimeCardResult(output_path=written, card=card)


def build_runtime_card(*, project_root: Path) -> RuntimeCardReport:
    """Build a runtime evidence card from existing local report artifacts."""

    root = project_root.expanduser().resolve()
    artifacts: list[RuntimeCardArtifact] = []
    findings: list[RuntimeCardFinding] = []

    run_doc = _load_artifact(_RUN_ARTIFACT, root=root, artifacts=artifacts)
    drift_doc = _load_artifact(_DRIFT_ARTIFACT, root=root, artifacts=artifacts)
    capture_doc = _load_artifact(_CAPTURE_ARTIFACT, root=root, artifacts=artifacts)
    manifest_doc = _load_artifact(_ARTIFACT_MANIFEST, root=root, artifacts=artifacts)
    evidence_doc, pilot_readiness = _load_evidence_bundle_artifact(
        root=root,
        artifacts=artifacts,
        findings=findings,
    )
    agent_doc = _load_artifact(_AGENT_BUNDLE, root=root, artifacts=artifacts)

    run = _run_evidence(run_doc)
    if run_doc is None:
        findings.append(
            _finding(
                "error",
                "missing_required_artifact",
                _RUN_ARTIFACT.path.as_posix(),
                "Run JSON evidence is required before a PR can claim runtime proof.",
            )
        )

    drift = _drift_evidence(drift_doc, findings=findings)
    redaction = _redaction_evidence(capture_doc, findings=findings)
    release = _release_evidence(
        run_doc,
        drift_doc,
        capture_doc,
        manifest_doc,
        evidence_doc,
        agent_doc,
        pilot_readiness=pilot_readiness,
        findings=findings,
    )
    agent = _agent_provenance(agent_doc, findings=findings)
    status = _card_status(run=run, drift=drift, redaction=redaction, findings=findings)

    return RuntimeCardReport(
        summary=RuntimeCardSummary(
            status=status,
            findings=len(findings),
            evidence_links=len(release.evidence_links),
        ),
        run=run,
        drift=drift,
        redaction=redaction,
        release=release,
        pilot_readiness=pilot_readiness,
        agent_provenance=agent,
        artifacts=tuple(artifacts),
        findings=tuple(findings),
    )


def render_runtime_card_markdown(card: RuntimeCardReport) -> str:
    """Render a GitHub-friendly, value-free runtime evidence card."""

    lines = [
        "# Entroping Runtime Evidence Card",
        "",
        f"- Status: `{card.summary.status}`",
    ]
    if card.run is not None:
        lines.extend(
            [
                f"- Project: `{_inline_code(card.run.project)}`",
                f"- Environment: `{_inline_code(card.run.environment)}`",
                f"- Tests: `{card.run.passed}/{card.run.total}` passed",
                f"- Failed tests: `{card.run.failed_tests}`",
                f"- Exit code: `{card.run.exit_code}`",
            ]
        )
        if card.run.failed_gate_ids:
            gates = ", ".join(f"`{_inline_code(gate)}`" for gate in card.run.failed_gate_ids)
            lines.append(f"- Failed gates: {gates}")

    lines.extend(
        [
            f"- Drift: `{card.drift.status}` ({card.drift.findings} findings)",
            f"- Redaction: `{card.redaction.status}` "
            f"({card.redaction.redacted_records}/{card.redaction.total_records} records redacted)",
            f"- Evidence bundle: `{card.release.evidence_bundle_status}`",
            f"- Pilot readiness: `{card.pilot_readiness.status}`",
            f"- Artifact manifest audit: `{card.release.artifact_manifest_audit_status}`",
            f"- Agent provenance: `{card.agent_provenance.status}` "
            f"({card.agent_provenance.manifests} manifests)",
            "",
            "## Pilot Readiness",
            "",
            f"- Status: `{card.pilot_readiness.status}`",
            f"- Evidence bundle: `{_inline_code(card.pilot_readiness.path)}`",
            f"- Missing artifacts: `{card.pilot_readiness.missing_artifacts}`",
            f"- Invalid artifacts: `{card.pilot_readiness.invalid_artifacts}`",
            f"- Checksum mismatches: `{card.pilot_readiness.checksum_mismatches}`",
            f"- Diagnostics: `{card.pilot_readiness.diagnostics}`",
            "- Artifact manifest audit: "
            f"`{_inline_code(card.pilot_readiness.manifest_audit_status)}`",
            "",
            "## Evidence Links",
            "",
        ]
    )
    if card.release.evidence_links:
        for link in card.release.evidence_links:
            lines.append(f"- `{_inline_code(link)}`")
    else:
        lines.append("No sanitized evidence links were found.")

    lines.extend(["", "## Artifacts", "", "| Artifact | State | Path |", "| --- | --- | --- |"])
    for artifact in card.artifacts:
        lines.append(
            "| "
            f"{_markdown_cell(artifact.name)} | "
            f"{_markdown_cell(artifact.state)} | "
            f"{_markdown_cell(artifact.path)} |"
        )

    lines.extend(["", "## Findings", ""])
    if not card.findings:
        lines.append("No runtime-card findings were found.")
    else:
        lines.extend(
            [
                "| Severity | Code | Path | Message |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in card.findings:
            lines.append(
                "| "
                f"{_markdown_cell(finding.severity)} | "
                f"{_markdown_cell(finding.code)} | "
                f"{_markdown_cell(finding.path or 'n/a')} | "
                f"{_markdown_cell(finding.message)} |"
            )

    return "\n".join(lines).rstrip() + "\n"


def _load_artifact(
    definition: _ArtifactDefinition,
    *,
    root: Path,
    artifacts: list[RuntimeCardArtifact],
) -> dict[str, object] | None:
    display_path = definition.path.as_posix()
    path = _resolve_artifact_path(definition.path, root=root)
    if not path.exists():
        artifacts.append(
            RuntimeCardArtifact(
                name=definition.name,
                path=display_path,
                state="missing",
                schema_version=None,
            )
        )
        return None
    artifact_label = "run report" if definition is _RUN_ARTIFACT else definition.name.lower()
    document = _load_json_object(path, artifact=artifact_label)
    schema_version = document.get("schema_version")
    if schema_version != definition.schema_version:
        msg = (
            f"{definition.name} {display_path} must use schema_version "
            f"{definition.schema_version}"
        )
        raise RuntimeCardError(msg)
    artifacts.append(
        RuntimeCardArtifact(
            name=definition.name,
            path=display_path,
            state="present",
            schema_version=definition.schema_version,
        )
    )
    return document


def _load_evidence_bundle_artifact(
    *,
    root: Path,
    artifacts: list[RuntimeCardArtifact],
    findings: list[RuntimeCardFinding],
) -> tuple[dict[str, object] | None, RuntimeCardPilotReadiness]:
    display_path = _EVIDENCE_BUNDLE.path.as_posix()
    try:
        path = _resolve_artifact_path(_EVIDENCE_BUNDLE.path, root=root)
    except RuntimeCardError:
        findings.append(
            _finding(
                "error",
                "pilot_readiness_unsafe",
                display_path,
                "Evidence bundle path is unsafe or not a file.",
            )
        )
        return None, _pilot_readiness(status="unsafe")
    if not path.exists():
        artifacts.append(
            RuntimeCardArtifact(
                name=_EVIDENCE_BUNDLE.name,
                path=display_path,
                state="missing",
                schema_version=None,
            )
        )
        return None, _pilot_readiness(status="missing")
    try:
        document = _load_json_object(path, artifact="evidence bundle")
    except RuntimeCardError:
        artifacts.append(
            RuntimeCardArtifact(
                name=_EVIDENCE_BUNDLE.name,
                path=display_path,
                state="present",
                schema_version=None,
            )
        )
        findings.append(
            _finding(
                "error",
                "pilot_readiness_invalid",
                display_path,
                "Evidence bundle is malformed or not a JSON object.",
            )
        )
        return None, _pilot_readiness(status="invalid", diagnostics=1)

    schema_version = document.get("schema_version")
    normalized_schema = schema_version if isinstance(schema_version, str) else None
    artifacts.append(
        RuntimeCardArtifact(
            name=_EVIDENCE_BUNDLE.name,
            path=display_path,
            state="present",
            schema_version=normalized_schema,
        )
    )
    if normalized_schema != _EVIDENCE_BUNDLE.schema_version:
        findings.append(
            _finding(
                "error",
                "pilot_readiness_invalid",
                display_path,
                "Evidence bundle schema version is unsupported.",
            )
        )
        return None, _pilot_readiness(status="invalid", diagnostics=1)
    try:
        return document, _pilot_readiness_from_document(document)
    except RuntimeCardError:
        findings.append(
            _finding(
                "error",
                "pilot_readiness_invalid",
                display_path,
                "Evidence bundle readiness metadata is malformed.",
            )
        )
        return None, _pilot_readiness(status="invalid", diagnostics=1)


def _pilot_readiness_from_document(document: dict[str, object]) -> RuntimeCardPilotReadiness:
    summary = _object_field(document, "summary", artifact="evidence bundle")
    diagnostics = _list_field(document, "diagnostics", artifact="evidence bundle")
    status_value = summary.get("status")
    if status_value not in {"ready", "not_ready"}:
        msg = "Evidence bundle summary status must be ready or not_ready"
        raise RuntimeCardError(msg)
    status: RuntimeCardPilotReadinessStatus = (
        "ready" if status_value == "ready" else "not_ready"
    )
    checksum_mismatches = sum(
        1
        for diagnostic in diagnostics
        if isinstance(diagnostic, dict) and diagnostic.get("code") == "checksum_mismatch"
    )
    return _pilot_readiness(
        status=status,
        missing_artifacts=_non_negative_int(
            summary.get("required_missing"),
            field="summary.required_missing",
        ),
        invalid_artifacts=_non_negative_int(
            summary.get("required_invalid"),
            field="summary.required_invalid",
        ),
        checksum_mismatches=checksum_mismatches,
        diagnostics=_non_negative_int(
            summary.get("diagnostics_total"),
            field="summary.diagnostics_total",
        ),
        manifest_audit_status=_evidence_bundle_manifest_audit_status(document),
    )


def _pilot_readiness(
    *,
    status: RuntimeCardPilotReadinessStatus,
    missing_artifacts: int = 0,
    invalid_artifacts: int = 0,
    checksum_mismatches: int = 0,
    diagnostics: int = 0,
    manifest_audit_status: str = "missing",
) -> RuntimeCardPilotReadiness:
    return RuntimeCardPilotReadiness(
        status=status,
        path=_EVIDENCE_BUNDLE.path.as_posix(),
        missing_artifacts=missing_artifacts,
        invalid_artifacts=invalid_artifacts,
        checksum_mismatches=checksum_mismatches,
        diagnostics=diagnostics,
        manifest_audit_status=_safe_text(manifest_audit_status),
    )


def _evidence_bundle_manifest_audit_status(document: dict[str, object]) -> str:
    audit = document.get("manifest_audit")
    if not isinstance(audit, dict):
        return "missing"
    return _safe_text(_string_value(audit.get("status"), fallback="unknown"))


def _run_evidence(document: dict[str, object] | None) -> RuntimeCardRunEvidence | None:
    if document is None:
        return None
    summary = _object_field(document, "summary", artifact="run report")
    tests = _list_field(document, "tests", artifact="run report")

    failed_gate_ids: set[str] = set()
    failed_tests = 0
    for raw_test in tests:
        if not isinstance(raw_test, dict):
            continue
        status = _string_value(raw_test.get("status"), fallback="unknown")
        exit_code = raw_test.get("exit_code")
        failed = status in {"failed", "error", "blocked", "timeout"} or (
            isinstance(exit_code, int) and exit_code != 0
        )
        if not failed:
            continue
        failed_tests += 1
        rule_ids = raw_test.get("rule_ids", [])
        if isinstance(rule_ids, list):
            failed_gate_ids.update(
                _safe_text(rule_id)
                for rule_id in rule_ids
                if isinstance(rule_id, str) and rule_id.strip()
            )

    return RuntimeCardRunEvidence(
        project=_safe_text(_string_value(document.get("project"), fallback="unknown")),
        environment=_safe_text(_string_value(document.get("environment"), fallback="default")),
        total=_non_negative_int(summary.get("total"), field="summary.total"),
        passed=_non_negative_int(summary.get("passed"), field="summary.passed"),
        failed=_non_negative_int(summary.get("failed"), field="summary.failed"),
        exit_code=_int_value(summary.get("exit_code"), field="summary.exit_code"),
        failed_tests=failed_tests,
        failed_gate_ids=tuple(sorted(failed_gate_ids)),
    )


def _drift_evidence(
    document: dict[str, object] | None,
    *,
    findings: list[RuntimeCardFinding],
) -> RuntimeCardDriftEvidence:
    if document is None:
        return RuntimeCardDriftEvidence(
            status="unknown",
            findings=0,
            drifted=0,
            missing_baseline=False,
        )
    summary = _object_field(document, "summary", artifact="drift report")
    finding_count = _non_negative_int(summary.get("findings"), field="summary.findings")
    drifted = _non_negative_int(summary.get("drifted"), field="summary.drifted")
    missing_baseline = summary.get("missing_baseline") is True
    if missing_baseline:
        status: RuntimeCardDriftStatus = "missing_baseline"
    elif drifted > 0 or finding_count > 0:
        status = "drift"
    else:
        status = "none"
    if status != "none":
        findings.append(
            _finding(
                "warning",
                "drift_attention",
                _DRIFT_ARTIFACT.path.as_posix(),
                "Drift evidence requires reviewer attention.",
            )
        )
    return RuntimeCardDriftEvidence(
        status=status,
        findings=finding_count,
        drifted=drifted,
        missing_baseline=missing_baseline,
    )


def _redaction_evidence(
    document: dict[str, object] | None,
    *,
    findings: list[RuntimeCardFinding],
) -> RuntimeCardRedactionEvidence:
    if document is None:
        return RuntimeCardRedactionEvidence(
            status="missing",
            total_records=0,
            redacted_records=0,
            unredacted_records=0,
        )
    summary = _object_field(document, "summary", artifact="capture summary")
    total_records = _non_negative_int(summary.get("total_records"), field="summary.total_records")
    redacted_records = _non_negative_int(
        summary.get("redacted_records"),
        field="summary.redacted_records",
    )
    unredacted_records = _non_negative_int(
        summary.get("unredacted_records"),
        field="summary.unredacted_records",
    )
    low_confidence = _low_confidence_categories(document)
    status: RuntimeCardRedactionStatus = (
        "attention" if unredacted_records > 0 or low_confidence else "verified"
    )
    if status == "attention":
        findings.append(
            _finding(
                "warning",
                "redaction_attention",
                _CAPTURE_ARTIFACT.path.as_posix(),
                "Capture summary reports unredacted or low-confidence traffic evidence.",
            )
        )
    return RuntimeCardRedactionEvidence(
        status=status,
        total_records=total_records,
        redacted_records=redacted_records,
        unredacted_records=unredacted_records,
        low_confidence_categories=low_confidence,
    )


def _release_evidence(
    run_doc: dict[str, object] | None,
    drift_doc: dict[str, object] | None,
    capture_doc: dict[str, object] | None,
    manifest_doc: dict[str, object] | None,
    evidence_doc: dict[str, object] | None,
    agent_doc: dict[str, object] | None,
    *,
    pilot_readiness: RuntimeCardPilotReadiness,
    findings: list[RuntimeCardFinding],
) -> RuntimeCardReleaseEvidence:
    audit_status = "missing"
    if manifest_doc is None:
        findings.append(
            _finding(
                "warning",
                "missing_artifact_manifest",
                _ARTIFACT_MANIFEST.path.as_posix(),
                "Artifact manifest evidence is required before a PR can claim "
                "release-ready runtime proof.",
            )
        )
    else:
        audit = manifest_doc.get("audit")
        if isinstance(audit, dict):
            verification = audit.get("verification")
            if isinstance(verification, dict):
                audit_status = _safe_text(
                    _string_value(verification.get("status"), fallback="unknown")
                )
        if audit_status != "verified":
            findings.append(
                _finding(
                    "warning",
                    "artifact_manifest_audit_attention",
                    _ARTIFACT_MANIFEST.path.as_posix(),
                    "Artifact manifest audit status is not verified.",
                )
            )

    evidence_status = pilot_readiness.status
    if evidence_doc is None and evidence_status == "missing":
        findings.append(
            _finding(
                "warning",
                "missing_evidence_bundle",
                _EVIDENCE_BUNDLE.path.as_posix(),
                "Evidence bundle is required before a PR can claim "
                "release-ready runtime proof.",
            )
        )
    elif evidence_doc is not None and evidence_status != "ready":
        findings.append(
            _finding(
                "warning",
                "evidence_bundle_attention",
                _EVIDENCE_BUNDLE.path.as_posix(),
                "Evidence bundle is not ready.",
            )
        )

    links = tuple(
        artifact.path.as_posix()
        for artifact, present in (
            (_EVIDENCE_BUNDLE, evidence_doc is not None),
            (_ARTIFACT_MANIFEST, manifest_doc is not None),
            (_RUN_ARTIFACT, run_doc is not None),
            (_DRIFT_ARTIFACT, drift_doc is not None),
            (_CAPTURE_ARTIFACT, capture_doc is not None),
            (_AGENT_BUNDLE, agent_doc is not None),
        )
        if present
    )
    return RuntimeCardReleaseEvidence(
        artifact_manifest_audit_status=audit_status,
        evidence_bundle_status=evidence_status,
        evidence_links=links,
    )


def _agent_provenance(
    document: dict[str, object] | None,
    *,
    findings: list[RuntimeCardFinding],
) -> RuntimeCardAgentProvenance:
    if document is None:
        return RuntimeCardAgentProvenance(
            status="missing",
            configured_roles=0,
            manifests=0,
            findings=0,
        )
    summary = _object_field(document, "summary", artifact="agent bundle")
    status, recognized_status = _agent_status(summary.get("status"))
    finding_count = _non_negative_int(summary.get("findings"), field="summary.findings")
    if not recognized_status:
        findings.append(
            _finding(
                "warning",
                "agent_status_unrecognized",
                _AGENT_BUNDLE.path.as_posix(),
                "Agent bundle summary status is unrecognized.",
            )
        )
    if status != "pass" or finding_count > 0:
        findings.append(
            _finding(
                "warning",
                "agent_provenance_attention",
                _AGENT_BUNDLE.path.as_posix(),
                "Agent provenance evidence requires reviewer attention.",
            )
        )
    return RuntimeCardAgentProvenance(
        status=status,
        configured_roles=_non_negative_int(
            summary.get("configured_roles"),
            field="summary.configured_roles",
        ),
        manifests=_non_negative_int(summary.get("manifests"), field="summary.manifests"),
        findings=finding_count,
    )


def _card_status(
    *,
    run: RuntimeCardRunEvidence | None,
    drift: RuntimeCardDriftEvidence,
    redaction: RuntimeCardRedactionEvidence,
    findings: list[RuntimeCardFinding],
) -> RuntimeCardStatus:
    if run is None:
        return "fail"
    if run.failed > 0 or run.exit_code != 0 or run.failed_tests > 0:
        return "fail"
    if any(finding.severity == "error" for finding in findings):
        return "fail"
    if drift.status in {"drift", "missing_baseline"} or redaction.status != "verified":
        return "attention"
    if any(finding.severity == "warning" for finding in findings):
        return "attention"
    return "pass"


def _low_confidence_categories(document: dict[str, object]) -> tuple[str, ...]:
    rows = document.get("redaction_categories", [])
    if not isinstance(rows, list):
        msg = "Capture summary field redaction_categories must be a list"
        raise RuntimeCardError(msg)
    labels: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        count = row.get("count")
        if (
            isinstance(label, str)
            and isinstance(count, int)
            and count > 0
            and "low" in label.lower()
        ):
            labels.append(_safe_text(label))
    return tuple(sorted(labels))


def _load_json_object(path: Path, *, artifact: str) -> dict[str, object]:
    try:
        if path.stat().st_size > _MAX_RUNTIME_CARD_ARTIFACT_BYTES:
            msg = (
                f"{artifact.capitalize()} {path} exceeds "
                f"{_MAX_RUNTIME_CARD_ARTIFACT_BYTES} bytes"
            )
            raise RuntimeCardError(msg)
        raw_json = path.read_text(encoding="utf-8")
    except RuntimeCardError:
        raise
    except UnicodeDecodeError as exc:
        msg = f"Could not decode {artifact} {path} as UTF-8: {exc}"
        raise RuntimeCardError(msg) from exc
    except OSError as exc:
        msg = f"Could not read {artifact} {path}: {exc}"
        raise RuntimeCardError(msg) from exc
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact} {path}: {exc}"
        raise RuntimeCardError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{artifact.capitalize()} {path} must be a JSON object"
        raise RuntimeCardError(msg)
    return data


def _resolve_artifact_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    try:
        symlink_path = first_symlink_path_component(candidate, root=root)
    except ValueError as exc:
        msg = f"runtime card artifact path must stay inside the project: {raw_path}"
        raise RuntimeCardError(msg) from exc
    if symlink_path is not None:
        msg = f"runtime card artifact path uses symlinked component: {symlink_path}"
        raise RuntimeCardError(msg)
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"runtime card artifact path is not a file: {raw_path.as_posix()}"
        raise RuntimeCardError(msg)
    return resolved


def _object_field(
    document: dict[str, object],
    field: str,
    *,
    artifact: str,
) -> dict[str, object]:
    value = document.get(field)
    if not isinstance(value, dict):
        msg = f"{artifact.capitalize()} field {field} must be an object"
        raise RuntimeCardError(msg)
    return value


def _list_field(
    document: dict[str, object],
    field: str,
    *,
    artifact: str,
) -> list[object]:
    value = document.get(field)
    if not isinstance(value, list):
        msg = f"{artifact.capitalize()} field {field} must be a list"
        raise RuntimeCardError(msg)
    return value


def _non_negative_int(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"Runtime card source field {field} must be a non-negative integer"
        raise RuntimeCardError(msg)
    return value


def _int_value(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"Runtime card source field {field} must be an integer"
        raise RuntimeCardError(msg)
    return value


def _string_value(value: object, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return fallback


def _agent_status(value: object) -> tuple[RuntimeCardAgentStatus, bool]:
    if value == "pass":
        return ("pass", True)
    if value == "attention":
        return ("attention", True)
    if value == "fail":
        return ("fail", True)
    return ("attention", False)


def _finding(
    severity: RuntimeCardSeverity,
    code: str,
    path: str | None,
    message: str,
) -> RuntimeCardFinding:
    return RuntimeCardFinding(
        severity=severity,
        code=code,
        path=path,
        message=message,
    )


def _safe_text(value: str) -> str:
    sanitized = redact_secret_like_values(value).translate(_ASCII_CONTROL_CHAR_TRANSLATION)
    return " ".join(sanitized.split())


def _contains_unredacted_secret_like_value(value: str) -> bool:
    # Markdown inline-code fences can trail an already-redacted marker.
    normalized = value.replace("[REDACTED]`", "[REDACTED]")
    return contains_secret_like_value(normalized)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|")
