"""Core orchestration for dependency map exports."""

import shutil
import subprocess  # nosec B404
import tempfile
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


def run_dependency_map(
    *,
    project_root: Path,
    export_format: str | None,
) -> DependencyMapResult:
    """Read redacted traffic state and render a dependency map export."""

    normalized_export = _normalize_export_format(export_format)
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

    if normalized_export == "png":
        output_path = root / "reports" / "dependency-map.png"
        _render_png_export(graph, output_path=output_path, root=root)
        return DependencyMapResult(
            export_format=normalized_export,
            content="",
            route_count=len(graph.routes),
            output_path=output_path,
        )

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
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_path(path, root=root)
    temporary_path = _write_temporary_file(path, content)
    try:
        if path.is_symlink():
            msg = f"Refusing to overwrite symlinked dependency map: {path}"
            raise DependencyMapError(msg)
        temporary_path.replace(path)
    except OSError as exc:
        msg = f"Could not write dependency map {path}: {exc}"
        raise DependencyMapError(msg) from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _write_temporary_file(path: Path, content: bytes) -> Path:
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            return Path(temporary_file.name)
    except OSError as exc:
        msg = f"Could not create temporary dependency map next to {path}: {exc}"
        raise DependencyMapError(msg) from exc


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to write symlinked dependency map: {current}"
            raise DependencyMapError(msg)
