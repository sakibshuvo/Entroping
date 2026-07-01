"""Local Evidence Cloud workspace dashboard packets for design-partner review."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.export.evidence_cloud_export import (
    EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION,
    EvidenceCloudExportBoundaryControl,
    EvidenceCloudExportPacket,
)
from entroping.core.markdown_report import markdown_cell as _md
from entroping.core.markdown_report import markdown_table_row
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_report_output_path, safe_write_text

EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION: Final = "entroping.evidence-cloud-workspace.v1"

EvidenceCloudWorkspaceOutput = Literal["md", "json"]
EvidenceCloudWorkspaceStatus = Literal["ready", "partial", "insufficient"]
EvidenceCloudWorkspaceManifestState = Literal["present", "missing", "invalid", "unsafe"]
EvidenceCloudWorkspaceRepositoryStatus = Literal["ready", "partial", "insufficient"]
EvidenceCloudWorkspaceNextActionPriority = Literal["high", "medium", "low"]
EvidenceCloudWorkspaceBoundaryControlId = Literal[
    "explicit_upload_only",
    "no_remote_api",
    "no_raw_traffic",
    "no_secrets",
    "no_prompts_or_provider_outputs",
    "no_source_hurl",
    "no_env_values",
    "no_full_report_payloads",
]

_DEFAULT_OUTPUTS: Final[dict[EvidenceCloudWorkspaceOutput, Path]] = {
    "md": Path("reports") / "evidence-cloud-workspace.md",
    "json": Path("reports") / "evidence-cloud-workspace.json",
}
_MAX_MANIFEST_BYTES: Final = 1024 * 1024
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_FORBIDDEN_MANIFEST_COMPONENTS: Final = {".entroping", "envs"}


class EvidenceCloudWorkspaceError(ValueError):
    """Raised when an Evidence Cloud workspace packet cannot be generated safely."""


class EvidenceCloudWorkspaceSummary(BaseModel):
    """Aggregate local Evidence Cloud workspace state."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceCloudWorkspaceStatus
    manifests_total: int = Field(ge=0)
    manifests_present: int = Field(ge=0)
    manifests_missing: int = Field(ge=0)
    manifests_invalid: int = Field(ge=0)
    manifests_unsafe: int = Field(ge=0)
    repositories_total: int = Field(ge=0)
    repositories_ready: int = Field(ge=0)
    repositories_partial: int = Field(ge=0)
    repositories_insufficient: int = Field(ge=0)
    export_items_total: int = Field(ge=0)
    export_items_ready: int = Field(ge=0)
    export_items_blocked: int = Field(ge=0)
    boundary_controls_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidenceCloudWorkspaceManifest(BaseModel):
    """One explicit local Evidence Cloud export manifest considered for aggregation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    state: EvidenceCloudWorkspaceManifestState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    project: str | None = None
    export_status: EvidenceCloudWorkspaceRepositoryStatus | None = None
    summary: str


class EvidenceCloudWorkspaceRepository(BaseModel):
    """One value-free repository card derived from a valid export manifest."""

    model_config = ConfigDict(extra="forbid")

    id: str
    manifest_id: str
    project: str
    status: EvidenceCloudWorkspaceRepositoryStatus
    sources_present: int = Field(ge=0)
    sources_total: int = Field(ge=0)
    export_items_ready: int = Field(ge=0)
    export_items_total: int = Field(ge=0)
    export_items_blocked: int = Field(ge=0)
    boundary_controls_total: int = Field(ge=0)
    local_reference: str
    summary: str


class EvidenceCloudWorkspaceBoundaryControl(BaseModel):
    """Aggregate boundary-control evidence across workspace manifests."""

    model_config = ConfigDict(extra="forbid")

    id: EvidenceCloudWorkspaceBoundaryControlId
    label: str
    total_manifests: int = Field(ge=0)
    enforced_manifests: int = Field(ge=0)
    summary: str


class EvidenceCloudWorkspaceNextAction(BaseModel):
    """One local action needed before Evidence Cloud workspace promotion."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidenceCloudWorkspaceNextActionPriority
    action: str
    manifest_ids: tuple[str, ...] = ()
    repository_ids: tuple[str, ...] = ()


