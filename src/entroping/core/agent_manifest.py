"""Sanitized local evidence for prompt-backed Architect agent runs."""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.safe_write import SafeWriteError, safe_write_text

AGENT_RUN_MANIFEST_SCHEMA_VERSION: Final = "entroping.agent-run-manifest.v1"

AgentRunCommand = Literal["architect build", "architect refactor", "architect audit"]
AgentRunMode = Literal["create", "merge", "refactor", "review"]
AgentRunValidationStatus = Literal["passed", "failed"]


class AgentRunManifestError(ValueError):
    """Raised when an agent run manifest cannot be written safely."""


@dataclass(frozen=True, slots=True)
class AgentRunUsageEvidence:
    """Value-free provider usage evidence."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class AgentRunCostEvidence:
    """Value-free provider cost estimate evidence."""

    estimated_usd: float | None
    input_cost_per_1m_tokens_usd: float | None
    output_cost_per_1m_tokens_usd: float | None

    @classmethod
    def empty(cls) -> "AgentRunCostEvidence":
        """Return empty cost evidence when rates or usage are unavailable."""

        return cls(
            estimated_usd=None,
            input_cost_per_1m_tokens_usd=None,
            output_cost_per_1m_tokens_usd=None,
        )


@dataclass(frozen=True, slots=True)
class AgentRunManifestInput:
    """Input required to write one sanitized agent run manifest."""

    project_root: Path
    command: AgentRunCommand
    mode: AgentRunMode
    agent: str
    model: str
    persona_source_path: Path
    persona_content: str
    prompt_intent: str
    prompt_package_messages: tuple[str, ...]
    output_paths: tuple[Path, ...]
    tags: tuple[str, ...]
    validation_status: AgentRunValidationStatus
    structured_output_validated: bool
    hurl_validated: bool
    latency_ms: int
    usage: AgentRunUsageEvidence
    provider: str | None = None
    cost: AgentRunCostEvidence = field(default_factory=AgentRunCostEvidence.empty)
    generated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AgentRunManifestResult:
    """Result of writing one sanitized agent run manifest."""

    manifest_path: Path


def write_agent_run_manifest(input_data: AgentRunManifestInput) -> AgentRunManifestResult:
    """Write a sanitized manifest for one prompt-backed Architect run."""

    root = input_data.project_root.expanduser().resolve()
    generated_at = _generated_at(input_data.generated_at)
    intent_sha256 = _sha256(input_data.prompt_intent)
    payload = {
        "schema_version": AGENT_RUN_MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "command": _validate_plain_text(input_data.command, field="command"),
        "mode": _validate_plain_text(input_data.mode, field="mode"),
        "agent": _validate_plain_text(input_data.agent, field="agent"),
        "model": _validate_plain_text(input_data.model, field="model"),
        "provider": _validate_optional_plain_text(input_data.provider, field="provider"),
        "persona": {
            "source_path": _display_project_path(input_data.persona_source_path, root=root),
            "sha256": _sha256(input_data.persona_content),
        },
        "prompt": {
            "intent_sha256": intent_sha256,
            "package_sha256": _sha256("\n\n".join(input_data.prompt_package_messages)),
        },
        "output_paths": [
            _display_project_path(path, root=root, field="output path")
            for path in input_data.output_paths
        ],
        "tags": sorted(_validate_plain_text(tag, field="tag") for tag in input_data.tags),
        "validation": {
            "status": input_data.validation_status,
            "structured_output_validated": input_data.structured_output_validated,
            "hurl_validated": input_data.hurl_validated,
        },
        "latency_ms": input_data.latency_ms,
        "cost": {
            "estimated_usd": _validate_optional_cost(
                input_data.cost.estimated_usd,
                field="estimated cost",
            ),
            "input_cost_per_1m_tokens_usd": _validate_optional_cost(
                input_data.cost.input_cost_per_1m_tokens_usd,
                field="input cost per 1M tokens",
            ),
            "output_cost_per_1m_tokens_usd": _validate_optional_cost(
                input_data.cost.output_cost_per_1m_tokens_usd,
                field="output cost per 1M tokens",
            ),
        },
        "usage": {
            "prompt_tokens": input_data.usage.prompt_tokens,
            "completion_tokens": input_data.usage.completion_tokens,
            "total_tokens": input_data.usage.total_tokens,
        },
    }
    path = (
        root
        / ".entroping"
        / "agent-runs"
        / (
            f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{input_data.command.replace(' ', '-')}-"
            f"{input_data.agent}-{intent_sha256[:12]}.json"
        )
    )
    try:
        manifest_path = safe_write_text(
            path,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            artifact="agent run manifest",
            root=root,
        )
    except SafeWriteError as exc:
        raise AgentRunManifestError(str(exc)) from exc
    return AgentRunManifestResult(manifest_path=manifest_path)


def _generated_at(value: datetime | None) -> datetime:
    generated_at = value or datetime.now(UTC)
    if generated_at.tzinfo is None:
        msg = "generated_at must be timezone-aware"
        raise AgentRunManifestError(msg)
    return generated_at.astimezone(UTC)


def _display_project_path(path: Path, *, root: Path, field: str = "persona source path") -> str:
    raw_path = path.expanduser()
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        msg = f"{field} must stay inside the project"
        raise AgentRunManifestError(msg) from exc
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = f"{field} must not use symlinks: {symlink_component}"
        raise AgentRunManifestError(msg)
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        msg = f"{field} must stay inside the project"
        raise AgentRunManifestError(msg) from exc
    return relative.as_posix()


def _validate_plain_text(value: str, *, field: str) -> str:
    text = value.strip()
    if not text:
        msg = f"{field} must not be empty"
        raise AgentRunManifestError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        msg = f"{field} must not contain control characters"
        raise AgentRunManifestError(msg)
    return text


def _validate_optional_plain_text(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    return _validate_plain_text(value, field=field)


def _validate_optional_cost(value: float | None, *, field: str) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        msg = f"{field} must be finite"
        raise AgentRunManifestError(msg)
    if value < 0:
        msg = f"{field} must be greater than or equal to 0"
        raise AgentRunManifestError(msg)
    return value


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
