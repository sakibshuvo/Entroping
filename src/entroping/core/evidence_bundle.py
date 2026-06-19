"""Sanitized upload-readiness evidence bundle generation."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_artifact_manifest import (
    REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ReportArtifactManifest,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.secrets import contains_secret_like_value, redact_secret_like_values

EVIDENCE_BUNDLE_SCHEMA_VERSION: Final = "entroping.evidence-bundle.v1"

EvidenceBundleStatus = Literal["ready", "not_ready"]
EvidenceBundleSeverity = Literal["error", "warning"]
EvidenceBundleArtifactKind = Literal[
    "artifact_manifest",
    "effective_policy",
    "run_json",
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

_DEFAULT_OUTPUT_PATH: Final = Path("reports") / "evidence-bundle.json"
_DEFAULT_PURPOSE: Final = "design-partner-upload-readiness"
_MAX_EVIDENCE_ARTIFACT_BYTES: Final = 100 * 1024 * 1024
_SECRET_SCAN_DIGEST_FIELDS: Final = frozenset({"latest_event_hash", "sha256"})
_ARTIFACT_INVALID_DIAGNOSTIC_CODES: Final = frozenset(
    {
        "artifact_manifest_invalid",
        "checksum_mismatch",
        "schema_mismatch",
    }
)


@dataclass(frozen=True, slots=True)
class _EvidenceArtifactDefinition:
    kind: EvidenceBundleArtifactKind
    path: Path
    schema_version: str
    required: bool = True


_ARTIFACTS: Final = (
    _EvidenceArtifactDefinition(
        kind="artifact_manifest",
        path=Path("reports") / "artifact-manifest.json",
        schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ),
    _EvidenceArtifactDefinition(
        kind="effective_policy",
        path=Path("reports") / "effective-policy.json",
        schema_version="entroping.effective-policy-report.v1",
    ),
    _EvidenceArtifactDefinition(
        kind="run_json",
        path=Path("reports") / "run-latest.json",
        schema_version="entroping.run-report.v1",
    ),
)


class EvidenceBundleArtifact(BaseModel):
    """One local report artifact reference included without contents."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceBundleArtifactKind
    path: str
    required: bool
    schema_version: str | None
    size_bytes: int = Field(ge=0)
    sha256: Sha256Digest


class EvidenceBundleMissingArtifact(BaseModel):
    """One required report artifact missing from local review evidence."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceBundleArtifactKind
    path: str
    required: bool


class EvidenceBundleDiagnostic(BaseModel):
    """One value-free verifier diagnostic for evidence-bundle readiness."""

    model_config = ConfigDict(extra="forbid")

    severity: EvidenceBundleSeverity
    code: str
    path: str | None = None
    message: str


class EvidenceBundleSummary(BaseModel):
    """Aggregate readiness counts for the evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceBundleStatus
    required_total: int = Field(ge=0)
    required_present: int = Field(ge=0)
    required_missing: int = Field(ge=0)
    required_invalid: int = Field(ge=0)
    artifacts_total: int = Field(ge=0)
    diagnostics_total: int = Field(ge=0)


class EvidenceBundleManifestAudit(BaseModel):
    """Value-free audit-chain status copied from the artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    path: str
    status: str
    chain_path: str
    checked_events: int = Field(ge=0)
    latest_event_hash: Sha256Digest | None
    diagnostics: tuple[str, ...]


class EvidenceBundleReport(BaseModel):
    """Upload-ready, value-free evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-bundle.v1"] = (
        "entroping.evidence-bundle.v1"
    )
    generated_at: str
    purpose: str
    project: str | None
    summary: EvidenceBundleSummary
    artifacts: tuple[EvidenceBundleArtifact, ...]
    missing_artifacts: tuple[EvidenceBundleMissingArtifact, ...]
    diagnostics: tuple[EvidenceBundleDiagnostic, ...]
    manifest_audit: EvidenceBundleManifestAudit | None


