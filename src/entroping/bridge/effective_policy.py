"""Compile and render effective QAnstitution policy evidence."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from entroping.models.qanstitution import Enforcement
from entroping.models.qanstitution_evidence import QanstitutionEvidence

EFFECTIVE_POLICY_SCHEMA_VERSION = "entroping.effective-policy-report.v1"


class EffectivePolicyGateReport(BaseModel):
    """One gate in the effective policy report."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_path: str
    condition: str
    gate: str
    enforcement: Enforcement
    final: bool
    group: str | None = None
    description: str | None = None


class EffectivePolicyReport(BaseModel):
    """Machine-readable effective QAnstitution evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.effective-policy-report.v1"] = (
        "entroping.effective-policy-report.v1"
    )
    project: str
    config_path: str
    imports: tuple[str, ...]
    gates: tuple[EffectivePolicyGateReport, ...]


def compile_effective_policy_report(
    evidence: QanstitutionEvidence,
    *,
    root: Path,
) -> EffectivePolicyReport:
    """Compile a value-safe report for loaded local QAnstitution evidence."""

    return _report_from_evidence(evidence, root=root.expanduser().resolve())


def render_effective_policy_markdown(report: EffectivePolicyReport) -> str:
    """Render a human-readable effective policy report."""

    lines = [
        "# Entroping Effective Policy",
        "",
        "Local-only evidence for the resolved QAnstitution gates. Raw traffic, "
        "provider credentials, and model prompts are not included.",
        "",
        "## Summary",
        "",
        f"- Project: {_escape_markdown_text(report.project)}",
        f"- Config: `{_escape_markdown_text(report.config_path)}`",
        f"- Imports: {len(report.imports)}",
        f"- Gates: {len(report.gates)}",
        "",
    ]
    if report.imports:
        lines.extend(["## Imports", ""])
        lines.extend(f"- `{_escape_markdown_text(import_path)}`" for import_path in report.imports)
        lines.append("")

    lines.extend(
        [
            "## Gates",
            "",
            "| ID | Source | Group | Enforcement | Final | Condition | Assertion | Description |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for gate in report.gates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(gate.id),
                    _escape_markdown_cell(gate.source_path),
                    _escape_markdown_cell(gate.group or ""),
                    _escape_markdown_cell(gate.enforcement),
                    "yes" if gate.final else "no",
                    _escape_markdown_cell(gate.condition),
                    _escape_markdown_cell(gate.gate),
                    _escape_markdown_cell(gate.description or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _report_from_evidence(evidence: QanstitutionEvidence, *, root: Path) -> EffectivePolicyReport:
    return EffectivePolicyReport(
        project=evidence.policy.project,
        config_path=_display_path(evidence.root_path, root=root),
        imports=tuple(_display_path(path, root=root) for path in evidence.import_paths),
        gates=tuple(
            EffectivePolicyGateReport(
                id=gate_evidence.rule.id,
                source_path=_display_path(gate_evidence.source_path, root=root),
                condition=gate_evidence.rule.condition,
                gate=gate_evidence.rule.gate,
                enforcement=gate_evidence.rule.enforcement,
                final=gate_evidence.rule.final,
                group=gate_evidence.group,
                description=gate_evidence.rule.description,
            )
            for gate_evidence in evidence.gates
        ),
    )


def _display_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _escape_markdown_cell(value: str) -> str:
    return _escape_markdown_text(value).replace("|", "\\|")


def _escape_markdown_text(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")
