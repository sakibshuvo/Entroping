"""Domain model tests."""

import pytest
from pydantic import ValidationError

from entroping.models import AgentConfig, GateRule, Qanstitution, parse_condition
from entroping.models.conditions import ContainsCondition, MetaEqualsCondition, TrueCondition


def test_qanstitution_accepts_minimal_project() -> None:
    law = Qanstitution(project="checkout-api")

    assert law.project == "checkout-api"
    assert law.gates == []
    assert law.settings.timeout == 30_000


@pytest.mark.parametrize(
    ("model", "message"),
    [
        ("", "model identifier must not be empty"),
        ("   ", "model identifier must not be empty"),
        ("openai/gpt-4.1\x07", "model identifier must not contain control characters"),
        ("sk-proj-live-secret", "model identifier must not look like a secret"),
        ("ghp_live-secret", "model identifier must not look like a secret"),
        ("xoxb-live-secret", "model identifier must not look like a secret"),
        ("AIza-live-secret", "model identifier must not look like a secret"),
    ],
)
def test_agent_config_rejects_unsafe_model_identifier(model: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        AgentConfig(source="agents/builder.md", model=model)


def test_gate_rule_enforcement_values() -> None:
    gate = GateRule(
        id="global_latency",
        condition="true",
        gate="duration < 2000",
        enforcement="block",
    )

    assert gate.enforcement == "block"


@pytest.mark.parametrize(
    "condition",
    [
        "true",
        "tags contains 'smoke'",
        "method == 'POST'",
        "path startswith '/api/v1'",
        "path contains '/checkout'",
        "url contains 'payments'",
        "meta.story_id == 'CHK-001'",
    ],
)
def test_gate_rule_validates_supported_conditions(condition: str) -> None:
    gate = GateRule(
        id="condition_check",
        condition=condition,
        gate="duration < 2000",
        enforcement="block",
    )

    assert gate.condition == condition


def test_gate_rule_rejects_unsupported_condition() -> None:
    with pytest.raises(ValidationError, match="Unsupported QAnstitution condition syntax"):
        GateRule(
            id="bad_condition",
            condition="tags includes 'smoke'",
            gate="duration < 2000",
            enforcement="block",
        )


def test_parse_condition_returns_typed_condition() -> None:
    assert isinstance(parse_condition("true"), TrueCondition)
    assert parse_condition("tags contains 'smoke'") == ContainsCondition(
        field="tags",
        value="smoke",
    )
    assert parse_condition("meta.story_id == 'CHK-001'") == MetaEqualsCondition(
        key="story_id",
        value="CHK-001",
    )
