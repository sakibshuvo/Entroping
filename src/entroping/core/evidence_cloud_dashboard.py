"""Static local Evidence Cloud workspace dashboard for design-partner review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_cloud_workspace import (
    EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION,
    EvidenceCloudWorkspaceBoundaryControl,
    EvidenceCloudWorkspaceError,
    EvidenceCloudWorkspaceManifest,
    EvidenceCloudWorkspaceNextAction,
    EvidenceCloudWorkspacePacket,
    EvidenceCloudWorkspaceRepository,
    EvidenceCloudWorkspaceRepositoryStatus,
    EvidenceCloudWorkspaceStatus,
    build_evidence_cloud_workspace_packet,
)
from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text

EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION: Final = "entroping.evidence-cloud-dashboard.v1"

EvidenceCloudDashboardOutput = Literal["html", "json"]
EvidenceCloudDashboardStatus = EvidenceCloudWorkspaceStatus
EvidenceCloudDashboardRepositoryState = Literal["ready", "attention"]

_DEFAULT_OUTPUTS: Final[dict[EvidenceCloudDashboardOutput, Path]] = {
    "html": Path("reports") / "evidence-cloud-dashboard.html",
    "json": Path("reports") / "evidence-cloud-dashboard.json",
}
_SHA256_HEX_RE: Final = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)


class EvidenceCloudDashboardError(ValueError):
    """Raised when the Evidence Cloud dashboard cannot be generated safely."""


class EvidenceCloudDashboardSummary(BaseModel):
    """Aggregate value-free Evidence Cloud dashboard state."""

    model_config = ConfigDict(extra="forbid")

    status: EvidenceCloudDashboardStatus
    manifests_total: int = Field(ge=0)
    manifests_present: int = Field(ge=0)
    repositories_total: int = Field(ge=0)
    repositories_ready: int = Field(ge=0)
    repositories_attention: int = Field(ge=0)
    export_items_total: int = Field(ge=0)
    export_items_ready: int = Field(ge=0)
    export_items_blocked: int = Field(ge=0)
    boundary_controls_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidenceCloudDashboardRepository(BaseModel):
    """One repository card for the static Evidence Cloud dashboard."""

    model_config = ConfigDict(extra="forbid")

    id: str
    manifest_id: str
    project: str
    status: EvidenceCloudWorkspaceRepositoryStatus
    dashboard_state: EvidenceCloudDashboardRepositoryState
    sources_present: int = Field(ge=0)
    sources_total: int = Field(ge=0)
    export_items_ready: int = Field(ge=0)
    export_items_total: int = Field(ge=0)
    export_items_blocked: int = Field(ge=0)
    boundary_controls_total: int = Field(ge=0)
    local_reference: str
    summary: str


class EvidenceCloudDashboardPacket(BaseModel):
    """Schema-versioned local static Evidence Cloud dashboard packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-cloud-dashboard.v1"] = (
        EVIDENCE_CLOUD_DASHBOARD_SCHEMA_VERSION
    )
    generated_at: str
    project: str
    workspace_schema_version: Literal["entroping.evidence-cloud-workspace.v1"] = (
        EVIDENCE_CLOUD_WORKSPACE_SCHEMA_VERSION
    )
    summary: EvidenceCloudDashboardSummary
    manifests: tuple[EvidenceCloudWorkspaceManifest, ...]
    repositories: tuple[EvidenceCloudDashboardRepository, ...]
    boundary_controls: tuple[EvidenceCloudWorkspaceBoundaryControl, ...]
    next_actions: tuple[EvidenceCloudWorkspaceNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCloudDashboardResult:
    """Result of writing one Evidence Cloud dashboard report."""

    output_path: Path
    packet: EvidenceCloudDashboardPacket


def run_evidence_cloud_dashboard_report(
    *,
    project_root: Path,
    manifests: tuple[Path, ...],
    output: EvidenceCloudDashboardOutput,
    output_path: Path | None = None,
) -> EvidenceCloudDashboardResult:
    """Write a static local Evidence Cloud workspace dashboard."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-cloud-dashboard output: {output}"
        raise EvidenceCloudDashboardError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_cloud_dashboard_packet(project_root=root, manifests=manifests)
    content = _render_packet_content(packet, output=output)
    if _contains_unredacted_dashboard_secret(content):
        msg = "Evidence Cloud dashboard contains secret-like content"
        raise EvidenceCloudDashboardError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="Evidence Cloud dashboard",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidenceCloudDashboardError(str(exc)) from exc
    return EvidenceCloudDashboardResult(output_path=written, packet=packet)


def build_evidence_cloud_dashboard_packet(
    *,
    project_root: Path,
    manifests: tuple[Path, ...],
) -> EvidenceCloudDashboardPacket:
    """Build a value-free static Evidence Cloud dashboard packet."""

    try:
        workspace = build_evidence_cloud_workspace_packet(
            project_root=project_root,
            manifests=manifests,
        )
    except EvidenceCloudWorkspaceError as exc:
        raise EvidenceCloudDashboardError(str(exc)) from exc
    repositories = tuple(_repository_from_workspace(row) for row in workspace.repositories)
    return EvidenceCloudDashboardPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=workspace.project,
        summary=_summary(workspace=workspace, repositories=repositories),
        manifests=workspace.manifests,
        repositories=repositories,
        boundary_controls=workspace.boundary_controls,
        next_actions=workspace.next_actions,
    )


def render_evidence_cloud_dashboard_html(packet: EvidenceCloudDashboardPacket) -> str:
    """Render a static, value-free Evidence Cloud dashboard."""

    summary_tiles = "\n".join(
        (
            _tile_html(packet.summary.status, "Workspace status"),
            _tile_html(
                f"{packet.summary.manifests_present}/{packet.summary.manifests_total}",
                "Manifests present",
            ),
            _tile_html(
                f"{packet.summary.repositories_ready}/{packet.summary.repositories_total}",
                "Repositories ready",
            ),
            _tile_html(
                f"{packet.summary.export_items_ready}/{packet.summary.export_items_total}",
                "Export items ready",
            ),
        )
    )
    repository_cards = "\n".join(_repository_card_html(row) for row in packet.repositories)
    if not repository_cards:
        repository_cards = "        <p>No valid Evidence Cloud export manifests loaded.</p>"
    manifest_rows = "\n".join(_manifest_row_html(row) for row in packet.manifests)
    boundary_rows = "\n".join(_boundary_row_html(row) for row in packet.boundary_controls)
    if not boundary_rows:
        boundary_rows = (
            "          <tr><td colspan=\"3\">No boundary controls available.</td></tr>"
        )
    action_items = "\n".join(
        f"<li><strong>{_html(action.priority)}</strong> {_html(action.action)}</li>"
        for action in packet.next_actions
    )
    if not action_items:
        action_items = "<li>No Evidence Cloud dashboard actions are currently needed.</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entroping Evidence Cloud Dashboard</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 2rem;
      color: #172026;
      background: #f7f8fa;
    }}
    main {{ max-width: 1160px; margin: 0 auto; }}
    h1, h2, h3 {{ margin: 0 0 0.75rem; }}
    .summary, .repositories {{
      display: grid;
      gap: 0.75rem;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .tile, .repository, table {{
      background: #ffffff;
      border: 1px solid #d8dde3;
      border-radius: 8px;
    }}
    .tile, .repository {{ padding: 1rem; }}
    .metric {{ font-size: 1.85rem; font-weight: 700; line-height: 1.1; }}
    .label {{ color: #53606b; font-size: 0.85rem; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{
      padding: 0.65rem 0.75rem;
      border-bottom: 1px solid #e3e7eb;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #eef2f5; }}
    code {{ background: #eef2f5; padding: 0.1rem 0.25rem; border-radius: 4px; }}
    section {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <main>
    <h1>Entroping Evidence Cloud Dashboard</h1>
    <p>
      Static local workspace dashboard for explicit Evidence Cloud export manifests.
      It summarizes sanitized metadata only and does not upload, sync, or embed
      report artifact payloads.
    </p>
    <section class="summary" aria-label="Workspace summary">
{summary_tiles}
    </section>
    <section>
      <h2>Repository Cards</h2>
      <div class="repositories">
{repository_cards}
      </div>
    </section>
    <section>
      <h2>Manifests</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th><th>State</th><th>Project</th>
            <th>Export Status</th><th>Path</th><th>SHA-256</th><th>Summary</th>
          </tr>
        </thead>
        <tbody>
{manifest_rows}
        </tbody>
      </table>
    </section>
    <section>
      <h2>Boundary Controls</h2>
      <table>
        <thead><tr><th>Control</th><th>Enforced Manifests</th><th>Summary</th></tr></thead>
        <tbody>
{boundary_rows}
        </tbody>
      </table>
    </section>
    <section>
      <h2>Next Actions</h2>
      <ul>{action_items}</ul>
    </section>
  </main>
</body>
</html>
"""


def _repository_from_workspace(
    row: EvidenceCloudWorkspaceRepository,
) -> EvidenceCloudDashboardRepository:
    return EvidenceCloudDashboardRepository(
        id=row.id,
        manifest_id=row.manifest_id,
        project=row.project,
        status=row.status,
        dashboard_state="ready" if row.status == "ready" else "attention",
        sources_present=row.sources_present,
        sources_total=row.sources_total,
        export_items_ready=row.export_items_ready,
        export_items_total=row.export_items_total,
        export_items_blocked=row.export_items_blocked,
        boundary_controls_total=row.boundary_controls_total,
        local_reference=row.local_reference,
        summary=_repository_summary(row),
    )


def _summary(
    *,
    workspace: EvidenceCloudWorkspacePacket,
    repositories: tuple[EvidenceCloudDashboardRepository, ...],
) -> EvidenceCloudDashboardSummary:
    return EvidenceCloudDashboardSummary(
        status=workspace.summary.status,
        manifests_total=workspace.summary.manifests_total,
        manifests_present=workspace.summary.manifests_present,
        repositories_total=workspace.summary.repositories_total,
        repositories_ready=workspace.summary.repositories_ready,
        repositories_attention=sum(
            1 for repository in repositories if repository.dashboard_state == "attention"
        ),
        export_items_total=workspace.summary.export_items_total,
        export_items_ready=workspace.summary.export_items_ready,
        export_items_blocked=workspace.summary.export_items_blocked,
        boundary_controls_total=workspace.summary.boundary_controls_total,
        next_actions_total=workspace.summary.next_actions_total,
    )


def _repository_summary(row: EvidenceCloudWorkspaceRepository) -> str:
    return (
        f"{row.status}; {row.sources_present}/{row.sources_total} sources present; "
        f"{row.export_items_ready}/{row.export_items_total} export items ready"
    )


def _render_packet_content(
    packet: EvidenceCloudDashboardPacket,
    *,
    output: EvidenceCloudDashboardOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_cloud_dashboard_html(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "Evidence Cloud dashboard output path must stay under the project root"
        raise EvidenceCloudDashboardError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "Evidence Cloud dashboard must not be written into .entroping or envs"
        raise EvidenceCloudDashboardError(msg)
    return resolved


def _manifest_row_html(row: EvidenceCloudWorkspaceManifest) -> str:
    return (
        "          <tr>"
        f"<td>{_html(row.id)}</td>"
        f"<td>{_html(row.state)}</td>"
        f"<td>{_html(row.project or 'n/a')}</td>"
        f"<td>{_html(row.export_status or 'n/a')}</td>"
        f"<td><code>{_html(row.path)}</code></td>"
        f"<td><code>{_html(row.sha256 or 'n/a')}</code></td>"
        f"<td>{_html(row.summary)}</td>"
        "</tr>"
    )


def _boundary_row_html(row: EvidenceCloudWorkspaceBoundaryControl) -> str:
    return (
        "          <tr>"
        f"<td>{_html(row.label)}</td>"
        f"<td>{row.enforced_manifests}/{row.total_manifests}</td>"
        f"<td>{_html(row.summary)}</td>"
        "</tr>"
    )


def _repository_card_html(row: EvidenceCloudDashboardRepository) -> str:
    return f"""        <article class="repository">
          <h3>{_html(row.project)}</h3>
          <p class="label">{_html(row.dashboard_state)} &middot; {_html(row.status)}</p>
          <p>Sources: {row.sources_present}/{row.sources_total}</p>
          <p>
            Export items: {row.export_items_ready}/{row.export_items_total} ready,
            {row.export_items_blocked} blocked.
          </p>
          <p>Boundary controls: {row.boundary_controls_total}</p>
          <p>{_html(row.summary)}</p>
          <p><code>{_html(row.local_reference)}</code></p>
        </article>"""


def _tile_html(metric: object, label: str) -> str:
    return (
        '      <div class="tile">'
        f'<div class="metric">{_html(metric)}</div>'
        f'<div class="label">{_html(label)}</div>'
        "</div>"
    )


def _contains_unredacted_dashboard_secret(raw_text: str) -> bool:
    return contains_unredacted_evidence_secret(_SHA256_HEX_RE.sub("[SHA256]", raw_text))


def _html(value: object) -> str:
    return escape(safe_evidence_text(str(value)), quote=True)
