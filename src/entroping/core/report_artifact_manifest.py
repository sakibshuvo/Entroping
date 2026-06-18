"""Deterministic manifest for local report artifacts."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.models.secrets import redact_secret_like_values

REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION: Final = "entroping.report-artifact-manifest.v1"
REPORT_AUDIT_EVENT_SCHEMA_VERSION: Final = "entroping.report-audit-event.v1"

ReportArtifactKind = Literal[
    "run_json",
    "run_plan",
    "junit",
    "run_html",
    "drift_json",
    "agent_bundle",
    "sarif",
    "review_summary",
]
ReportArtifactAuditVerificationStatus = Literal["verified", "broken"]

_DEFAULT_OUTPUT_PATH: Final = Path("reports") / "artifact-manifest.json"
_DEFAULT_AUDIT_CHAIN_PATH: Final = Path(".entroping") / "report-audit-chain.jsonl"


@dataclass(frozen=True, slots=True)
class _ReportArtifactDefinition:
    kind: ReportArtifactKind
    path: Path
    schema_hint: str | None


_DEFAULT_REPORT_ARTIFACTS: Final = (
    _ReportArtifactDefinition(
        kind="run_json",
        path=Path("reports") / "run-latest.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="run_plan",
        path=Path("reports") / "run-plan.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="junit",
        path=Path("reports") / "junit.xml",
        schema_hint="junit.xml",
    ),
    _ReportArtifactDefinition(
        kind="run_html",
        path=Path("reports") / "run-latest.html",
        schema_hint="entroping.run-report.html",
    ),
    _ReportArtifactDefinition(
        kind="drift_json",
        path=Path("reports") / "drift.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="agent_bundle",
        path=Path("reports") / "agent-bundle.json",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="sarif",
        path=Path("reports") / "entroping.sarif",
        schema_hint=None,
    ),
    _ReportArtifactDefinition(
        kind="review_summary",
        path=Path("reports") / "review-summary.md",
        schema_hint="entroping.review-summary.md",
    ),
)


class ReportArtifactEntry(BaseModel):
    """One present local report artifact."""

    model_config = ConfigDict(extra="forbid")

    kind: ReportArtifactKind
    path: str
    schema_version: str | None
    size_bytes: int
    sha256: str


class ReportArtifactMissing(BaseModel):
    """One expected local report artifact that was not present."""

    model_config = ConfigDict(extra="forbid")

    kind: ReportArtifactKind
    path: str


class ReportArtifactManifestSummary(BaseModel):
    """Aggregate counts for a report artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    total_expected: int
    total_present: int
    total_missing: int


class ReportArtifactAuditCommand(BaseModel):
    """Value-free command metadata for an audit-chain event."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["entroping report artifact-manifest"]
    output_path: str


class ReportArtifactAuditEvent(BaseModel):
    """One tamper-evident local report audit event."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.report-audit-event.v1"] = (
        "entroping.report-audit-event.v1"
    )
    event_type: Literal["report_artifact_manifest"] = "report_artifact_manifest"
    sequence: int = Field(ge=1)
    generated_at: str
    previous_event_hash: str | None
    command: ReportArtifactAuditCommand
    summary: ReportArtifactManifestSummary
    artifacts: tuple[ReportArtifactEntry, ...]
    event_hash: str


class ReportArtifactAuditVerification(BaseModel):
    """Verification result for the local report audit chain."""

    model_config = ConfigDict(extra="forbid")

    status: ReportArtifactAuditVerificationStatus
    checked_events: int = Field(ge=0)
    latest_event_hash: str | None
    diagnostics: tuple[str, ...] = ()


class ReportArtifactAuditEvidence(BaseModel):
    """Audit-chain evidence embedded in the artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    chain_path: str
    verification: ReportArtifactAuditVerification
    event: ReportArtifactAuditEvent | None


class ReportArtifactManifest(BaseModel):
    """Machine-readable integrity evidence for local report artifacts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.report-artifact-manifest.v1"] = (
        "entroping.report-artifact-manifest.v1"
    )
    summary: ReportArtifactManifestSummary
    artifacts: tuple[ReportArtifactEntry, ...]
    missing_artifacts: tuple[ReportArtifactMissing, ...]
    audit: ReportArtifactAuditEvidence


