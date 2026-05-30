"""QAnstitution gate-to-Hurl assertion compiler boundary."""

from collections.abc import Sequence
from dataclasses import dataclass

from entroping.models.conditions import (
    Condition,
    ConditionSyntaxError,
    ContainsCondition,
    EqualsCondition,
    MetaEqualsCondition,
    StartsWithCondition,
    TrueCondition,
    parse_condition,
)
from entroping.models.hurl import HurlExchange, HurlTest
from entroping.models.qanstitution import Enforcement, GateRule


class GateCompilationError(ValueError):
    """Raised when a QAnstitution gate cannot be compiled safely."""


@dataclass(frozen=True)
class HurlGateAssertion:
    """Compiled Hurl assertion plus Entroping rule metadata."""

    rule_id: str
    assertion: str
    enforcement: Enforcement
    condition: str


def compile_matching_gates(
    gates: Sequence[GateRule],
    hurl_test: HurlTest,
    *,
    exchange: HurlExchange | None = None,
) -> tuple[HurlGateAssertion, ...]:
    """Compile gates whose conditions match a Hurl test or one exchange."""

    compiled: list[HurlGateAssertion] = []
    for gate in gates:
        condition = _parse_gate_condition(gate)
        if _matches_condition(condition, hurl_test, exchange=exchange):
            compiled.append(compile_gate_assertion(gate))
    return tuple(compiled)


def compile_gate_assertion(gate: GateRule) -> HurlGateAssertion:
    """Compile one QAnstitution gate into a Hurl assertion line."""

    rule_id = gate.id.strip()
    if not rule_id or "\n" in rule_id or "\r" in rule_id:
        msg = f"Gate {gate.id!r} has an invalid rule id for Hurl injection"
        raise GateCompilationError(msg)

    assertion = gate.gate.strip()
    if not assertion or "\n" in assertion or "\r" in assertion:
        msg = f"Gate {gate.id!r} has an invalid Hurl assertion"
        raise GateCompilationError(msg)
    if assertion.startswith("#") or (assertion.startswith("[") and assertion.endswith("]")):
        msg = f"Gate {gate.id!r} does not contain an executable Hurl assertion"
        raise GateCompilationError(msg)

    return HurlGateAssertion(
        rule_id=rule_id,
        assertion=assertion,
        enforcement=gate.enforcement,
        condition=gate.condition,
    )


def gate_matches_test(
    gate: GateRule,
    hurl_test: HurlTest,
    *,
    exchange: HurlExchange | None = None,
) -> bool:
    """Return whether a gate applies to a discovered Hurl test."""

    return _matches_condition(_parse_gate_condition(gate), hurl_test, exchange=exchange)


def _parse_gate_condition(gate: GateRule) -> Condition:
    try:
        return parse_condition(gate.condition)
    except ConditionSyntaxError as exc:
        msg = f"Gate {gate.id!r} has invalid condition {gate.condition!r}: {exc}"
        raise GateCompilationError(msg) from exc


def _matches_condition(
    condition: Condition,
    hurl_test: HurlTest,
    *,
    exchange: HurlExchange | None,
) -> bool:
    if isinstance(condition, TrueCondition):
        return True

    if isinstance(condition, ContainsCondition):
        if condition.field == "tags":
            return condition.value in hurl_test.tags
        return any(
            condition.value in _field_value(candidate, condition.field)
            for candidate in _candidate_exchanges(hurl_test, exchange)
        )

    if isinstance(condition, StartsWithCondition):
        return any(
            candidate.path.startswith(condition.value)
            for candidate in _candidate_exchanges(hurl_test, exchange)
        )

    if isinstance(condition, EqualsCondition):
        expected_method = condition.value.upper()
        return any(
            candidate.method.upper() == expected_method
            for candidate in _candidate_exchanges(hurl_test, exchange)
        )

    if isinstance(condition, MetaEqualsCondition):
        return hurl_test.metadata.meta.get(condition.key) == condition.value

    return False


def _candidate_exchanges(
    hurl_test: HurlTest,
    exchange: HurlExchange | None,
) -> tuple[HurlExchange, ...]:
    if exchange is not None:
        return (exchange,)
    return hurl_test.exchanges


def _field_value(exchange: HurlExchange, field: str) -> str:
    if field == "path":
        return exchange.path
    if field == "url":
        return exchange.url
    msg = f"Unsupported Hurl exchange field for gate matching: {field}"
    raise GateCompilationError(msg)
