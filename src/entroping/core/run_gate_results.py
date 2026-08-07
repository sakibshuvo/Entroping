"""Pure mapping of one Hurl result to injected gate evidence."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from entroping.bridge.policy_to_hurl import HurlGateAssertion
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_runner import HurlAssertionEvidence, HurlFileResult
from entroping.models.report import GateResultEvidence


def gate_results_for_result(
    execution_copy: HurlExecutionCopy,
    result: HurlFileResult,
) -> tuple[tuple[GateResultEvidence, ...], bool]:
    """Map structured assertion lines to the gates in one execution copy."""

    expected_lines = _expected_lines(execution_copy.injected_gate_lines)
    if result.assertion_evidence is None:
        return _missing_gate_results(execution_copy.injected_gates, result.exit_code), True
    observed_by_line = _observed_by_line(result.assertion_evidence)
    return _gate_results(
        execution_copy.injected_gates,
        expected_lines,
        observed_by_line,
        result.exit_code,
    )


def apply_gate_result(
    execution_copy: HurlExecutionCopy,
    result: HurlFileResult,
) -> tuple[HurlFileResult, tuple[GateResultEvidence, ...]]:
    """Apply nonblocking classification to one result without rerunning Hurl."""

    gate_results, evidence_invalid = gate_results_for_result(execution_copy, result)
    result = _mark_invalid_evidence(result, evidence_invalid)
    result = _mark_block_failure(result, gate_results)
    return result, gate_results


def _expected_lines(
    injected_gate_lines: Sequence[tuple[int, HurlGateAssertion]],
) -> dict[str, list[int]]:
    expected_lines: dict[str, list[int]] = {}
    for line, gate in injected_gate_lines:
        expected_lines.setdefault(gate.rule_id, []).append(line)
    return expected_lines


def _observed_by_line(
    assertions: Sequence[HurlAssertionEvidence],
) -> dict[int, list[bool]]:
    observed: dict[int, list[bool]] = {}
    for assertion in assertions:
        observed.setdefault(assertion.line, []).append(assertion.success)
    return observed


def _missing_gate_results(
    gates: Sequence[HurlGateAssertion],
    exit_code: int,
) -> tuple[GateResultEvidence, ...]:
    return tuple(_error_gate_result(gate, exit_code) for gate in gates)


def _gate_results(
    gates: Sequence[HurlGateAssertion],
    expected_lines: Mapping[str, Sequence[int]],
    observed_by_line: Mapping[int, Sequence[bool]],
    exit_code: int,
) -> tuple[tuple[GateResultEvidence, ...], bool]:
    results: list[GateResultEvidence] = []
    evidence_invalid = False
    for gate in gates:
        passed, invalid = _evaluate_gate(gate, expected_lines, observed_by_line)
        evidence_invalid = evidence_invalid or invalid
        results.append(
            _error_gate_result(gate, exit_code)
            if evidence_invalid
            else _gate_result(gate, passed, exit_code)
        )
    return tuple(results), evidence_invalid


def _evaluate_gate(
    gate: HurlGateAssertion,
    expected_lines: Mapping[str, Sequence[int]],
    observed_by_line: Mapping[int, Sequence[bool]],
) -> tuple[bool, bool]:
    lines = expected_lines.get(gate.rule_id, ())
    if not lines:
        return False, True
    outcomes = tuple(_observed_line(line, observed_by_line) for line in lines)
    return _outcome_result(outcomes)


def _outcome_result(outcomes: Sequence[bool | None]) -> tuple[bool, bool]:
    if any(outcome is None for outcome in outcomes):
        return False, True
    return all(outcome is True for outcome in outcomes), False


def _observed_line(
    line: int,
    observed_by_line: Mapping[int, Sequence[bool]],
) -> bool | None:
    matches = observed_by_line.get(line, ())
    return matches[0] if len(matches) == 1 else None


def _gate_result(
    gate: HurlGateAssertion,
    passed: bool,
    exit_code: int,
) -> GateResultEvidence:
    return GateResultEvidence(
        rule_id=gate.rule_id,
        enforcement=gate.enforcement,
        result="passed" if passed else "failed",
        exit_code=0 if passed else max(1, exit_code),
    )


def _error_gate_result(gate: HurlGateAssertion, exit_code: int) -> GateResultEvidence:
    return GateResultEvidence(
        rule_id=gate.rule_id,
        enforcement=gate.enforcement,
        result="error",
        exit_code=exit_code if exit_code != 0 else 126,
    )


def _mark_invalid_evidence(result: HurlFileResult, invalid: bool) -> HurlFileResult:
    if not invalid or not result.passed:
        return result
    stderr = (
        f"{result.stderr}\nHurl structured assertion evidence invalid"
        if result.stderr
        else "Hurl structured assertion evidence invalid"
    )
    return replace(result, status="error", exit_code=126, stderr=stderr)


def _mark_block_failure(
    result: HurlFileResult,
    gate_results: Sequence[GateResultEvidence],
) -> HurlFileResult:
    if result.passed and _has_block_failure(gate_results):
        return replace(result, status="failed", exit_code=1, attempts=())
    return result


def _has_block_failure(gate_results: Sequence[GateResultEvidence]) -> bool:
    return any(
        gate.enforcement == "block"
        and not (gate.result == "passed" and gate.exit_code == 0)
        for gate in gate_results
    )
