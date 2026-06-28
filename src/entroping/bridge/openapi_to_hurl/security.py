import json
from collections.abc import Mapping

from entroping.bridge.openapi_to_hurl.models import (
    GeneratedHurlFile,
    OpenApiHurlCompilationResult,
    OpenApiSecurityCoverageFinding,
    _JsonContentSchema,
    _SecurityScheme,
)
from entroping.bridge.openapi_to_hurl.parameters import (
    _operation_parameters,
    _render_parameter_headers,
    _render_request_target,
    _url_component,
)
from entroping.bridge.openapi_to_hurl.rendering import (
    _negative_path_safety,
    _render_tags,
    _slugify_operation_id,
)
from entroping.bridge.openapi_to_hurl.schema import _example_for_schema
from entroping.bridge.openapi_to_hurl.security_schemes import (
    _operation_security_requirements,
    _supported_security_scheme,
)
from entroping.bridge.openapi_to_hurl.validation import _mapping_field


def _security_negative_files(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
    security_schemes: Mapping[str, object],
    parameter_components: Mapping[str, object],
    document_security: tuple[tuple[str, ...], ...] | None,
    request_content: _JsonContentSchema | None,
) -> OpenApiHurlCompilationResult:
    requirements = _operation_security_requirements(
        operation,
        document_security=document_security,
        operation_id=operation_id,
    )
    if not requirements:
        return OpenApiHurlCompilationResult(files=(), security_findings=())
    if any(not requirement for requirement in requirements):
        return OpenApiHurlCompilationResult(files=(), security_findings=())

    supported: list[_SecurityScheme] = []
    findings: list[OpenApiSecurityCoverageFinding] = []
    seen_schemes: set[str] = set()
    for scheme_name in (scheme for requirement in requirements for scheme in requirement):
        if scheme_name in seen_schemes:
            continue
        seen_schemes.add(scheme_name)
        scheme = _supported_security_scheme(
            scheme_name,
            security_schemes=security_schemes,
            operation_id=operation_id,
            method=method,
            path=path,
        )
        if isinstance(scheme, OpenApiSecurityCoverageFinding):
            findings.append(scheme)
        else:
            supported.append(scheme)

    unauthorized_status = _auth_failure_status(operation)
    if unauthorized_status is None:
        findings.extend(
            OpenApiSecurityCoverageFinding(
                operation_id=operation_id,
                method=method,
                path=path,
                scheme_name=scheme.name,
                reason="missing explicit 401 or 403 response for auth-negative test",
            )
            for scheme in supported
        )
        return OpenApiHurlCompilationResult(files=(), security_findings=tuple(findings))

    security_tags = frozenset({*tags, "auth", "invalid-auth", "negative"})
    slug = _slugify_operation_id(operation_id)
    files: list[GeneratedHurlFile] = []
    if supported:
        files.append(
            GeneratedHurlFile(
                relative_path=f"tests/generated/security/{slug}_missing_auth.hurl",
                content=_render_security_negative_operation(
                    method=method,
                    path=path,
                    path_item=path_item,
                    operation=operation,
                    operation_id=operation_id,
                    tags=security_tags,
                    status=unauthorized_status,
                    security="missing_auth",
                    scheme_name="*",
                    auth_lines=(),
                    query_parameter=None,
                    cookie_parameter=None,
                    parameter_components=parameter_components,
                    request_content=request_content,
                ),
            )
        )
    files.extend(
        GeneratedHurlFile(
            relative_path=(
                "tests/generated/security/"
                f"{slug}_invalid_{_slugify_operation_id(scheme.name)}.hurl"
            ),
            content=_render_security_negative_operation(
                method=method,
                path=path,
                path_item=path_item,
                operation=operation,
                operation_id=operation_id,
                tags=security_tags,
                status=unauthorized_status,
                security="invalid_auth",
                scheme_name=scheme.name,
                auth_lines=scheme.auth_lines,
                query_parameter=scheme.query_parameter,
                cookie_parameter=scheme.cookie_parameter,
                parameter_components=parameter_components,
                request_content=request_content,
            ),
        )
        for scheme in supported
    )
    return OpenApiHurlCompilationResult(
        files=tuple(files),
        security_findings=tuple(findings),
    )


def _render_security_negative_operation(
    *,
    method: str,
    path: str,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    operation_id: str,
    tags: frozenset[str],
    status: str,
    security: str,
    scheme_name: str,
    auth_lines: tuple[str, ...],
    query_parameter: tuple[str, str] | None,
    cookie_parameter: tuple[str, str] | None,
    parameter_components: Mapping[str, object],
    request_content: _JsonContentSchema | None,
) -> str:
    parameters = _operation_parameters(
        path_item=path_item,
        operation=operation,
        path=path,
        parameter_components=parameter_components,
    )
    target = _render_request_target(path, parameters)
    if query_parameter is not None:
        separator = "&" if "?" in target else "?"
        target = (
            f"{target}{separator}"
            f"{_url_component(query_parameter[0])}={_url_component(query_parameter[1])}"
        )
    lines = [
        f"# entroping: tags={_render_tags(tags)}",
        "# entroping: source=openapi",
        f"# entroping: operation_id={operation_id}",
        "# entroping: negative_category=invalid-auth",
        "# entroping: severity=high",
        f"# entroping: safety={_negative_path_safety(method)}",
        f"# entroping: security={security}",
        f"# entroping: security_scheme={scheme_name}",
        f"# entroping: path={path}",
        "",
        f"{method} {{{{base_url}}}}{target}",
    ]
    extra_cookie_pairs = () if cookie_parameter is None else (cookie_parameter,)
    lines.extend(_render_parameter_headers(parameters, extra_cookie_pairs=extra_cookie_pairs))
    lines.extend(auth_lines)

    if request_content is not None:
        lines.append(f"Content-Type: {request_content.media_type}")
        lines.extend(
            json.dumps(
                _example_for_schema(request_content.schema),
                indent=2,
                allow_nan=False,
            ).splitlines()
        )

    lines.extend((f"HTTP {status}", ""))
    return "\n".join(lines)


def _auth_failure_status(operation: Mapping[str, object]) -> str | None:
    responses = _mapping_field(operation, "responses", "OpenAPI operation must contain responses")
    if "401" in responses:
        return "401"
    if "403" in responses:
        return "403"
    return None
