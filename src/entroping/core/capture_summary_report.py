"""Core orchestration for safe captured-traffic summary reports."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.capture_summary import (
    CaptureSummaryReport,
    capture_summary_report_to_dict,
    compile_capture_summary,
    render_capture_summary_markdown,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly

CaptureSummaryOutput = Literal["md", "json"]


class CaptureSummaryError(ValueError):
    """Raised when a capture summary report cannot be generated."""


@dataclass(frozen=True, slots=True)
class CaptureSummaryResult:
    """Result of a successful capture summary report workflow."""

    output_path: Path
    report: CaptureSummaryReport


def run_capture_summary_report(
    *,
    project_root: Path,
    output: CaptureSummaryOutput,
) -> CaptureSummaryResult:
    """Read local traffic state and write a safe capture summary report."""

    root = project_root.expanduser().resolve()
    state_path = root / ".entroping" / "state.db"
    if not state_path.is_file():
        msg = "No traffic state found. Run entroping watch before report capture-summary."
        raise CaptureSummaryError(msg)

    try:
        exchanges = list_project_exchanges_readonly(root)
    except TrafficStoreError as exc:
        raise CaptureSummaryError(str(exc)) from exc

    report = compile_capture_summary(exchanges)
    content = _render_report(report, output)
    output_path = root / "reports" / f"capture-summary.{output}"
    _write_text_atomically(output_path, content, root=root)
    return CaptureSummaryResult(output_path=output_path, report=report)


def _render_report(report: CaptureSummaryReport, output: CaptureSummaryOutput) -> str:
    if output == "json":
        return json.dumps(
            capture_summary_report_to_dict(report),
            indent=2,
            sort_keys=True,
        ) + "\n"
    return render_capture_summary_markdown(report)


def _write_text_atomically(path: Path, content: str, *, root: Path) -> None:
    try:
        safe_write_text(path, content, artifact="capture summary report", root=root)
    except SafeWriteError as exc:
        raise CaptureSummaryError(str(exc)) from exc
