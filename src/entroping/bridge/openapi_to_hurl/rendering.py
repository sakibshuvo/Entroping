import re

from entroping.bridge.openapi_to_hurl.models import OpenApiCompilationError
from entroping.bridge.openapi_to_hurl.validation import (
    _has_control,
    _has_hurl_template_delimiter,
)

_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _negative_path_safety(method: str) -> str:
    if method.upper() in _READ_ONLY_METHODS:
        return "read-only"
    return "destructive"


def _slugify_operation_id(operation_id: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", operation_id).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", snake).strip("_")
    if not slug:
        msg = f"OpenAPI operationId cannot produce a safe file name: {operation_id!r}"
        raise OpenApiCompilationError(msg)
    return slug


def _render_tags(tags: frozenset[str]) -> str:
    normalized = {"generated", *tags}
    for tag in normalized:
        if not tag.strip():
            msg = "OpenAPI generated tags must not be empty"
            raise OpenApiCompilationError(msg)
        if "\n" in tag or "\r" in tag or "," in tag:
            msg = f"OpenAPI generated tag is not safe for metadata comments: {tag!r}"
            raise OpenApiCompilationError(msg)
    return ",".join(sorted(normalized))


def _validate_security_scheme_name(value: str, *, context: str) -> str:
    if _has_control(value):
        msg = f"{context} security scheme name contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = f"{context} security scheme name contains Hurl template delimiters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value
