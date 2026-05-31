"""Lazy LiteLLM adapter for Architect model calls."""

import importlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from entroping.brain.prompt_builder import ArchitectPromptPackage
from entroping.brain.safety import redact_secret_like_values

CompletionFunc = Callable[..., object]


class BrainProviderError(RuntimeError):
    """Raised when a model provider call fails safely."""


class BrainProviderUnavailableError(BrainProviderError):
    """Raised when the optional LiteLLM dependency is not installed."""


@dataclass(frozen=True)
class LiteLLMUsage:
    """Token usage returned by a provider when available."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class LiteLLMCompletionResult:
    """Normalized completion result for Brain callers."""

    content: str
    model: str
    latency_ms: int
    usage: LiteLLMUsage


class LiteLLMClient:
    """Thin wrapper around ``litellm.completion`` with test injection."""

    def __init__(self, completion_func: CompletionFunc | None = None) -> None:
        self._completion_func = completion_func

    def complete(self, package: ArchitectPromptPackage) -> LiteLLMCompletionResult:
        """Call LiteLLM with an already validated prompt package."""

        completion_func = self._completion_func or _load_completion_func()
        kwargs = _completion_kwargs(package)
        started = time.monotonic()
        try:
            response = completion_func(**kwargs)
        except BrainProviderError:
            raise
        except Exception as exc:
            message = redact_secret_like_values(str(exc))
            raise BrainProviderError(f"LiteLLM completion failed: {message}") from exc

        latency_ms = max(0, round((time.monotonic() - started) * 1000))
        content = _extract_content(response)
        if not content.strip():
            msg = "LiteLLM completion returned empty content"
            raise BrainProviderError(msg)
        return LiteLLMCompletionResult(
            content=content,
            model=_string_or_default(_get_field(response, "model"), package.model),
            latency_ms=latency_ms,
            usage=_extract_usage(response),
        )


def _load_completion_func() -> CompletionFunc:
    try:
        module = importlib.import_module("litellm")
    except ModuleNotFoundError as exc:
        msg = "litellm optional dependency is not installed; install entroping[ai]"
        raise BrainProviderUnavailableError(msg) from exc
    completion = getattr(module, "completion", None)
    if not callable(completion):
        msg = "litellm optional dependency does not expose completion"
        raise BrainProviderUnavailableError(msg)
    return cast(CompletionFunc, completion)


def _completion_kwargs(package: ArchitectPromptPackage) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "model": package.model,
        "messages": [message.model_dump() for message in package.messages],
        "temperature": package.temperature,
    }
    if package.max_tokens is not None:
        kwargs["max_tokens"] = package.max_tokens
    if package.api_base is not None:
        kwargs["api_base"] = package.api_base
    if package.api_key_env is not None:
        kwargs["api_key"] = _read_api_key(package.api_key_env)
    return kwargs


def _read_api_key(env_name: str) -> str:
    value = os.environ.get(env_name)
    if value is None or not value.strip():
        msg = f"API key environment variable is not set: {env_name}"
        raise BrainProviderError(msg)
    return value


def _extract_content(response: object) -> str:
    choices = _get_field(response, "choices")
    if not isinstance(choices, Sequence) or isinstance(choices, str | bytes) or not choices:
        msg = "LiteLLM completion response did not include choices"
        raise BrainProviderError(msg)
    first_choice = choices[0]
    message = _get_field(first_choice, "message")
    content = _get_field(message, "content")
    if not isinstance(content, str):
        msg = "LiteLLM completion response did not include message content"
        raise BrainProviderError(msg)
    return content


def _extract_usage(response: object) -> LiteLLMUsage:
    usage = _get_field(response, "usage")
    return LiteLLMUsage(
        prompt_tokens=_int_or_none(_get_field(usage, "prompt_tokens")),
        completion_tokens=_int_or_none(_get_field(usage, "completion_tokens")),
        total_tokens=_int_or_none(_get_field(usage, "total_tokens")),
    )


def _get_field(value: object, field: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _int_or_none(value: object | None) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _string_or_default(value: object | None, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default
