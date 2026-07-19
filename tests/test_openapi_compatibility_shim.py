import importlib

import pytest

from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import (
    OpenApiCompilationError,
    compile_openapi_to_hurl_with_report,
)


def test_openapi_to_hurl_package_exposes_compatibility_surface() -> None:
    compiler_module = importlib.import_module("entroping.bridge.openapi_to_hurl.compiler")
    parameters_module = importlib.import_module("entroping.bridge.openapi_to_hurl.parameters")

    assert openapi_compiler.compile_openapi_to_hurl is compiler_module.compile_openapi_to_hurl
    assert openapi_compiler.OpenApiCompilationError is compiler_module.OpenApiCompilationError
    assert openapi_compiler._OpenApiParameter is compiler_module._OpenApiParameter  # noqa: SLF001
    assert openapi_compiler._TraversalBudget is compiler_module._TraversalBudget  # noqa: SLF001
    assert openapi_compiler._render_request_target is parameters_module._render_request_target  # noqa: SLF001
    assert openapi_compiler._render_parameter_headers is parameters_module._render_parameter_headers  # noqa: SLF001
    assert openapi_compiler._validate_path_template is parameters_module._validate_path_template  # noqa: SLF001
    with pytest.raises(
        AttributeError,
        match=r"module 'entroping\.bridge\.openapi_to_hurl' has no attribute '_missing'",
    ):
        missing_attribute = "_missing"
        getattr(openapi_compiler, missing_attribute)


def test_compile_openapi_rejects_duplicate_schema_negative_generated_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def duplicate_schema_negative_file(**_: object) -> tuple[openapi_compiler.GeneratedHurlFile]:
        return (
            openapi_compiler.GeneratedHurlFile(
                relative_path="tests/generated/get_health.hurl",
                content="GET {{base_url}}/duplicate\nHTTP 400\n",
            ),
        )

    monkeypatch.setattr(openapi_compiler, "_schema_negative_files", duplicate_schema_negative_file)

    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }

    with pytest.raises(OpenApiCompilationError, match="duplicate Hurl path"):
        compile_openapi_to_hurl_with_report(document, tags=frozenset())
