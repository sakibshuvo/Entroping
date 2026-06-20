"""Parameter parsing and rendering for OpenAPI-to-Hurl compilation."""

import math
import re
from collections.abc import Mapping, Sequence
from urllib.parse import quote

from entroping.bridge.openapi_to_hurl.models import (
    _MISSING,
    OpenApiCompilationError,
    _OpenApiParameter,
    _ParameterExampleValue,
    _ScalarParameterValue,
)
from entroping.bridge.openapi_to_hurl.schema import _schema_preferred_value
from entroping.bridge.openapi_to_hurl.validation import (
    _ensure_mapping,
    _has_control,
    _has_hurl_template_delimiter,
)

__all__ = (
    "_HTTP_TOKEN_RE",
    "_MAX_PARAMETER_REF_DEPTH",
    "_PARAMETER_LOCATIONS",
    "_PARAMETER_REF_PREFIX",
    "_PATH_PARAMETER_RE",
    "_SENSITIVE_VARIABLE_PARTS",
    "_ensure_array_parameter_value",
    "_ensure_scalar_parameter_value",
    "_is_secret_like_variable_name",
    "_merge_parameters",
    "_operation_parameters",
    "_parameter_example_value",
    "_parameter_explode",
    "_parameter_location",
    "_parameter_name",
    "_parameter_style",
    "_parameter_value_token",
    "_parameters_from_container",
    "_parse_parameter",
    "_render_parameter_headers",
    "_render_query_parameter",
    "_render_request_target",
    "_resolve_parameter_ref",
    "_scalar_to_text",
    "_url_component",
    "_validate_fallback_variable_names",
    "_validate_path_template",
    "_variable_name",
)

_PATH_PARAMETER_RE = re.compile(r"\{([^{}]+)\}")
_HTTP_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PARAMETER_LOCATIONS = frozenset({"path", "query", "header", "cookie"})
_MAX_PARAMETER_REF_DEPTH = 64
_PARAMETER_REF_PREFIX = "#/components/parameters/"
_SENSITIVE_VARIABLE_PARTS = (
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "jwt",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "session",
    "token",
)


def _operation_parameters(
    *,
    path_item: Mapping[str, object],
    operation: Mapping[str, object],
    path: str,
    parameter_components: Mapping[str, object],
) -> tuple[_OpenApiParameter, ...]:
    path_parameters = _parameters_from_container(
        path_item,
        context=f"OpenAPI path {path!r}",
        parameter_components=parameter_components,
    )
    operation_parameters = _parameters_from_container(
        operation,
        context=f"OpenAPI operation for {path!r}",
        parameter_components=parameter_components,
    )
    parameters = _merge_parameters(path_parameters, operation_parameters)
    _validate_path_template(path)
    _validate_fallback_variable_names(parameters, path=path)
    return parameters


def _parameters_from_container(
    container: Mapping[str, object],
    *,
    context: str,
    parameter_components: Mapping[str, object],
) -> tuple[_OpenApiParameter, ...]:
    raw_parameters = container.get("parameters")
    if raw_parameters is None:
        return ()
    if not isinstance(raw_parameters, Sequence) or isinstance(raw_parameters, str | bytes):
        msg = f"{context} parameters must be a list"
        raise OpenApiCompilationError(msg)

    parsed: list[_OpenApiParameter] = []
    for index, raw_parameter in enumerate(raw_parameters):
        parameter = _ensure_mapping(raw_parameter, f"{context} parameter {index}")
        parameter_context = f"{context} parameter {index}"
        resolved = _resolve_parameter_ref(
            parameter,
            parameter_components=parameter_components,
            context=parameter_context,
        )
        parsed.append(_parse_parameter(resolved, context=parameter_context))
    return tuple(parsed)


