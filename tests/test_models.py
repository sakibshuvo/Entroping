"""Domain model tests."""

from entroping.models import GateRule, Qanstitution


def test_qanstitution_accepts_minimal_project() -> None:
    law = Qanstitution(project="checkout-api")

    assert law.project == "checkout-api"
    assert law.gates == []
    assert law.settings.timeout == 30_000


def test_gate_rule_enforcement_values() -> None:
    gate = GateRule(
        id="global_latency",
        condition="true",
        gate="duration < 2000",
        enforcement="block",
    )

    assert gate.enforcement == "block"