class EvidenceCloudWorkspacePacket(BaseModel):
    """Schema-versioned local Evidence Cloud workspace dashboard packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-cloud-workspace.v1"] = (
        EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    summary: EvidenceCloudWorkspaceSummary
    manifests: tuple[EvidenceCloudWorkspaceManifest, ...]
    repositories: tuple[EvidenceCloudWorkspaceRepository, ...]
    boundary_controls: tuple[EvidenceCloudWorkspaceBoundaryControl, ...]
    next_actions: tuple[EvidenceCloudWorkspaceNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCloudWorkspaceResult:
    """Result of writing one Evidence Cloud workspace report."""

    output_path: Path
    packet: EvidenceCloudWorkspacePacket


@dataclass(frozen=True, slots=True)
class _LoadedManifest:
    row: EvidenceCloudWorkspaceManifest
    packet: EvidenceCloudExportPacket | None


def run_evidence_cloud_workspace_report(
    *,
    project_root: Path,
    manifests: tuple[Path, ...],
    output: EvidenceCloudWorkspaceOutput,
    output_path: Path | None = None,
) -> EvidenceCloudWorkspaceResult:
    """Write a local Evidence Cloud workspace dashboard packet."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-cloud-workspace output: {output}"
        raise EvidenceCloudWorkspaceError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_cloud_workspace_packet(project_root=root, manifests=manifests)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_workspace_secret(content):
        msg = "Evidence Cloud workspace packet contains secret-like content"
        raise EvidenceCloudWorkspaceError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="Evidence Cloud workspace packet",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceCloudWorkspaceError(str(exc)) from exc
    return EvidenceCloudWorkspaceResult(output_path=written, packet=packet)


def build_evidence_cloud_workspace_packet(
    *,
    project_root: Path,
    manifests: tuple[Path, ...],
) -> EvidenceCloudWorkspacePacket:
    """Build a value-free local Evidence Cloud workspace packet."""

    if not manifests:
        msg = "Evidence Cloud workspace requires at least one export manifest"
        raise EvidenceCloudWorkspaceError(msg)
    root = project_root.expanduser().resolve()
    loaded = tuple(
        _load_manifest(raw_path, root=root, index=index)
        for index, raw_path in enumerate(manifests, start=1)
    )
    manifest_rows = tuple(item.row for item in loaded)
    repositories = _repositories(loaded)
    boundary_controls = _boundary_controls(loaded)
    next_actions = _next_actions(
        manifests=manifest_rows,
        repositories=repositories,
    )
    return EvidenceCloudWorkspacePacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=safe_evidence_text(root.name),
        summary=_summary(
            manifests=manifest_rows,
            repositories=repositories,
            boundary_controls=boundary_controls,
            next_actions=next_actions,
        ),
        manifests=manifest_rows,
        repositories=repositories,
        boundary_controls=boundary_controls,
        next_actions=next_actions,
    )


