"""Cross-surface handoff packets from local sanitized evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.bridge.test_pyramid import TEST_PYRAMID_REPORT_SCHEMA_VERSION
from entroping.core.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA_VERSION
from entroping.core.evidence_common import (
    LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES,
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.pilot_metrics import PILOT_METRICS_SCHEMA_VERSION
from entroping.core.report_artifact_manifest import REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION
from entroping.core.runtime_card import RUNTIME_CARD_SCHEMA_VERSION
from entroping.core.safe_write import SafeWriteError, safe_write_text

HANDOFF_SCHEMA_VERSION: Final = "entroping.handoff.v1"

HandoffOutput = Literal["md", "json"]
HandoffStatus = Literal["ready", "partial", "insufficient"]
HandoffArtifactState = Literal["present", "missing", "invalid", "unsafe"]
HandoffArtifactId = Literal[
    "runtime_card",
    "evidence_bundle",
    "pilot_metrics",
    "artifact_manifest",
    "test_pyramid",
]
HandoffTargetId = Literal["cli", "pr", "desktop", "cloud", "mobile", "agent"]

_MAX_HANDOFF_ARTIFACT_BYTES: Final = LOCAL_EVIDENCE_MAX_ARTIFACT_BYTES
_GIT_SUBPROCESS_SYSTEM_PATHS: Final = ("/usr/bin", "/bin")
_DEFAULT_OUTPUTS: Final[dict[HandoffOutput, Path]] = {
    "md": Path("reports") / "handoff.md",
    "json": Path("reports") / "handoff.json",
}
_GIT_TIMEOUT_SECONDS: Final = 2.0


class HandoffError(ValueError):
    """Raised when a handoff packet cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _SourceDefinition:
    id: HandoffArtifactId
    label: str
    path: Path
    schema_version: str


@dataclass(frozen=True, slots=True)
class _LoadedSource:
    artifact: HandoffArtifact
    document: dict[str, object] | None


_SOURCE_DEFINITIONS: Final = (
    _SourceDefinition(
        id="runtime_card",
        label="Runtime card",
        path=Path("reports") / "runtime-card.json",
        schema_version=RUNTIME_CARD_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="evidence_bundle",
        label="Evidence bundle",
        path=Path("reports") / "evidence-bundle.json",
        schema_version=EVIDENCE_BUNDLE_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="pilot_metrics",
        label="Pilot metrics",
        path=Path("reports") / "pilot-metrics.json",
        schema_version=PILOT_METRICS_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="artifact_manifest",
        label="Artifact manifest",
        path=Path("reports") / "artifact-manifest.json",
        schema_version=REPORT_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ),
    _SourceDefinition(
        id="test_pyramid",
        label="Test pyramid",
        path=Path("reports") / "test-pyramid.json",
        schema_version=TEST_PYRAMID_REPORT_SCHEMA_VERSION,
    ),
)


class HandoffGit(BaseModel):
    """Best-effort local Git position for cross-surface continuity."""

    model_config = ConfigDict(extra="forbid")

    branch: str | None
    commit: str | None


class HandoffSummary(BaseModel):
    """Aggregate state of the handoff packet."""

    model_config = ConfigDict(extra="forbid")

    status: HandoffStatus
    artifacts_total: int = Field(ge=0)
    artifacts_present: int = Field(ge=0)
    artifacts_missing: int = Field(ge=0)
    artifacts_invalid: int = Field(ge=0)
    artifacts_unsafe: int = Field(ge=0)


class HandoffRuntimeSummary(BaseModel):
    """Value-free runtime-card fields carried into the handoff."""

    model_config = ConfigDict(extra="forbid")

    status: str
    findings: int = Field(ge=0)
    evidence_links: int = Field(ge=0)
    failed_gate_ids: int = Field(ge=0)
    pilot_readiness_status: str | None
    test_pyramid_status: str | None


class HandoffArtifact(BaseModel):
    """One local report artifact referenced by the handoff packet."""

    model_config = ConfigDict(extra="forbid")

    id: HandoffArtifactId
    label: str
    path: str
    state: HandoffArtifactState
    schema_version: str | None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class HandoffTarget(BaseModel):
    """One value-free destination surface for this handoff packet."""

    model_config = ConfigDict(extra="forbid")

    id: HandoffTargetId
    label: str
    next_action: str
    artifact_paths: tuple[str, ...] = ()


