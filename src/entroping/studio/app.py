"""Interactive read-only Studio TUI adapter."""

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from entroping.core.evidence_index import LocalEvidenceArtifact
from entroping.core.hurl_runner import redact_hurl_output
from entroping.studio.status import (
    LatestRunTestStatus,
    StudioAppliedGateStatus,
    StudioDependencyError,
    StudioStatus,
    StudioTrafficRedactionStatus,
    StudioTrafficRouteStatus,
)

TableRows = tuple[tuple[str, ...], ...]


class _RunnableApp(Protocol):
    """Small protocol for the lazily-created Textual app."""

    def run(self) -> object:
        """Run the terminal UI."""


@dataclass(frozen=True)
class TextualTypes:
    """Marker returned after optional Textual imports are available."""

    available: bool = True


@dataclass(frozen=True)
class StudioViewModel:
    """Pure view model rendered by the Textual adapter."""

    summary_rows: TableRows
    suite_rows: TableRows
    failure_rows: TableRows
    gate_rows: TableRows
    report_rows: TableRows
    traffic_rows: TableRows


def build_studio_view_model(status: StudioStatus) -> StudioViewModel:
    """Build read-only rows for the Studio tabs."""

    return StudioViewModel(
        summary_rows=_summary_rows(status),
        suite_rows=_suite_rows(status.latest_run.tests if status.latest_run else ()),
        failure_rows=_failure_rows(status.latest_run.tests if status.latest_run else ()),
        gate_rows=_gate_rows(status.applied_gates),
        report_rows=_report_rows(status.evidence_artifacts, status.report_paths),
        traffic_rows=_traffic_rows(status),
    )


def run_studio_app(status: StudioStatus) -> None:
    """Run the interactive read-only Studio TUI."""

    try:
        _load_textual_types()
    except ModuleNotFoundError as exc:
        msg = (
            "Studio requires the optional Textual dependency. "
            "Install Studio dependencies with: uv sync --extra studio"
        )
        raise StudioDependencyError(msg) from exc

    app = _create_textual_app(build_studio_view_model(status))
    app.run()


def _summary_rows(status: StudioStatus) -> TableRows:
    rows: list[tuple[str, str]] = [
        ("Environment", status.environment),
        ("Project", status.project),
        ("QAnstitution", status.qanstitution_status),
    ]
    if status.latest_run is None:
        rows.append(("Latest run", status.latest_run_status))
        return tuple(rows)

    latest = status.latest_run
    rows.extend(
        [
            ("Latest run", f"{latest.passed} passed, {latest.failed} failed, {latest.total} total"),
            ("Exit code", str(latest.exit_code)),
            ("Generated", latest.generated_at),
        ]
    )
    return tuple(rows)


def _suite_rows(tests: Sequence[LatestRunTestStatus]) -> TableRows:
    if not tests:
        return (("No latest run found", "", "", "", ""),)
    return tuple(
        (
            test.path,
            test.status,
            str(test.exit_code),
            f"{test.duration_ms} ms",
            ", ".join(sorted(test.rule_ids)) or "-",
        )
        for test in tests
    )


def _failure_rows(tests: Sequence[LatestRunTestStatus]) -> TableRows:
    failed = tuple(test for test in tests if test.status != "passed" or test.exit_code != 0)
    if not failed:
        return (("No failed tests", "", ""),)
    return tuple(
        (test.path, f"exit {test.exit_code}", _stderr_preview(test.stderr))
        for test in failed
    )


def _report_rows(
    evidence_artifacts: tuple[LocalEvidenceArtifact, ...],
    report_paths: tuple[str, ...],
) -> TableRows:
    visible_artifacts = tuple(
        artifact for artifact in evidence_artifacts if artifact.state != "missing"
    )
    if visible_artifacts:
        return tuple(
            (
                _safe_cell(artifact.id),
                artifact.state,
                _safe_cell(artifact.path),
                _safe_cell(artifact.schema_version or "-"),
                _safe_cell(artifact.summary),
            )
            for artifact in visible_artifacts
        )
    if report_paths:
        return tuple(
            ("legacy-report", "present", _safe_cell(path), "-", "report path present")
            for path in sorted(report_paths)
        )
    return (("No evidence artifacts found", "", "", "", ""),)


def _gate_rows(applied_gates: Sequence[StudioAppliedGateStatus]) -> TableRows:
    if not applied_gates:
        return (("No applied gates found", "", "", "", "", ""),)
    return tuple(
        (
            gate.rule_id,
            gate.test_path,
            gate.enforcement,
            gate.test_status,
            redact_hurl_output(gate.condition)[:120],
            redact_hurl_output(gate.assertion)[:120],
        )
        for gate in applied_gates
    )


