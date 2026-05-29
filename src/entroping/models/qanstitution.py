"""Domain models for ``qanstitution.yaml``."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from entroping.models.conditions import ConditionSyntaxError, parse_condition

Enforcement = Literal["block", "warn", "audit_only"]
AgentRole = Literal["builder", "auditor", "breaker"]


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
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class GateRule(BaseModel):
    """Runtime governance assertion injected into matching Hurl executions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    condition: str
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
