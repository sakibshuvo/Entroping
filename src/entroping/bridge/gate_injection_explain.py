"""Compile deterministic QAnstitution gate-injection explanation reports."""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from entroping.bridge.policy_to_hurl import gate_matches_test
from entroping.models.hurl import HurlTest
from entroping.models.qanstitution import (
    Enforcement,
    KnownFailure,
    KnownFailureValidationError,
    validate_known_failure_expiries,
)
from entroping.models.qanstitution_evidence import EffectiveGateEvidence, QanstitutionEvidence

GATE_INJECTION_REPORT_SCHEMA_VERSION = "entroping.gate-injection-report.v1"
GateInjectionStatus = Literal["would_inject", "known_failure"]


class GateInjectionGateReport(BaseModel):
    """One effective gate's injection status for one Hurl target."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_path: str
    condition: str
    gate: str
    enforcement: Enforcement
    final: bool
    status: GateInjectionStatus
    group: str | None = None
    description: str | None = None
    issue_id: str | None = None
    expires: str | None = None
    reason: str | None = None


class GateInjectionTargetReport(BaseModel):
    """Gate-injection explanation for one selected Hurl target."""

    model_config = ConfigDict(extra="forbid")

    path: str
    tags: tuple[str, ...]
    operation_id: str | None = None
    gates: tuple[GateInjectionGateReport, ...]


class GateInjectionSummary(BaseModel):
    """Aggregate counts for a gate-injection explanation."""

    model_config = ConfigDict(extra="forbid")

    total_targets: int
    total_would_inject: int
    total_known_failures: int


class GateInjectionReport(BaseModel):
    """Machine-readable local gate-injection explanation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.gate-injection-report.v1"] = (
        "entroping.gate-injection-report.v1"
    )
    project: str
    config_path: str
    summary: GateInjectionSummary
    targets: tuple[GateInjectionTargetReport, ...]


def compile_gate_injection_report(
    evidence: QanstitutionEvidence,
    hurl_tests: tuple[HurlTest, ...],
    *,
    root: Path,
    today: date | None = None,
) -> GateInjectionReport:
    """Compile local, value-safe evidence for gates that would be injected."""

    resolved_root = root.expanduser().resolve()
    reference_date = today or date.today()
    targets: list[GateInjectionTargetReport] = []
    would_inject_count = 0
    known_failure_count = 0

    for hurl_test in hurl_tests:
        test_key = _display_path(hurl_test.path, root=resolved_root)
        known_failures = _known_failures_by_rule_id(
            test_key=test_key,
            known_failures=tuple(evidence.policy.ignore_failures),
            reference_date=reference_date,
        )
        gates: list[GateInjectionGateReport] = []
        for gate_evidence in evidence.gates:
            if not gate_matches_test(gate_evidence.rule, hurl_test):
                continue
            known_failure = known_failures.get(gate_evidence.rule.id)
            status: GateInjectionStatus = (
                "known_failure" if known_failure is not None else "would_inject"
            )
            if status == "known_failure":
                known_failure_count += 1
            else:
                would_inject_count += 1
            gates.append(
                _gate_report(
                    gate_evidence,
                    status=status,
                    root=resolved_root,
                    known_failure=known_failure,
                )
            )
        targets.append(
            GateInjectionTargetReport(
                path=test_key,
                tags=tuple(sorted(hurl_test.metadata.tags)),
                operation_id=hurl_test.metadata.operation_id,
                gates=tuple(gates),
            )
        )

    return GateInjectionReport(
        project=evidence.policy.project,
        config_path=_display_path(evidence.root_path, root=resolved_root),
        summary=GateInjectionSummary(
            total_targets=len(targets),
            total_would_inject=would_inject_count,
            total_known_failures=known_failure_count,
        ),
        targets=tuple(targets),
    )


def render_gate_injection_markdown(report: GateInjectionReport) -> str:
    """Render a human-readable gate-injection explanation."""

    lines = [
        "# Entroping Gate Injection Explanation",
        "",
        "Local-only evidence for QAnstitution gates that would be injected into selected "
        + "Hurl files. Hurl is not executed and source files are not modified.",
        "",
        "## Summary",
        "",
        f"- Project: {_escape_markdown_text(report.project)}",
        f"- Config: `{_escape_markdown_text(report.config_path)}`",
        f"- Targets: {report.summary.total_targets}",
        f"- Gates to inject: {report.summary.total_would_inject}",
        f"- Known-failure skips: {report.summary.total_known_failures}",
        "",
    ]
    for target in report.targets:
        lines.extend(
            [
                f"## `{_escape_markdown_text(target.path)}`",
                "",
                f"- Operation ID: {_escape_markdown_text(target.operation_id or '')}",
                f"- Tags: {_escape_markdown_text(', '.join(target.tags) or '')}",
                "",
            ]
        )
        if not target.gates:
            lines.extend(["No matching gates.", ""])
            continue
        lines.extend(
            [
                "| Status | Gate ID | Source | Enforcement | Final | Condition | Assertion | "
                + "Known Failure |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for gate in target.gates:
            known_failure = ""
            if gate.status == "known_failure":
                known_failure = (
                    f"{gate.issue_id or ''} until {gate.expires or ''}: {gate.reason or ''}"
                )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_markdown_cell(gate.status),
                        _escape_markdown_cell(gate.id),
                        _escape_markdown_cell(gate.source_path),
                        _escape_markdown_cell(gate.enforcement),
                        "yes" if gate.final else "no",
                        _escape_markdown_cell(gate.condition),
                        _escape_markdown_cell(gate.gate),
                        _escape_markdown_cell(known_failure),
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _gate_report(
    gate_evidence: EffectiveGateEvidence,
    *,
    status: GateInjectionStatus,
    root: Path,
    known_failure: KnownFailure | None,
) -> GateInjectionGateReport:
    return GateInjectionGateReport(
        id=gate_evidence.rule.id,
        source_path=_display_path(gate_evidence.source_path, root=root),
        condition=gate_evidence.rule.condition,
        gate=gate_evidence.rule.gate,
        enforcement=gate_evidence.rule.enforcement,
        final=gate_evidence.rule.final,
        group=gate_evidence.group,
        description=gate_evidence.rule.description,
        status=status,
        issue_id=known_failure.issue_id if known_failure is not None else None,
        expires=known_failure.expires if known_failure is not None else None,
        reason=known_failure.reason if known_failure is not None else None,
    )


def _known_failures_by_rule_id(
    *,
    test_key: str,
    known_failures: tuple[KnownFailure, ...],
    reference_date: date,
) -> dict[str, KnownFailure]:
    try:
        validate_known_failure_expiries(known_failures, today=reference_date)
    except KnownFailureValidationError as exc:
        raise ValueError(str(exc)) from exc

    matches: dict[str, KnownFailure] = {}
    for known_failure in known_failures:
        if _normalize_test_key(known_failure.test) != test_key:
            continue
        matches.setdefault(known_failure.rule_id, known_failure)
    return matches


def _normalize_test_key(test: str) -> str:
    return test.strip().replace("\\", "/")


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
