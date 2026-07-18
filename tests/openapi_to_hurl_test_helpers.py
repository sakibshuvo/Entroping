from entroping.bridge import openapi_to_hurl as openapi_compiler
from entroping.bridge.openapi_to_hurl import compile_openapi_to_hurl


def _compile_single_operation(
    operation: dict[str, object],
    *,
    path: str = "/health",
    method: str = "get",
    tags: frozenset[str] = frozenset(),
) -> str:
    document: dict[str, object] = {
        "openapi": "3.1.0",
        "paths": {path: {method: operation}},
    }
    return compile_openapi_to_hurl(document, tags=tags)[0].content


def _ok_operation(operation_id: str = "getHealth") -> dict[str, object]:
    return {
        "operationId": operation_id,
        "responses": {"200": {"description": "ok"}},
    }


def _deep_required_object_schema(depth: int) -> dict[str, object]:
    schema: dict[str, object] = {"type": "string"}
    for index in range(depth):
        field = f"child_{index}"
        schema = {
            "type": "object",
            "required": [field],
            "properties": {field: schema},
        }
    return schema


def _deep_json_value(depth: int) -> dict[str, object]:
    value: dict[str, object] = {"leaf": "ok"}
    for index in range(depth):
        value = {f"child_{index}": value}
    return value


def _oversized_openapi_string() -> str:
    return "x" * (openapi_compiler._MAX_OPENAPI_GENERATED_STRING_LENGTH + 1)  # noqa: SLF001
