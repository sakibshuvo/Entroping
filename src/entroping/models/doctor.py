"""Structured local doctor health report models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from entroping.models.qanstitution import AgentRole

DoctorHealthStatus = Literal["ok", "warn", "error"]
DoctorHurlCompatibilityState = Literal["compatible", "missing", "unsupported", "unparsable"]


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
