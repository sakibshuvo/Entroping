"""OpenAPI-to-Hurl compiler package.

The package-level surface intentionally mirrors the former
``entroping.bridge.openapi_to_hurl`` module so callers can keep importing the
compiler entrypoints and compatibility-tested helper types from the package
while implementation details move into bounded modules.
"""

import sys
from types import ModuleType

from . import compiler as _compiler
from .compiler import (
    _MAX_OPENAPI_GENERATED_STRING_LENGTH,
    _MAX_OPENAPI_JSON_DEPTH,
    _MAX_OPENAPI_JSON_NODES,
    _MAX_OPENAPI_SCHEMA_DEPTH,
    _MAX_OPENAPI_SCHEMA_NODES,
    GeneratedHurlFile,
    OpenApiCompilationError,
    OpenApiHurlCompilationResult,
    OpenApiSecurityCoverageFinding,
    _check_openapi_json_budget,
    _check_openapi_schema_budget,
    _ensure_json_value,
    _ensure_string_keys,
    _example_for_schema,
    _first_enum_value,
    _first_example_value,
    _generated_string,
    _JsonContentSchema,
    _NegativePathCase,
    _OpenApiParameter,
    _render_parameter_headers,
    _render_request_target,
    _schema_negative_files,
    _schema_preferred_value,
    _SecurityScheme,
    _TraversalBudget,
    _validate_path_template,
    compile_openapi_to_hurl,
    compile_openapi_to_hurl_with_report,
)

__all__ = (
    "GeneratedHurlFile",
    "OpenApiCompilationError",
    "OpenApiHurlCompilationResult",
    "OpenApiSecurityCoverageFinding",
    "compile_openapi_to_hurl",
    "compile_openapi_to_hurl_with_report",
    "_JsonContentSchema",
    "_MAX_OPENAPI_GENERATED_STRING_LENGTH",
    "_MAX_OPENAPI_JSON_DEPTH",
    "_MAX_OPENAPI_JSON_NODES",
    "_MAX_OPENAPI_SCHEMA_DEPTH",
    "_MAX_OPENAPI_SCHEMA_NODES",
    "_NegativePathCase",
    "_OpenApiParameter",
    "_SecurityScheme",
    "_TraversalBudget",
    "_check_openapi_json_budget",
    "_check_openapi_schema_budget",
    "_ensure_json_value",
    "_ensure_string_keys",
    "_example_for_schema",
    "_first_enum_value",
    "_first_example_value",
    "_generated_string",
    "_render_parameter_headers",
    "_render_request_target",
    "_schema_negative_files",
    "_schema_preferred_value",
    "_validate_path_template",
)


class _CompilerCompatibilityModule(ModuleType):
    """Propagate old module-level monkeypatches into the compiler module."""

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if hasattr(_compiler, name):
            setattr(_compiler, name, value)


def __getattr__(name: str) -> object:
    try:
        return getattr(_compiler, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


sys.modules[__name__].__class__ = _CompilerCompatibilityModule
