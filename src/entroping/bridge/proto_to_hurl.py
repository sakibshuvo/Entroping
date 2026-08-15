import re
from dataclasses import dataclass
from typing import Final, NoReturn
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_PROTO_STRING_RE: Final = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_PROTO_WHITESPACE_RE: Final = re.compile(r"\s*")
_PROTO_BLOCK_COMMENT_RE: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_PROTO_LINE_COMMENT_RE: Final = re.compile(r"(?m)//.*$")
_PROTO_COMMENT_TOKEN_RE: Final = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*(?=\n|$)',
    re.DOTALL,
)
_PROTO_RPC_RE: Final = re.compile(r"(?m)^[ \t]*rpc\s+[_A-Za-z][_0-9A-Za-z]*\s*\(")
_PROTO_RPC_DECL_RE: Final = re.compile(
    r"\brpc\s+(?P<name>[_A-Za-z][_0-9A-Za-z]{0,127})\s*"
    r"\(\s*(?P<request>[^()]*)\)\s*returns\s*"
    r"\(\s*(?P<response>[^()]*)\)\s*(?P<opening>\{)?",
)
_PROTO_HTTP_RULE_RE: Final = re.compile(r"\boption\s*\(\s*google\.api\.http\s*\)\s*=")
_PROTO_HTTP_VERB_RE: Final = re.compile(r"\b(?P<verb>get|post|put|patch|delete)\s*:")
_PROTO_HTTP_FIELD_RE: Final = re.compile(r"\b(?P<key>[_A-Za-z][_0-9A-Za-z]*)\s*:")
_PROTO_HTTP_VALUE_RE: Final = re.compile(r'\s*"(?P<value>(?:\\.|[^"\\])*)"')
_RPC_NAME_RE: Final = re.compile(r"[_A-Za-z][_0-9A-Za-z]{0,127}\Z")
_PATH_PLACEHOLDER_RE: Final = re.compile(
    r"\{[_A-Za-z][_0-9A-Za-z]*(?:\.[_A-Za-z][_0-9A-Za-z]*)*\}",
)
_BODY_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})
_MAX_FILENAME_BYTES: Final = 255
_SUPPORTED_HTTP_FIELDS: Final = frozenset(
    {"get", "post", "put", "patch", "delete", "body", "additional_bindings", "custom"}
)


class ProtoHurlCompilationError(ValueError):
    pass


def _fail(message: str) -> NoReturn:
    raise ProtoHurlCompilationError(message)


@dataclass(frozen=True, slots=True)
class GeneratedProtoHurlFile:
    relative_path: str
    content: str


@dataclass(frozen=True, slots=True)
class _ProtoRpcDeclaration:
    name: str
    request: str
    response: str
    body: str | None


def compile_proto_http_transcoding_to_hurl(
    proto_text: str,
    *,
    target_url: str,
    rpc_name: str | None = None,
) -> GeneratedProtoHurlFile:
    _validate_proto_text(proto_text)
    normalized_proto = _strip_proto_ignored_text(proto_text)
    rpc_count = len(_PROTO_RPC_RE.findall(normalized_proto))
    http_rule_count = len(_PROTO_HTTP_RULE_RE.findall(normalized_proto))
    if rpc_name is not None:
        # Selection is metadata-only; the compiler never contacts the RPC service.
        method, declared_path = _select_http_rule(proto_text, rpc_name)
        _, target_origin = _safe_target_url(target_url)
        normalized_url = f"{target_origin}{declared_path}"
    else:
        if rpc_count == 0:
            _fail("proto document must define at least one rpc declaration")
        if http_rule_count == 0:
            _fail("proto document must define at least one google.api.http rule")
        method = _first_http_rule_method(normalized_proto)
        normalized_url, target_origin = _safe_target_url(target_url)
    return _render_proto_hurl(
        normalized_url,
        method=method,
        target_origin=target_origin,
        rpc_count=rpc_count,
        http_rule_count=http_rule_count,
    )


