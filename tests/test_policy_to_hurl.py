"""Unit tests for QAnstitution gate matching and Hurl assertion compilation."""

from pathlib import Path
from typing import cast

import pytest

from entroping.bridge import policy_to_hurl
from entroping.bridge.policy_to_hurl import (
    GateCompilationError,
    compile_gate_assertion,
    compile_matching_gates,
    gate_matches_test,
)
from entroping.models.conditions import Condition, ContainsCondition, ContainsField
from entroping.models.hurl import HurlExchange, HurlMetadata, HurlTest
from entroping.models.qanstitution import Enforcement, GateRule


def _gate(
    gate_id: str,
    condition: str,
    assertion: str,
    enforcement: Enforcement = "block",
) -> GateRule:
    return GateRule(
        id=gate_id,
        condition=condition,
        gate=assertion,
        enforcement=enforcement,
    )


def _checkout_test() -> HurlTest:
    return HurlTest(
        path=Path("tests/checkout.hurl"),
        metadata=HurlMetadata(
            tags=frozenset({"smoke", "checkout"}),
            meta={"story_id": "CHK-001", "owner": "payments"},
        ),
        exchanges=(
            HurlExchange(method="GET", url="{{base_url}}/health", path="/health"),
            HurlExchange(
                method="POST",
                url="{{base_url}}/api/v1/checkout",
                path="/api/v1/checkout",
            ),
        ),
    )


def test_compile_matching_gates_covers_supported_condition_subset() -> None:
    gates = [
        _gate("global_latency", "true", "duration < 2000"),
        _gate("smoke_latency", "tags contains 'smoke'", "duration < 500", "warn"),
        _gate("post_json", "method == 'POST'", 'header "Content-Type" exists'),
        _gate("api_path", "path startswith '/api/v1'", "status < 500"),
        _gate("checkout_path", "path contains '/checkout'", "status < 500"),
        _gate("checkout_url", "url contains 'checkout'", "status < 500"),
        _gate("story_gate", "meta.story_id == 'CHK-001'", "duration < 1000"),
        _gate("billing_tag", "tags contains 'billing'", "duration < 300"),
        _gate("delete_only", "method == 'DELETE'", "status < 500"),
        _gate("admin_path", "path startswith '/admin'", "status < 500"),
    ]

    compiled = compile_matching_gates(gates, _checkout_test())

    assert [(gate.rule_id, gate.assertion, gate.enforcement) for gate in compiled] == [
        ("global_latency", "duration < 2000", "block"),
        ("smoke_latency", "duration < 500", "warn"),
        ("post_json", 'header "Content-Type" exists', "block"),
        ("api_path", "status < 500", "block"),
        ("checkout_path", "status < 500", "block"),
        ("checkout_url", "status < 500", "block"),
        ("story_gate", "duration < 1000", "block"),
    ]


def test_compile_matching_gates_can_target_a_single_exchange() -> None:
    test = _checkout_test()
    gates = [
        _gate("global_latency", "true", "duration < 2000"),
        _gate("post_json", "method == 'POST'", 'header "Content-Type" exists'),
        _gate("health_path", "path contains '/health'", "duration < 50"),
    ]

    compiled = compile_matching_gates(gates, test, exchange=test.exchanges[0])

    assert [gate.rule_id for gate in compiled] == ["global_latency", "health_path"]


def test_gate_matches_test_exposes_matching_without_compilation() -> None:
    assert gate_matches_test(
        _gate("smoke_only", "tags contains 'smoke'", "status < 500"),
        _checkout_test(),
    )
    assert not gate_matches_test(
        _gate("billing_only", "tags contains 'billing'", "status < 500"),
        _checkout_test(),
    )


def test_compile_matching_gates_surfaces_invalid_conditions_with_rule_id() -> None:
    broken_gate = GateRule.model_construct(
        id="bad_condition",
        condition="tags includes 'smoke'",
        gate="duration < 2000",
        enforcement="block",
        description=None,
        final=False,
    )

    with pytest.raises(GateCompilationError, match="bad_condition"):
        compile_matching_gates([broken_gate], _checkout_test())


@pytest.mark.parametrize(
    "gate_id",
    ["", "  ", "\nvalid", "bad\nid", "bad\rid", "bad\x00id", "bad\x1fid", "bad\x7fid"],
)
def test_compile_gate_assertion_rejects_invalid_rule_ids(gate_id: str) -> None:
    gate = GateRule.model_construct(
        id=gate_id,
        condition="true",
        gate="duration < 2000",
        enforcement="block",
        description=None,
        final=False,
    )

    with pytest.raises(GateCompilationError, match="invalid rule id"):
        compile_gate_assertion(gate)


@pytest.mark.parametrize("assertion", ["", "  ", "status == 200\nheader exists", "status\r== 200"])
def test_compile_gate_assertion_rejects_empty_or_multiline_assertions(assertion: str) -> None:
    gate = GateRule.model_construct(
        id="must_check_status",
        condition="true",
        gate=assertion,
        enforcement="block",
        description=None,
        final=False,
    )

    with pytest.raises(GateCompilationError, match="invalid Hurl assertion"):
        compile_gate_assertion(gate)


@pytest.mark.parametrize("assertion", ["# no-op", "[Options]", "[Asserts]"])
def test_compile_gate_assertion_rejects_non_executable_lines(assertion: str) -> None:
    gate = GateRule.model_construct(
        id="must_check_status",
        condition="true",
        gate=assertion,
        enforcement="block",
        description=None,
        final=False,
    )

    with pytest.raises(GateCompilationError, match="executable Hurl assertion"):
        compile_gate_assertion(gate)


def test_compile_matching_gates_rejects_unsupported_contains_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unknown_field_condition(_expression: str) -> Condition:
        return cast(
            Condition,
            ContainsCondition(field=cast(ContainsField, "header"), value="json"),
        )

    monkeypatch.setattr(policy_to_hurl, "parse_condition", unknown_field_condition)

    with pytest.raises(GateCompilationError, match="Unsupported Hurl exchange field"):
        compile_matching_gates([_gate("header_gate", "true", "status < 500")], _checkout_test())


def test_gate_matches_test_fails_closed_for_unknown_future_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def future_condition(_expression: str) -> Condition:
        return cast(Condition, object())

    monkeypatch.setattr(policy_to_hurl, "parse_condition", future_condition)

    with pytest.raises(GateCompilationError, match="future_gate"):
        gate_matches_test(_gate("future_gate", "true", "status < 500"), _checkout_test())


def test_compile_matching_gates_fails_closed_for_unknown_future_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def future_condition(_expression: str) -> Condition:
        return cast(Condition, object())

    monkeypatch.setattr(policy_to_hurl, "parse_condition", future_condition)

    with pytest.raises(GateCompilationError, match="future_gate"):
        compile_matching_gates([_gate("future_gate", "true", "status < 500")], _checkout_test())
