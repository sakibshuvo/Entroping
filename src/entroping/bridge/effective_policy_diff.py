"""Compile deterministic diffs between effective policy evidence reports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.bridge.effective_policy import EffectivePolicyGateReport, EffectivePolicyReport
from entroping.models.qanstitution import Enforcement

EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION = "entroping.effective-policy-diff.v1"


class EffectivePolicyDiffError(ValueError):
    """Raised when effective policy evidence cannot be compared safely."""


@dataclass(frozen=True, slots=True)
class EffectivePolicyImportDiff:
    """One added or removed import path."""

    path: str


@dataclass(frozen=True, slots=True)
class EffectivePolicyGateSnapshot:
    """Comparable value-safe gate evidence."""

    id: str
    source_path: str
    condition: str
    gate: str
    enforcement: Enforcement
    final: bool
    group: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class EffectivePolicyGateChange:
    """One gate present in both reports with changed fields."""

    id: str
    changed_fields: tuple[str, ...]
    base: EffectivePolicyGateSnapshot
    current: EffectivePolicyGateSnapshot


@dataclass(frozen=True, slots=True)
class EffectivePolicyDiffReport:
    """Schema-versioned comparison between two effective policy reports."""

    base_project: str
    current_project: str
    base_config_path: str
    current_config_path: str
    base_path: str
    current_path: str
    added_imports: tuple[EffectivePolicyImportDiff, ...]
    removed_imports: tuple[EffectivePolicyImportDiff, ...]
    added_gates: tuple[EffectivePolicyGateSnapshot, ...]
    removed_gates: tuple[EffectivePolicyGateSnapshot, ...]
    changed_gates: tuple[EffectivePolicyGateChange, ...]

    @property
    def changed(self) -> bool:
        """Return whether the effective policy evidence differs."""

        return bool(
            self.added_imports
            or self.removed_imports
            or self.added_gates
            or self.removed_gates
            or self.changed_gates
        )


def build_effective_policy_diff_report(
    *,
    base: EffectivePolicyReport,
    current: EffectivePolicyReport,
    base_path: Path,
    current_path: Path,
) -> EffectivePolicyDiffReport:
    """Compare two effective policy reports without loading QAnstitution files."""

    base_gates = _index_gates(base.gates, side="base")
    current_gates = _index_gates(current.gates, side="current")
    base_imports = set(base.imports)
    current_imports = set(current.imports)

    changed_gates: list[EffectivePolicyGateChange] = []
    for gate_id in sorted(set(base_gates) & set(current_gates)):
        base_snapshot = _snapshot(base_gates[gate_id])
        current_snapshot = _snapshot(current_gates[gate_id])
        changed_fields = _changed_gate_fields(base_snapshot, current_snapshot)
        if changed_fields:
            changed_gates.append(
                EffectivePolicyGateChange(
                    id=gate_id,
                    changed_fields=changed_fields,
                    base=base_snapshot,
                    current=current_snapshot,
                )
            )

    return EffectivePolicyDiffReport(
        base_project=base.project,
        current_project=current.project,
        base_config_path=base.config_path,
        current_config_path=current.config_path,
        base_path=base_path.as_posix(),
        current_path=current_path.as_posix(),
        added_imports=tuple(
            EffectivePolicyImportDiff(path=path)
            for path in sorted(current_imports - base_imports)
        ),
        removed_imports=tuple(
            EffectivePolicyImportDiff(path=path)
            for path in sorted(base_imports - current_imports)
        ),
        added_gates=tuple(
            _snapshot(current_gates[gate_id])
            for gate_id in sorted(set(current_gates) - set(base_gates))
        ),
        removed_gates=tuple(
            _snapshot(base_gates[gate_id])
            for gate_id in sorted(set(base_gates) - set(current_gates))
        ),
        changed_gates=tuple(changed_gates),
    )


def effective_policy_diff_report_to_dict(
    report: EffectivePolicyDiffReport,
) -> dict[str, object]:
    """Return the JSON-serializable policy-diff report payload."""

    return {
        "schema_version": EFFECTIVE_POLICY_DIFF_SCHEMA_VERSION,
        "status": "changed" if report.changed else "unchanged",
        "base": {
            "project": report.base_project,
            "config_path": report.base_config_path,
            "path": report.base_path,
        },
        "current": {
            "project": report.current_project,
            "config_path": report.current_config_path,
            "path": report.current_path,
        },
        "summary": {
            "added_imports": len(report.added_imports),
            "removed_imports": len(report.removed_imports),
            "added_gates": len(report.added_gates),
            "removed_gates": len(report.removed_gates),
            "changed_gates": len(report.changed_gates),
        },
        "added_imports": [_import_diff_to_dict(item) for item in report.added_imports],
        "removed_imports": [_import_diff_to_dict(item) for item in report.removed_imports],
        "added_gates": [_gate_snapshot_to_dict(item) for item in report.added_gates],
        "removed_gates": [_gate_snapshot_to_dict(item) for item in report.removed_gates],
        "changed_gates": [_gate_change_to_dict(item) for item in report.changed_gates],
    }


def render_effective_policy_diff_markdown(report: EffectivePolicyDiffReport) -> str:
    """Render a provider-neutral effective-policy diff for PR review."""

    lines = [
        "# Entroping Effective Policy Diff",
        "",
        f"Status: **{'changed' if report.changed else 'unchanged'}**",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Added imports | {len(report.added_imports)} |",
        f"| Removed imports | {len(report.removed_imports)} |",
        f"| Added gates | {len(report.added_gates)} |",
        f"| Removed gates | {len(report.removed_gates)} |",
        f"| Changed gates | {len(report.changed_gates)} |",
        "",
    ]
    if not report.changed:
        lines.extend(("No effective policy differences found.", ""))
        return "\n".join(lines).rstrip() + "\n"

    _append_import_section(lines, "Added Imports", report.added_imports)
    _append_import_section(lines, "Removed Imports", report.removed_imports)
    _append_gate_section(lines, "Added Gates", report.added_gates)
    _append_gate_section(lines, "Removed Gates", report.removed_gates)
    _append_changed_gate_section(lines, report.changed_gates)
    return "\n".join(lines).rstrip() + "\n"


def _index_gates(
    gates: tuple[EffectivePolicyGateReport, ...],
    *,
    side: Literal["base", "current"],
) -> dict[str, EffectivePolicyGateReport]:
    indexed: dict[str, EffectivePolicyGateReport] = {}
    for gate in gates:
        if gate.id in indexed:
            msg = f"{side} effective policy contains duplicate gate id: {gate.id}"
            raise EffectivePolicyDiffError(msg)
        indexed[gate.id] = gate
    return indexed


def _snapshot(gate: EffectivePolicyGateReport) -> EffectivePolicyGateSnapshot:
    return EffectivePolicyGateSnapshot(
        id=gate.id,
        source_path=gate.source_path,
        condition=gate.condition,
        gate=gate.gate,
        enforcement=gate.enforcement,
        final=gate.final,
        group=gate.group,
        description=gate.description,
    )


def _changed_gate_fields(
    base: EffectivePolicyGateSnapshot,
    current: EffectivePolicyGateSnapshot,
) -> tuple[str, ...]:
    fields = (
        "condition",
        "description",
        "enforcement",
        "final",
        "gate",
        "group",
        "source_path",
    )
    return tuple(
        field
        for field in fields
        if getattr(base, field) != getattr(current, field)
    )


def _import_diff_to_dict(item: EffectivePolicyImportDiff) -> dict[str, str]:
    return {"path": item.path}


def _gate_snapshot_to_dict(item: EffectivePolicyGateSnapshot) -> dict[str, object]:
    return {
        "id": item.id,
        "source_path": item.source_path,
        "condition": item.condition,
        "gate": item.gate,
        "enforcement": item.enforcement,
        "final": item.final,
        "group": item.group,
        "description": item.description,
    }


def _gate_change_to_dict(item: EffectivePolicyGateChange) -> dict[str, object]:
    return {
        "id": item.id,
        "changed_fields": list(item.changed_fields),
        "base": _gate_snapshot_to_dict(item.base),
        "current": _gate_snapshot_to_dict(item.current),
    }


def _append_import_section(
    lines: list[str],
    title: str,
    items: tuple[EffectivePolicyImportDiff, ...],
) -> None:
    lines.append(f"## {title}")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.append("")
    lines.extend(f"- `{_markdown_text(item.path)}`" for item in items)
    lines.append("")


def _append_gate_section(
    lines: list[str],
    title: str,
    items: tuple[EffectivePolicyGateSnapshot, ...],
) -> None:
    lines.append(f"## {title}")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.extend(("", "| Gate | Source | Enforcement | Final |", "| --- | --- | --- | --- |"))
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(item.id),
                    _markdown_cell(item.source_path),
                    _markdown_cell(item.enforcement),
                    "yes" if item.final else "no",
                )
            )
            + " |"
        )
    lines.append("")


def _append_changed_gate_section(
    lines: list[str],
    items: tuple[EffectivePolicyGateChange, ...],
) -> None:
    lines.append("## Changed Gates")
    if not items:
        lines.extend(("", "None.", ""))
        return
    lines.extend(("", "| Gate | Changed fields |", "| --- | --- |"))
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(item.id),
                    _markdown_cell(", ".join(item.changed_fields)),
                )
            )
            + " |"
        )
    lines.append("")


def _markdown_cell(value: str) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_text(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")