def _resolve_parameter_ref(
    parameter: Mapping[str, object],
    *,
    parameter_components: Mapping[str, object],
    context: str,
    seen_refs: tuple[str, ...] = (),
) -> Mapping[str, object]:
    if "$ref" not in parameter:
        return parameter
    if len(parameter) != 1:
        msg = f"{context} parameter ref must not define sibling fields"
        raise OpenApiCompilationError(msg)
    raw_ref = parameter["$ref"]
    if not isinstance(raw_ref, str):
        msg = f"{context} parameter ref must be a string"
        raise OpenApiCompilationError(msg)
    if not raw_ref.startswith("#/"):
        msg = f"{context} only local parameter refs are supported"
        raise OpenApiCompilationError(msg)
    if not raw_ref.startswith(_PARAMETER_REF_PREFIX):
        msg = f"{context} unsupported parameter ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    if len(seen_refs) >= _MAX_PARAMETER_REF_DEPTH:
        msg = f"{context} parameter ref depth exceeds {_MAX_PARAMETER_REF_DEPTH}"
        raise OpenApiCompilationError(msg)
    component_name = _parameter_component_name(raw_ref, context=context)
    if raw_ref in seen_refs:
        msg = f"{context} cyclic parameter ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    target = parameter_components.get(component_name)
    if target is None:
        msg = f"{context} unknown parameter ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)
    target_mapping = _ensure_mapping(target, f"{context} parameter ref target {raw_ref!r}")
    return _resolve_parameter_ref(
        target_mapping,
        parameter_components=parameter_components,
        context=f"{context} ref {raw_ref!r}",
        seen_refs=(*seen_refs, raw_ref),
    )


def _parameter_component_name(raw_ref: str, *, context: str) -> str:
    component_name = raw_ref.removeprefix(_PARAMETER_REF_PREFIX)
    if not component_name or "/" in component_name:
        msg = f"{context} malformed parameter ref {raw_ref!r}"
        raise OpenApiCompilationError(msg)

    decoded: list[str] = []
    index = 0
    while index < len(component_name):
        character = component_name[index]
        if character != "~":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(component_name):
            msg = f"{context} malformed parameter ref {raw_ref!r}"
            raise OpenApiCompilationError(msg)
        escape = component_name[index + 1]
        if escape == "0":
            decoded.append("~")
        elif escape == "1":
            decoded.append("/")
        else:
            msg = f"{context} malformed parameter ref {raw_ref!r}"
            raise OpenApiCompilationError(msg)
        index += 2
    return "".join(decoded)


def _parse_parameter(
    parameter: Mapping[str, object],
    *,
    context: str,
) -> _OpenApiParameter:
    name = _parameter_name(parameter.get("name"), context=context)
    location = _parameter_location(parameter.get("in"), context=context)
    if location in {"header", "cookie"} and _HTTP_TOKEN_RE.fullmatch(name) is None:
        msg = f"{context} parameter name is not safe for {location}: {name!r}"
        raise OpenApiCompilationError(msg)

    schema = parameter.get("schema")
    schema_mapping = _ensure_mapping(schema, f"{context} schema") if schema is not None else {}
    style = _parameter_style(parameter.get("style"), location=location, context=context)
    explode = _parameter_explode(parameter.get("explode"), style=style, context=context)
    value = _parameter_example_value(
        parameter,
        schema_mapping,
        location=location,
        style=style,
        context=context,
    )
    return _OpenApiParameter(
        name=name,
        location=location,
        variable_name=_variable_name(name),
        example_value=value,
        style=style,
        explode=explode,
    )


