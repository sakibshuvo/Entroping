"""Core workflow for effective QAnstitution policy reports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from entroping.bridge.effective_policy import (
    EffectivePolicyReport,
    compile_effective_policy_report,
    render_effective_policy_markdown,
)
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence
from entroping.core.safe_write import SafeWriteError, safe_write_text

EffectivePolicyOutput = Literal["md", "json"]


class EffectivePolicyReportError(ValueError):
    """Raised when an effective policy report cannot be generated."""


@dataclass(frozen=True, slots=True)
class EffectivePolicyReportResult:
    """Result of a successful effective policy report workflow."""

    output_path: Path
    report: EffectivePolicyReport


def run_effective_policy_report(
    *,
    project_root: Path,
    output: str,
) -> EffectivePolicyReportResult:
    """Load local QAnstitution evidence and write a report artifact."""

    root = project_root.expanduser().resolve()
    normalized_output = _normalize_output(output)
    try:
        evidence = load_qanstitution_evidence(root / "qanstitution.yaml")
        report = compile_effective_policy_report(evidence, root=root)
    except QanstitutionLoadError as exc:
        raise EffectivePolicyReportError(str(exc)) from exc

    content = _render_report(report, normalized_output)
    output_path = root / "reports" / f"effective-policy.{normalized_output}"
    try:
        safe_write_text(output_path, content, artifact="effective policy report", root=root)
    except SafeWriteError as exc:
        raise EffectivePolicyReportError(str(exc)) from exc
    return EffectivePolicyReportResult(output_path=output_path, report=report)


def _normalize_output(output: str) -> EffectivePolicyOutput:
    normalized = output.strip().lower()
    if normalized not in {"md", "json"}:
        msg = f"Unsupported effective policy output: {output}"
        raise EffectivePolicyReportError(msg)
    return cast(EffectivePolicyOutput, normalized)


def _render_report(report: EffectivePolicyReport, output: EffectivePolicyOutput) -> str:
    if output == "md":
        return render_effective_policy_markdown(report)
    return report.model_dump_json(indent=2) + "\n"