def render_evidence_cloud_workspace_markdown(packet: EvidenceCloudWorkspacePacket) -> str:
    """Render a human-readable, value-free Evidence Cloud workspace packet."""

    lines = [
        "# Entroping Evidence Cloud Workspace",
        "",
        "Local dashboard packet for explicit Evidence Cloud export manifests. This",
        "report aggregates metadata only and does not upload or embed artifact payloads.",
        "",
        "## Summary",
        "",
        f"- Status: `{_md(packet.summary.status, style='evidence_cloud')}`",
        f"- Manifests: `{packet.summary.manifests_present}/"
        f"{packet.summary.manifests_total}` present",
        f"- Repositories: `{packet.summary.repositories_ready}/"
        f"{packet.summary.repositories_total}` ready",
        f"- Export items: `{packet.summary.export_items_ready}/"
        f"{packet.summary.export_items_total}` ready",
        "",
        "## Manifests",
        "",
        "| ID | State | Project | Export Status | Path | SHA-256 | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for manifest in packet.manifests:
        lines.append(
            markdown_table_row(
                _md(manifest.id, style="evidence_cloud"),
                _md(manifest.state, style="evidence_cloud"),
                _md(manifest.project or "n/a", style="evidence_cloud"),
                _md(manifest.export_status or "n/a", style="evidence_cloud"),
                _md(manifest.path, style="evidence_cloud"),
                _md(manifest.sha256 or "n/a", style="evidence_cloud"),
                _md(manifest.summary, style="evidence_cloud"),
            )
        )
    lines.extend(
        [
            "",
            "## Repositories",
            "",
            "| Project | Status | Sources | Export Items | Boundary Controls | Local Reference |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for repository in packet.repositories:
        lines.append(
            markdown_table_row(
                _md(repository.project, style="evidence_cloud"),
                _md(repository.status, style="evidence_cloud"),
                f"{repository.sources_present}/{repository.sources_total}",
                f"{repository.export_items_ready}/{repository.export_items_total}",
                str(repository.boundary_controls_total),
                _md(repository.local_reference, style="evidence_cloud"),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary Controls",
            "",
            "| Control | Enforced Manifests | Summary |",
            "| --- | --- | --- |",
        ]
    )
    for control in packet.boundary_controls:
        lines.append(
            markdown_table_row(
                _md(control.label, style="evidence_cloud"),
                f"{control.enforced_manifests}/{control.total_manifests}",
                _md(control.summary, style="evidence_cloud"),
            )
        )
    lines.extend(["", "## Next Actions", ""])
    if packet.next_actions:
        for action in packet.next_actions:
            lines.append(
                f"- `{_md(action.priority, style='evidence_cloud')}` "
                f"{_md(action.action, style='evidence_cloud')}"
            )
    else:
        lines.append("No Evidence Cloud workspace actions are currently needed.")
    return "\n".join(lines) + "\n"


def _load_manifest(raw_path: Path, *, root: Path, index: int) -> _LoadedManifest:
    manifest_id = f"manifest-{index}"
    path = _normalize_manifest_path(raw_path, root=root)
    display_path = _display_path(path, root=root)
    if _has_forbidden_component(path, root=root):
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary="forbidden manifest path component",
        )
    if _first_manifest_symlink_component(path, root=root) is not None:
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary="symlinked path component",
        )
    if _relative_manifest_escapes_root(raw_path, path=path, root=root):
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary="manifest path outside project",
        )
    if not path.exists():
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="missing",
            summary="manifest missing",
        )
    if not path.is_file():
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary="manifest is not a file",
        )
    raw_bytes, load_error = _read_manifest_bytes(path)
    if raw_bytes is None:
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary=load_error,
        )
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if _contains_unredacted_workspace_secret(raw_text):
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="unsafe",
            summary="secret-like content",
        )
    try:
        packet = EvidenceCloudExportPacket.model_validate_json(raw_bytes)
    except (ValidationError, ValueError):
        return _invalid_manifest(
            manifest_id,
            display_path,
            state="invalid",
            summary="invalid Evidence Cloud export manifest",
        )
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return _LoadedManifest(
        row=EvidenceCloudWorkspaceManifest(
            id=manifest_id,
            path=display_path,
            state="present",
            schema_version=EVIDENCE_CLOUD_EXPORT_SCHEMA_VERSION,
            sha256=sha256,
            project=safe_evidence_text(packet.project),
            export_status=packet.summary.status,
            summary=packet.summary.status,
        ),
        packet=packet,
    )


def _read_manifest_bytes(path: Path) -> tuple[bytes | None, str]:
    try:
        with path.open("rb") as handle:
            raw_bytes = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError:
        return None, "manifest unreadable"
    if len(raw_bytes) > _MAX_MANIFEST_BYTES:
        return None, "manifest too large"
    return raw_bytes, ""


