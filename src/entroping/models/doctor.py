"""Structured local doctor health report models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.models.qanstitution import AgentRole

DoctorHealthStatus = Literal["ok", "warn", "error"]
DoctorHurlCompatibilityState = Literal["compatible", "missing", "unsupported", "unparsable"]

_OLLAMA_SETUP_REFERENCE = (
    "Local setup reference: "
    "docs/user/AI_PROVIDER_SETUP.md#local-qwen-through-ollama"
)
_LOCAL_OPENAI_COMPATIBLE_SETUP_REFERENCE = (
    "Local setup reference: "
    "docs/user/AI_PROVIDER_SETUP.md#local-openai-compatible-runtime"
)


def doctor_agent_setup_reference(*, model: str, api_base: str | None) -> str | None:
    """Return fixed local setup guidance from non-secret routing metadata."""

    provider = model.partition("/")[0]
    if provider == "ollama":
        return _OLLAMA_SETUP_REFERENCE
    if provider == "openai" and api_base is not None:
        return _LOCAL_OPENAI_COMPATIBLE_SETUP_REFERENCE
    return None


class DoctorToolHealth(BaseModel):
    """Availability status for a local tool used by Entroping."""

    model_config = ConfigDict(extra="forbid")

    status: DoctorHealthStatus
    available: bool
    path: str | None = None
    message: str


class DoctorHurlCompatibility(BaseModel):
    """Compatibility evidence for the installed Hurl executable."""

    model_config = ConfigDict(extra="forbid")

    status: DoctorHealthStatus
    compatibility: DoctorHurlCompatibilityState
    version: str | None = None
    minimum_version: str
    path: str | None = None
    message: str


class DoctorTrafficStateHealth(BaseModel):
    """Read-only health for local captured-traffic state."""

    model_config = ConfigDict(extra="forbid")

    status: DoctorHealthStatus
    path: str
    exchange_count: int | None = Field(default=None, ge=0)
    message: str


class DoctorQanstitutionHealth(BaseModel):
    """Read-only health for the local QAnstitution file."""

    model_config = ConfigDict(extra="forbid")

    status: DoctorHealthStatus
    path: str
    project: str | None = None
    gate_count: int | None = Field(default=None, ge=0)
    import_count: int | None = Field(default=None, ge=0)
    message: str


class DoctorAgentHealth(BaseModel):
    """Readiness status for one configured Architect agent role."""

    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    status: DoctorHealthStatus
    model: str | None = None
    source: str | None = None
    api_key_env: str | None = None
    api_key_env_present: bool | None = None
    message: str

    @staticmethod
    def message_for(
        model: str,
        api_base: str | None,
        api_key_env_present: bool | None,
    ) -> str:
        """Build the value-free doctor message for one configured agent."""

        message = "api_key_env not set" if api_key_env_present is False else "agent ready"
        setup_reference = doctor_agent_setup_reference(model=model, api_base=api_base)
        if setup_reference is None:
            return message
        if message == "agent ready":
            return setup_reference
        return f"{message}; {setup_reference}"

    @property
    def message_suffix(self) -> str:
        """Return the human-only suffix for local setup guidance."""

        _, marker, reference = self.message.partition("Local setup reference:")
        return f"\n{marker}{reference}" if marker else ""


class DoctorCiReadinessCheck(BaseModel):
    """One CI-readiness check for deterministic PR-gate setup."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: DoctorHealthStatus
    message: str
    path: str | None = None
    suites: list[str] = Field(default_factory=list)
    required_env_names: list[str] = Field(default_factory=list)


class DoctorCiReadiness(BaseModel):
    """CI-focused doctor evidence without provider calls or secret values."""

    model_config = ConfigDict(extra="forbid")

    status: DoctorHealthStatus
    provider_free_run: bool = True
    message: str
    checks: list[DoctorCiReadinessCheck] = Field(default_factory=list)


class DoctorHealthReport(BaseModel):
    """Machine-readable doctor output contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["entroping.doctor.v1"] = "entroping.doctor.v1"
    status: DoctorHealthStatus
    python_version: str
    tools: dict[Literal["hurl", "hurl_parser"], DoctorToolHealth]
    hurl_compatibility: DoctorHurlCompatibility
    traffic_state: DoctorTrafficStateHealth
    qanstitution: DoctorQanstitutionHealth
    agents: list[DoctorAgentHealth] = Field(default_factory=list)
    ci_readiness: DoctorCiReadiness | None = None
