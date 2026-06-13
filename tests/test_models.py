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


def test_agent_config_accepts_provider_connection_metadata() -> None:
    config = AgentConfig(
        source="agents/builder.md",
        model="openai/qwen3-coder",
        api_base="http://127.0.0.1:8000/v1",
        api_key_env="ENTROPING_OMLX_API_KEY",
        input_cost_per_1m_tokens_usd=0.25,
        output_cost_per_1m_tokens_usd=1.25,
    )

    assert config.api_base == "http://127.0.0.1:8000/v1"
    assert config.api_key_env == "ENTROPING_OMLX_API_KEY"
    assert config.input_cost_per_1m_tokens_usd == 0.25
    assert config.output_cost_per_1m_tokens_usd == 1.25


@pytest.mark.parametrize(
    "api_base",
    [
        "http://localhost:8000/v1",
        "http://localhost.:8000/v1",
        "http://[::1]:8000/v1",
    ],
)
def test_agent_config_accepts_loopback_provider_api_base(api_base: str) -> None:
    config = AgentConfig(
        source="agents/builder.md",
        model="openai/qwen3-coder",
        api_base=api_base,
    )

    assert config.api_base == api_base


def test_agent_config_rejects_negative_cost_metadata() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        AgentConfig(
            source="agents/builder.md",
            model="openai/qwen3-coder",
            input_cost_per_1m_tokens_usd=-0.01,
        )
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        AgentConfig(
            source="agents/builder.md",
            model="openai/qwen3-coder",
            output_cost_per_1m_tokens_usd=-0.01,
        )


@pytest.mark.parametrize(
    ("api_base", "message"),
    [
        ("", "api_base must not be empty"),
        ("ftp://127.0.0.1:8000/v1", "api_base must use http or https"),
        ("http://user:pass@127.0.0.1:8000/v1", "api_base must not contain userinfo"),
        ("http://127.0.0.1:8000/v1?token=secret", "api_base must not contain query"),
        ("http://127.0.0.1:8000/v1#models", "api_base must not contain fragments"),
        ("https://api.evil.example/v1", "api_base must target a local loopback host"),
        ("http://:8000/v1", "api_base must target a local loopback host"),
        ("sk-proj-live-secret", "api_base must not look like a secret"),
        ("http://127.0.0.1:8000/v1\x00", "api_base must not contain control characters"),
    ],
)
def test_agent_config_rejects_unsafe_api_base(api_base: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        AgentConfig(source="agents/builder.md", model="openai/qwen3-coder", api_base=api_base)


@pytest.mark.parametrize(
    ("api_key_env", "message"),
    [
        ("", "api_key_env must not be empty"),
        ("OPENAI-API-KEY", "api_key_env must be an environment variable name"),
        ("sk-proj-live-secret", "api_key_env must not look like a secret"),
        ("OPENAI_API_KEY\x00", "api_key_env must not contain control characters"),
    ],
)
def test_agent_config_rejects_unsafe_api_key_env(api_key_env: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        AgentConfig(
            source="agents/builder.md",
            model="openai/qwen3-coder",
            api_key_env=api_key_env,
        )


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