def _render_proto_hurl(
    url: str,
    *,
    method: str,
    target_origin: str,
    rpc_count: int,
    http_rule_count: int,
) -> GeneratedProtoHurlFile:
    lines = [
        # The scaffold deliberately contains only fixed, secret-free values.
        "# entroping: tags=smoke,grpc,transcoding",
        "# entroping: source=proto",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: rpc_count={rpc_count}",
        f"# entroping: http_rule_count={http_rule_count}",
        "# entroping: scaffold=http-transcoding-smoke",
        "# entroping: native_grpc_streaming=future",
        "",
        f"{method} {url}",
        "Accept: application/json",
    ]
    if method in _BODY_METHODS:
        lines.extend(
            [
                "Content-Type: application/json",
                "{",
                '  "entroping": "grpc-http-transcoding-smoke"',
                "}",
            ]
        )
    lines.extend(
        [
            "HTTP 200",
            "",
        ]
    )
    return GeneratedProtoHurlFile(
        relative_path=f"tests/generated/{_target_file_stem(url)}.hurl",
        content="\n".join(lines),
    )


def _select_http_rule(proto_text: str, rpc_name: str) -> tuple[str, str]:
    _validate_rpc_selector(rpc_name)
    declaration = _selected_rpc_declaration(proto_text, rpc_name)
    _validate_unary_rpc(declaration)
    if declaration.body is None:
        _fail("selected RPC must define one primary google.api.http rule")
    return _parse_http_option(declaration.body)


def _validate_rpc_selector(rpc_name: str) -> None:
    if _RPC_NAME_RE.fullmatch(rpc_name) is None:
        _fail("rpc_name selector is invalid")
    if contains_secret_like_value(rpc_name):
        _fail("rpc_name selector is unsafe")


def _selected_rpc_declaration(proto_text: str, rpc_name: str) -> _ProtoRpcDeclaration:
    declarations = _rpc_declarations(proto_text)
    matches = tuple(declaration for declaration in declarations if declaration.name == rpc_name)
    if len(matches) != 1:
        _fail("rpc_name selector must match exactly one RPC")

    return matches[0]


def _validate_unary_rpc(declaration: _ProtoRpcDeclaration) -> None:
    if declaration.request.strip().startswith("stream ") or declaration.response.strip().startswith(
        "stream "
    ):
        _fail("rpc_name selector must match one unary RPC")


def _rpc_declarations(proto_text: str) -> tuple[_ProtoRpcDeclaration, ...]:
    source = _mask_proto_comments(proto_text)
    masked = _mask_proto_strings(source)
    declarations: list[_ProtoRpcDeclaration] = []
    for match in _PROTO_RPC_DECL_RE.finditer(masked):
        body: str | None = None
        if match.group("opening") is not None:
            opening = match.end() - 1
            closing = _matching_brace(masked, opening)
            if closing is not None:
                body = source[opening + 1 : closing]
        declarations.append(
            _ProtoRpcDeclaration(
                name=match.group("name"),
                request=match.group("request"),
                response=match.group("response"),
                body=body,
            )
        )
    return tuple(declarations)


def _parse_http_option(body: str) -> tuple[str, str]:
    # Masking preserves source positions while preventing strings/comments from parsing as fields.
    option_source, option_masked = _http_option_parts(body)
    fields = _scan_top_level_http_fields(option_source, option_masked)
    # Only the approved google.api.http field names may reach value parsing.
    methods, body_values, has_unsupported_binding, has_unknown_field = _parse_http_fields(
        option_source,
        fields,
    )
    method, raw_path = _validate_http_fields(
        methods,
        body_values,
        has_unsupported_binding=has_unsupported_binding,
        has_unknown_field=has_unknown_field,
    )
    _validate_http_body(method, body_values)
    return method, _safe_declared_path(raw_path)


