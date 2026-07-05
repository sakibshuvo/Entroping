"""Compile deterministic QAnstitution policy gate coverage reports."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from entroping.bridge.policy_to_hurl import gate_matches_test
from entroping.models.hurl import HurlExchange, HurlTest
from entroping.models.qanstitution import Enforcement
from entroping.models.qanstitution_evidence import EffectiveGateEvidence, QanstitutionEvidence

GATE_COVERAGE_REPORT_SCHEMA_VERSION = "entroping.gate-coverage-report.v1"


class GateCoverageExchangeReport(BaseModel):
    """Value-safe request routing evidence for one matched Hurl exchange."""

    model_config = ConfigDict(extra="forbid")

    method: str
    path: str


class GateCoverageTestReport(BaseModel):
    """One Hurl test matched by a policy gate."""

    model_config = ConfigDict(extra="forbid")

    path: str
    tags: tuple[str, ...]
    operation_id: str | None = None
    exchanges: tuple[GateCoverageExchangeReport, ...]


class GateCoverageGateReport(BaseModel):
    """Coverage evidence for one effective QAnstitution gate."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_path: str
    condition: str
    gate: str
    enforcement: Enforcement
    final: bool
    group: str | None = None
    description: str | None = None
    matched: bool
    tests: tuple[GateCoverageTestReport, ...]


class GateCoverageSummary(BaseModel):
    """Aggregate counts for a gate coverage matrix."""

    model_config = ConfigDict(extra="forbid")

    total_gates: int
    matched_gates: int
    unmatched_gates: int
    total_tests: int
    total_test_matches: int