def _invalid_manifest(
    manifest_id: str,
    path: str,
    *,
    state: EvidenceCloudWorkspaceManifestState,
    summary: str,
) -> _LoadedManifest:
    return _LoadedManifest(
        row=EvidenceCloudWorkspaceManifest(
            id=manifest_id,
            path=path,
            state=state,
            schema_version=None,
            sha256=None,
            project=None,
            export_status=None,
            summary=safe_evidence_text(summary),
        ),
        packet=None,
    )


def _repositories(
    loaded: tuple[_LoadedManifest, ...],
) -> tuple[EvidenceCloudWorkspaceRepository, ...]:
    repositories: list[EvidenceCloudWorkspaceRepository] = []
    for item in loaded:
        packet = item.packet
        if packet is None:
            continue
        repository_id = f"repository-{len(repositories) + 1}"
        summary = packet.summary
        repositories.append(
            EvidenceCloudWorkspaceRepository(
                id=repository_id,
                manifest_id=item.row.id,
                project=safe_evidence_text(packet.project),
                status=summary.status,
                sources_present=summary.sources_present,
                sources_total=summary.sources_total,
                export_items_ready=summary.export_items_ready,
                export_items_total=summary.export_items_total,
                export_items_blocked=summary.export_items_blocked,
                boundary_controls_total=summary.boundary_controls_total,
                local_reference=f"entroping://evidence-cloud-workspace/{repository_id}",
                summary=summary.status,
            )
        )
    return tuple(repositories)


def _boundary_controls(
    loaded: tuple[_LoadedManifest, ...],
) -> tuple[EvidenceCloudWorkspaceBoundaryControl, ...]:
    controls_by_id: dict[str, list[EvidenceCloudExportBoundaryControl]] = defaultdict(list)
    present_manifests = sum(1 for item in loaded if item.packet is not None)
    for item in loaded:
        if item.packet is None:
            continue
        for control in item.packet.boundary_controls:
            controls_by_id[control.id].append(control)
    controls: list[EvidenceCloudWorkspaceBoundaryControl] = []
    for control_id in sorted(controls_by_id):
        controls_for_id = controls_by_id[control_id]
        first = controls_for_id[0]
        enforced = sum(1 for control in controls_for_id if control.enforced)
        controls.append(
            EvidenceCloudWorkspaceBoundaryControl(
                id=first.id,
                label=safe_evidence_text(first.label),
                total_manifests=present_manifests,
                enforced_manifests=enforced,
                summary=_boundary_summary(
                    label=first.label,
                    enforced=enforced,
                    total=present_manifests,
                ),
            )
        )
    return tuple(controls)


def _boundary_summary(*, label: str, enforced: int, total: int) -> str:
    if total == 0:
        return f"{safe_evidence_text(label)} has no valid manifests to summarize."
    if enforced == total:
        return f"{safe_evidence_text(label)} is enforced across all valid manifests."
    return f"{safe_evidence_text(label)} is enforced across {enforced}/{total} valid manifests."


def _summary(
    *,
    manifests: tuple[EvidenceCloudWorkspaceManifest, ...],
    repositories: tuple[EvidenceCloudWorkspaceRepository, ...],
    boundary_controls: tuple[EvidenceCloudWorkspaceBoundaryControl, ...],
    next_actions: tuple[EvidenceCloudWorkspaceNextAction, ...],
) -> EvidenceCloudWorkspaceSummary:
    return EvidenceCloudWorkspaceSummary(
        status=_workspace_status(manifests=manifests, repositories=repositories),
        manifests_total=len(manifests),
        manifests_present=sum(1 for manifest in manifests if manifest.state == "present"),
        manifests_missing=sum(1 for manifest in manifests if manifest.state == "missing"),
        manifests_invalid=sum(1 for manifest in manifests if manifest.state == "invalid"),
        manifests_unsafe=sum(1 for manifest in manifests if manifest.state == "unsafe"),
        repositories_total=len(repositories),
        repositories_ready=sum(1 for repository in repositories if repository.status == "ready"),
        repositories_partial=sum(
            1 for repository in repositories if repository.status == "partial"
        ),
        repositories_insufficient=sum(
            1 for repository in repositories if repository.status == "insufficient"
        ),
        export_items_total=sum(repository.export_items_total for repository in repositories),
        export_items_ready=sum(repository.export_items_ready for repository in repositories),
        export_items_blocked=sum(repository.export_items_blocked for repository in repositories),
        boundary_controls_total=len(boundary_controls),
        next_actions_total=len(next_actions),
    )