class HandoffPacket(BaseModel):
    """Schema-versioned cross-surface handoff packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.handoff.v1"] = HANDOFF_SCHEMA_VERSION
    generated_at: str
    project: str | None
    git: HandoffGit
    summary: HandoffSummary
    runtime: HandoffRuntimeSummary | None
    artifacts: tuple[HandoffArtifact, ...]
    targets: tuple[HandoffTarget, ...]


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Result of writing one handoff artifact."""

    output_path: Path
    packet: HandoffPacket


def run_handoff_report(
    *,
    project_root: Path,
    output: HandoffOutput,
    output_path: Path | None = None,
) -> HandoffResult:
    """Write a local cross-surface evidence handoff packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported handoff output: {output}"
        raise HandoffError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_handoff_packet(
        project_root=root,
        handoff_path=destination.relative_to(root).as_posix(),
    )
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_secret_like_value(content):
        msg = "handoff packet contains secret-like content"
        raise HandoffError(msg)
    try:
        written = safe_write_text(destination, content, artifact="handoff packet", root=root)
    except SafeWriteError as exc:
        raise HandoffError(str(exc)) from exc
    return HandoffResult(output_path=written, packet=packet)


def build_handoff_packet(
    *,
    project_root: Path,
    handoff_path: str = "reports/handoff.json",
) -> HandoffPacket:
    """Build a value-free handoff packet from existing local report artifacts."""

    root = project_root.expanduser().resolve()
    loaded = tuple(_load_source(definition, root=root) for definition in _SOURCE_DEFINITIONS)
    artifacts = tuple(source.artifact for source in loaded)
    documents = {source.artifact.id: source.document for source in loaded}
    runtime = _runtime_summary(documents["runtime_card"])
    return HandoffPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_runtime_card(documents["runtime_card"]),
        git=_git_metadata(root),
        summary=_summary(artifacts),
        runtime=runtime,
        artifacts=artifacts,
        targets=_targets(artifacts, handoff_path=_safe_text(handoff_path)),
    )


def render_handoff_markdown(packet: HandoffPacket) -> str:
    """Render a human-readable handoff packet."""

    lines = [
        "# Entroping Evidence Handoff",
        "",
        f"- Status: `{packet.summary.status}`",
        f"- Project: `{_inline_code(packet.project or 'unknown')}`",
        f"- Branch: `{_inline_code(packet.git.branch or 'unknown')}`",
        f"- Commit: `{_inline_code(packet.git.commit or 'unknown')}`",
        "- Artifacts: "
        f"`{packet.summary.artifacts_present}/{packet.summary.artifacts_total}` present, "
        f"`{packet.summary.artifacts_missing}` missing, "
        f"`{packet.summary.artifacts_invalid}` invalid, "
        f"`{packet.summary.artifacts_unsafe}` unsafe",
        "",
        "## Runtime",
        "",
    ]
    if packet.runtime is None:
        lines.append("No runtime-card summary is available.")
    else:
        lines.extend(
            [
                f"- Runtime status: `{_inline_code(packet.runtime.status)}`",
                f"- Findings: `{packet.runtime.findings}`",
                f"- Evidence links: `{packet.runtime.evidence_links}`",
                f"- Failed gates: `{packet.runtime.failed_gate_ids}`",
                "- Pilot readiness: "
                f"`{_inline_code(packet.runtime.pilot_readiness_status or 'unknown')}`",
                "- Test pyramid: "
                f"`{_inline_code(packet.runtime.test_pyramid_status or 'unknown')}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Artifact | State | Path | Schema | SHA-256 | Summary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for artifact in packet.artifacts:
        lines.append(
            "| "
            f"{_markdown_cell(artifact.id)} | "
            f"{_markdown_cell(artifact.state)} | "
            f"{_markdown_cell(artifact.path)} | "
            f"{_markdown_cell(artifact.schema_version or 'n/a')} | "
            f"{_markdown_cell(artifact.sha256 or 'n/a')} | "
            f"{_markdown_cell(artifact.summary)} |"
        )

    lines.extend(
        [
            "",
            "## Targets",
            "",
            "| Surface | Next Action | Artifact Paths |",
            "| --- | --- | --- |",
        ]
    )
    for target in packet.targets:
        lines.append(
            "| "
            f"{_markdown_cell(target.id)} | "
            f"{_markdown_cell(target.next_action)} | "
            f"{_markdown_cell(', '.join(target.artifact_paths) or 'n/a')} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_packet_content(packet: HandoffPacket, *, output: HandoffOutput) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_handoff_markdown(packet)


def _load_source(definition: _SourceDefinition, *, root: Path) -> _LoadedSource:
    try:
        path = _resolve_source_path(definition.path, root=root)
    except HandoffError as exc:
        return _loaded_source(
            definition,
            state="unsafe",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    if not path.exists():
        return _loaded_source(
            definition,
            state="missing",
            schema_version=None,
            sha256=None,
            summary="Artifact is missing.",
            document=None,
        )
    try:
        raw_bytes = _read_bounded_bytes(path, artifact=definition.label.lower())
        raw_text = raw_bytes.decode("utf-8")
    except HandoffError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    except UnicodeDecodeError as exc:
        msg = f"Could not decode {definition.label.lower()} as UTF-8: {exc}"
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(msg),
            document=None,
        )
    if _contains_unredacted_secret_like_value(raw_text):
        return _loaded_source(
            definition,
            state="unsafe",
            schema_version=None,
            sha256=None,
            summary=f"{definition.label} contains secret-like content.",
            document=None,
        )
    try:
        document = _json_object(raw_text, artifact=definition.label.lower())
        schema_version = _schema_version(document)
        if schema_version != definition.schema_version:
            return _loaded_source(
                definition,
                state="invalid",
                schema_version=schema_version,
                sha256=None,
                summary=(
                    "unsupported schema_version; expected "
                    f"{definition.schema_version}"
                ),
                document=None,
            )
        summary = _source_summary(definition, document)
    except HandoffError as exc:
        return _loaded_source(
            definition,
            state="invalid",
            schema_version=None,
            sha256=None,
            summary=_safe_text(str(exc)),
            document=None,
        )
    return _loaded_source(
        definition,
        state="present",
        schema_version=definition.schema_version,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        summary=summary,
        document=document,
    )


def _loaded_source(
    definition: _SourceDefinition,
    *,
    state: HandoffArtifactState,
    schema_version: str | None,
    sha256: str | None,
    summary: str,
    document: dict[str, object] | None,
) -> _LoadedSource:
    return _LoadedSource(
        artifact=HandoffArtifact(
            id=definition.id,
            label=definition.label,
            path=definition.path.as_posix(),
            state=state,
            schema_version=_safe_text(schema_version) if schema_version else None,
            sha256=sha256,
            summary=_safe_text(summary),
        ),
        document=document,
    )


def _resolve_source_path(raw_path: Path, *, root: Path) -> Path:
    candidate = root / raw_path
    symlink_path = first_symlink_path_component(candidate, root=root)
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"handoff source path uses symlinked component: {display_path}"
        raise HandoffError(msg)
    resolved = candidate.resolve(strict=False)
    if resolved.exists() and not resolved.is_file():
        msg = f"handoff source path is not a file: {raw_path.as_posix()}"
        raise HandoffError(msg)
    return resolved


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        symlink_path = first_symlink_path_component(path, root=root)
    except ValueError as exc:
        msg = "handoff output path must stay under the project root"
        raise HandoffError(msg) from exc
    if symlink_path is not None:
        display_path = symlink_path.relative_to(root).as_posix()
        msg = f"handoff output path uses symlinked component: {display_path}"
        raise HandoffError(msg)
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "handoff output path must stay under the project root"
        raise HandoffError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "handoff packet must not be written into .entroping or envs"
        raise HandoffError(msg)
    return resolved


def _read_bounded_bytes(path: Path, *, artifact: str) -> bytes:
    try:
        if path.stat().st_size > _MAX_HANDOFF_ARTIFACT_BYTES:
            msg = (
                f"{artifact.capitalize()} {path.name} exceeds "
                f"{_MAX_HANDOFF_ARTIFACT_BYTES} bytes"
            )
            raise HandoffError(msg)
        return path.read_bytes()
    except HandoffError:
        raise
    except OSError as exc:
        msg = f"Could not read {artifact}: {exc}"
        raise HandoffError(msg) from exc


def _json_object(raw_text: str, *, artifact: str) -> dict[str, object]:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse {artifact}: {exc}"
        raise HandoffError(msg) from exc
    if not isinstance(document, dict):
        msg = f"{artifact.capitalize()} must be a JSON object"
        raise HandoffError(msg)
    return document


def _schema_version(document: dict[str, object]) -> str | None:
    value = document.get("schema_version")
    return _safe_text(value) if isinstance(value, str) else None


def _source_summary(definition: _SourceDefinition, document: dict[str, object]) -> str:
    if definition.id == "runtime_card":
        runtime = _runtime_summary_from_document(document)
        return f"{runtime.status}; {runtime.findings} findings"
    if definition.id == "evidence_bundle":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        present = _required_non_negative_int(
            summary,
            "required_present",
            artifact=definition.label,
        )
        total = _required_non_negative_int(
            summary,
            "required_total",
            artifact=definition.label,
        )
        return f"{status}; {present}/{total} required present"
    if definition.id == "pilot_metrics":
        summary = _required_object(document, "summary", artifact=definition.label)
        status = _required_text(summary, "status", artifact=definition.label)
        return f"{status} pilot metrics"
    if definition.id == "artifact_manifest":
        audit = _required_object(document, "audit", artifact=definition.label)
        verification = _required_object(audit, "verification", artifact=definition.label)
        status = _required_text(verification, "status", artifact=definition.label)
        return f"audit {status}"
    summary = _required_object(document, "summary", artifact=definition.label)
    status = _required_text(summary, "runtime_governance_status", artifact=definition.label)
    present = _required_non_negative_int(
        summary,
        "present_layers",
        artifact=definition.label,
    )
    total = _required_non_negative_int(summary, "total_layers", artifact=definition.label)
    return f"{status}; {present}/{total} runtime-governance layers present"


def _runtime_summary(document: dict[str, object] | None) -> HandoffRuntimeSummary | None:
    if document is None:
        return None
    return _runtime_summary_from_document(document)


def _runtime_summary_from_document(document: dict[str, object]) -> HandoffRuntimeSummary:
    summary = _required_object(document, "summary", artifact="Runtime card")
    status = _required_text(summary, "status", artifact="Runtime card")
    run = document.get("run")
    failed_gate_ids = 0
    if isinstance(run, dict):
        raw_failed_gate_ids = run.get("failed_gate_ids", [])
        if isinstance(raw_failed_gate_ids, list):
            failed_gate_ids = sum(1 for gate in raw_failed_gate_ids if isinstance(gate, str))
    return HandoffRuntimeSummary(
        status=status,
        findings=_required_non_negative_int(summary, "findings", artifact="Runtime card"),
        evidence_links=_required_non_negative_int(
            summary,
            "evidence_links",
            artifact="Runtime card",
        ),
        failed_gate_ids=failed_gate_ids,
        pilot_readiness_status=_nested_status(document, "pilot_readiness"),
        test_pyramid_status=_nested_status(document, "test_pyramid"),
    )


def _project_from_runtime_card(document: dict[str, object] | None) -> str | None:
    if document is None:
        return None
    run = document.get("run")
    if not isinstance(run, dict):
        return None
    project = run.get("project")
    return _safe_text(project) if isinstance(project, str) and project.strip() else None


def _nested_status(document: dict[str, object], key: str) -> str | None:
    value = document.get(key)
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    return _safe_text(status) if isinstance(status, str) and status.strip() else None


def _required_object(
    document: dict[str, object],
    key: str,
    *,
    artifact: str,
) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        msg = f"{artifact} field {key} must be an object"
        raise HandoffError(msg)
    return value


def _required_text(document: dict[str, object], key: str, *, artifact: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{artifact} field {key} must be a non-empty string"
        raise HandoffError(msg)
    return _safe_text(value)


def _required_non_negative_int(
    document: dict[str, object],
    key: str,
    *,
    artifact: str,
) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"{artifact} field {key} must be a non-negative integer"
        raise HandoffError(msg)
    return value


def _summary(artifacts: tuple[HandoffArtifact, ...]) -> HandoffSummary:
    present = sum(1 for artifact in artifacts if artifact.state == "present")
    invalid = sum(1 for artifact in artifacts if artifact.state == "invalid")
    unsafe = sum(1 for artifact in artifacts if artifact.state == "unsafe")
    missing = sum(1 for artifact in artifacts if artifact.state == "missing")
    status: HandoffStatus = (
        "ready" if present > 0 and invalid == 0 and unsafe == 0 else "partial"
    )
    if present == 0:
        status = "insufficient"
    return HandoffSummary(
        status=status,
        artifacts_total=len(artifacts),
        artifacts_present=present,
        artifacts_missing=missing,
        artifacts_invalid=invalid,
        artifacts_unsafe=unsafe,
    )


def _targets(
    artifacts: tuple[HandoffArtifact, ...],
    *,
    handoff_path: str,
) -> tuple[HandoffTarget, ...]:
    present_paths = tuple(artifact.path for artifact in artifacts if artifact.state == "present")
    present_by_id = {
        artifact.id: artifact.path for artifact in artifacts if artifact.state == "present"
    }
    pr_paths = (handoff_path, *(
        (present_by_id["runtime_card"],) if "runtime_card" in present_by_id else ()
    ))
    return (
        HandoffTarget(
            id="cli",
            label="CLI",
            next_action="Open the local handoff packet and referenced reports.",
            artifact_paths=(handoff_path, *present_paths),
        ),
        HandoffTarget(
            id="pr",
            label="Pull request",
            next_action="Attach the handoff packet and runtime card as reviewer evidence.",
            artifact_paths=pr_paths,
        ),
        HandoffTarget(
            id="desktop",
            label="Desktop",
            next_action="Render read-only report summaries from the handoff packet.",
            artifact_paths=(handoff_path,),
        ),
        HandoffTarget(
            id="cloud",
            label="Cloud",
            next_action="Upload only the sanitized handoff packet after explicit consent.",
            artifact_paths=(handoff_path,),
        ),
        HandoffTarget(
            id="mobile",
            label="Mobile",
            next_action="Show read-only status, blockers, and local evidence links.",
            artifact_paths=(handoff_path,),
        ),
        HandoffTarget(
            id="agent",
            label="Agent",
            next_action="Use the handoff packet as bounded context before proposing work.",
            artifact_paths=(handoff_path,),
        ),
    )


def _git_metadata(root: Path) -> HandoffGit:
    return HandoffGit(
        branch=_git_value(root, "branch", "--show-current"),
        commit=_git_value(root, "rev-parse", "HEAD"),
    )


def _git_value(root: Path, *args: str) -> str | None:
    git_binary = shutil.which("git")
    if git_binary is None:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [git_binary, "-C", str(root), *args],
            check=False,
            capture_output=True,
            env=_minimal_git_subprocess_env(git_binary),
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = _safe_text(result.stdout.strip())
    return value or None


def _minimal_git_subprocess_env(git_binary: str) -> dict[str, str]:
    path_entries = [
        str(Path(git_binary).resolve().parent),
        *_GIT_SUBPROCESS_SYSTEM_PATHS,
    ]
    return {"PATH": ":".join(dict.fromkeys(path_entries))}


def _safe_text(value: object) -> str:
    return safe_evidence_text(str(value))


def _contains_unredacted_secret_like_value(value: str) -> bool:
    return contains_unredacted_evidence_secret(value)


def _inline_code(value: str) -> str:
    return _markdown_text(value).replace("`", "'")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("\n", "<br>")


def _markdown_text(value: str) -> str:
    backslash_placeholder = "\0ENTROPING_BACKSLASH\0"
    text = value.replace("\r", " ").replace("\\", backslash_placeholder)
    text = escape(text, quote=False).replace("|", "\\|")
    return text.replace(backslash_placeholder, "&#92;")
