"""Domain models for ``qanstitution.yaml``."""

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from entroping.models.conditions import (
    CONDITION_JSON_SCHEMA_PATTERN,
    ConditionSyntaxError,
    parse_condition,
)

Enforcement = Literal["block", "warn", "audit_only"]
AgentRole = Literal["builder", "auditor", "breaker"]
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceConfig(BaseModel):
    """Source inputs available to Architect commands."""

    model_config = ConfigDict(extra="forbid")

    spec: str | None = None
    stories: str | None = None
    traffic: str | None = None
    graph: str | None = None
    types: str | None = None


class DependencyConfig(BaseModel):
    """Read-only provider service context."""

    model_config = ConfigDict(extra="forbid")

    name: str
    spec: str


class AgentConfig(BaseModel):
    """Model and persona routing for an Architect role."""

    model_config = ConfigDict(extra="forbid")

    source: str
    model: str
    api_base: str | None = None
    api_key_env: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)

    @field_validator("model")
    @classmethod
    def validate_model_identifier(cls, value: str) -> str:
        """Reject empty, malformed, or secret-looking model identifiers."""

        model = value.strip()
        if not model:
            msg = "model identifier must not be empty"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in model):
            msg = "model identifier must not contain control characters"
            raise ValueError(msg)
        if _looks_like_secret(model):
            msg = "model identifier must not look like a secret"
            raise ValueError(msg)
        return model

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str | None) -> str | None:
        """Validate an optional OpenAI-compatible provider base URL."""

        if value is None:
            return None
        api_base = value.strip()
        if not api_base:
            msg = "api_base must not be empty"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in api_base):
            msg = "api_base must not contain control characters"
            raise ValueError(msg)
        if _looks_like_secret(api_base):
            msg = "api_base must not look like a secret"
            raise ValueError(msg)

        parsed = urlparse(api_base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "api_base must use http or https"
            raise ValueError(msg)
        if parsed.username is not None or parsed.password is not None:
            msg = "api_base must not contain userinfo"
            raise ValueError(msg)
        if parsed.query:
            msg = "api_base must not contain query parameters"
            raise ValueError(msg)
        if parsed.fragment:
            msg = "api_base must not contain fragments"
            raise ValueError(msg)
        return api_base

    @field_validator("api_key_env")
    @classmethod
    def validate_api_key_env(cls, value: str | None) -> str | None:
        """Validate an optional environment variable name for provider auth."""

        if value is None:
            return None
        api_key_env = value.strip()
        if not api_key_env:
            msg = "api_key_env must not be empty"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in api_key_env):
            msg = "api_key_env must not contain control characters"
            raise ValueError(msg)
        if _looks_like_secret(api_key_env):
            msg = "api_key_env must not look like a secret"
            raise ValueError(msg)
        if _ENV_NAME_RE.fullmatch(api_key_env) is None:
            msg = "api_key_env must be an environment variable name"
            raise ValueError(msg)
        return api_key_env


class GateRule(BaseModel):
    """Runtime governance assertion injected into matching Hurl executions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    condition: str = Field(
        json_schema_extra={
            "description": "Deterministic QAnstitution condition DSL.",
            "pattern": CONDITION_JSON_SCHEMA_PATTERN,
        }
    )
    gate: str
    enforcement: Enforcement
    description: str | None = None
    final: bool = False

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: str) -> str:
        """Fail fast when a gate uses unsupported condition syntax."""

        try:
            parse_condition(value)
        except ConditionSyntaxError as exc:
            raise ValueError(str(exc)) from exc
        return value


class KnownFailure(BaseModel):
    """Temporary exception that must remain traceable and expiring."""

    model_config = ConfigDict(extra="forbid")

    test: str
    rule_id: str
    issue_id: str
    expires: str
    reason: str


class RuntimeSettings(BaseModel):
    """Deterministic execution defaults."""

    model_config = ConfigDict(extra="forbid")

    timeout: int = Field(default=30_000, gt=0)
    parallel_workers: int = Field(default=4, gt=0)
    follow_redirects: bool = True
    retry: int = Field(default=0, ge=0)


class Qanstitution(BaseModel):
    """Validated quality law for an Entroping project."""

    model_config = ConfigDict(extra="forbid")

    project: str
    version: str | None = None
    description: str | None = None
    sources: SourceConfig | None = None
    dependencies: list[DependencyConfig] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    agents: dict[AgentRole, AgentConfig] = Field(default_factory=dict)
    gates: list[GateRule] = Field(default_factory=list)
    ignore_failures: list[KnownFailure] = Field(default_factory=list)
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)


def _looks_like_secret(value: str) -> bool:
    normalized = value.strip()
    upper = normalized.upper()
    return (
        normalized.startswith(
            (
                "sk-",
                "sk_proj_",
                "sk-proj-",
                "ghp_",
                "github_pat_",
                "glpat-",
                "hf_",
                "xoxb-",
                "xoxp-",
            )
        )
        or upper.startswith(("AKIA", "ASIA"))
        or normalized.startswith("AIza")
        or normalized.startswith("ya29.")
        or "BEGIN PRIVATE KEY" in upper
    )
