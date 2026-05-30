"""Core orchestration for dependency map exports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_graph import (
    TrafficDependencyGraph,
    TrafficGraphCompilationError,
    compile_traffic_dependency_graph,
    render_dependency_graph_dot,
    render_dependency_graph_markdown,
    render_dependency_graph_mermaid,
)
from entroping.core.traffic_store import TrafficStore, TrafficStoreError

MapExportFormat = Literal["mermaid", "dot", "md", "png"]
_SUPPORTED_EXPORTS: tuple[MapExportFormat, ...] = ("mermaid", "dot", "md", "png")
_PRINTABLE_EXPORTS: tuple[MapExportFormat, ...] = ("mermaid", "dot", "md")


class DependencyMapError(ValueError):
    """Raised when dependency map export cannot be completed."""


@dataclass(frozen=True, slots=True)
class DependencyMapResult:
    """Result of a printable dependency map export."""

    export_format: MapExportFormat
    content: str
    route_count: int


def run_dependency_map(
    *,
    project_root: Path,
    export_format: str | None,
) -> DependencyMapResult:
    """Read redacted traffic state and render a dependency map export."""

    normalized_export = _normalize_export_format(export_format)
    if normalized_export == "png":
        msg = "PNG map export requires a graph renderer. Use --export mermaid, dot, or md."
        raise DependencyMapError(msg)

    root = project_root.expanduser().resolve()
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        msg = "No traffic state found. Run entroping watch before map."
        raise DependencyMapError(msg)

    try:
        store = TrafficStore.open_project(root)
        session = build_traffic_session_candidate(
            store.list_exchanges(),
            name="dependency_map",
            target_url=None,
        )
        graph = compile_traffic_dependency_graph(session)
    except (TrafficGraphCompilationError, TrafficSessionError, TrafficStoreError) as exc:
        raise DependencyMapError(str(exc)) from exc

    return DependencyMapResult(
        export_format=normalized_export,
        content=_render_printable_export(graph, normalized_export),
        route_count=len(graph.routes),
    )


def _normalize_export_format(export_format: str | None) -> MapExportFormat:
    value = (export_format or "mermaid").strip().lower()
    if value not in _SUPPORTED_EXPORTS:
        msg = "Unsupported map export. Use one of: mermaid, dot, md, png."
        raise DependencyMapError(msg)
    return value


def _render_printable_export(graph: TrafficDependencyGraph, export_format: MapExportFormat) -> str:
    if export_format not in _PRINTABLE_EXPORTS:
        msg = "PNG map export requires a graph renderer. Use --export mermaid, dot, or md."
        raise DependencyMapError(msg)
    if export_format == "mermaid":
        return render_dependency_graph_mermaid(graph)
    if export_format == "dot":
        return render_dependency_graph_dot(graph)
    return render_dependency_graph_markdown(graph)