class ReportArtifactManifestError(ValueError):
    """Raised when a report artifact manifest cannot be written safely."""


@dataclass(frozen=True, slots=True)
class ReportArtifactManifestResult:
    """Result of a successful report artifact manifest workflow."""

    output_path: Path
    manifest: ReportArtifactManifest


@dataclass(frozen=True, slots=True)
class _AuditChainState:
    events: tuple[ReportArtifactAuditEvent, ...]
    verification: ReportArtifactAuditVerification


def write_report_artifact_manifest(
    *,
    project_root: Path,
    output_path: Path | None = None,
) -> ReportArtifactManifestResult:
    """Write checksum evidence for known local Entroping report artifacts."""

    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUT_PATH, root=root)
    artifacts: list[ReportArtifactEntry] = []
    missing_artifacts: list[ReportArtifactMissing] = []

    for definition in sorted(_DEFAULT_REPORT_ARTIFACTS, key=lambda item: item.path.as_posix()):
        resolved = _resolve_artifact_path(definition.path, root=root)
        display_path = _display_path(resolved, root=root)
        if not resolved.exists():
            missing_artifacts.append(
                ReportArtifactMissing(kind=definition.kind, path=display_path)
            )
            continue
        if not resolved.is_file():
            msg = f"report artifact path is not a file: {display_path}"
            raise ReportArtifactManifestError(msg)

        content = _read_artifact_bytes(resolved, artifact_path=display_path)
        artifacts.append(
            ReportArtifactEntry(
                kind=definition.kind,
                path=display_path,
                schema_version=_schema_version(
                    definition,
                    content,
                    artifact_path=display_path,
                ),
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    summary = ReportArtifactManifestSummary(
        total_expected=len(_DEFAULT_REPORT_ARTIFACTS),
        total_present=len(artifacts),
        total_missing=len(missing_artifacts),
    )
    audit = _write_audit_event(
        root=root,
        output_path=destination,
        summary=summary,
        artifacts=tuple(artifacts),
    )
    manifest = ReportArtifactManifest(
        summary=summary,
        artifacts=tuple(artifacts),
        missing_artifacts=tuple(missing_artifacts),
        audit=audit,
    )

    try:
        safe_write_text(
            destination,
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            artifact="report artifact manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise ReportArtifactManifestError(str(exc)) from exc
    return ReportArtifactManifestResult(output_path=destination, manifest=manifest)


def _resolve_artifact_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if path.is_absolute():
        msg = f"report artifact path must be project-relative: {raw_path}"
        raise ReportArtifactManifestError(msg)
    candidate = root / path
    _reject_symlink_path(candidate, root=root, artifact="report artifact")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"report artifact path must stay inside the project: {raw_path}"
        raise ReportArtifactManifestError(msg) from exc
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    _reject_symlink_path(path, root=root, artifact="report artifact manifest output")
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = f"report artifact manifest output path must stay inside the project: {raw_path}"
        raise ReportArtifactManifestError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "report artifact manifest output must not be written into .entroping or envs"
        raise ReportArtifactManifestError(msg)
    return resolved


def _reject_symlink_path(path: Path, *, root: Path, artifact: str) -> None:
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = f"{artifact} path must stay inside the project: {path}"
        raise ReportArtifactManifestError(msg) from exc
    if symlink_path is not None:
        msg = f"{artifact} path uses symlinked component: {symlink_path}"
        raise ReportArtifactManifestError(msg)


def _read_artifact_bytes(path: Path, *, artifact_path: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        msg = f"Could not read report artifact {artifact_path}: {exc}"
        raise ReportArtifactManifestError(msg) from exc


def _schema_version(
    definition: _ReportArtifactDefinition,
    content: bytes,
    *,
    artifact_path: str,
) -> str | None:
    if definition.kind == "sarif":
        return _sarif_schema_version(content, artifact_path=artifact_path)
    if definition.schema_hint is not None:
        return _validated_schema_hint(definition, content)
    return _json_schema_version(content, artifact_path=artifact_path)


def _validated_schema_hint(
    definition: _ReportArtifactDefinition,
    content: bytes,
) -> str | None:
    validators = {
        "junit": _looks_like_junit_xml,
        "run_html": _looks_like_run_report_html,
        "review_summary": _looks_like_review_summary_markdown,
    }
    validator = validators.get(definition.kind)
    return definition.schema_hint if validator is not None and validator(content) else None


def _looks_like_junit_xml(content: bytes) -> bool:
    try:
        root = ElementTree.fromstring(content)
    except (DefusedXmlException, ElementTree.ParseError):
        return False
    return _xml_local_name(root.tag) in {"testsuite", "testsuites"}


def _looks_like_run_report_html(content: bytes) -> bool:
    text = content.decode("utf-8-sig", errors="replace").casefold()
    return text.lstrip().startswith("<!doctype html") and "entroping run report" in text[:4096]


def _looks_like_review_summary_markdown(content: bytes) -> bool:
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    return bool(lines) and lines[0].strip() == "# Entroping Review Summary"


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _json_schema_version(content: bytes, *, artifact_path: str) -> str | None:
    document = _load_json_document_or_none(content, artifact_path=artifact_path)
    if not isinstance(document, dict):
        return None
    schema_version = document.get("schema_version")
    return _safe_metadata_text(schema_version) if isinstance(schema_version, str) else None


def _sarif_schema_version(content: bytes, *, artifact_path: str) -> str | None:
    document = _load_json_document_or_none(content, artifact_path=artifact_path)
    if not isinstance(document, dict):
        return None
    version = document.get("version")
    return _safe_metadata_text(f"SARIF {version}") if isinstance(version, str) else None


def _load_json_document_or_none(content: bytes, *, artifact_path: str) -> object | None:
    try:
        return _load_json_document(content, artifact_path=artifact_path)
    except ReportArtifactManifestError:
        return None


def _load_json_document(content: bytes, *, artifact_path: str) -> object:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"Could not read schema version from report artifact {artifact_path}: {exc}"
        raise ReportArtifactManifestError(msg) from exc


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _write_audit_event(
    *,
    root: Path,
    output_path: Path,
    summary: ReportArtifactManifestSummary,
    artifacts: tuple[ReportArtifactEntry, ...],
) -> ReportArtifactAuditEvidence:
    chain_path = _resolve_audit_chain_path(root=root)
    chain_display_path = _display_path(chain_path, root=root)
    state = _load_audit_chain(chain_path, root=root)
    if state.verification.status == "broken":
        return ReportArtifactAuditEvidence(
            chain_path=chain_display_path,
            verification=state.verification,
            event=None,
        )

    event = _build_audit_event(
        sequence=len(state.events) + 1,
        previous_event_hash=state.verification.latest_event_hash,
        output_path=_safe_metadata_text(_display_path(output_path, root=root)),
        summary=summary,
        artifacts=artifacts,
    )
    try:
        safe_write_text(
            chain_path,
            "".join(_audit_event_line(item) for item in (*state.events, event)),
            artifact="report audit chain",
            root=root,
        )
    except SafeWriteError as exc:
        raise ReportArtifactManifestError(str(exc)) from exc

    verification = ReportArtifactAuditVerification(
        status="verified",
        checked_events=len(state.events) + 1,
        latest_event_hash=event.event_hash,
        diagnostics=(),
    )
    return ReportArtifactAuditEvidence(
        chain_path=chain_display_path,
        verification=verification,
        event=event,
    )


def _resolve_audit_chain_path(*, root: Path) -> Path:
    candidate = root / _DEFAULT_AUDIT_CHAIN_PATH
    _reject_symlink_path(candidate, root=root, artifact="report audit chain")
    return candidate.resolve(strict=False)


def _load_audit_chain(path: Path, *, root: Path) -> _AuditChainState:
    if not path.exists():
        return _AuditChainState(
            events=(),
            verification=ReportArtifactAuditVerification(
                status="verified",
                checked_events=0,
                latest_event_hash=None,
                diagnostics=(),
            ),
        )
    if not path.is_file():
        msg = f"report audit chain path is not a file: {_display_path(path, root=root)}"
        raise ReportArtifactManifestError(msg)

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        msg = f"Could not read report audit chain {_display_path(path, root=root)}: {exc}"
        raise ReportArtifactManifestError(msg) from exc

    events: list[ReportArtifactAuditEvent] = []
    expected_previous_hash: str | None = None
    latest_event_hash: str | None = None
    checked_events = 0
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue
        checked_events = line_number
        try:
            raw_event = json.loads(line)
        except json.JSONDecodeError:
            return _broken_chain(events, checked_events, f"line {line_number} invalid JSON")
        if not isinstance(raw_event, dict):
            return _broken_chain(events, checked_events, f"line {line_number} is not an object")

        raw_event_hash = raw_event.get("event_hash")
        if not isinstance(raw_event_hash, str):
            return _broken_chain(
                events,
                checked_events,
                f"line {line_number} missing event hash",
            )
        expected_event_hash = _hash_audit_event_payload(
            {key: value for key, value in raw_event.items() if key != "event_hash"}
        )
        if raw_event_hash != expected_event_hash:
            return _broken_chain(
                events,
                checked_events,
                f"line {line_number} event hash mismatch",
            )
        if raw_event.get("previous_event_hash") != expected_previous_hash:
            return _broken_chain(
                events,
                checked_events,
                f"line {line_number} previous hash mismatch",
            )
        try:
            event = ReportArtifactAuditEvent.model_validate(raw_event)
        except ValidationError:
            return _broken_chain(
                events,
                checked_events,
                f"line {line_number} failed schema validation",
            )
        events.append(event)
        latest_event_hash = event.event_hash
        expected_previous_hash = event.event_hash

    return _AuditChainState(
        events=tuple(events),
        verification=ReportArtifactAuditVerification(
            status="verified",
            checked_events=checked_events if raw_lines else 0,
            latest_event_hash=latest_event_hash,
            diagnostics=(),
        ),
    )


def _broken_chain(
    events: list[ReportArtifactAuditEvent],
    checked_events: int,
    diagnostic: str,
) -> _AuditChainState:
    return _AuditChainState(
        events=tuple(events),
        verification=ReportArtifactAuditVerification(
            status="broken",
            checked_events=checked_events,
            latest_event_hash=None,
            diagnostics=(diagnostic,),
        ),
    )


def _build_audit_event(
    *,
    sequence: int,
    previous_event_hash: str | None,
    output_path: str,
    summary: ReportArtifactManifestSummary,
    artifacts: tuple[ReportArtifactEntry, ...],
) -> ReportArtifactAuditEvent:
    payload = {
        "schema_version": REPORT_AUDIT_EVENT_SCHEMA_VERSION,
        "event_type": "report_artifact_manifest",
        "sequence": sequence,
        "generated_at": datetime.now(UTC).isoformat(),
        "previous_event_hash": previous_event_hash,
        "command": {
            "name": "entroping report artifact-manifest",
            "output_path": output_path,
        },
        "summary": summary.model_dump(mode="json"),
        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
    }
    return ReportArtifactAuditEvent.model_validate(
        {
            **payload,
            "event_hash": _hash_audit_event_payload(payload),
        }
    )


def _audit_event_line(event: ReportArtifactAuditEvent) -> str:
    return (
        json.dumps(
            event.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _hash_audit_event_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _safe_metadata_text(value: str) -> str:
    return redact_secret_like_values(value).replace("\r", " ").replace("\n", " ")