class GateCoverageReport(BaseModel):
    """Machine-readable local gate coverage matrix."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.gate-coverage-report.v1"] = (
        "entroping.gate-coverage-report.v1"
    )
    project: str
    config_path: str
    summary: GateCoverageSummary
    gates: tuple[GateCoverageGateReport, ...]


def compile_gate_coverage_report(
    evidence: QanstitutionEvidence,
    hurl_tests: tuple[HurlTest, ...],
    *,
    root: Path,
) -> GateCoverageReport:
    """Compile a gate-first matrix from effective policy and committed Hurl tests."""

    resolved_root = root.expanduser().resolve()
    gates: list[GateCoverageGateReport] = []
    matched_gate_count = 0
    test_match_count = 0

    for gate_evidence in evidence.gates:
        tests = _matching_tests(gate_evidence, hurl_tests, root=resolved_root)
        if tests:
            matched_gate_count += 1
            test_match_count += len(tests)
        gates.append(
            GateCoverageGateReport(
                id=gate_evidence.rule.id,
                source_path=_display_path(gate_evidence.source_path, root=resolved_root),
                condition=gate_evidence.rule.condition,
                gate=gate_evidence.rule.gate,
                enforcement=gate_evidence.rule.enforcement,
                final=gate_evidence.rule.final,
                group=gate_evidence.group,
                description=gate_evidence.rule.description,
                matched=bool(tests),
                tests=tests,
            )
        )

    return GateCoverageReport(
        project=evidence.policy.project,
        config_path=_display_path(evidence.root_path, root=resolved_root),
        summary=GateCoverageSummary(
            total_gates=len(gates),
            matched_gates=matched_gate_count,
            unmatched_gates=len(gates) - matched_gate_count,
            total_tests=len(hurl_tests),
            total_test_matches=test_match_count,
        ),
        gates=tuple(gates),
    )


def render_gate_coverage_markdown(report: GateCoverageReport) -> str:
    """Render a human-readable policy gate coverage matrix."""

    lines = [
        "# Entroping Policy Gate Coverage Matrix",
        "",
        "Local-only evidence showing which committed Hurl tests match each effective "
        + "QAnstitution gate. This does not execute Hurl, evaluate assertion pass/fail, "
        + "or call model providers.",
        "",
        "Use this beside `entroping report policy` for effective policy provenance and "
        + "`entroping run` reports for runtime pass/fail evidence.",
        "",
        "## Summary",
        "",
        f"- Project: {_escape_markdown_text(report.project)}",
        f"- Config: `{_escape_markdown_text(report.config_path)}`",
        f"- Effective gates: {report.summary.total_gates}",
        f"- Matched gates: {report.summary.matched_gates}",
        f"- Unmatched gates: {report.summary.unmatched_gates}",
        f"- Tests discovered: {report.summary.total_tests}",
        f"- Gate/test matches: {report.summary.total_test_matches}",
        "",
        "## Matrix",
        "",
        "| Gate ID | Source | Enforcement | Final | Condition | Matched Tests |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for gate in report.gates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(gate.id),
                    _escape_markdown_cell(gate.source_path),
                    _escape_markdown_cell(gate.enforcement),
                    "yes" if gate.final else "no",
                    _escape_markdown_cell(gate.condition),
                    str(len(gate.tests)),
                ]
            )
            + " |"
        )
    lines.append("")

    for gate in report.gates:
        lines.extend(
            [
                f"## `{_escape_markdown_text(gate.id)}`",
                "",
                f"- Source: `{_escape_markdown_text(gate.source_path)}`",
                f"- Enforcement: {_escape_markdown_text(gate.enforcement)}",
                f"- Final: {'yes' if gate.final else 'no'}",
                f"- Condition: `{_escape_markdown_text(gate.condition)}`",
                "",
            ]
        )
        if not gate.tests:
            lines.extend(["No matching Hurl tests.", ""])
            continue
        lines.extend(
            [
                "| Hurl Test | Tags | Operation ID | Methods | Paths |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for test in gate.tests:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_markdown_cell(test.path),
                        _escape_markdown_cell(", ".join(test.tags)),
                        _escape_markdown_cell(test.operation_id or ""),
                        _escape_markdown_cell(_methods_text(test.exchanges)),
                        _escape_markdown_cell(_paths_text(test.exchanges)),
                    ]
                )
                + " |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _matching_tests(
    gate_evidence: EffectiveGateEvidence,
    hurl_tests: tuple[HurlTest, ...],
    *,
    root: Path,
) -> tuple[GateCoverageTestReport, ...]:
    matches: list[GateCoverageTestReport] = []
    for hurl_test in hurl_tests:
        if not gate_matches_test(gate_evidence.rule, hurl_test):
            continue
        matches.append(
            GateCoverageTestReport(
                path=_display_path(hurl_test.path, root=root),
                tags=tuple(sorted(hurl_test.metadata.tags)),
                operation_id=hurl_test.metadata.operation_id,
                exchanges=_matching_exchanges(gate_evidence, hurl_test),
            )
        )
    return tuple(matches)


def _matching_exchanges(
    gate_evidence: EffectiveGateEvidence,
    hurl_test: HurlTest,
) -> tuple[GateCoverageExchangeReport, ...]:
    exchange_matches = tuple(
        exchange
        for exchange in hurl_test.exchanges
        if gate_matches_test(gate_evidence.rule, hurl_test, exchange=exchange)
    )
    exchanges = exchange_matches or hurl_test.exchanges
    return tuple(_exchange_report(exchange) for exchange in exchanges)


def _exchange_report(exchange: HurlExchange) -> GateCoverageExchangeReport:
    return GateCoverageExchangeReport(method=exchange.method.upper(), path=exchange.path)


def _display_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _methods_text(exchanges: tuple[GateCoverageExchangeReport, ...]) -> str:
    return ", ".join(dict.fromkeys(exchange.method for exchange in exchanges))


def _paths_text(exchanges: tuple[GateCoverageExchangeReport, ...]) -> str:
    return ", ".join(dict.fromkeys(exchange.path for exchange in exchanges))


def _escape_markdown_cell(value: str) -> str:
    return _escape_markdown_text(value).replace("|", "\\|")


def _escape_markdown_text(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")
