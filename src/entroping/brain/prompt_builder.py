"""Deterministic prompt packaging for Architect roles."""

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.brain.persona_loader import AgentPersona
from entroping.brain.safety import contains_secret_like_value, has_disallowed_control
from entroping.models.qanstitution import Qanstitution


class PromptBuildError(ValueError):
    """Raised when a prompt package would include unsafe context."""


class PromptMessage(BaseModel):
    """OpenAI-compatible chat message used by the LiteLLM adapter."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user"]
    content: str


class ArchitectPromptPackage(BaseModel):
    """Validated prompt payload before model-provider invocation."""

    model_config = ConfigDict(extra="forbid")

    role: str
    model: str
    api_base: str | None = None
    api_key_env: str | None = None
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    messages: tuple[PromptMessage, ...] = Field(min_length=2)


def build_architect_prompt_package(
    *,
    law: Qanstitution,
    persona: AgentPersona,
    intent: str,
    source_context: Mapping[str, str],
) -> ArchitectPromptPackage:
    """Build a deterministic, redaction-checked Architect prompt package."""

    clean_intent = _validate_text(intent, field="intent")
    clean_context = _validate_source_context(source_context)
    persona_content = _validate_text(persona.content, field="persona")
    policy_summary = _validate_text(_render_policy_summary(law), field="QAnstitution summary")
    system_content = "\n\n".join(
        [
            persona_content,
            "The QAnstitution is law. Return structured JSON matching the Architect schema.",
            policy_summary,
        ]
    )
    user_content = "\n\n".join(
        [
            f"Intent:\n{clean_intent}",
            _render_source_context(clean_context),
        ]
    )
    return ArchitectPromptPackage(
        role=persona.role,
        model=persona.model,
        api_base=persona.api_base,
        api_key_env=persona.api_key_env,
        temperature=persona.temperature,
        max_tokens=persona.max_tokens,
        messages=(
            PromptMessage(role="system", content=system_content),
            PromptMessage(role="user", content=user_content),
        ),
    )


def build_auditor_prompt_package(
    *,
    law: Qanstitution,
    persona: AgentPersona,
    source_context: Mapping[str, str],
) -> ArchitectPromptPackage:
    """Build a deterministic, redaction-checked Auditor review prompt package."""

    clean_context = _validate_source_context(source_context)
    persona_content = _validate_text(persona.content, field="persona")
    policy_summary = _validate_text(_render_policy_summary(law), field="QAnstitution summary")
    system_content = "\n\n".join(
        [
            persona_content,
            "The QAnstitution is law. Return structured JSON matching the Auditor review schema.",
            (
                "Auditor schema: {summary: string, findings: [{code: string, "
                "severity: 'info'|'warn'|'error', title: string, detail: string, "
                "recommendation: string, evidence?: string[]}], warnings?: string[]}."
            ),
            "Do not propose file edits. Do not include secrets or raw private data.",
            policy_summary,
        ]
    )
    user_content = "\n\n".join(
        [
            "Audit committed Hurl coverage, QAnstitution policy risk, and actionable gaps.",
            "Return only the Auditor JSON object. Do not wrap it in Markdown fences.",
            _render_source_context(clean_context),
        ]
    )
    return ArchitectPromptPackage(
        role=persona.role,
        model=persona.model,
        api_base=persona.api_base,
        api_key_env=persona.api_key_env,
        temperature=persona.temperature,
        max_tokens=persona.max_tokens,
        messages=(
            PromptMessage(role="system", content=system_content),
            PromptMessage(role="user", content=user_content),
        ),
    )


def _validate_text(value: str, *, field: str) -> str:
    text = value.strip()
    if not text:
        msg = f"{field} must not be empty"
        raise PromptBuildError(msg)
    if has_disallowed_control(text):
        msg = f"{field} must not contain control characters"
        raise PromptBuildError(msg)
    if contains_secret_like_value(text):
        msg = f"{field} must not contain secret-like values"
        raise PromptBuildError(msg)
    return text


def _validate_source_context(source_context: Mapping[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for raw_path, raw_content in source_context.items():
        path = _validate_context_path(raw_path)
        content = _validate_text(raw_content, field=f"context {path}")
        clean[path] = content
    return clean


def _validate_context_path(value: str) -> str:
    path = value.strip()
    if not path:
        msg = "context path must not be empty"
        raise PromptBuildError(msg)
    if "\\" in path:
        msg = "context path must use POSIX separators"
        raise PromptBuildError(msg)
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        msg = "context path must stay under project"
        raise PromptBuildError(msg)
    if has_disallowed_control(path):
        msg = "context path must not contain control characters"
        raise PromptBuildError(msg)
    return path


def _render_policy_summary(law: Qanstitution) -> str:
    lines = [f"QAnstitution project: {law.project}"]
    if law.version is not None:
        lines.append(f"Version: {law.version}")
    if law.sources is not None and law.sources.spec is not None:
        lines.append(f"OpenAPI source: {law.sources.spec}")
    if law.gates:
        lines.append("Gates:")
        for gate in law.gates:
            lines.append(
                f"- {gate.id}: condition={gate.condition}; enforcement={gate.enforcement}; "
                f"assert={gate.gate}"
            )
    else:
        lines.append("Gates: none")
    return "\n".join(lines)


def _render_source_context(source_context: Mapping[str, str]) -> str:
    if not source_context:
        return "Source context: none"

    lines = ["Source context:"]
    for path, content in source_context.items():
        lines.append(f"## {path}")
        lines.append(content)
    return "\n".join(lines)
