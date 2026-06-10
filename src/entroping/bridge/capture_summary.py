"""Compile safe summaries from redacted captured traffic."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from entroping.bridge.redaction_review import (
    RedactionReviewCategory,
    RedactionReviewReport,
    compile_redaction_review,
)
from entroping.models.traffic import TrafficExchange

CAPTURE_SUMMARY_SCHEMA_VERSION: Final = "entroping.capture-summary.v1"
DEFAULT_SESSION_GAP = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class CaptureSummaryCount:
    """One safe label/count pair."""

    label: str
    count: int


@dataclass(frozen=True, slots=True)
class CaptureSummaryTotals:
    """Top-level capture summary counts."""

    total_records: int
    total_sessions: int
    redacted_records: int
    unredacted_records: int


@dataclass(frozen=True, slots=True)
class CaptureSessionSummary:
    """Safe aggregate for one derived capture session."""

    id: str
    started_at: str
    ended_at: str
    record_count: int
    primary_host: str
    methods: tuple[CaptureSummaryCount, ...]
    hosts: tuple[CaptureSummaryCount, ...]
    dependency_targets: tuple[CaptureSummaryCount, ...]
    status_families: tuple[CaptureSummaryCount, ...]
    redaction_categories: tuple[CaptureSummaryCount, ...]


@dataclass(frozen=True, slots=True)
class CaptureSummaryReport:
    """Safe report derived from local captured traffic state."""

    summary: CaptureSummaryTotals
    sessions: tuple[CaptureSessionSummary, ...]
    methods: tuple[CaptureSummaryCount, ...]
    hosts: tuple[CaptureSummaryCount, ...]
    dependency_targets: tuple[CaptureSummaryCount, ...]
    status_families: tuple[CaptureSummaryCount, ...]
    redaction_categories: tuple[CaptureSummaryCount, ...]


def compile_capture_summary(exchanges: Iterable[TrafficExchange]) -> CaptureSummaryReport:
    """Compile value-free capture summaries from local traffic exchanges."""

    ordered = _ordered_exchanges(tuple(exchanges))
    session_groups = _split_sessions(ordered)
    session_summaries = tuple(
        _session_summary(index=index, exchanges=session)
        for index, session in enumerate(session_groups, start=1)
    )

    dependency_counter: Counter[str] = Counter()
    for session in session_groups:
        primary_host = session[0].request.host
        for exchange in session:
            host = exchange.request.host
            if host != primary_host:
                dependency_counter[host] += 1

    redacted_records = sum(1 for exchange in ordered if exchange.redacted)
    return CaptureSummaryReport(
        summary=CaptureSummaryTotals(
            total_records=len(ordered),
            total_sessions=len(session_summaries),
            redacted_records=redacted_records,
            unredacted_records=len(ordered) - redacted_records,
        ),
        sessions=session_summaries,
        methods=_count_rows(Counter(exchange.request.method for exchange in ordered)),
        hosts=_count_rows(Counter(exchange.request.host for exchange in ordered)),
        dependency_targets=_count_rows(dependency_counter),
        status_families=_count_rows(Counter(_status_family(exchange) for exchange in ordered)),
        redaction_categories=_redaction_count_rows(compile_redaction_review(ordered)),
    )


def capture_summary_report_to_dict(report: CaptureSummaryReport) -> dict[str, object]:
    """Return the JSON-serializable capture summary payload."""

    return {
        "schema_version": CAPTURE_SUMMARY_SCHEMA_VERSION,
        "summary": {
            "total_records": report.summary.total_records,
            "total_sessions": report.summary.total_sessions,
            "redacted_records": report.summary.redacted_records,
            "unredacted_records": report.summary.unredacted_records,
        },
        "sessions": [_session_to_dict(session) for session in report.sessions],
        "methods": [_count_to_dict(item) for item in report.methods],
        "hosts": [_count_to_dict(item) for item in report.hosts],
        "dependency_targets": [_count_to_dict(item) for item in report.dependency_targets],
        "status_families": [_count_to_dict(item) for item in report.status_families],
        "redaction_categories": [
            _count_to_dict(item) for item in report.redaction_categories
        ],
    }


def render_capture_summary_markdown(report: CaptureSummaryReport) -> str:
    """Render a safe Markdown capture summary."""

    lines = [
        "# Entroping Capture Summary",
        "",
        (
            "Counts only; raw URLs, query values, headers, cookies, request bodies, "
            "response bodies, and tokens are not rendered."
        ),
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Total records | {report.summary.total_records} |",
        f"| Sessions | {report.summary.total_sessions} |",
        f"| Redacted records | {report.summary.redacted_records} |",
        f"| Unredacted records | {report.summary.unredacted_records} |",
        "",
    ]

    if report.summary.total_records == 0:
        lines.extend(("No captured traffic records found.", ""))
        return "\n".join(lines).rstrip() + "\n"

    _append_sessions_table(lines, report.sessions)
    _append_count_section(lines, "Methods", report.methods)
    _append_count_section(lines, "Hosts", report.hosts)
    _append_count_section(lines, "Dependency Targets", report.dependency_targets)
    _append_count_section(lines, "Status Families", report.status_families)
    _append_count_section(lines, "Redaction Categories", report.redaction_categories)
    return "\n".join(lines).rstrip() + "\n"


def _ordered_exchanges(exchanges: tuple[TrafficExchange, ...]) -> tuple[TrafficExchange, ...]:
    return tuple(
        exchange
        for _, exchange in sorted(
            enumerate(exchanges),
            key=lambda item: (item[1].captured_at, item[0]),
        )
    )


def _split_sessions(
    exchanges: tuple[TrafficExchange, ...],
) -> tuple[tuple[TrafficExchange, ...], ...]:
    if not exchanges:
        return ()

    sessions: list[tuple[TrafficExchange, ...]] = []
    current: list[TrafficExchange] = [exchanges[0]]
    previous = exchanges[0]
    for exchange in exchanges[1:]:
        if exchange.captured_at - previous.captured_at > DEFAULT_SESSION_GAP:
            sessions.append(tuple(current))
            current = []
        current.append(exchange)
        previous = exchange
    sessions.append(tuple(current))
    return tuple(sessions)


def _session_summary(
    *,
    index: int,
    exchanges: tuple[TrafficExchange, ...],
) -> CaptureSessionSummary:
    primary_host = exchanges[0].request.host
    dependency_counter = Counter(
        exchange.request.host
        for exchange in exchanges
        if exchange.request.host != primary_host
    )
    return CaptureSessionSummary(
        id=f"session-{index:03d}",
        started_at=exchanges[0].captured_at.isoformat(),
        ended_at=exchanges[-1].captured_at.isoformat(),
        record_count=len(exchanges),
        primary_host=primary_host,
        methods=_count_rows(Counter(exchange.request.method for exchange in exchanges)),
        hosts=_count_rows(Counter(exchange.request.host for exchange in exchanges)),
        dependency_targets=_count_rows(dependency_counter),
        status_families=_count_rows(Counter(_status_family(exchange) for exchange in exchanges)),
        redaction_categories=_redaction_count_rows(compile_redaction_review(exchanges)),
    )


def _status_family(exchange: TrafficExchange) -> str:
    if exchange.response is None:
        return "no response"
    return f"{exchange.response.status_code // 100}xx"


def _redaction_count_rows(report: RedactionReviewReport) -> tuple[CaptureSummaryCount, ...]:
    counter: Counter[str] = Counter()
    for row in _redaction_category_rows(report):
        counter[row.category] += row.count
    return _count_rows(counter)


def _redaction_category_rows(
    report: RedactionReviewReport,
) -> tuple[RedactionReviewCategory, ...]:
    return (
        *report.header_categories,
        *report.query_categories,
        *report.body_categories,
    )


def _count_rows(counter: Counter[str]) -> tuple[CaptureSummaryCount, ...]:
    return tuple(
        CaptureSummaryCount(label=label, count=count)
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count > 0
    )


def _session_to_dict(session: CaptureSessionSummary) -> dict[str, object]:
    return {
        "id": session.id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "record_count": session.record_count,
        "primary_host": session.primary_host,
        "methods": [_count_to_dict(item) for item in session.methods],
        "hosts": [_count_to_dict(item) for item in session.hosts],
        "dependency_targets": [_count_to_dict(item) for item in session.dependency_targets],
        "status_families": [_count_to_dict(item) for item in session.status_families],
        "redaction_categories": [
            _count_to_dict(item) for item in session.redaction_categories
        ],
    }


def _count_to_dict(item: CaptureSummaryCount) -> dict[str, object]:
    return {"label": item.label, "count": item.count}


def _append_sessions_table(
    lines: list[str],
    sessions: tuple[CaptureSessionSummary, ...],
) -> None:
    lines.extend(
        (
            "## Sessions",
            "",
            "| Session | Started | Ended | Records | Primary host | Dependencies |",
            "| --- | --- | --- | ---: | --- | --- |",
        )
    )
    for session in sessions:
        dependencies = ", ".join(item.label for item in session.dependency_targets) or "none"
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(session.id),
                    _markdown_cell(session.started_at),
                    _markdown_cell(session.ended_at),
                    str(session.record_count),
                    _markdown_cell(session.primary_host),
                    _markdown_cell(dependencies),
                )
            )
            + " |"
        )
    lines.append("")


def _append_count_section(
    lines: list[str],
    title: str,
    rows: tuple[CaptureSummaryCount, ...],
) -> None:
    lines.extend((f"## {title}", ""))
    if not rows:
        lines.extend(("None.", ""))
        return
    lines.extend(("| Label | Count |", "| --- | ---: |"))
    for row in rows:
        lines.append(f"| {_markdown_cell(row.label)} | {row.count} |")
    lines.append("")


def _markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace("|", "\\|")