class EvidenceBundleError(ValueError):
    """Raised when an evidence bundle cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class EvidenceBundleResult:
    """Result of an evidence-bundle report workflow."""

    output_path: Path
    bundle: EvidenceBundleReport


def run_evidence_bundle_report(
    *,
    project_root: Path,
    output_path: Path | None = None,
    purpose: str = _DEFAULT_PURPOSE,
) -> EvidenceBundleResult:
    """Write sanitized local evidence for design-partner upload readiness."""

    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUT_PATH, root=root)
    bundle = _build_bundle(root=root, purpose=purpose)
    content = _render_bundle_content(bundle, output_path=destination)
    if _bundle_contains_secret_like_metadata(bundle.model_dump(mode="json")):
        msg = "evidence bundle metadata contains secret-like content"
        raise EvidenceBundleError(msg)
    try:
        safe_write_text(destination, content, artifact="evidence bundle", root=root)
    except SafeWriteError as exc:
        raise EvidenceBundleError(str(exc)) from exc
    return EvidenceBundleResult(output_path=destination, bundle=bundle)


def _render_bundle_content(bundle: EvidenceBundleReport, *, output_path: Path) -> str:
    if output_path.suffix.lower() in {".md", ".markdown"}:
        return render_evidence_bundle_markdown(bundle)
    return json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def render_evidence_bundle_markdown(bundle: EvidenceBundleReport) -> str:
    """Render a value-free Markdown summary from sanitized evidence metadata."""

    manifest_status = (
        bundle.manifest_audit.status if bundle.manifest_audit is not None else "missing"
    )
    lines = [
        "# Evidence Bundle",
        "",
        f"- Status: `{bundle.summary.status}`",
        f"- Purpose: `{_inline_code(bundle.purpose)}`",
        f"- Project: `{_inline_code(bundle.project or 'unknown')}`",
        "- Required artifacts: "
        f"`{bundle.summary.required_present}/{bundle.summary.required_total}` present, "
        f"`{bundle.summary.required_missing}` missing, "
        f"`{bundle.summary.required_invalid}` invalid",
        f"- Diagnostics: `{bundle.summary.diagnostics_total}`",
        f"- Artifact manifest audit: `{_inline_code(manifest_status)}`",
        "",
        "## Required Artifacts",
        "",
        "| Kind | Path | State | Schema | Size bytes | SHA-256 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in _artifact_rows(bundle):
        lines.append(
            f"| {_markdown_cell(row[0])} | "
            f"{_markdown_cell(row[1])} | "
            f"{_markdown_cell(row[2])} | "
            f"{_markdown_cell(row[3])} | "
            f"{_markdown_cell(row[4])} | "
            f"{_markdown_cell(row[5])} |"
        )

    lines.extend(["", "## Diagnostics", ""])
    if not bundle.diagnostics:
        lines.append("No diagnostics were found.")
    else:
        lines.extend(
            [
                "| Severity | Code | Path | Message |",
                "| --- | --- | --- | --- |",
            ]
        )
        for diagnostic in bundle.diagnostics:
            lines.append(
                f"| {_markdown_cell(diagnostic.severity)} | "
                f"{_markdown_cell(diagnostic.code)} | "
                f"{_markdown_cell(diagnostic.path or 'n/a')} | "
                f"{_markdown_cell(diagnostic.message)} |"
            )

    lines.extend(["", "## Next Local Commands", ""])
    commands = _next_missing_evidence_commands(bundle)
    if not commands:
        lines.append("No missing required artifacts were found.")
    else:
        for command in commands:
            lines.append(f"- `{_inline_code(command)}`")
    return "\n".join(lines) + "\n"


def _artifact_rows(bundle: EvidenceBundleReport) -> list[tuple[str, str, str, str, str, str]]:
    rows = [
        (
            artifact.kind,
            artifact.path,
            "present",
            artifact.schema_version or "unknown",
            str(artifact.size_bytes),
            artifact.sha256,
        )
        for artifact in bundle.artifacts
    ]
    rows.extend(
        (
            artifact.kind,
            artifact.path,
            "missing",
            "n/a",
            "0",
            "n/a",
        )
        for artifact in bundle.missing_artifacts
    )
    return sorted(rows, key=lambda row: row[1])


def _next_missing_evidence_commands(bundle: EvidenceBundleReport) -> tuple[str, ...]:
    if not bundle.missing_artifacts:
        return ()
    commands_by_kind = {
        "artifact_manifest": "entroping report artifact-manifest",
        "effective_policy": "entroping report policy --output json",
        "run_json": "entroping run --report json",
    }
    commands = [
        commands_by_kind[artifact.kind]
        for artifact in bundle.missing_artifacts
        if artifact.kind in commands_by_kind
    ]
    commands.append("entroping report evidence-bundle --output reports/evidence-bundle.md")
    return tuple(dict.fromkeys(commands))


def _build_bundle(*, root: Path, purpose: str) -> EvidenceBundleReport:
    artifacts: list[EvidenceBundleArtifact] = []
    missing: list[EvidenceBundleMissingArtifact] = []
    diagnostics: list[EvidenceBundleDiagnostic] = []
    manifest = _load_artifact_manifest(root=root, diagnostics=diagnostics)
    manifest_checksums = {
        artifact.path: artifact.sha256
        for artifact in manifest.artifacts
    } if manifest is not None else {}

    project: str | None = None
    for definition in sorted(_ARTIFACTS, key=lambda item: item.path.as_posix()):
        display_path = definition.path.as_posix()
        resolved = _resolve_artifact_path(definition.path, root=root)
        if not resolved.exists():
            missing.append(
                EvidenceBundleMissingArtifact(
                    kind=definition.kind,
                    path=display_path,
                    required=definition.required,
                )
            )
            diagnostics.append(
                _diagnostic(
                    "error",
                    "missing_required_artifact",
                    display_path,
                    "Required evidence artifact is missing.",
                )
            )
            continue
        content = _read_artifact_bytes(resolved, artifact_path=display_path)
        schema_version, document = _artifact_schema_version(content)
        artifact = EvidenceBundleArtifact(
            kind=definition.kind,
            path=display_path,
            required=definition.required,
            schema_version=schema_version,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        artifacts.append(artifact)
        if schema_version != definition.schema_version:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "schema_mismatch",
                    display_path,
                    "Evidence artifact schema version is unsupported.",
                )
            )
        expected_sha = manifest_checksums.get(display_path)
        if expected_sha is not None and expected_sha != artifact.sha256:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "checksum_mismatch",
                    display_path,
                    "Evidence artifact checksum does not match artifact manifest.",
                )
            )
        if definition.kind == "run_json" and isinstance(document, dict):
            raw_project = document.get("project")
            project = _safe_metadata_text(raw_project) if isinstance(raw_project, str) else None

    required_invalid = sum(
        1
        for item in diagnostics
        if item.severity == "error" and item.code in _ARTIFACT_INVALID_DIAGNOSTIC_CODES
    )
    has_error_diagnostics = any(item.severity == "error" for item in diagnostics)
    status: EvidenceBundleStatus = (
        "ready" if not missing and not has_error_diagnostics else "not_ready"
    )
    return EvidenceBundleReport(
        generated_at=datetime.now(UTC).isoformat(),
        purpose=_safe_metadata_text(purpose),
        project=project,
        summary=EvidenceBundleSummary(
            status=status,
            required_total=len(_ARTIFACTS),
            required_present=len(artifacts),
            required_missing=len(missing),
            required_invalid=required_invalid,
            artifacts_total=len(artifacts),
            diagnostics_total=len(diagnostics),
        ),
        artifacts=tuple(artifacts),
        missing_artifacts=tuple(missing),
        diagnostics=tuple(diagnostics),
        manifest_audit=_manifest_audit(manifest) if manifest is not None else None,
    )


def _load_artifact_manifest(
    *,
    root: Path,
    diagnostics: list[EvidenceBundleDiagnostic],
) -> ReportArtifactManifest | None:
    path = root / "reports" / "artifact-manifest.json"
    if not path.exists():
        return None
    content = _read_artifact_bytes(path, artifact_path="reports/artifact-manifest.json")
    try:
        manifest = ReportArtifactManifest.model_validate_json(content)
    except ValidationError:
        diagnostics.append(
            _diagnostic(
                "error",
                "artifact_manifest_invalid",
                "reports/artifact-manifest.json",
                "Artifact manifest failed schema validation.",
            )
        )
        return None
    if manifest.audit.verification.status != "verified":
        diagnostics.append(
            _diagnostic(
                "error",
                "artifact_manifest_audit_broken",
                "reports/artifact-manifest.json",
                "Artifact manifest audit chain is not verified.",
            )
        )
    return manifest


def _artifact_schema_version(content: bytes) -> tuple[str | None, object | None]:
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(document, dict):
        return None, document
    schema_version = document.get("schema_version")
    if not isinstance(schema_version, str):
        return None, document
    return _safe_metadata_text(schema_version), document


def _manifest_audit(manifest: ReportArtifactManifest) -> EvidenceBundleManifestAudit:
    verification = manifest.audit.verification
    return EvidenceBundleManifestAudit(
        path="reports/artifact-manifest.json",
        status=_safe_metadata_text(verification.status),
        chain_path=_safe_metadata_text(manifest.audit.chain_path),
        checked_events=verification.checked_events,
        latest_event_hash=verification.latest_event_hash,
        diagnostics=tuple(_safe_metadata_text(item) for item in verification.diagnostics),
    )


def _resolve_artifact_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    _reject_symlink_path(candidate, root=root, artifact="evidence artifact")
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"evidence artifact path is not a file: {raw_path.as_posix()}"
        raise EvidenceBundleError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    _reject_symlink_path(path, root=root, artifact="evidence bundle output")
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"evidence bundle output path must stay inside the project: {raw_path}"
        raise EvidenceBundleError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "evidence bundle output must not be written into .entroping or envs"
        raise EvidenceBundleError(msg)
    return resolved


def _reject_symlink_path(path: Path, *, root: Path, artifact: str) -> None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = f"{artifact} path must stay inside the project: {path}"
        raise EvidenceBundleError(msg) from exc
    if symlink_path is not None:
        msg = f"{artifact} path uses symlinked component: {symlink_path}"
        raise EvidenceBundleError(msg)


def _read_artifact_bytes(path: Path, *, artifact_path: str) -> bytes:
    try:
        if path.stat().st_size > _MAX_EVIDENCE_ARTIFACT_BYTES:
            msg = (
                f"evidence artifact {artifact_path} exceeds "
                f"{_MAX_EVIDENCE_ARTIFACT_BYTES} bytes"
            )
            raise EvidenceBundleError(msg)
        return path.read_bytes()
    except EvidenceBundleError:
        raise
    except OSError as exc:
        msg = f"Could not read evidence artifact {artifact_path}: {exc}"
        raise EvidenceBundleError(msg) from exc


def _diagnostic(
    severity: EvidenceBundleSeverity,
    code: str,
    path: str | None,
    message: str,
) -> EvidenceBundleDiagnostic:
    return EvidenceBundleDiagnostic(
        severity=severity,
        code=code,
        path=path,
        message=message,
    )


def _safe_metadata_text(value: str) -> str:
    return redact_secret_like_values(value).replace("\r", " ").replace("\n", " ")


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|")


def _bundle_contains_secret_like_metadata(
    value: object,
    *,
    parent_key: str | None = None,
) -> bool:
    if isinstance(value, str):
        if parent_key in _SECRET_SCAN_DIGEST_FIELDS:
            return False
        return contains_secret_like_value(value)
    if isinstance(value, dict):
        return any(
            _bundle_contains_secret_like_metadata(item, parent_key=str(key))
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_bundle_contains_secret_like_metadata(item) for item in value)
    return False
