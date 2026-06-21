"""Static local evidence portal dashboard for report artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.core.evidence_common import (
    contains_unredacted_evidence_secret,
    safe_evidence_text,
)
from entroping.core.evidence_index import (
    EvidenceArtifactState,
    LocalEvidenceArtifact,
    build_local_evidence_index,
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text

EVIDENCE_PORTAL_SCHEMA_VERSION: Final = "entroping.evidence-portal.v1"

EvidencePortalOutput = Literal["html", "json"]
EvidencePortalStatus = Literal["ready", "partial", "insufficient"]
EvidencePortalSourceState = EvidenceArtifactState
EvidencePortalCardState = Literal["ready", "blocked"]
EvidencePortalPriority = Literal["high", "medium"]
EvidencePortalSourceId = Literal[
    "evidence-links-json",
    "evidence-index-json",
    "runtime-card-json",
    "handoff-json",
    "evidence-cloud-readiness-json",
    "devex-readiness-json",
    "connector-intent-json",
    "observability-packet-json",
    "test-pyramid-json",
]

_DEFAULT_OUTPUTS: Final[dict[EvidencePortalOutput, Path]] = {
    "html": Path("reports") / "evidence-portal.html",
    "json": Path("reports") / "evidence-portal.json",
}


class EvidencePortalError(ValueError):
    """Raised when the evidence portal cannot be generated safely."""


@dataclass(frozen=True, slots=True)
class _PortalSourceDefinition:
    id: EvidencePortalSourceId
    label: str
    path: Path
    schema_version: str


_PORTAL_SOURCE_DEFINITIONS: Final[tuple[_PortalSourceDefinition, ...]] = (
    _PortalSourceDefinition(
        "evidence-links-json",
        "Evidence Links JSON",
        Path("reports") / "evidence-links.json",
        "entroping.evidence-links.v1",
    ),
    _PortalSourceDefinition(
        "evidence-index-json",
        "Evidence Index JSON",
        Path("reports") / "evidence-index.json",
        "entroping.evidence-index.v1",
    ),
    _PortalSourceDefinition(
        "runtime-card-json",
        "Runtime Card JSON",
        Path("reports") / "runtime-card.json",
        "entroping.runtime-card.v1",
    ),
    _PortalSourceDefinition(
        "handoff-json",
        "Handoff JSON",
        Path("reports") / "handoff.json",
        "entroping.handoff.v1",
    ),
    _PortalSourceDefinition(
        "evidence-cloud-readiness-json",
        "Evidence Cloud Readiness JSON",
        Path("reports") / "evidence-cloud-readiness.json",
        "entroping.evidence-cloud-readiness.v1",
    ),
    _PortalSourceDefinition(
        "devex-readiness-json",
        "Developer Experience Readiness JSON",
        Path("reports") / "devex-readiness.json",
        "entroping.devex-readiness.v1",
    ),
    _PortalSourceDefinition(
        "connector-intent-json",
        "Connector Intent JSON",
        Path("reports") / "connector-intent.json",
        "entroping.connector-intent.v1",
    ),
    _PortalSourceDefinition(
        "observability-packet-json",
        "Observability Packet JSON",
        Path("reports") / "observability-packet.json",
        "entroping.observability-packet.v1",
    ),
    _PortalSourceDefinition(
        "test-pyramid-json",
        "Test Pyramid JSON",
        Path("reports") / "test-pyramid.json",
        "entroping.test-pyramid-report.v1",
    ),
)


class EvidencePortalSummary(BaseModel):
    """Aggregate local evidence portal readiness."""

    model_config = ConfigDict(extra="forbid")

    status: EvidencePortalStatus
    sources_total: int = Field(ge=0)
    sources_present: int = Field(ge=0)
    sources_missing: int = Field(ge=0)
    sources_invalid: int = Field(ge=0)
    sources_unsafe: int = Field(ge=0)
    cards_total: int = Field(ge=0)
    cards_ready: int = Field(ge=0)
    cards_blocked: int = Field(ge=0)
    surfaces_total: int = Field(ge=0)
    next_actions_total: int = Field(ge=0)


class EvidencePortalSource(BaseModel):
    """One sanitized local artifact backing the evidence portal."""

    model_config = ConfigDict(extra="forbid")

    id: EvidencePortalSourceId
    label: str
    path: str
    state: EvidencePortalSourceState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str


class EvidencePortalCard(BaseModel):
    """One value-free dashboard card derived from a sanitized artifact."""

    model_config = ConfigDict(extra="forbid")

    id: EvidencePortalSourceId
    label: str
    source_id: EvidencePortalSourceId
    path: str
    state: EvidencePortalCardState
    schema_version: str | None = None
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str
    ready_targets: int | None = Field(default=None, ge=0)
    blocked_targets: int | None = Field(default=None, ge=0)
    surface_count: int | None = Field(default=None, ge=0)
    next_actions_count: int | None = Field(default=None, ge=0)


class EvidencePortalNextAction(BaseModel):
    """One local repair/generation action for the evidence portal."""

    model_config = ConfigDict(extra="forbid")

    priority: EvidencePortalPriority
    action: str
    source_ids: tuple[EvidencePortalSourceId, ...] = ()
    card_ids: tuple[EvidencePortalSourceId, ...] = ()


class EvidencePortalPacket(BaseModel):
    """Schema-versioned static evidence portal packet."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.evidence-portal.v1"] = EVIDENCE_PORTAL_SCHEMA_VERSION
    generated_at: str
    project: str
    summary: EvidencePortalSummary
    sources: tuple[EvidencePortalSource, ...]
    cards: tuple[EvidencePortalCard, ...]
    next_actions: tuple[EvidencePortalNextAction, ...]


