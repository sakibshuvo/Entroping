"""Core orchestration for captured-traffic redaction review reports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.redaction_review import (
    RedactionReviewReport,
    compile_redaction_review,
    render_redaction_review_html,
    render_redaction_review_markdown,
)
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.traffic_store import TrafficStore, TrafficStoreError

RedactionReviewOutput = Literal["md", "html"]


class RedactionReviewError(ValueError):
    """Raised when a redaction review report cannot be generated."""


@dataclass(frozen=True, slots=True)
class RedactionReviewResult:
    """Result of a successful redaction review report workflow."""

    output_path: Path
    report: RedactionReviewReport


def run_redaction_review(
    *,
    project_root: Path,
    output: RedactionReviewOutput,
) -> RedactionReviewResult:
    """Read local traffic state and write a safe redaction review report."""

    root = project_root.expanduser().resolve()
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        msg = "No traffic state found. Run entroping watch before report redaction."
        raise RedactionReviewError(msg)

    try:
        store = TrafficStore.open_project(root)
        exchanges = store.list_exchanges()
    except TrafficStoreError as exc:
        raise RedactionReviewError(str(exc)) from exc

    if not exchanges:
        msg = "Traffic state contains no traffic records to review."
        raise RedactionReviewError(msg)

    report = compile_redaction_review(exchanges)
    content = _render_report(report, output)
    output_path = root / "reports" / f"redaction-review.{output}"
    _write_text_atomically(output_path, content, root=root)
    return RedactionReviewResult(output_path=output_path, report=report)


def _render_report(report: RedactionReviewReport, output: RedactionReviewOutput) -> str:
    if output == "md":
        return render_redaction_review_markdown(report)
    return render_redaction_review_html(report)


def _write_text_atomically(path: Path, content: str, *, root: Path) -> None:
    try:
        safe_write_text(path, content, artifact="redaction review report", root=root)
    except SafeWriteError as exc:
        raise RedactionReviewError(str(exc)) from exc
