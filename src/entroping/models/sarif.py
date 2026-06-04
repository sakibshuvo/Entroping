"""Strict SARIF 2.1.0 report models for Entroping findings."""

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

SarifResultLevel = Literal["error", "warning", "note"]


class _SarifModel(BaseModel):
    """Base configuration for SARIF payload models."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SarifMessage(_SarifModel):
    """SARIF message object."""

    text: str


class SarifRegion(_SarifModel):
    """SARIF source region."""

    start_line: int = Field(alias="startLine", ge=1)


class SarifArtifactLocation(_SarifModel):
    """SARIF artifact location."""

    uri: str


class SarifPhysicalLocation(_SarifModel):
    """SARIF physical location."""

    artifact_location: SarifArtifactLocation = Field(alias="artifactLocation")
    region: SarifRegion | None = None


class SarifLocation(_SarifModel):
    """SARIF result location."""

    physical_location: SarifPhysicalLocation = Field(alias="physicalLocation")


class SarifRule(_SarifModel):
    """SARIF reporting descriptor for a stable Entroping rule."""

    id: str
    name: str
    short_description: SarifMessage = Field(alias="shortDescription")


class SarifDriver(_SarifModel):
    """SARIF tool driver metadata."""

    name: str = "Entroping"
    rules: list[SarifRule] = Field(default_factory=list)


class SarifTool(_SarifModel):
    """SARIF tool metadata."""

    driver: SarifDriver


class SarifResult(_SarifModel):
    """SARIF result for one Entroping annotation."""

    rule_id: str = Field(alias="ruleId")
    level: SarifResultLevel
    message: SarifMessage
    locations: list[SarifLocation] | None = None


class SarifRun(_SarifModel):
    """SARIF run containing Entroping results."""

    tool: SarifTool
    results: list[SarifResult] = Field(default_factory=list)


class SarifReport(_SarifModel):
    """SARIF 2.1.0 report."""

    schema_uri: str = Field(
        default="https://json.schemastore.org/sarif-2.1.0.json",
        alias="$schema",
    )
    version: Literal["2.1.0"] = "2.1.0"
    runs: list[SarifRun]


class SarifMessagePayload(TypedDict):
    """Serialized SARIF message payload."""

    text: str


class SarifRegionPayload(TypedDict):
    """Serialized SARIF region payload."""

    startLine: int


class SarifArtifactLocationPayload(TypedDict):
    """Serialized SARIF artifact location payload."""

    uri: str


class SarifPhysicalLocationPayload(TypedDict, total=False):
    """Serialized SARIF physical location payload."""

    artifactLocation: SarifArtifactLocationPayload
    region: SarifRegionPayload


class SarifLocationPayload(TypedDict):
    """Serialized SARIF location payload."""

    physicalLocation: SarifPhysicalLocationPayload


class SarifResultPayload(TypedDict, total=False):
    """Serialized SARIF result payload."""

    ruleId: str
    level: SarifResultLevel
    message: SarifMessagePayload
    locations: list[SarifLocationPayload]


class SarifRulePayload(TypedDict):
    """Serialized SARIF rule payload."""

    id: str
    name: str
    shortDescription: SarifMessagePayload


class SarifDriverPayload(TypedDict):
    """Serialized SARIF driver payload."""

    name: str
    rules: list[SarifRulePayload]


class SarifToolPayload(TypedDict):
    """Serialized SARIF tool payload."""

    driver: SarifDriverPayload


class SarifRunPayload(TypedDict):
    """Serialized SARIF run payload."""

    tool: SarifToolPayload
    results: list[SarifResultPayload]


SarifReportPayload = TypedDict(
    "SarifReportPayload",
    {
        "$schema": str,
        "version": Literal["2.1.0"],
        "runs": list[SarifRunPayload],
    },
)
