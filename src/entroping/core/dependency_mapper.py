"""Core orchestration for dependency map exports."""

import shutil
import subprocess  # nosec B404
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
from entroping.core.safe_write import SafeWriteError, safe_write_bytes
from entroping.core.traffic_artifact_manifest import (
    TrafficArtifactApprovalError,
    TrafficArtifactManifestArtifact,
    write_traffic_artifact_approval_manifest,
)
from entroping.core.traffic_filters import (
    TrafficCaptureFilters,
    TrafficFilterError,
    filter_traffic_exchanges,
)
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly
from entroping.models.traffic import TrafficExchange

MapExportFormat = Literal["mermaid", "dot", "md", "png"]
_SUPPORTED_EXPORTS: tuple[MapExportFormat, ...] = ("mermaid", "dot", "md", "png")
_PRINTABLE_EXPORTS: tuple[MapExportFormat, ...] = ("mermaid", "dot", "md")
_GRAPHVIZ_TIMEOUT_SECONDS = 15


class DependencyMapError(ValueError):
    """Raised when dependency map export cannot be completed."""


@dataclass(frozen=True, slots=True)
class DependencyMapResult:
    """Result of a dependency map export."""

    export_format: MapExportFormat
    content: str
    route_count: int
    output_path: Path | None = None
    manifest_path: Path | None = None


def run_dependency_map(
    *,
    project_root: Path,
    export_format: str | None,
    capture_filters: TrafficCaptureFilters | None = None,
) -> DependencyMapResult:
    """Read redacted traffic state and render a dependency map export."""

    normalized_export = _normalize_export_format(export_format)
    root = project_root.expanduser().resolve()
    state_path = root / ".entroping" / "state.db"
    if not state_path.is_file():
        msg = "No traffic state found. Run entroping watch before map."
        raise DependencyMapError(msg)

    try:
        exchanges = _filtered_exchanges(
            list_project_exchanges_readonly(root),
            capture_filters,
        )
        session = build_traffic_session_candidate(
            exchanges,
            name="dependency_map",
            target_url=None,
        )
        graph = compile_traffic_dependency_graph(session)
    except (
        TrafficFilterError,
        TrafficGraphCompilationError,
        TrafficSessionError,
        TrafficStoreError,
    ) as exc:
        raise DependencyMapError(str(exc)) from exc

    if normalized_export == "png":
        output_path = root / "reports" / "dependency-map.png"
        _render_png_export(graph, output_path=output_path, root=root)
        try:
            manifest = write_traffic_artifact_approval_manifest(
                project_root=root,
                manifest_name="dependency-map-png",
                workflow="dependency-map",
                source_session_name=session.name,
                source_records=tuple(record.exchange for record in session.records),
                artifacts=(
                    TrafficArtifactManifestArtifact(
                        kind="dependency_map",
                        path=output_path,
                    ),
                ),
            )
        except TrafficArtifactApprovalError as exc:
            raise DependencyMapError(str(exc)) from exc
        return DependencyMapResult(
            export_format=normalized_export,
            content="",
            route_count=len(graph.routes),
            output_path=output_path,
            manifest_path=manifest.manifest_path,
        )

    return DependencyMapResult(
        export_format=normalized_export,
        content=_render_printable_export(graph, normalized_export),
        route_count=len(graph.routes),
    )


def _filtered_exchanges(
    exchanges: tuple[TrafficExchange, ...],
    capture_filters: TrafficCaptureFilters | None,
) -> tuple[TrafficExchange, ...]:
    if capture_filters is None or not capture_filters.is_active:
        return exchanges
    filtered = filter_traffic_exchanges(exchanges, capture_filters)
    if not filtered:
        msg = "No traffic records matched capture filters."
        raise TrafficFilterError(msg)
    return filtered


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


def _render_png_export(
    graph: TrafficDependencyGraph,
    *,
    output_path: Path,
    root: Path,
) -> None:
    dot_binary = shutil.which("dot")
    if dot_binary is None:
        msg = (
            "Graphviz dot is required for PNG map export. "
            "Install graphviz or use --export mermaid, dot, or md."
        )
        raise DependencyMapError(msg)

    dot_content = render_dependency_graph_dot(graph)
    try:
        completed = subprocess.run(  # nosec B603
            [dot_binary, "-Tpng"],
            input=dot_content.encode("utf-8"),
            capture_output=True,
            text=False,
            timeout=_GRAPHVIZ_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (
            f"Graphviz dot timed out after {_GRAPHVIZ_TIMEOUT_SECONDS}s while rendering "
            "the PNG dependency map."
        )
        raise DependencyMapError(msg) from exc
    except OSError as exc:
        msg = f"Could not run Graphviz dot for PNG map export: {exc}"
        raise DependencyMapError(msg) from exc

    if completed.returncode != 0:
        msg = (
            f"Graphviz dot failed with exit code {completed.returncode}. "
            "Use --export dot to inspect the source graph."
        )
        raise DependencyMapError(msg)
    if not completed.stdout:
        msg = "Graphviz dot did not produce PNG output."
        raise DependencyMapError(msg)

    _write_binary_atomically(output_path, completed.stdout, root=root)


def _write_binary_atomically(path: Path, content: bytes, *, root: Path) -> None:
    try:
        safe_write_bytes(path, content, artifact="dependency map", root=root)
    except SafeWriteError as exc:
        raise DependencyMapError(str(exc)) from exc
