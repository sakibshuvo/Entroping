"""Domain models for ``qanstitution.yaml``."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from entroping.models.conditions import (
    CONDITION_JSON_SCHEMA_PATTERN,
    ConditionSyntaxError,
    parse_condition,
)

Enforcement = Literal["block", "warn", "audit_only"]
AgentRole = Literal["builder", "auditor", "breaker"]
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KNOWN_FAILURE_EXPIRY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SUPPORTED_QANSTITUTION_VERSIONS: tuple[str, ...] = ("4.1",)
DEFAULT_PROTECTED_ENVIRONMENTS: tuple[str, ...] = ("prod", "production", "protected")
_QANSTITUTION_VERSION_MIGRATION_NOTE = (
    "Update to a supported QAnstitution version and follow the migration guidance in "
    "docs/technical/QANSTITUTION_REFERENCE.md#qanstitution-schema-compatibility."
)


@dataclass(frozen=True, slots=True)
class ExpandedGateEntry:
    """One authored gate after reusable group expansion."""

    rule: "GateRule"
    group: str | None = None


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
    input_cost_per_1m_tokens_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    output_cost_per_1m_tokens_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
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


class GateGroupReference(BaseModel):
    """Top-level reference to a reusable local gate group."""

    model_config = ConfigDict(extra="forbid")

    group: str

    @field_validator("group")
    @classmethod
    def validate_group_name(cls, value: str) -> str:
        """Reject ambiguous or unsafe gate group references."""

        return _validate_gate_group_name(value)


class GateGroup(BaseModel):
    """Reusable local collection of governance gates."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    groups: list[str] = Field(default_factory=list)
    gates: list[GateRule] = Field(default_factory=list)

    @field_validator("groups")
    @classmethod
    def validate_nested_group_names(cls, value: list[str]) -> list[str]:
        """Reject ambiguous or unsafe nested gate group names."""

        return [_validate_gate_group_name(group_name) for group_name in value]


class KnownFailure(BaseModel):
    """Temporary exception that must remain traceable and expiring."""

    model_config = ConfigDict(extra="forbid")

    test: str
    rule_id: str
    issue_id: str
    expires: str = Field(json_schema_extra={"pattern": r"^\d{4}-\d{2}-\d{2}$"})
    reason: str

    @field_validator("expires")
    @classmethod
    def validate_expires(cls, value: str) -> str:
        """Require an exact ISO calendar date for governance exceptions."""

        if _KNOWN_FAILURE_EXPIRY_RE.fullmatch(value) is None:
            msg = "expires must use YYYY-MM-DD"
            raise ValueError(msg)
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            msg = "expires must use YYYY-MM-DD"
            raise ValueError(msg) from exc
        return value


class KnownFailureValidationError(ValueError):
    """Raised when known-failure runtime validity fails."""


def parse_known_failure_expiry(known_failure: KnownFailure) -> date:
    """Return the parsed expiry date for a validated known-failure entry."""

    try:
        if _KNOWN_FAILURE_EXPIRY_RE.fullmatch(known_failure.expires) is None:
            msg = "expires must use YYYY-MM-DD"
            raise ValueError(msg)
        return date.fromisoformat(known_failure.expires)
    except ValueError as exc:
        msg = (
            "Known failure exception expiry must be YYYY-MM-DD "
            f"for {known_failure.issue_id} on {known_failure.test} "
            f"rule {known_failure.rule_id}: {known_failure.expires}"
        )
        raise KnownFailureValidationError(msg) from exc


def validate_known_failure_expiries(
    known_failures: Sequence[KnownFailure],
    *,
    today: date | None = None,
) -> None:
    """Fail closed when any known-failure exception is expired."""

    reference_date = today or date.today()
    for known_failure in known_failures:
        expires = parse_known_failure_expiry(known_failure)
        if expires < reference_date:
            msg = (
                "Known failure exception expired "
                f"for {known_failure.issue_id} on {known_failure.test} "
                f"rule {known_failure.rule_id}: expired {known_failure.expires}"
            )
            raise KnownFailureValidationError(msg)


class RuntimeSettings(BaseModel):
    """Deterministic execution defaults."""

    model_config = ConfigDict(extra="forbid")

    timeout: int = Field(default=30_000, gt=0)
    parallel_workers: int = Field(default=4, gt=0)
    follow_redirects: bool = True
    retry: int = Field(default=0, ge=0)
    protected_environments: list[str] = Field(
        default_factory=lambda: list(DEFAULT_PROTECTED_ENVIRONMENTS)
    )

    @field_validator("protected_environments")
    @classmethod
    def validate_protected_environments(cls, value: list[str]) -> list[str]:
        """Normalize protected environment names for run safety classification."""

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            stripped = item.strip().lower()
            if not stripped:
                msg = "protected environment names must not be empty"
                raise ValueError(msg)
            if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
                msg = "protected environment names must not contain control characters"
                raise ValueError(msg)
            if stripped in seen:
                continue
            seen.add(stripped)
            normalized.append(stripped)
        return normalized