def _parameter_name(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        msg = f"{context} parameter name must be a non-empty string"
        raise OpenApiCompilationError(msg)
    if _has_control(value):
        msg = f"{context} parameter name contains control characters: {value!r}"
        raise OpenApiCompilationError(msg)
    return value


def _parameter_location(value: object, *, context: str) -> str:
    if not isinstance(value, str) or _has_control(value):
        msg = f"{context} parameter location must be one of {sorted(_PARAMETER_LOCATIONS)}"
        raise OpenApiCompilationError(msg)
    location = value.lower()
    if location not in _PARAMETER_LOCATIONS:
        msg = f"{context} parameter location is not supported: {value!r}"
        raise OpenApiCompilationError(msg)
    return location


def _parameter_example_value(
    parameter: Mapping[str, object],
    schema: Mapping[str, object],
    *,
    location: str,
    style: str,
    context: str,
) -> _ParameterExampleValue | None:
    value = parameter.get("example", _MISSING)
    if value is _MISSING:
        value = _schema_preferred_value(schema, context=f"{context} schema")
    if value is _MISSING or value is None:
        return None
    if schema.get("type") == "array":
        return _ensure_array_parameter_value(
            value,
            location=location,
            style=style,
            context=context,
        )
    return _ensure_scalar_parameter_value(value, context=context)


def _ensure_scalar_parameter_value(
    value: object,
    *,
    context: str,
) -> _ScalarParameterValue:
    if not isinstance(value, str | int | float | bool):
        msg = f"{context} parameter example/default must be a scalar"
        raise OpenApiCompilationError(msg)
    if isinstance(value, str) and _has_control(value):
        msg = f"{context} parameter example/default contains control characters"
        raise OpenApiCompilationError(msg)
    if isinstance(value, str) and _has_hurl_template_delimiter(value):
        msg = f"{context} parameter example/default contains Hurl template delimiters"
        raise OpenApiCompilationError(msg)
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{context} parameter example/default must be finite"
        raise OpenApiCompilationError(msg)
    return value


def _ensure_array_parameter_value(
    value: object,
    *,
    location: str,
    style: str,
    context: str,
) -> tuple[_ScalarParameterValue, ...]:
    if location != "query":
        msg = (
            f"{context} array parameter examples/defaults are only supported for "
            "query parameters"
        )
        raise OpenApiCompilationError(msg)
    if style != "form":
        msg = (
            f"{context} array query parameter style {style!r} is not supported; "
            "supported style is 'form'"
        )
        raise OpenApiCompilationError(msg)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"{context} array query parameter example/default must be a list"
        raise OpenApiCompilationError(msg)
    if not value:
        msg = f"{context} array query parameter example/default must contain at least one item"
        raise OpenApiCompilationError(msg)
    return tuple(
        _ensure_scalar_parameter_value(
            item,
            context=f"{context} array item {index}",
        )
        for index, item in enumerate(value)
    )


def _parameter_style(value: object, *, location: str, context: str) -> str:
    if value is None:
        return "form" if location in {"query", "cookie"} else "simple"
    if not isinstance(value, str) or _has_control(value):
        msg = f"{context} parameter style must be a string without control characters"
        raise OpenApiCompilationError(msg)
    return value


def _parameter_explode(value: object, *, style: str, context: str) -> bool:
    if value is None:
        return style == "form"
    if not isinstance(value, bool):
        msg = f"{context} parameter explode must be a boolean"
        raise OpenApiCompilationError(msg)
    return value


def _merge_parameters(
    path_parameters: tuple[_OpenApiParameter, ...],
    operation_parameters: tuple[_OpenApiParameter, ...],
) -> tuple[_OpenApiParameter, ...]:
    merged: list[_OpenApiParameter] = []
    indexes: dict[tuple[str, str], int] = {}
    for parameter in (*path_parameters, *operation_parameters):
        key = (parameter.location, parameter.name)
        if key in indexes:
            merged[indexes[key]] = parameter
            continue
        indexes[key] = len(merged)
        merged.append(parameter)
    return tuple(merged)


def _validate_path_template(path: str) -> None:
    stripped = _PATH_PARAMETER_RE.sub("", path)
    if "{" in stripped or "}" in stripped:
        msg = f"OpenAPI path template contains malformed parameter braces: {path!r}"
        raise OpenApiCompilationError(msg)
    for raw_name in _PATH_PARAMETER_RE.findall(path):
        if _has_control(raw_name):
            msg = f"OpenAPI path parameter name contains control characters: {raw_name!r}"
            raise OpenApiCompilationError(msg)
        _variable_name(raw_name)


def _validate_fallback_variable_names(
    parameters: tuple[_OpenApiParameter, ...],
    *,
    path: str,
) -> None:
    path_parameter_names = {
        parameter.name for parameter in parameters if parameter.location == "path"
    }
    seen: dict[str, str] = {}

    def remember(variable_name: str, descriptor: str) -> None:
        if _is_secret_like_variable_name(variable_name):
            msg = (
                "OpenAPI parameter would compile to secret-like fallback variable "
                f"{variable_name!r}: {descriptor}. Provide an explicit safe example "
                "or default instead."
            )
            raise OpenApiCompilationError(msg)
        previous = seen.get(variable_name)
        if previous is not None and previous != descriptor:
            msg = (
                "OpenAPI parameters compile to duplicate fallback variable "
                f"{variable_name!r}: {previous} and {descriptor}"
            )
            raise OpenApiCompilationError(msg)
        seen[variable_name] = descriptor

    for parameter in parameters:
        if parameter.example_value is None:
            remember(
                parameter.variable_name,
                f"{parameter.location} parameter {parameter.name!r}",
            )

    for raw_name in _PATH_PARAMETER_RE.findall(path):
        if raw_name not in path_parameter_names:
            remember(_variable_name(raw_name), f"path template parameter {raw_name!r}")


def _render_request_target(
    path: str,
    parameters: tuple[_OpenApiParameter, ...],
    *,
    path_overrides: Mapping[str, _ScalarParameterValue] | None = None,
) -> str:
    path_parameters = {
        parameter.name: parameter for parameter in parameters if parameter.location == "path"
    }
    overrides = path_overrides or {}

    def replace_path_parameter(match: re.Match[str]) -> str:
        raw_name = match.group(1)
        if raw_name in overrides:
            return _url_component(overrides[raw_name])
        parameter = path_parameters.get(raw_name)
        if parameter is None:
            return f"{{{{{_variable_name(raw_name)}}}}}"
        if parameter.example_value is None:
            return f"{{{{{parameter.variable_name}}}}}"
        if isinstance(parameter.example_value, tuple):
            msg = "array parameter values can only be rendered as query parameters"
            raise OpenApiCompilationError(msg)
        return _url_component(parameter.example_value)

    rendered_path = _PATH_PARAMETER_RE.sub(replace_path_parameter, path)
    query_parts = [
        part
        for parameter in parameters
        if parameter.location == "query"
        for part in _render_query_parameter(parameter)
    ]
    if not query_parts:
        return rendered_path
    return f"{rendered_path}?{'&'.join(query_parts)}"


def _render_query_parameter(parameter: _OpenApiParameter) -> tuple[str, ...]:
    name = _url_component(parameter.name)
    value = parameter.example_value
    if isinstance(value, tuple):
        if parameter.explode:
            return tuple(f"{name}={_url_component(item)}" for item in value)
        return (f"{name}={','.join(_url_component(item) for item in value)}",)
    return (f"{name}={_parameter_value_token(parameter, url_component=True)}",)


def _render_parameter_headers(parameters: tuple[_OpenApiParameter, ...]) -> list[str]:
    headers = [
        f"{parameter.name}: {_parameter_value_token(parameter, url_component=False)}"
        for parameter in parameters
        if parameter.location == "header"
    ]
    cookie_parameters = [parameter for parameter in parameters if parameter.location == "cookie"]
    if cookie_parameters:
        cookie = "; ".join(
            f"{parameter.name}={_parameter_value_token(parameter, url_component=True)}"
            for parameter in cookie_parameters
        )
        headers.append(f"Cookie: {cookie}")
    return headers


def _parameter_value_token(parameter: _OpenApiParameter, *, url_component: bool) -> str:
    if parameter.example_value is None:
        return f"{{{{{parameter.variable_name}}}}}"
    if isinstance(parameter.example_value, tuple):
        msg = "array parameter values can only be rendered as query parameters"
        raise OpenApiCompilationError(msg)
    if url_component:
        return _url_component(parameter.example_value)
    return _scalar_to_text(parameter.example_value)


def _url_component(value: _ScalarParameterValue) -> str:
    return quote(_scalar_to_text(value), safe="-._~")


def _scalar_to_text(value: _ScalarParameterValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _variable_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    if not normalized:
        msg = f"OpenAPI parameter name cannot produce a safe variable name: {name!r}"
        raise OpenApiCompilationError(msg)
    if normalized[0].isdigit():
        normalized = f"param_{normalized}"
    return normalized


def _is_secret_like_variable_name(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_VARIABLE_PARTS)
