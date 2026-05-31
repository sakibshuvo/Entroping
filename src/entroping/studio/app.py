"""Interactive read-only Studio TUI adapter."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from entroping.core.hurl_runner import redact_hurl_output
from entroping.studio.status import LatestRunTestStatus, StudioDependencyError, StudioStatus

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
    report_rows: TableRows
    traffic_rows: TableRows


def build_studio_view_model(status: StudioStatus) -> StudioViewModel:
    """Build read-only rows for the Studio tabs."""

    return StudioViewModel(
        summary_rows=_summary_rows(status),
        suite_rows=_suite_rows(status.latest_run.tests if status.latest_run else ()),
        failure_rows=_failure_rows(status.latest_run.tests if status.latest_run else ()),
        report_rows=_report_rows(status.report_paths),
        traffic_rows=(
            ("Traffic state", "available" if status.traffic_state_available else "missing"),
        ),
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


def _report_rows(report_paths: tuple[str, ...]) -> TableRows:
    if not report_paths:
        return (("No report artifacts found",),)
    return tuple((path,) for path in sorted(report_paths))


def _stderr_preview(stderr: str) -> str:
    redacted = redact_hurl_output(stderr)
    for line in redacted.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def _load_textual_types() -> TextualTypes:  # pragma: no cover - optional dependency boundary
    from textual import app as _textual_app
    from textual import widgets as _textual_widgets

    _ = (_textual_app, _textual_widgets)
    return TextualTypes()


def _create_textual_app(model: StudioViewModel) -> _RunnableApp:  # pragma: no cover - terminal UI
    from textual.app import App, ComposeResult
    from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

    class EntropingStudioApp(App[None]):
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

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with TabbedContent():
                with TabPane("Summary", id="summary"):
                    yield Static(_render_table(("Field", "Value"), model.summary_rows))
                with TabPane("Suite", id="suite"):
                    yield Static(
                        _render_table(
                            ("Path", "Status", "Exit", "Duration", "Rules"),
                            model.suite_rows,
                        )
                    )
                with TabPane("Failures", id="failures"):
                    yield Static(_render_table(("Path", "Exit", "Detail"), model.failure_rows))
                with TabPane("Reports", id="reports"):
                    yield Static(_render_table(("Artifact",), model.report_rows))
                with TabPane("Traffic", id="traffic"):
                    yield Static(_render_table(("Signal", "Status"), model.traffic_rows))
            yield Footer()

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