def _workspace_status(
    *,
    manifests: tuple[EvidenceCloudWorkspaceManifest, ...],
    repositories: tuple[EvidenceCloudWorkspaceRepository, ...],
) -> EvidenceCloudWorkspaceStatus:
    if any(manifest.state != "present" for manifest in manifests):
        return "insufficient"
    if not repositories:
        return "insufficient"
    if any(repository.status == "insufficient" for repository in repositories):
        return "insufficient"
    if any(repository.status == "partial" for repository in repositories):
        return "partial"
    return "ready"


def _next_actions(
    *,
    manifests: tuple[EvidenceCloudWorkspaceManifest, ...],
    repositories: tuple[EvidenceCloudWorkspaceRepository, ...],
) -> tuple[EvidenceCloudWorkspaceNextAction, ...]:
    actions: list[EvidenceCloudWorkspaceNextAction] = []
    for manifest in manifests:
        if manifest.state == "present":
            continue
        repair = manifest.state in {"invalid", "unsafe"}
        actions.append(
            EvidenceCloudWorkspaceNextAction(
                priority="high" if repair else "medium",
                action=_manifest_action(manifest),
                manifest_ids=(manifest.id,),
            )
        )
    partial_repositories = tuple(
        repository for repository in repositories if repository.status == "partial"
    )
    if partial_repositories:
        actions.append(
            EvidenceCloudWorkspaceNextAction(
                priority="medium",
                action="Review partial Evidence Cloud export manifests before workspace promotion.",
                manifest_ids=tuple(repository.manifest_id for repository in partial_repositories),
                repository_ids=tuple(repository.id for repository in partial_repositories),
            )
        )
    insufficient_repositories = tuple(
        repository for repository in repositories if repository.status == "insufficient"
    )
    if insufficient_repositories:
        actions.append(
            EvidenceCloudWorkspaceNextAction(
                priority="high",
                action=(
                    "Repair insufficient Evidence Cloud export manifests before workspace "
                    "promotion."
                ),
                manifest_ids=tuple(
                    repository.manifest_id for repository in insufficient_repositories
                ),
                repository_ids=tuple(repository.id for repository in insufficient_repositories),
            )
        )
    return tuple(actions)


def _manifest_action(manifest: EvidenceCloudWorkspaceManifest) -> str:
    if manifest.state == "missing":
        return f"Generate or provide {manifest.id} before Evidence Cloud workspace review."
    return f"Repair {manifest.id} before Evidence Cloud workspace review."


def _normalize_manifest_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def _relative_manifest_escapes_root(raw_path: Path, *, path: Path, root: Path) -> bool:
    if raw_path.expanduser().is_absolute():
        return False
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        return True
    return False


def _first_manifest_symlink_component(path: Path, *, root: Path) -> Path | None:
    if path.is_relative_to(root):
        return first_symlink_path_component(path, root=root)
    return first_symlink_path_component(path)


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _has_forbidden_component(path: Path, *, root: Path) -> bool:
    candidate = path if path.is_absolute() else root / path
    try:
        parts = candidate.resolve(strict=False).relative_to(root).parts
    except ValueError:
        return False
    return any(part.lower() in _FORBIDDEN_MANIFEST_COMPONENTS for part in parts)


def _render_packet_content(
    packet: EvidenceCloudWorkspacePacket,
    *,
    output: EvidenceCloudWorkspaceOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_cloud_workspace_markdown(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    try:
        return safe_report_output_path(raw_path, root=root, artifact="Evidence Cloud workspace")
    except SafeWriteError as exc:
        raise EvidenceCloudWorkspaceError(str(exc)) from exc


def _contains_unredacted_workspace_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))