def _scan_top_level_http_fields(
    option_source: str,
    option_masked: str,
) -> tuple[re.Match[str], ...]:
    fields: list[re.Match[str]] = []
    depth = 0
    position = 0
    while position < len(option_masked):
        character = option_masked[position]
        if depth:
            depth += character == "{"
            depth -= character == "}"
            position += 1
            continue
        if character.isspace():
            position += 1
            continue
        field = _PROTO_HTTP_FIELD_RE.match(option_masked, position)
        if field is None:
            _fail("selected google.api.http rule has unsupported or malformed tokens")
        fields.append(field)
        position, depth = _advance_http_field_value(
            option_source,
            option_masked,
            field.end(),
        )
    return tuple(fields)


def _advance_http_field_value(
    option_source: str,
    option_masked: str,
    position: int,
) -> tuple[int, int]:
    whitespace = _PROTO_WHITESPACE_RE.match(option_source, position)
    assert whitespace is not None
    position = whitespace.end()
    if position >= len(option_source):
        return position, 0
    value = _PROTO_STRING_RE.match(option_source, position)
    if value is not None:
        return value.end(), 0
    if option_masked[position] == "{":
        return position + 1, 1
    _fail("selected google.api.http rule has an invalid literal")


def _http_option_parts(body: str) -> tuple[str, str]:
    source = _mask_proto_comments(body)
    masked = _mask_proto_strings(source)
    options = tuple(_PROTO_HTTP_RULE_RE.finditer(masked))
    if len(options) != 1:
        _fail("selected RPC must define one primary google.api.http rule")
    option = options[0]
    opening = masked.find("{", option.end())
    if opening < 0:
        _fail("selected google.api.http rule is malformed")
    closing = _matching_brace(masked, opening)
    if closing is None:
        _fail("selected google.api.http rule is malformed")
    return source[opening + 1 : closing], masked[opening + 1 : closing]


def _parse_http_fields(
    option_source: str,
    fields: tuple[re.Match[str], ...],
) -> tuple[list[tuple[str, str]], list[str], bool, bool]:
    if any(field.group("key") in {"additional_bindings", "custom"} for field in fields):
        return [], [], True, False
    if any(field.group("key") not in _SUPPORTED_HTTP_FIELDS for field in fields):
        return [], [], False, True
    methods: list[tuple[str, str]] = []
    body_values: list[str] = []
    for field in fields:
        key = field.group("key")
        value = _http_field_value(option_source, field)
        if key == "body":
            body_values.append(value)
        else:
            methods.append((key.upper(), value))
    return methods, body_values, False, False


def _http_field_value(option_source: str, field: re.Match[str]) -> str:
    value_match = _PROTO_HTTP_VALUE_RE.match(option_source, field.end())
    if value_match is None:
        _fail("selected google.api.http rule has an invalid literal")
    return value_match.group("value")


def _validate_http_fields(
    methods: list[tuple[str, str]],
    body_values: list[str],
    *,
    has_unsupported_binding: bool,
    has_unknown_field: bool,
) -> tuple[str, str]:
    if has_unsupported_binding:
        _fail("selected google.api.http rule has unsupported or duplicate bindings")
    if has_unknown_field:
        _fail("selected google.api.http rule has unsupported or unknown fields")
    if any((len(methods) != 1, len(body_values) > 1)):
        _fail("selected google.api.http rule has duplicate bindings")
    method, raw_path = methods[0]
    return method, raw_path


def _validate_http_body(method: str, body_values: list[str]) -> None:
    # Mutating rules must use the exact body-star policy; no request data is copied.
    if method in _BODY_METHODS and body_values != ["*"]:
        _fail("selected google.api.http rule requires body star")
    if method not in _BODY_METHODS and body_values:
        _fail("selected google.api.http rule forbids a body")


