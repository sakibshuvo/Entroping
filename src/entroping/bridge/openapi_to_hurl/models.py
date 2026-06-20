"""Typed data models for deterministic OpenAPI-to-Hurl compilation."""

from collections.abc import Mapping
from dataclasses import dataclass

_ScalarParameterValue = str | int | float | bool
_ParameterExampleValue = _ScalarParameterValue | tuple[_ScalarParameterValue, ...]


class _MissingValue:
    """Sentinel for absent OpenAPI examples/defaults."""


_MISSING = _MissingValue()


class OpenApiCompilationError(ValueError):
    """Raised when an OpenAPI document cannot be compiled into Hurl content."""


@dataclass(frozen=True)
class GeneratedHurlFile:
    """Generated Hurl file content plus its deterministic repository path."""

    relative_path: str
    content: str


@dataclass(frozen=True)
class OpenApiSecurityCoverageFinding:
    """Security coverage gap found while compiling OpenAPI auth tests."""

    operation_id: str
    method: str
    path: str
    scheme_name: str
    reason: str


@dataclass(frozen=True)
class OpenApiHurlCompilationResult:
    """Generated Hurl files plus non-blocking OpenAPI security findings."""

    files: tuple[GeneratedHurlFile, ...]
    security_findings: tuple[OpenApiSecurityCoverageFinding, ...]


@dataclass(frozen=True)
class _OpenApiParameter:
    """Normalized OpenAPI parameter data used by the pure compiler."""

    name: str
    location: str
    variable_name: str
    example_value: _ParameterExampleValue | None
    style: str
    explode: bool


@dataclass(frozen=True)
class _SecurityScheme:
    """Supported OpenAPI security scheme rendering metadata."""

    name: str
    auth_lines: tuple[str, ...]
    query_parameter: tuple[str, str] | None = None
    cookie_parameter: tuple[str, str] | None = None


@dataclass(frozen=True)
class _JsonContentSchema:
    """Selected JSON media type and schema from an OpenAPI content map."""

    media_type: str
    schema: Mapping[str, object]


@dataclass(frozen=True)
class _NegativePathCase:
    """One deterministic negative-path Hurl variant for an OpenAPI operation."""

    category: str
    severity: str
    target: str
    body: object | str


@dataclass(slots=True)
class _TraversalBudget:
    """Mutable traversal budget for untrusted OpenAPI structures."""

    nodes: int = 0
