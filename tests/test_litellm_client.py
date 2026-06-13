"""LiteLLM adapter boundary tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import entroping.brain.litellm_client as litellm_client
from entroping.brain.litellm_client import (
    BrainProviderError,
    BrainProviderUnavailableError,
    LiteLLMClient,
    LiteLLMCostEstimate,
)
from entroping.brain.persona_loader import AgentPersona
from entroping.brain.prompt_builder import (
    ArchitectPromptPackage,
    PromptMessage,
    build_architect_prompt_package,
)
from entroping.core.config_loader import load_qanstitution


def _package(tmp_path: Path) -> ArchitectPromptPackage:
    config_path = tmp_path / "qanstitution.yaml"
    config_path.write_text(
        """
project: checkout-api
agents:
  builder:
    source: agents/builder.md
    model: openai/gpt-4.1-mini
    temperature: 0.2
    max_tokens: 1024
gates: []
""".lstrip(),
        encoding="utf-8",
    )
    law = load_qanstitution(config_path)
    persona = AgentPersona(
        role="builder",
        source_path=tmp_path / "agents" / "builder.md",
        content="Build tests.",
        model="openai/gpt-4.1-mini",
        api_base=None,
        api_key_env=None,
        temperature=0.2,
        max_tokens=1024,
    )
    return build_architect_prompt_package(
        law=law,
        persona=persona,
        intent="Generate checkout tests.",
        source_context={},
    )


def test_litellm_client_calls_injected_completion_without_network(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "model": "openai/gpt-4.1-mini",
            "choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
        }

    result = LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))

    assert calls
    assert calls[0]["model"] == "openai/gpt-4.1-mini"
    assert calls[0]["temperature"] == 0.2
    assert calls[0]["max_tokens"] == 1024
    assert "api_base" not in calls[0]
    assert "api_key" not in calls[0]
    assert result.content == '{"summary":"ok","edits":[]}'
    assert result.provider == "openai"
    assert result.usage.total_tokens == 17
    assert result.cost == LiteLLMCostEstimate(
        estimated_usd=None,
        input_cost_per_1m_tokens_usd=None,
        output_cost_per_1m_tokens_usd=None,
    )
    assert result.latency_ms >= 0


def test_litellm_client_estimates_cost_when_rates_and_usage_are_available(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path).model_copy(
        update={
            "input_cost_per_1m_tokens_usd": 0.25,
            "output_cost_per_1m_tokens_usd": 1.25,
        }
    )
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "model": "openai/gpt-4.1-mini",
            "choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}],
            "usage": {
                "prompt_tokens": 2_000,
                "completion_tokens": 4_000,
                "total_tokens": 6_000,
            },
        }

    result = LiteLLMClient(completion_func=fake_completion).complete(package)

    assert "input_cost_per_1m_tokens_usd" not in calls[0]
    assert "output_cost_per_1m_tokens_usd" not in calls[0]
    assert result.provider == "openai"
    assert result.cost == LiteLLMCostEstimate(
        estimated_usd=0.0055,
        input_cost_per_1m_tokens_usd=0.25,
        output_cost_per_1m_tokens_usd=1.25,
    )


def test_litellm_client_degrades_malformed_usage_metadata_to_unknown_cost(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path).model_copy(
        update={
            "input_cost_per_1m_tokens_usd": 0.25,
            "output_cost_per_1m_tokens_usd": 1.25,
        }
    )

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}],
            "usage": {
                "prompt_tokens": "2000",
                "completion_tokens": True,
                "total_tokens": -1,
            },
        }

    result = LiteLLMClient(completion_func=fake_completion).complete(package)

    assert result.provider == "openai"
    assert result.usage.prompt_tokens is None
    assert result.usage.completion_tokens is None
    assert result.usage.total_tokens is None
    assert result.cost == LiteLLMCostEstimate(
        estimated_usd=None,
        input_cost_per_1m_tokens_usd=0.25,
        output_cost_per_1m_tokens_usd=1.25,
    )


def test_litellm_client_reports_unknown_provider_for_unqualified_models(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path).model_copy(update={"model": "gpt-4.1-mini"})

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    result = LiteLLMClient(completion_func=fake_completion).complete(package)

    assert result.provider is None


def test_litellm_client_drops_non_finite_cost_estimates(tmp_path: Path) -> None:
    package = _package(tmp_path).model_copy(
        update={
            "input_cost_per_1m_tokens_usd": float("inf"),
            "output_cost_per_1m_tokens_usd": 1.25,
        }
    )

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {
            "choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    result = LiteLLMClient(completion_func=fake_completion).complete(package)

    assert result.cost.estimated_usd is None


def test_litellm_client_passes_openai_compatible_provider_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path).model_copy(
        update={
            "model": "openai/qwen3-coder",
            "api_base": "http://127.0.0.1:8000/v1",
            "api_key_env": "ENTROPING_OMLX_API_KEY",
        }
    )
    monkeypatch.setenv("ENTROPING_OMLX_API_KEY", "local-provider-key")
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls[0]["model"] == "openai/qwen3-coder"
    assert calls[0]["api_base"] == "http://127.0.0.1:8000/v1"
    assert calls[0]["api_key"] == "local-provider-key"


def test_litellm_client_rejects_disallowed_api_base_before_api_key_lookup(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path).model_copy(
        update={
            "api_base": "https://api.evil.example/v1",
            "api_key_env": "ENTROPING_MISSING_KEY",
        }
    )
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError, match="api_base must target a local loopback host"):
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []


def test_litellm_client_rejects_unsafe_api_key_env_before_lookup(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path).model_copy(update={"api_key_env": "sk-proj-live-secret"})
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError, match="api_key_env must not look like a secret"):
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []


def test_litellm_client_rejects_missing_api_key_env(tmp_path: Path) -> None:
    package = _package(tmp_path).model_copy(update={"api_key_env": "ENTROPING_MISSING_KEY"})

    with pytest.raises(BrainProviderError, match="API key environment variable is not set"):
        LiteLLMClient(completion_func=lambda **_: {}).complete(package)


def test_litellm_client_raises_when_optional_dependency_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str) -> object:
        assert name == "litellm"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "entroping.brain.litellm_client.importlib.import_module",
        fake_import_module,
    )

    with pytest.raises(BrainProviderUnavailableError, match="litellm optional dependency"):
        LiteLLMClient().complete(_package(tmp_path))


def test_litellm_client_sanitizes_provider_errors(tmp_path: Path) -> None:
    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        raise RuntimeError("provider rejected sk-proj-live-secret")

    with pytest.raises(BrainProviderError) as exc_info:
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))

    assert "sk-proj-live-secret" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_litellm_client_sanitizes_cookie_and_api_key_provider_errors(
    tmp_path: Path,
) -> None:
    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        raise RuntimeError(
            "provider rejected Cookie: sessionid=live-session-cookie; "
            "X-API-Key: live-api-key"
        )

    with pytest.raises(BrainProviderError) as exc_info:
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))

    message = str(exc_info.value)
    assert "live-session-cookie" not in message
    assert "live-api-key" not in message
    assert "[REDACTED]" in message


def test_litellm_client_rejects_unsafe_prompt_before_provider_call(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    package = _package(tmp_path).model_copy(
        update={
            "messages": (
                PromptMessage(role="system", content="Build tests."),
                PromptMessage(role="user", content="Authorization: Bearer live-token"),
            )
        }
    )

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError) as exc_info:
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []
    message = str(exc_info.value)
    assert "live-token" not in message
    assert "secret-like values" in message


def test_litellm_client_rejects_control_prompt_before_provider_call(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    package = _package(tmp_path).model_copy(
        update={
            "messages": (
                PromptMessage(role="system", content="Build tests."),
                PromptMessage(role="user", content="bad\x00prompt"),
            )
        }
    )

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError, match="control characters"):
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []


def test_litellm_client_rejects_unsafe_completion_payload_fields(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    package = _package(tmp_path).model_copy(update={"model": "openai/sk-proj-live-key"})

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError, match="secret-like values"):
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []


def test_litellm_client_rejects_control_characters_in_completion_payload_fields(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    package = _package(tmp_path).model_copy(update={"api_base": "http://127.0.0.1:8000/v1\x00"})

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    with pytest.raises(BrainProviderError, match="control characters"):
        LiteLLMClient(completion_func=fake_completion).complete(package)

    assert calls == []


def test_litellm_client_rejects_control_payload_from_boundary_kwargs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    original_package = _package(tmp_path)

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    def fake_kwargs(_: ArchitectPromptPackage) -> dict[str, object]:
        return {
            "model": "openai/gpt\x00",
            "messages": [message.model_dump() for message in original_package.messages],
            "temperature": original_package.temperature,
        }

    monkeypatch.setattr(
        litellm_client,
        "_completion_kwargs",
        fake_kwargs,
    )

    with pytest.raises(BrainProviderError, match="control characters"):
        LiteLLMClient(completion_func=fake_completion).complete(original_package)

    assert calls == []


def test_litellm_client_rejects_unsupported_completion_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"summary":"ok","edits":[]}'}}]}

    original_package = _package(tmp_path)

    def fake_kwargs(_: ArchitectPromptPackage) -> dict[str, object]:
        return {"model": original_package.model, "unexpected": "value"}

    monkeypatch.setattr(
        litellm_client,
        "_completion_kwargs",
        fake_kwargs,
    )

    with pytest.raises(BrainProviderError, match="unsupported completion argument"):
        LiteLLMClient(completion_func=fake_completion).complete(original_package)

    assert calls == []


def test_litellm_client_rejects_empty_response_content(tmp_path: Path) -> None:
    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": ""}}]}

    with pytest.raises(BrainProviderError, match="empty content"):
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))


def test_litellm_client_reraises_boundary_errors_without_wrapping(tmp_path: Path) -> None:
    expected = BrainProviderError("already sanitized")

    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        raise expected

    with pytest.raises(BrainProviderError) as exc_info:
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))

    assert exc_info.value is expected


def test_litellm_client_rejects_litellm_without_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str) -> object:
        assert name == "litellm"
        return SimpleNamespace(not_completion=object())

    monkeypatch.setattr(
        "entroping.brain.litellm_client.importlib.import_module",
        fake_import_module,
    )

    with pytest.raises(BrainProviderUnavailableError, match="does not expose completion"):
        LiteLLMClient().complete(_package(tmp_path))


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        {"choices": "not-a-sequence"},
    ],
)
def test_litellm_client_rejects_responses_without_choices(
    tmp_path: Path,
    response: object,
) -> None:
    def fake_completion(**kwargs: object) -> object:
        _ = kwargs
        return response

    with pytest.raises(BrainProviderError, match="did not include choices"):
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))


def test_litellm_client_rejects_response_without_string_content(tmp_path: Path) -> None:
    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": 123}}]}

    with pytest.raises(BrainProviderError, match="did not include message content"):
        LiteLLMClient(completion_func=fake_completion).complete(_package(tmp_path))


def test_litellm_client_reads_attribute_responses_and_defaults_metadata(tmp_path: Path) -> None:
    package = _package(tmp_path)

    def fake_completion(**kwargs: object) -> object:
        _ = kwargs
        return SimpleNamespace(
            model="",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"summary":"ok","edits":[]}'),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens="12",
                completion_tokens=None,
                total_tokens=17,
            ),
        )

    result = LiteLLMClient(completion_func=fake_completion).complete(package)

    assert result.model == package.model
    assert result.content == '{"summary":"ok","edits":[]}'
    assert result.usage.prompt_tokens is None
    assert result.usage.completion_tokens is None
    assert result.usage.total_tokens == 17


def test_litellm_completion_loader_returns_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_completion(**kwargs: object) -> dict[str, object]:
        _ = kwargs
        return {"choices": [{"message": {"content": "ok"}}]}

    def fake_import_module(name: str) -> object:
        assert name == "litellm"
        return SimpleNamespace(completion=fake_completion)

    monkeypatch.setattr(
        "entroping.brain.litellm_client.importlib.import_module",
        fake_import_module,
    )

    assert litellm_client._load_completion_func() is fake_completion
