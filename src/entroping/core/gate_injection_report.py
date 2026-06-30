"""Core workflow for QAnstitution gate-injection explanation reports."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.gate_injection_explain import (
    GateInjectionReport,
    compile_gate_injection_report,
    render_gate_injection_markdown,
)
from entroping.bridge.policy_to_hurl import GateCompilationError
from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution_evidence
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.hurl_source import read_hurl_source_text
from entroping.models.hurl import (
    HurlMetadataSyntaxError,
    HurlTest,
    parse_hurl_exchanges,
    parse_hurl_metadata,
)

GateInjectionOutput = Literal["md", "json"]


class GateInjectionReportError(ValueError):
    """Raised when a gate-injection explanation cannot be generated."""


@dataclass(frozen=True, slots=True)
class GateInjectionReportResult:
    """Result of a successful gate-injection explanation workflow."""

    output_path: Path
    report: GateInjectionReport


def run_gate_injection_report(
    *,
    project_root: Path,
    targets: Sequence[Path],
    output: GateInjectionOutput,
) -> GateInjectionReportResult:
    """Explain effective QAnstitution gates for selected Hurl files."""

    root = project_root.expanduser().resolve()
    if not targets:
        msg = "At least one --target .hurl file is required"
        raise GateInjectionReportError(msg)

    try:
        evidence = load_qanstitution_evidence(root / "qanstitution.yaml")
        hurl_tests = tuple(_load_hurl_target(target, root=root) for target in targets)
        report = compile_gate_injection_report(evidence, hurl_tests, root=root)
    except (
        GateCompilationError,
        HurlMetadataSyntaxError,
        OSError,
        QanstitutionLoadError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise GateInjectionReportError(str(exc)) from exc

    content = _render_report(report, output)
    output_path = root / "reports" / f"gate-injection.{output}"
    try:
        safe_write_text(output_path, content, artifact="gate injection report", root=root)
    except SafeWriteError as exc:
        raise GateInjectionReportError(str(exc)) from exc
    return GateInjectionReportResult(output_path=output_path, report=report)


def _load_hurl_target(raw_target: Path, *, root: Path) -> HurlTest:
    resolved = _resolve_hurl_target(raw_target, root=root)
    content = read_hurl_source_text(resolved)
    return HurlTest(
        path=resolved,
        metadata=parse_hurl_metadata(content, source=resolved),
        exchanges=parse_hurl_exchanges(content),
    )


def _resolve_hurl_target(raw_target: Path, *, root: Path) -> Path:
    if ".." in raw_target.parts:
        msg = f"Target must stay inside project: {raw_target}"
        raise GateInjectionReportError(msg)

    candidate = raw_target.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        symlink_component = first_symlink_path_component(candidate, root=root)
    except ValueError:
        symlink_component = None
    if symlink_component is not None:
        msg = f"Target must not use symlinks: {symlink_component}"
        raise GateInjectionReportError(msg)

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Target must stay inside project: {raw_target}"
        raise GateInjectionReportError(msg)
    if resolved.suffix != ".hurl":
        msg = f"Expected a .hurl target, got: {resolved}"
        raise GateInjectionReportError(msg)
    if not resolved.is_file():
        msg = f"Hurl target not found: {resolved}"
        raise GateInjectionReportError(msg)
    return resolved


def _render_report(report: GateInjectionReport, output: GateInjectionOutput) -> str:
    if output == "md":
        return render_gate_injection_markdown(report)
    return report.model_dump_json(indent=2) + "\n"
