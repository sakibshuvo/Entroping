from collections.abc import Mapping, Sequence

from entroping.bridge.openapi_to_hurl.models import (
    OpenApiCompilationError,
    OpenApiSecurityCoverageFinding,
    _SecurityScheme,
)
from entroping.bridge.openapi_to_hurl.parameters import _HTTP_TOKEN_RE
from entroping.bridge.openapi_to_hurl.rendering import _validate_security_scheme_name
from entroping.bridge.openapi_to_hurl.validation import _ensure_mapping, _has_control


def _security_schemes(document: Mapping[str, object]) -> Mapping[str, object]:
    components = document.get("components")
    if components is None:
        return {}
    components_mapping = _ensure_mapping(components, "OpenAPI components")
    security_schemes = components_mapping.get("securitySchemes")
    if security_schemes is None:
        return {}
    normalized = _ensure_mapping(security_schemes, "OpenAPI securitySchemes")
    for scheme_name in normalized:
        _validate_security_scheme_name(scheme_name, context="OpenAPI securitySchemes")
    return normalized


def _security_requirements(
    raw_security: object,
    *,
    context: str,
) -> tuple[tuple[str, ...], ...] | None:
    if raw_security is None:
        return None
    if not isinstance(raw_security, Sequence) or isinstance(raw_security, str | bytes):
        msg = f"{context} must be a list"
        raise OpenApiCompilationError(msg)
    requirements: list[tuple[str, ...]] = []
    for index, raw_requirement in enumerate(raw_security):
        requirement = _ensure_mapping(raw_requirement, f"{context} requirement {index}")
        requirements.append(
            tuple(
                _validate_security_scheme_name(
                    scheme_name,
                    context=f"{context} requirement {index}",
                )
                for scheme_name in requirement
            )
        )
    return tuple(requirements)


def _operation_security_requirements(
    operation: Mapping[str, object],
    *,
    document_security: tuple[tuple[str, ...], ...] | None,
    operation_id: str,
) -> tuple[tuple[str, ...], ...]:
    operation_security = _security_requirements(
        operation.get("security"),
        context=f"OpenAPI operation {operation_id!r} security",
    )
    if operation_security is not None:
        return operation_security
    return document_security or ()


def _supported_security_scheme(
    scheme_name: str,
    *,
    security_schemes: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    raw_scheme = security_schemes.get(scheme_name)
    if raw_scheme is None:
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="security scheme is not defined",
        )
    scheme = _ensure_mapping(raw_scheme, f"OpenAPI security scheme {scheme_name!r}")
    scheme_type = scheme.get("type")
    if scheme_type == "http":
        return _supported_http_security_scheme(
            scheme_name,
            scheme=scheme,
            operation_id=operation_id,
            method=method,
            path=path,
        )
    if scheme_type == "apiKey":
        return _supported_api_key_security_scheme(
            scheme_name,
            scheme=scheme,
            operation_id=operation_id,
            method=method,
            path=path,
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported security scheme type {scheme_type}",
    )


def _supported_http_security_scheme(
    scheme_name: str,
    *,
    scheme: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    http_scheme = scheme.get("scheme")
    if not isinstance(http_scheme, str):
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="http security scheme is missing a string scheme",
        )
    normalized = http_scheme.lower()
    if normalized == "bearer":
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=("Authorization: Bearer invalid-token",),
        )
    if normalized == "basic":
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=("Authorization: Basic ZW50cm9waW5nOmludmFsaWQ=",),
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported http security scheme {http_scheme}",
    )


def _supported_api_key_security_scheme(
    scheme_name: str,
    *,
    scheme: Mapping[str, object],
    operation_id: str,
    method: str,
    path: str,
) -> _SecurityScheme | OpenApiSecurityCoverageFinding:
    api_key_location = scheme.get("in")
    api_key_name = scheme.get("name")
    if not isinstance(api_key_location, str) or not isinstance(api_key_name, str):
        return _security_finding(
            operation_id=operation_id,
            method=method,
            path=path,
            scheme_name=scheme_name,
            reason="apiKey security scheme requires string in and name fields",
        )
    if api_key_location == "header" and _HTTP_TOKEN_RE.fullmatch(api_key_name) is not None:
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(f"{api_key_name}: invalid-api-key",),
        )
    if api_key_location == "query" and not _has_control(api_key_name):
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(),
            query_parameter=(api_key_name, "invalid-api-key"),
        )
    if api_key_location == "cookie" and _HTTP_TOKEN_RE.fullmatch(api_key_name) is not None:
        return _SecurityScheme(
            name=scheme_name,
            auth_lines=(),
            cookie_parameter=(api_key_name, "invalid-session"),
        )
    return _security_finding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=f"unsupported apiKey location or name {api_key_location!r}",
    )


def _security_finding(
    *,
    operation_id: str,
    method: str,
    path: str,
    scheme_name: str,
    reason: str,
) -> OpenApiSecurityCoverageFinding:
    return OpenApiSecurityCoverageFinding(
        operation_id=operation_id,
        method=method,
        path=path,
        scheme_name=scheme_name,
        reason=reason,
    )
