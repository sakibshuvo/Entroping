"""Pure dependency graph compilation from redacted traffic sessions."""

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from entroping.bridge.traffic_sessions import TrafficSessionCandidate

_UUIDISH_RE = re.compile(
    r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_HEXISH_RE = re.compile(r"(?i)^[0-9a-f]{8,}$")
_REDACTED_SEGMENT_PARTS = ("[redacted]", "%5bredacted%5d")


class TrafficGraphCompilationError(ValueError):
    """Raised when redacted traffic cannot be compiled into a graph."""


@dataclass(frozen=True, slots=True)
class TrafficDependencyRoute:
    """One aggregated dependency route in the observed traffic map."""

    destination_host: str
    method: str
    path_template: str
    call_count: int
    failure_count: int
    latency_min_ms: int | None
    latency_average_ms: int | None
    latency_max_ms: int | None


@dataclass(frozen=True, slots=True)
class TrafficDependencyGraph:
    """Host-level dependency graph compiled from redacted traffic."""

    source_label: str
    routes: tuple[TrafficDependencyRoute, ...]


@dataclass(slots=True)
class _RouteAggregate:
    destination_host: str
    method: str
    path_template: str
    call_count: int = 0
    failure_count: int = 0
    latencies_ms: list[int] = field(default_factory=list)


def compile_traffic_dependency_graph(
    session: TrafficSessionCandidate,
    *,
    source_label: str = "client",
) -> TrafficDependencyGraph:
    """Aggregate redacted traffic into host/method/path dependency routes."""

    if not session.records:
        msg = f"traffic map {session.name!r} contains no traffic records"
        raise TrafficGraphCompilationError(msg)

    aggregates: dict[tuple[str, str, str], _RouteAggregate] = {}
    for record in session.records:
        exchange = record.exchange
        if not exchange.redacted:
            msg = "traffic graph compilation requires redacted traffic"
            raise TrafficGraphCompilationError(msg)

        parsed = urlsplit(exchange.request.url)
        destination_host = parsed.netloc.lower()
        path_template = _path_template_candidate(parsed.path)
        method = exchange.request.method.upper()
        key = (destination_host, method, path_template)
        aggregate = aggregates.setdefault(
            key,
            _RouteAggregate(
                destination_host=destination_host,
                method=method,
                path_template=path_template,
            ),
        )
        aggregate.call_count += 1
        if exchange.response is not None and exchange.response.status_code >= 400:
            aggregate.failure_count += 1
        if exchange.duration_ms is not None:
            aggregate.latencies_ms.append(exchange.duration_ms)

    return TrafficDependencyGraph(
        source_label=source_label,
        routes=tuple(_route_from_aggregate(aggregate) for aggregate in aggregates.values()),
    )


def render_dependency_graph_mermaid(graph: TrafficDependencyGraph) -> str:
    """Render a dependency graph as escaped Mermaid flowchart text."""

    lines = ["flowchart LR", f'  source["{_escape_mermaid_label(graph.source_label)}"]']
    for index, route in enumerate(graph.routes, start=1):
        node_id = f"host_{index}"
        host_label = _escape_mermaid_label(route.destination_host)
        edge_label = _escape_mermaid_label(_route_mermaid_label(route))
        lines.append(f'  {node_id}["{host_label}"]')
        lines.append(f"  source -->|{edge_label}| {node_id}")
    return "\n".join(lines) + "\n"


def render_dependency_graph_markdown(graph: TrafficDependencyGraph) -> str:
    """Render a dependency graph as Markdown table plus Mermaid block."""

    lines = [
        "# Entroping Dependency Map",
        "",
        "| Host | Method | Path | Calls | Failures | Min ms | Avg ms | Max ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for route in graph.routes:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(route.destination_host),
                    _escape_markdown_cell(route.method),
                    _escape_markdown_cell(route.path_template),
                    str(route.call_count),
                    str(route.failure_count),
                    _display_optional_int(route.latency_min_ms),
                    _display_optional_int(route.latency_average_ms),
                    _display_optional_int(route.latency_max_ms),
                ]
            )
            + " |"
        )

    lines.extend(["", "```mermaid", render_dependency_graph_mermaid(graph).rstrip(), "```", ""])
    return "\n".join(lines)


def render_dependency_graph_dot(graph: TrafficDependencyGraph) -> str:
    """Render a dependency graph as escaped DOT text."""

    lines = [
        "digraph entroping_dependency_map {",
        "  rankdir=LR;",
        "  node [shape=box];",
        f'  source [label="{_escape_dot_label(graph.source_label)}"];',
    ]
    for index, route in enumerate(graph.routes, start=1):
        node_id = f"host_{index}"
        lines.append(f'  {node_id} [label="{_escape_dot_label(route.destination_host)}"];')
        lines.append(
            f'  source -> {node_id} [label="{_escape_dot_label(_route_dot_label(route))}"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _route_from_aggregate(aggregate: _RouteAggregate) -> TrafficDependencyRoute:
    latencies = aggregate.latencies_ms
    return TrafficDependencyRoute(
        destination_host=aggregate.destination_host,
        method=aggregate.method,
        path_template=aggregate.path_template,
        call_count=aggregate.call_count,
        failure_count=aggregate.failure_count,
        latency_min_ms=min(latencies) if latencies else None,
        latency_average_ms=(sum(latencies) // len(latencies)) if latencies else None,
        latency_max_ms=max(latencies) if latencies else None,
    )


def _path_template_candidate(path: str) -> str:
    if not path:
        return "/"

    templated_segments: list[str] = []
    for segment in path.split("/"):
        if segment == "":
            templated_segments.append(segment)
        elif _is_volatile_path_segment(segment):
            templated_segments.append("{id}")
        else:
            templated_segments.append(segment)
    templated = "/".join(templated_segments)
    return templated if templated.startswith("/") else f"/{templated}"


def _is_volatile_path_segment(segment: str) -> bool:
    normalized = segment.lower()
    if any(part in normalized for part in _REDACTED_SEGMENT_PARTS):
        return True
    return segment.isdigit() or bool(
        _UUIDISH_RE.fullmatch(segment) or _HEXISH_RE.fullmatch(segment)
    )


def _route_mermaid_label(route: TrafficDependencyRoute) -> str:
    latency = (
        "n/a avg"
        if route.latency_average_ms is None
        else f"{route.latency_average_ms}ms avg"
    )
    return (
        f"{route.method} {route.path_template} "
        f"calls={route.call_count} failures={route.failure_count} {latency}"
    )


def _route_dot_label(route: TrafficDependencyRoute) -> str:
    latency = "avg=n/a" if route.latency_average_ms is None else f"avg={route.latency_average_ms}ms"
    return (
        f"{route.method} {route.path_template}\\n"
        f"calls={route.call_count}, failures={route.failure_count}, {latency}"
    )


def _escape_mermaid_label(value: str) -> str:
    return html.escape(_normalize_label(value).replace("|", "/"), quote=True)


def _escape_markdown_cell(value: str) -> str:
    return html.escape(_normalize_label(value), quote=True).replace("|", r"\|")


def _escape_dot_label(value: str) -> str:
    return _normalize_label(value).replace("\\", "\\\\").replace('"', r"\"")


def _normalize_label(value: str) -> str:
    return " ".join(value.split())


def _display_optional_int(value: int | None) -> str:
    return "" if value is None else str(value)