@dataclass(frozen=True, slots=True)
class EvidencePortalResult:
    """Result of writing one evidence portal report."""

    output_path: Path
    packet: EvidencePortalPacket


def run_evidence_portal_report(
    *,
    project_root: Path,
    output: EvidencePortalOutput,
    output_path: Path | None = None,
) -> EvidencePortalResult:
    """Write a static local evidence portal report."""

    if output not in _DEFAULT_OUTPUTS:
        msg = f"Unsupported evidence-portal output: {output}"
        raise EvidencePortalError(msg)
    root = project_root.expanduser().resolve()
    destination = _resolve_output_path(output_path or _DEFAULT_OUTPUTS[output], root=root)
    packet = build_evidence_portal_packet(project_root=root)
    content = _render_packet_content(packet, output=output)
    if contains_unredacted_evidence_secret(content):
        msg = "Evidence portal contains secret-like content"
        raise EvidencePortalError(msg)
    try:
        written = safe_write_text(
            destination,
            content,
            artifact="evidence portal",
            root=root,
        )
    except SafeWriteError as exc:
        raise EvidencePortalError(str(exc)) from exc
    return EvidencePortalResult(output_path=written, packet=packet)


def build_evidence_portal_packet(*, project_root: Path) -> EvidencePortalPacket:
    """Build a value-free local evidence portal packet."""

    root = project_root.expanduser().resolve()
    indexed = {artifact.id: artifact for artifact in build_local_evidence_index(project_root=root)}
    source_rows: list[EvidencePortalSource] = []
    source_documents: dict[EvidencePortalSourceId, dict[str, object]] = {}
    for definition in _PORTAL_SOURCE_DEFINITIONS:
        source, document = _source_from_index(definition, indexed.get(definition.id), root=root)
        source_rows.append(source)
        if document is not None:
            source_documents[definition.id] = document
    sources = tuple(source_rows)
    cards = tuple(
        _card_from_source(source, source_documents.get(source.id))
        for source in sources
    )
    next_actions = _next_actions(sources=sources, cards=cards)
    return EvidencePortalPacket(
        generated_at=datetime.now(UTC).isoformat(),
        project=_project_from_documents(root=root, documents=source_documents.values()),
        summary=_summary(sources=sources, cards=cards, next_actions=next_actions),
        sources=sources,
        cards=cards,
        next_actions=next_actions,
    )