def _safe_declared_path(path: str) -> str:
    # Declared paths are normalized to fixed placeholders before entering Hurl.
    if _declared_path_has_invalid_shape(path):
        _fail("selected google.api.http path is unsafe")
    parts = urlsplit(path)
    if any(
        (
            parts.scheme,
            parts.netloc,
            parts.query,
            parts.fragment,
            any(segment in {".", ".."} for segment in path.split("/")),
        )
    ):
        _fail("selected google.api.http path is unsafe")
    output: list[str] = []
    position = 0
    for match in _PATH_PLACEHOLDER_RE.finditer(path):
        literal = path[position : match.start()]
        if "{" in literal or "}" in literal:
            _fail("selected google.api.http path is unsafe")
        output.extend((literal, "entroping"))
        position = match.end()
    trailing = path[position:]
    if "{" in trailing or "}" in trailing:
        _fail("selected google.api.http path is unsafe")
    output.append(trailing)
    return "".join(output)


def _declared_path_has_invalid_shape(path: str) -> bool:
    # Reject URL/query syntax and secret-like material before any rendering.
    return any(
        (
            not path,
            len(path.encode("utf-8")) > 1_024,
            not path.isascii(),
            not path.startswith("/"),
            path.startswith("//"),
            any(character.isspace() or ord(character) < 32 for character in path),
            any(marker in path for marker in ("%", "?", "#", "=", "*", "\\", "://")),
            contains_secret_like_value(path),
        )
    )


def _mask_proto_comments(proto_text: str) -> str:
    def blank(match: re.Match[str]) -> str:
        token = match.group()
        if token.startswith(('"', "'")):
            return token
        return "".join("\n" if character == "\n" else " " for character in token)

    return _PROTO_COMMENT_TOKEN_RE.sub(blank, proto_text)


def _mask_proto_strings(proto_text: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group())

    return _PROTO_STRING_RE.sub(blank, proto_text)


def _matching_brace(value: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _validate_proto_text(proto_text: str) -> None:
    if proto_text.strip() == "":
        _fail("proto document is required")
    if _contains_disallowed_control(proto_text):
        _fail("proto document contains disallowed control characters")
    if contains_secret_like_value(proto_text):
        _fail("proto document contains secret-like material")


def _strip_proto_ignored_text(proto_text: str) -> str:
    without_strings = _PROTO_STRING_RE.sub("", proto_text)
    without_block_comments = _PROTO_BLOCK_COMMENT_RE.sub("", without_strings)
    return _PROTO_LINE_COMMENT_RE.sub("", without_block_comments)


def _first_http_rule_method(proto_text: str) -> str:
    match = _PROTO_HTTP_VERB_RE.search(proto_text)
    if match is None:
        return "POST"
    return match.group("verb").upper()


def _safe_target_url(value: str) -> tuple[str, str]:
    # The target contributes only a validated origin and a non-sensitive path.
    if not value:
        _fail("gRPC HTTP target URL is required")
    if _contains_disallowed_control(value):
        _fail("gRPC HTTP target URL contains control characters")
    if any(character.isspace() for character in value):
        _fail("gRPC HTTP target URL must not contain whitespace")
    if _has_hurl_template_delimiter(value):
        _fail("gRPC HTTP target URL contains Hurl template delimiters")

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        _fail("gRPC HTTP target URL scheme must be http or https")
    if parts.username is not None or parts.password is not None:
        _fail("gRPC HTTP target URL must not contain credentials")
    if parts.fragment:
        _fail("gRPC HTTP target URL must not contain a fragment")

    try:
        port = parts.port
    except ValueError:
        _fail("gRPC HTTP target URL contains an invalid port")

    hostname = parts.hostname
    if hostname is None:
        _fail("gRPC HTTP target URL must include a host")

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/grpc-transcoding"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    if contains_secret_like_value(normalized_url):
        _fail("gRPC HTTP target URL contains secret-like material")
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            _fail(f"gRPC HTTP target URL contains sensitive query key {key!r}")
        if contains_secret_like_value(value):
            _fail(f"gRPC HTTP target URL contains secret-like query value for {key!r}")


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "grpc-transcoding"
    raw_stem = f"grpc-{parts.hostname or 'target'}-{path}-smoke"
    stem = _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()
    if len(f"{stem}.hurl".encode()) > _MAX_FILENAME_BYTES:
        _fail("generated proto Hurl filename exceeds safe component limit")
    return stem


def _contains_disallowed_control(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
