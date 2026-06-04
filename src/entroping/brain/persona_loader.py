"""Root-bounded loading for Architect persona Markdown files."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from entroping.brain.safety import contains_secret_like_value, has_disallowed_control
from entroping.core.path_safety import first_symlink_path_component
from entroping.models.qanstitution import AgentRole, Qanstitution

_MAX_PERSONA_BYTES = 128_000


class PersonaLoadError(ValueError):
    """Raised when an Architect persona cannot be loaded safely."""


@dataclass(frozen=True)
class AgentPersona:
    """Loaded role persona and model routing metadata."""

    role: AgentRole
    source_path: Path
    content: str
    model: str
    api_base: str | None
    api_key_env: str | None
    temperature: float
    max_tokens: int | None
    input_cost_per_1m_tokens_usd: float | None = None
    output_cost_per_1m_tokens_usd: float | None = None


def load_agent_persona(
    law: Qanstitution,
    role: AgentRole,
    *,
    config_path: str | Path = "qanstitution.yaml",
) -> AgentPersona:
    """Load one configured Architect role persona from a local Markdown file."""

    agent = law.agents.get(role)
    if agent is None:
        msg = f"No agent config found for role {role}"
        raise PersonaLoadError(msg)

    root = Path(config_path).expanduser().resolve().parent
    source_path = _resolve_persona_path(agent.source, root=root)
    content = _read_persona(source_path)
    return AgentPersona(
        role=role,
        source_path=source_path,
        content=content,
        model=agent.model,
        api_base=agent.api_base,
        api_key_env=agent.api_key_env,
        input_cost_per_1m_tokens_usd=agent.input_cost_per_1m_tokens_usd,
        output_cost_per_1m_tokens_usd=agent.output_cost_per_1m_tokens_usd,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
    )


def _resolve_persona_path(source: str, *, root: Path) -> Path:
    parsed = urlparse(source)
    if parsed.scheme:
        msg = f"Agent persona source must be a local Markdown path: {source}"
        raise PersonaLoadError(msg)

    raw_path = Path(source)
    if raw_path.is_absolute():
        msg = f"Agent persona source must be relative: {source}"
        raise PersonaLoadError(msg)
    if raw_path.suffix.lower() != ".md":
        msg = f"Agent persona source must be a Markdown file: {source}"
        raise PersonaLoadError(msg)

    candidate = root / raw_path
    _reject_symlink_path(candidate, root=root)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Agent persona source must stay under {root}: {source}"
        raise PersonaLoadError(msg)
    if not resolved.is_file():
        msg = f"Agent persona file not found: {resolved}"
        raise PersonaLoadError(msg)
    return resolved


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = f"Agent persona source must not use symlinks: {symlink_component}"
        raise PersonaLoadError(msg)


def _read_persona(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        msg = f"Could not inspect agent persona {path}: {exc}"
        raise PersonaLoadError(msg) from exc
    if size > _MAX_PERSONA_BYTES:
        msg = f"Agent persona file is too large: {path}"
        raise PersonaLoadError(msg)

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Agent persona must be UTF-8 Markdown: {path}"
        raise PersonaLoadError(msg) from exc
    except OSError as exc:
        msg = f"Could not read agent persona {path}: {exc}"
        raise PersonaLoadError(msg) from exc

    if not content.strip():
        msg = f"Agent persona must not be empty: {path}"
        raise PersonaLoadError(msg)
    if has_disallowed_control(content):
        msg = f"Agent persona must not contain control characters: {path}"
        raise PersonaLoadError(msg)
    if contains_secret_like_value(content):
        msg = f"Agent persona must not contain secret-like values: {path}"
        raise PersonaLoadError(msg)
    return content
