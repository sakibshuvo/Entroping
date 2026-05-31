"""Read-only local Studio status collection and text rendering."""

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from entroping.bridge.redaction_review import RedactionReviewReport, compile_redaction_review
from entroping.bridge.traffic_sessions import (
    TrafficRecordRole,
    TrafficSessionCandidate,
    TrafficSessionError,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_graph import (
    TrafficDependencyRoute,
    TrafficGraphCompilationError,
    compile_traffic_dependency_graph,
)
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.report_writer import load_run_report
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly
from entroping.models.qanstitution import GateRule
from entroping.models.traffic import TrafficExchange

_KNOWN_REPORT_PATHS = (
    Path("reports") / "run-latest.json",
    Path("reports") / "junit.xml",
    Path("reports") / "run-latest.html",
    Path("reports") / "drift.json",
    Path("reports") / "bug.md",
)
_TRAFFIC_BROWSER_LIMIT = 1_000


class StudioDependencyError(RuntimeError):
    """Raised when optional Studio dependencies are unavailable."""


@dataclass(frozen=True)
class LatestRunTestStatus:
    """Small read-only latest-run test row for Studio."""

    path: str
    status: str
    exit_code: int
    duration_ms: int
    rule_ids: tuple[str, ...]
    stderr: str


@dataclass(frozen=True)
class LatestRunStatus:
    """Small read-only latest-run summary for Studio."""

    generated_at: str
    passed: int
    failed: int
    total: int
    exit_code: int
    tests: tuple[LatestRunTestStatus, ...]


@dataclass(frozen=True)
class StudioAppliedGateStatus:
    """Read-only link between a latest-run test and an applied QAnstitution gate."""

    rule_id: str
    test_path: str
    test_status: str
    enforcement: str
    condition: str
    assertion: str


@dataclass(frozen=True)
class StudioTrafficRouteStatus:
    """Read-only route summary compiled from redacted traffic state."""

    role: TrafficRecordRole
    destination_host: str
    method: str
    path_template: str
    call_count: int
    failure_count: int
    latency_average_ms: int | None


@dataclass(frozen=True)
class StudioTrafficRedactionStatus:
    """Safe redaction category count for the Studio traffic browser."""

    category: str
    count: int


@dataclass(frozen=True)
class StudioStatus:
    """Read-only local state snapshot for Studio."""

    environment: str
    project: str
    qanstitution_status: str
    latest_run: LatestRunStatus | None
    latest_run_status: str
    report_paths: tuple[str, ...]
    traffic_state_available: bool
    applied_gates: tuple[StudioAppliedGateStatus, ...] = ()
    traffic_state_status: str = "missing"
    traffic_record_count: int = 0
    traffic_redacted_count: int = 0
    traffic_routes: tuple[StudioTrafficRouteStatus, ...] = ()
    traffic_redactions: tuple[StudioTrafficRedactionStatus, ...] = ()


def ensure_studio_available() -> None:
    """Fail with actionable setup guidance when the optional Studio extra is missing."""

    if importlib.util.find_spec("textual") is None:
        msg = (
            "Studio requires the optional Textual dependency. "
            "Install Studio dependencies with: uv sync --extra studio"
        )
        raise StudioDependencyError(msg)


def collect_studio_status(*, project_root: Path, environment: str | None) -> StudioStatus:
    """Collect a read-only snapshot of local Entroping state."""

    root = project_root.expanduser().resolve()
    project, qanstitution_status, gates_by_id = _load_project_status(root)
    latest_run, latest_run_status = _load_latest_run_status(root)
    (
        traffic_state_available,
        traffic_state_status,
        traffic_record_count,
        traffic_redacted_count,
        traffic_routes,
        traffic_redactions,
    ) = _load_traffic_browser_status(root)
    return StudioStatus(
        environment=environment or "default",
        project=project,
        qanstitution_status=qanstitution_status,
        latest_run=latest_run,
        latest_run_status=latest_run_status,
        report_paths=_existing_report_paths(root),
        traffic_state_available=traffic_state_available,
        applied_gates=_applied_gate_statuses(latest_run, gates_by_id),
        traffic_state_status=traffic_state_status,
        traffic_record_count=traffic_record_count,
        traffic_redacted_count=traffic_redacted_count,
        traffic_routes=traffic_routes,
        traffic_redactions=traffic_redactions,
    )


def render_studio_status(status: StudioStatus) -> str:
    """Render the read-only status snapshot as terminal-friendly text."""

    lines = [
        "Entroping Studio (read-only)",
        f"Environment: {status.environment}",
        f"Project: {status.project}",
        f"QAnstitution: {status.qanstitution_status}",
        _latest_run_line(status),
        f"Applied gates: {len(status.applied_gates)}",
        f"Reports: {_reports_line(status.report_paths)}",
        _traffic_state_line(status),
        f"Traffic routes: {len(status.traffic_routes)}",
        f"Traffic redaction categories: {len(status.traffic_redactions)}",
    ]
    return "\n".join(lines) + "\n"


def _load_project_status(root: Path) -> tuple[str, str, dict[str, GateRule]]:
    config_path = root / "qanstitution.yaml"
    if not config_path.exists():
        return "not configured", "missing", {}
    try:
        law = load_qanstitution(config_path)
    except (QanstitutionLoadError, ValueError) as exc:
        return "unavailable", f"error: {exc}", {}
    return law.project, "ok", {gate.id: gate for gate in law.gates}


def _load_latest_run_status(root: Path) -> tuple[LatestRunStatus | None, str]:
    latest_path = root / ".entroping" / "latest-run.json"
    if not latest_path.exists():
        return None, "none"
    try:
        report = load_run_report(latest_path)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return None, f"error: {exc}"
    return (
        LatestRunStatus(
            generated_at=report.generated_at,
            passed=report.summary.passed,
            failed=report.summary.failed,
            total=report.summary.total,
            exit_code=report.summary.exit_code,
            tests=tuple(
                LatestRunTestStatus(
                    path=test.path,
                    status=test.status,
                    exit_code=test.exit_code,
                    duration_ms=test.duration_ms,
                    rule_ids=test.rule_ids,
                    stderr=test.stderr,
                )
                for test in report.tests
            ),
        ),
        "ok",
    )


def _existing_report_paths(root: Path) -> tuple[str, ...]:
    paths = [
        str(path)
        for path in _KNOWN_REPORT_PATHS
        if (root / path).is_file()
    ]
    return tuple(sorted(paths))


def _load_traffic_browser_status(
    root: Path,
) -> tuple[
    bool,
    str,
    int,
    int,
    tuple[StudioTrafficRouteStatus, ...],
    tuple[StudioTrafficRedactionStatus, ...],
]:
    state_path = root / ".entroping" / "state.db"
    if not state_path.is_file():
        return False, "missing", 0, 0, (), ()

    try:
        exchanges = list_project_exchanges_readonly(root, limit=_TRAFFIC_BROWSER_LIMIT)
        redaction_report = compile_redaction_review(exchanges)
        session = _studio_traffic_session(exchanges)
        routes = _studio_traffic_routes(session)
    except (
        TrafficGraphCompilationError,
        TrafficSessionError,
        TrafficStoreError,
        TypeError,
        ValueError,
    ) as exc:
        return True, _traffic_error_status(exc), 0, 0, (), ()

    return (
        True,
        "ok" if exchanges else "empty",
        len(exchanges),
        redaction_report.redacted_records,
        routes,
        _studio_redaction_statuses(redaction_report),
    )


def _studio_traffic_session(exchanges: tuple[TrafficExchange, ...]) -> TrafficSessionCandidate:
    observed_session = build_traffic_session_candidate(
        exchanges,
        name="studio_traffic",
        target_url=None,
    )
    target_url = _first_observed_origin(observed_session)
    if target_url is None:
        return observed_session
    return build_traffic_session_candidate(
        exchanges,
        name=observed_session.name,
        target_url=target_url,
    )


def _first_observed_origin(session: TrafficSessionCandidate) -> str | None:
    for record in session.records:
        parsed = urlsplit(record.exchange.request.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _studio_traffic_routes(
    session: TrafficSessionCandidate,
) -> tuple[StudioTrafficRouteStatus, ...]:
    rows: list[StudioTrafficRouteStatus] = []
    for role in _traffic_role_order():
        records = tuple(record for record in session.records if record.role == role)
        if not records:
            continue
        role_session = TrafficSessionCandidate(
            name=session.name,
            target_origin=session.target_origin,
            records=records,
        )
        graph = compile_traffic_dependency_graph(role_session)
        rows.extend(_studio_route_status(role, route) for route in graph.routes)
    return tuple(rows)


def _studio_route_status(
    role: TrafficRecordRole,
    route: TrafficDependencyRoute,
) -> StudioTrafficRouteStatus:
    return StudioTrafficRouteStatus(
        role=role,
        destination_host=route.destination_host,
        method=route.method,
        path_template=route.path_template,
        call_count=route.call_count,
        failure_count=route.failure_count,
        latency_average_ms=route.latency_average_ms,
    )


def _studio_redaction_statuses(
    report: RedactionReviewReport,
) -> tuple[StudioTrafficRedactionStatus, ...]:
    categories = (
        *report.header_categories,
        *report.body_categories,
        *report.query_categories,
    )
    return tuple(
        StudioTrafficRedactionStatus(category=row.category, count=row.count)
        for row in sorted(categories, key=lambda item: (-item.count, item.category))
    )


def _traffic_role_order() -> tuple[TrafficRecordRole, ...]:
    return ("target", "dependency", "observed")


def _traffic_error_status(exc: Exception) -> str:
    detail = str(exc).splitlines()[0].strip()[:120] or exc.__class__.__name__
    return f"error: {detail}"


def _applied_gate_statuses(
    latest_run: LatestRunStatus | None,
    gates_by_id: dict[str, GateRule],
) -> tuple[StudioAppliedGateStatus, ...]:
    if latest_run is None:
        return ()

    rows: list[StudioAppliedGateStatus] = []
    for test in latest_run.tests:
        for rule_id in sorted(test.rule_ids):
            gate = gates_by_id.get(rule_id)
            rows.append(
                StudioAppliedGateStatus(
                    rule_id=rule_id,
                    test_path=test.path,
                    test_status=test.status,
                    enforcement=gate.enforcement if gate is not None else "unknown",
                    condition=gate.condition if gate is not None else "unknown",
                    assertion=gate.gate if gate is not None else "unknown",
                )
            )
    return tuple(rows)


def _latest_run_line(status: StudioStatus) -> str:
    if status.latest_run is None:
        return f"Latest run: {status.latest_run_status}"
    latest = status.latest_run
    return (
        f"Latest run: {latest.passed} passed, {latest.failed} failed, "
        f"{latest.total} total"
    )


def _traffic_state_line(status: StudioStatus) -> str:
    if not status.traffic_state_available:
        return "Traffic state: missing"
    if status.traffic_state_status == "ok":
        return "Traffic state: available"
    return f"Traffic state: available ({status.traffic_state_status})"


def _reports_line(report_paths: tuple[str, ...]) -> str:
    if not report_paths:
        return "none"
    return ", ".join(report_paths)