class Qanstitution(BaseModel):
    """Validated quality law for an Entroping project."""

    model_config = ConfigDict(extra="forbid")

    project: str
    version: str | None = Field(
        default=None,
        json_schema_extra={
            "description": (
                "QAnstitution schema compatibility marker. Omit only for legacy "
                "v4.1-compatible policy files."
            ),
            "enum": [*SUPPORTED_QANSTITUTION_VERSIONS, None],
        },
    )
    description: str | None = None
    sources: SourceConfig | None = None
    dependencies: list[DependencyConfig] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    agents: dict[AgentRole, AgentConfig] = Field(default_factory=dict)
    gate_groups: dict[str, GateGroup] = Field(default_factory=dict)
    gates: list[GateRule] = Field(default_factory=list)
    ignore_failures: list[KnownFailure] = Field(default_factory=list)
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)

    @model_validator(mode="before")
    @classmethod
    def expand_gate_group_references(cls, data: object) -> object:
        """Normalize authoring-time group references into runtime gate rules."""

        if not isinstance(data, Mapping):
            return data

        normalized: dict[str, object] = dict(data)
        expanded = expand_qanstitution_gate_entries(data)
        normalized["gates"] = [entry.rule for entry in expanded]
        return normalized

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        """Validate optional policy version against supported schema versions."""

        if value is None:
            return None

        if not value:
            msg = f"QAnstitution version must not be empty. {_QANSTITUTION_VERSION_MIGRATION_NOTE}"
            raise ValueError(msg)

        if value != value.strip():
            msg = (
                "QAnstitution version must not contain leading or trailing whitespace. "
                f"{_QANSTITUTION_VERSION_MIGRATION_NOTE}"
            )
            raise ValueError(msg)

        if value not in SUPPORTED_QANSTITUTION_VERSIONS:
            msg = (
                f"Unsupported QAnstitution version {value!r}. "
                f"Supported versions: {', '.join(SUPPORTED_QANSTITUTION_VERSIONS)}. "
                f"{_QANSTITUTION_VERSION_MIGRATION_NOTE}"
            )
            raise ValueError(msg)

        return value


def expand_qanstitution_gate_entries(
    document: Mapping[str, object],
) -> tuple[ExpandedGateEntry, ...]:
    """Expand local gate group references while retaining authored provenance."""

    raw_gate_groups = document.get("gate_groups", {})
    gate_groups = _parse_gate_groups(raw_gate_groups)
    raw_gates_value = document.get("gates", [])
    raw_gates = _sequence_from_authoring_list(raw_gates_value, field_name="gates")
    expanded: list[ExpandedGateEntry] = []

    def expand_group(group_name: str, stack: tuple[str, ...]) -> None:
        validated_name = _validate_gate_group_name(group_name)
        if validated_name not in gate_groups:
            msg = f"Unknown gate group {validated_name!r}"
            raise ValueError(msg)
        if validated_name in stack:
            cycle = " -> ".join((*stack, validated_name))
            msg = f"Gate group cycle detected: {cycle}"
            raise ValueError(msg)

        group = gate_groups[validated_name]
        next_stack = (*stack, validated_name)
        for nested_group in group.groups:
            expand_group(nested_group, next_stack)
        expanded.extend(ExpandedGateEntry(rule=gate, group=validated_name) for gate in group.gates)

    for raw_gate in raw_gates:
        if _is_gate_group_reference(raw_gate):
            reference = GateGroupReference.model_validate(raw_gate)
            expand_group(reference.group, stack=())
            continue
        expanded.append(ExpandedGateEntry(rule=GateRule.model_validate(raw_gate)))

    return tuple(expanded)


def _parse_gate_groups(raw_gate_groups: object) -> dict[str, GateGroup]:
    if not isinstance(raw_gate_groups, Mapping):
        msg = "gate_groups must be a mapping"
        raise ValueError(msg)

    gate_groups: dict[str, GateGroup] = {}
    for raw_name, raw_group in raw_gate_groups.items():
        if not isinstance(raw_name, str):
            msg = "gate group names must be strings"
            raise ValueError(msg)
        name = _validate_gate_group_name(raw_name)
        gate_groups[name] = GateGroup.model_validate(raw_group)
    return gate_groups


def _sequence_from_authoring_list(raw_value: object, *, field_name: str) -> Sequence[object]:
    if isinstance(raw_value, str | bytes) or not isinstance(raw_value, Sequence):
        msg = f"{field_name} must be a list"
        raise ValueError(msg)
    return raw_value


def _is_gate_group_reference(raw_gate: object) -> bool:
    if isinstance(raw_gate, GateGroupReference):
        return True
    if not isinstance(raw_gate, Mapping):
        return False
    gate = cast(Mapping[object, object], raw_gate)
    return "group" in gate


def _validate_gate_group_name(value: str) -> str:
    group_name = value.strip()
    if not group_name:
        msg = "gate group name must not be empty"
        raise ValueError(msg)
    if any(ord(character) < 32 or ord(character) == 127 for character in group_name):
        msg = "gate group name must not contain control characters"
        raise ValueError(msg)
    return group_name


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