def render_evidence_portal_html(packet: EvidencePortalPacket) -> str:
    """Render a static, value-free evidence portal dashboard."""

    card_rows = "\n".join(_card_html(card) for card in packet.cards)
    source_rows = "\n".join(_source_html(source) for source in packet.sources)
    summary_tiles = "\n".join(
        (
            _tile_html(packet.summary.status, "Portal status"),
            _tile_html(
                f"{packet.summary.sources_present}/{packet.summary.sources_total}",
                "Sources present",
            ),
            _tile_html(
                f"{packet.summary.cards_ready}/{packet.summary.cards_total}",
                "Cards ready",
            ),
            _tile_html(packet.summary.surfaces_total, "Target coverage surfaces"),
        )
    )
    action_items = "\n".join(
        f"<li><strong>{_html(action.priority)}</strong> {_html(action.action)}</li>"
        for action in packet.next_actions
    )
    if not action_items:
        action_items = "<li>No evidence portal actions are currently needed.</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entroping Evidence Portal</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 2rem;
      color: #172026;
      background: #f7f8fa;
    }}
    main {{ max-width: 1120px; margin: 0 auto; }}
    h1, h2 {{ margin: 0 0 0.75rem; }}
    .summary, .cards {{
      display: grid;
      gap: 0.75rem;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .tile, .card, table {{ background: #ffffff; border: 1px solid #d8dde3; border-radius: 8px; }}
    .tile, .card {{ padding: 1rem; }}
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
    <h1>Entroping Evidence Portal</h1>
    <p>
      Static local dashboard for deterministic Entroping evidence. It links
      generated packets without embedding raw artifact payloads.
    </p>
    <section class="summary" aria-label="Portal summary">
{summary_tiles}
    </section>
    <section>
      <h2>Dashboard Cards</h2>
      <div class="cards">
{card_rows}
      </div>
    </section>
    <section>
      <h2>Evidence Sources</h2>
      <table>
        <thead><tr><th>Source</th><th>State</th><th>Path</th><th>Schema</th><th>SHA-256</th><th>Summary</th></tr></thead>
        <tbody>
{source_rows}
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


def _source_from_index(
    definition: _PortalSourceDefinition,
    artifact: LocalEvidenceArtifact | None,
    *,
    root: Path,
) -> tuple[EvidencePortalSource, dict[str, object] | None]:
    if artifact is None:
        return (
            EvidencePortalSource(
                id=definition.id,
                label=definition.label,
                path=definition.path.as_posix(),
                state="missing",
                schema_version=None,
                sha256=None,
                summary="not indexed",
            ),
            None,
        )
    state = artifact.state
    summary = safe_evidence_text(artifact.summary)
    sha256: str | None = None
    document: dict[str, object] | None = None
    if state == "present":
        raw_bytes, load_error = read_local_evidence_json_artifact_bytes(
            root / artifact.path,
            root=root,
        )
        if raw_bytes is None:
            state = _state_from_load_error(load_error)
            summary = safe_evidence_text(load_error)
        else:
            raw_text = raw_bytes.decode("utf-8", errors="replace")
            if contains_unredacted_evidence_secret(raw_text):
                state = "unsafe"
                summary = "secret-like content"
            else:
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                document = _parse_document(raw_text)
                if document is None:
                    state = "invalid"
                    summary = "invalid JSON"
                    sha256 = None
    return (
        EvidencePortalSource(
            id=definition.id,
            label=artifact.label,
            path=artifact.path,
            state=state,
            schema_version=artifact.schema_version,
            sha256=sha256,
            summary=summary,
        ),
        document,
    )


def _card_from_source(
    source: EvidencePortalSource,
    document: dict[str, object] | None,
) -> EvidencePortalCard:
    summary = _document_status_summary(document) if document is not None else source.summary
    document_summary = _object_field(document or {}, "summary")
    return EvidencePortalCard(
        id=source.id,
        label=source.label,
        source_id=source.id,
        path=source.path,
        state="ready" if source.state == "present" else "blocked",
        schema_version=source.schema_version,
        sha256=source.sha256,
        summary=safe_evidence_text(summary),
        ready_targets=_int_field(document_summary, "targets_ready"),
        blocked_targets=_int_field(document_summary, "targets_blocked"),
        surface_count=_int_field(document_summary, "surfaces_total"),
        next_actions_count=_int_field(document_summary, "next_actions_total"),
    )


def _summary(
    *,
    sources: tuple[EvidencePortalSource, ...],
    cards: tuple[EvidencePortalCard, ...],
    next_actions: tuple[EvidencePortalNextAction, ...],
) -> EvidencePortalSummary:
    return EvidencePortalSummary(
        status=_status(sources),
        sources_total=len(sources),
        sources_present=sum(1 for source in sources if source.state == "present"),
        sources_missing=sum(1 for source in sources if source.state == "missing"),
        sources_invalid=sum(1 for source in sources if source.state == "invalid"),
        sources_unsafe=sum(1 for source in sources if source.state == "unsafe"),
        cards_total=len(cards),
        cards_ready=sum(1 for card in cards if card.state == "ready"),
        cards_blocked=sum(1 for card in cards if card.state == "blocked"),
        # Surface count is portal-wide coverage, not a per-card sum.
        surfaces_total=max((card.surface_count or 0 for card in cards), default=0),
        next_actions_total=len(next_actions),
    )


def _status(sources: tuple[EvidencePortalSource, ...]) -> EvidencePortalStatus:
    if all(source.state == "present" for source in sources):
        return "ready"
    if any(source.state in {"invalid", "unsafe"} for source in sources):
        return "insufficient"
    if any(source.state == "present" for source in sources):
        return "partial"
    return "insufficient"


def _next_actions(
    *,
    sources: tuple[EvidencePortalSource, ...],
    cards: tuple[EvidencePortalCard, ...],
) -> tuple[EvidencePortalNextAction, ...]:
    actions: list[EvidencePortalNextAction] = []
    for source in sources:
        if source.state == "present":
            continue
        repair = source.state in {"invalid", "unsafe"}
        actions.append(
            EvidencePortalNextAction(
                priority="high" if repair else "medium",
                action=(
                    f"Repair {source.label} local evidence."
                    if repair
                    else f"Generate {source.label} local evidence."
                ),
                source_ids=(source.id,),
                card_ids=(source.id,),
            )
        )
    blocked = tuple(card.id for card in cards if card.state == "blocked")
    if blocked:
        actions.append(
            EvidencePortalNextAction(
                priority="medium",
                action="Regenerate evidence portal after blocked source artifacts are ready.",
                card_ids=blocked,
            )
        )
    return tuple(actions)


def _project_from_documents(
    *,
    root: Path,
    documents: Iterable[dict[str, object]],
) -> str:
    for document in documents:
        project = document.get("project")
        if isinstance(project, str) and project.strip():
            return safe_evidence_text(project)
    return safe_evidence_text(root.name)


def _parse_document(raw_text: str) -> dict[str, object] | None:
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def _document_status_summary(document: dict[str, object]) -> str:
    summary = _object_field(document, "summary")
    status = summary.get("status")
    if isinstance(status, str) and status.strip():
        return status
    return "present"


def _object_field(document: dict[str, object], field: str) -> dict[str, object]:
    value = document.get(field)
    return value if isinstance(value, dict) else {}


def _int_field(document: dict[str, object], field: str) -> int | None:
    value = document.get(field)
    return value if isinstance(value, int) and value >= 0 else None


def _state_from_load_error(load_error: str) -> EvidenceArtifactState:
    if load_error in {
        "artifact too large",
        "not a file",
        "path outside project",
        "symlinked path component",
        "unreadable",
    }:
        return "unsafe"
    return "invalid"


def _render_packet_content(
    packet: EvidencePortalPacket,
    *,
    output: EvidencePortalOutput,
) -> str:
    if output == "json":
        return json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return render_evidence_portal_html(packet)


def _resolve_output_path(raw_path: Path, *, root: Path) -> Path:
    path = raw_path.expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=False)
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        msg = "Evidence portal output path must stay under the project root"
        raise EvidencePortalError(msg) from exc
    if relative_parts and relative_parts[0] in {".entroping", "envs"}:
        msg = "Evidence portal must not be written into .entroping or envs"
        raise EvidencePortalError(msg)
    return resolved


def _source_html(source: EvidencePortalSource) -> str:
    return (
        "          <tr>"
        f"<td>{_html(source.label)}</td>"
        f"<td>{_html(source.state)}</td>"
        f"<td><code>{_html(source.path)}</code></td>"
        f"<td>{_html(source.schema_version or 'n/a')}</td>"
        f"<td><code>{_html(source.sha256 or 'n/a')}</code></td>"
        f"<td>{_html(source.summary)}</td>"
        "</tr>"
    )


def _card_html(card: EvidencePortalCard) -> str:
    ready_targets = "n/a" if card.ready_targets is None else str(card.ready_targets)
    blocked_targets = "n/a" if card.blocked_targets is None else str(card.blocked_targets)
    surface_count = "n/a" if card.surface_count is None else str(card.surface_count)
    next_actions_count = "n/a" if card.next_actions_count is None else str(card.next_actions_count)
    coverage = (
        f"{ready_targets} ready, {blocked_targets} blocked, "
        f"{surface_count} surfaces, {next_actions_count} next actions."
    )
    return f"""        <article class="card">
          <h3>{_html(card.label)}</h3>
          <p class="label">{_html(card.state)} &middot; <code>{_html(card.path)}</code></p>
          <p>{_html(card.summary)}</p>
          <p>Target coverage: {_html(coverage)}</p>
        </article>"""


def _tile_html(metric: object, label: str) -> str:
    return (
        '      <div class="tile">'
        f'<div class="metric">{_html(metric)}</div>'
        f'<div class="label">{_html(label)}</div>'
        "</div>"
    )


def _html(value: object) -> str:
    return escape(safe_evidence_text(str(value))).replace("`", "&#96;")
