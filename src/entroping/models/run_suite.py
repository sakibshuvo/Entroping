"""Domain model for committed run suite manifests."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunSuiteReportFormat = Literal["drift", "html", "json", "junit"]


class RunSuiteManifest(BaseModel):
    """Schema for ``suites/<name>.yaml`` run suite manifests."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["entroping.suite.v1"] = "entroping.suite.v1"
    name: str | None = None
    env: str | None = None
    tags: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    reports: list[RunSuiteReportFormat] = Field(default_factory=list)
    parallel: bool = False
    fail_fast: bool = False
    drift_check: bool = False

    @field_validator("name", "env")
    @classmethod
    def validate_optional_string(cls, value: str | None) -> str | None:
        """Reject empty optional string fields."""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            msg = "must not be empty"
            raise ValueError(msg)
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            msg = "must not contain control characters"
            raise ValueError(msg)
        return normalized

    @field_validator("tags", "paths")
    @classmethod
    def validate_string_list(cls, value: list[str]) -> list[str]:
        """Reject empty or control-character list values."""

        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                msg = "items must not be empty"
                raise ValueError(msg)
            if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
                msg = "items must not contain control characters"
                raise ValueError(msg)
            normalized.append(stripped)
        return normalized