def _traffic_rows(status: StudioStatus) -> TableRows:
    if not status.traffic_state_available:
        return (_traffic_state_row("missing"),)
    if status.traffic_state_status not in {"ok", "empty"}:
        return (_traffic_state_row(status.traffic_state_status),)

    rows: list[tuple[str, ...]] = [
        (
            "summary",
            "traffic records",
            "-",
            "-",
            str(status.traffic_record_count),
            "-",
            "-",
            f"{status.traffic_redacted_count}/{status.traffic_record_count} redacted",
        )
    ]
    rows.extend(_traffic_redaction_row(redaction) for redaction in status.traffic_redactions)
    rows.extend(_traffic_route_row(route) for route in status.traffic_routes)
    return tuple(rows)


def _traffic_state_row(status: str) -> tuple[str, str, str, str, str, str, str, str]:
    return ("state", status, "", "", "", "", "", "")


def _traffic_redaction_row(redaction: StudioTrafficRedactionStatus) -> tuple[str, ...]:
    return (
        "redaction",
        redact_hurl_output(redaction.category)[:120],
        "-",
        "-",
        str(redaction.count),
        "-",
        "-",
        "safe category count",
    )


def _traffic_route_row(route: StudioTrafficRouteStatus) -> tuple[str, ...]:
    return (
        route.role,
        redact_hurl_output(route.destination_host)[:120],
        route.method,
        redact_hurl_output(route.path_template)[:120],
        str(route.call_count),
        str(route.failure_count),
        _latency_display(route.latency_average_ms),
        "redacted",
    )


def _stderr_preview(stderr: str) -> str:
    redacted = redact_hurl_output(stderr)
    for line in redacted.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def _safe_cell(value: str) -> str:
    return redact_hurl_output(value)[:160]


def _latency_display(latency_average_ms: int | None) -> str:
    return "n/a" if latency_average_ms is None else f"{latency_average_ms} ms"


def _load_textual_types() -> TextualTypes:  # pragma: no cover - optional dependency boundary
    importlib.import_module("textual.app")
    importlib.import_module("textual.widgets")
    return TextualTypes()


def _create_textual_app(model: StudioViewModel) -> _RunnableApp:  # pragma: no cover - terminal UI
    textual_app = importlib.import_module("textual.app")
    textual_widgets = importlib.import_module("textual.widgets")
    app_base = textual_app.App
    footer = textual_widgets.Footer
    header = textual_widgets.Header
    static = textual_widgets.Static
    tabbed_content = textual_widgets.TabbedContent
    tab_pane = textual_widgets.TabPane

    class EntropingStudioApp(app_base):  # type: ignore[misc, valid-type]
        """Read-only Textual shell for local Entroping state."""

        TITLE = "Entroping Studio"
        SUB_TITLE = "read-only"
        BINDINGS = [("q", "quit", "Quit")]
        CSS = """
        Screen {
            layout: vertical;
        }
        TabbedContent {
            height: 1fr;
        }
        Static {
            padding: 1 2;
        }
        """

        def compose(self) -> object:
            yield header(show_clock=True)
            with tabbed_content():
                with tab_pane("Summary", id="summary"):
                    yield static(_render_table(("Field", "Value"), model.summary_rows))
                with tab_pane("Suite", id="suite"):
                    yield static(
                        _render_table(
                            ("Path", "Status", "Exit", "Duration", "Rules"),
                            model.suite_rows,
                        )
                    )
                with tab_pane("Failures", id="failures"):
                    yield static(_render_table(("Path", "Exit", "Detail"), model.failure_rows))
                with tab_pane("Gates", id="gates"):
                    yield static(
                        _render_table(
                            ("Rule", "Path", "Enforcement", "Status", "Condition", "Assertion"),
                            model.gate_rows,
                        )
                    )
                with tab_pane("Reports", id="reports"):
                    yield static(
                        _render_table(
                            ("ID", "State", "Path", "Schema", "Summary"),
                            model.report_rows,
                        )
                    )
                with tab_pane("Traffic", id="traffic"):
                    yield static(
                        _render_table(
                            (
                                "Group",
                                "Host/Category",
                                "Method",
                                "Path",
                                "Calls/Count",
                                "Failures",
                                "Avg",
                                "Safety",
                            ),
                            model.traffic_rows,
                        )
                    )
            yield footer()

    return EntropingStudioApp()


def _render_table(headers: tuple[str, ...], rows: TableRows) -> str:
    widths = _column_widths(headers, rows)
    header = _render_row(headers, widths)
    divider = "  ".join("-" * width for width in widths)
    body = [_render_row(row, widths) for row in rows]
    return "\n".join([header, divider, *body])


def _column_widths(headers: tuple[str, ...], rows: TableRows) -> tuple[int, ...]:
    return tuple(
        max(len(headers[index]), *(len(row[index]) for row in rows if index < len(row)))
        for index in range(len(headers))
    )


def _render_row(row: tuple[str, ...], widths: tuple[int, ...]) -> str:
    padded = [
        (row[index] if index < len(row) else "").ljust(width)
        for index, width in enumerate(widths)
    ]
    return "  ".join(padded).rstrip()
