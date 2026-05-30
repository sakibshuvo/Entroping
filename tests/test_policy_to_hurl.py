"""Unit tests for QAnstitution gate matching and Hurl assertion compilation."""

from pathlib import Path

import pytest

from entroping.bridge.policy_to_hurl import (
    GateCompilationError,
    compile_gate_assertion,
    compile_matching_gates,
)
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
