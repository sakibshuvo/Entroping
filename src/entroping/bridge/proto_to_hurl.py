import re
from dataclasses import dataclass
from typing import Final, NoReturn
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.bridge.target_url import contains_unsafe_target_authority, host_with_port
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
_PROTO_IDENTIFIER_RE: Final = re.compile(
    r"[_A-Za-z][_0-9A-Za-z]*(?:\.[_A-Za-z][_0-9A-Za-z]*)*\Z"
)  # ASCII names
_PROTO_FIELD_NAME_RE: Final = re.compile(r"(?:[_A-Za-z]\w*|\[[A-Za-z_]\w*[./\w]*\])\Z")
_PROTO_DISALLOWED_CONTROL_RE: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PROTO_OPTION_TOKEN_RE: Final = re.compile(
    r"""\s*(?:(?:"(?:\\(?:[abfnrtv\\'"]|x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|u[0-9A-Fa-f]{4}|U(?:000[0-9A-Fa-f]{5}|0010[0-9A-Fa-f]{4}))|[^"\\\r\n])*"|'(?:\\(?:[abfnrtv\\'"]|x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|u[0-9A-Fa-f]{4}|U(?:000[0-9A-Fa-f]{5}|0010[0-9A-Fa-f]{4}))|[^'\\\r\n])*')(?:\s*(?:"(?:\\(?:[abfnrtv\\'"]|x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|u[0-9A-Fa-f]{4}|U(?:000[0-9A-Fa-f]{5}|0010[0-9A-Fa-f]{4}))|[^"\\\r\n])*"|'(?:\\(?:[abfnrtv\\'"]|x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|u[0-9A-Fa-f]{4}|U(?:000[0-9A-Fa-f]{5}|0010[0-9A-Fa-f]{4}))|[^'\\\r\n])*'))*|\[[_A-Za-z][_0-9A-Za-z]*(?:[./][_A-Za-z][_0-9A-Za-z]*)*\]|(?:[_A-Za-z][_0-9A-Za-z]*|\(\.?[_A-Za-z][_0-9A-Za-z]*(?:\.[_A-Za-z][_0-9A-Za-z]*)*\))(?:\.(?:[_A-Za-z][_0-9A-Za-z]*|\(\.?[_A-Za-z][_0-9A-Za-z]*(?:\.[_A-Za-z][_0-9A-Za-z]*)*\)))*|[-+]?(?:(?:\d+\.\d*|\.\d+|\d+)[eE][+-]?\d+|\d+\.\d*|\.\d+|0[xX][0-9A-Fa-f]+|0[0-7]+|0|[1-9][0-9]*|inf|nan)|[{}\[\]():=,;<>+-]|\s*\Z)"""
)
_PROTO_COLLECTION_CLOSERS: Final = {"{": "};,", "[": "],", "<": ">;,"}  # bounded aggregates
_MALFORMED_OPTION_ERROR: Final = "selected HTTP rule is malformed"  # content-free error
_UNSUPPORTED_BINDING_ERROR: Final = (
    "selected google.api.http rule has unsupported or duplicate bindings"
)
_UNKNOWN_FIELD_ERROR: Final = "selected google.api.http rule has unsupported or unknown fields"
_DUPLICATE_BINDING_ERROR: Final = "selected google.api.http rule has duplicate bindings"
_BODY_STAR_ERROR: Final = "selected google.api.http rule requires body star"
_BODY_FORBID_ERROR: Final = "selected google.api.http rule forbids a body"
_MSG: Final = frozenset({"{", "<"})  # message aggregate delimiters
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


def _require(condition: bool, message: str) -> None:
    condition or _fail(message)


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
    _require(proto_text.strip() != "", "proto document is required")  # required input
    _require(
        _PROTO_DISALLOWED_CONTROL_RE.search(proto_text) is None,
        "proto document contains disallowed control characters",
    )
    _require(
        not contains_secret_like_value(proto_text), "proto document contains secret-like material"
    )
    normalized_proto = _PROTO_LINE_COMMENT_RE.sub(  # omitted mode keeps legacy scan
        "", _PROTO_BLOCK_COMMENT_RE.sub("", _PROTO_STRING_RE.sub("", proto_text))
    )
    rpc_count = len(_PROTO_RPC_RE.findall(normalized_proto))
    http_rule_count = len(_PROTO_HTTP_RULE_RE.findall(normalized_proto))
    if rpc_name is not None:
        method, declared_path = _select_http_rule(proto_text, rpc_name)
        _, target_origin = _safe_target_url(target_url)
        normalized_url = f"{target_origin}{declared_path}"
    else:
        if rpc_count == 0:
            _fail("proto document must define at least one rpc declaration")
        if http_rule_count == 0:
            _fail("proto document must define at least one google.api.http rule")
        verb = _PROTO_HTTP_VERB_RE.search(normalized_proto)
        method = verb.group("verb").upper() if verb is not None else "POST"
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
    body = (
        'Content-Type: application/json\n{\n  "entroping": "grpc-http-transcoding-smoke"\n}\n'
        if method in _BODY_METHODS
        else ""
    )
    content = (
        "# entroping: tags=smoke,grpc,transcoding\n"
        "# entroping: source=proto\n"
        f"# entroping: target_origin={target_origin}\n"
        f"# entroping: rpc_count={rpc_count}\n"
        f"# entroping: http_rule_count={http_rule_count}\n"
        "# entroping: scaffold=http-transcoding-smoke\n"
        "# entroping: native_grpc_streaming=future\n\n"
        f"{method} {url}\nAccept: application/json\n"
        f"{body}HTTP 200\n"
    )
    parts = urlsplit(url)
    path = parts.path.strip("/") or "grpc-transcoding"
    raw_stem = f"grpc-{parts.hostname or 'target'}-{path}-smoke"
    stem = _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()
    _require(
        len(f"{stem}.hurl".encode()) <= _MAX_FILENAME_BYTES,
        "generated proto Hurl filename exceeds safe component limit",
    )
    return GeneratedProtoHurlFile(
        relative_path=f"tests/generated/{stem}.hurl",
        content=content,
    )


def _select_http_rule(proto_text: str, rpc_name: str) -> tuple[str, str]:
    _require(
        _RPC_NAME_RE.fullmatch(rpc_name) is not None, "rpc_name selector is invalid"
    )  # ASCII selector
    _require(not contains_secret_like_value(rpc_name), "rpc_name selector is unsafe")
    declarations = _rpc_declarations(proto_text)
    matches = tuple(declaration for declaration in declarations if declaration.name == rpc_name)
    _require(len(matches) == 1, "rpc_name selector must match exactly one RPC")
    declaration = matches[0]
    _require(
        not (
            declaration.request.strip().startswith("stream ")
            or declaration.response.strip().startswith("stream ")
        ),
        "rpc_name selector must match one unary RPC",
    )
    body = declaration.body or _fail("selected RPC must define one primary google.api.http rule")
    return _parse_http_option(body)


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
    option_source, option_masked = _http_option_parts(body)  # preserve source positions
    fields = _scan_top_level_http_fields(option_source, option_masked)  # approved fields
    parsed_fields = _parse_http_fields(option_source, fields)
    methods, body_values, has_unsupported_binding, has_unknown_field = parsed_fields
    method, raw_path = _validate_http_fields(
        methods,
        body_values,
        has_unsupported_binding=has_unsupported_binding,
        has_unknown_field=has_unknown_field,
    )
    _require(method not in _BODY_METHODS or body_values == ["*"], _BODY_STAR_ERROR)
    _require(method in _BODY_METHODS or not body_values, _BODY_FORBID_ERROR)
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
    position = next(_PROTO_WHITESPACE_RE.finditer(option_source, position)).end()
    if position >= len(option_source):
        return position, 0
    value = _PROTO_STRING_RE.match(option_source, position)
    if value is not None:
        return value.end(), 0
    if option_masked[position] == "{":
        return position + 1, 1
    return _fail("selected google.api.http rule has an invalid literal")


def _http_option_parts(body: str) -> tuple[str, str]:
    source = _mask_proto_comments(body)  # preserve source offsets
    masked = _mask_proto_strings(source)
    options = tuple(_PROTO_HTTP_RULE_RE.finditer(masked))
    if len(options) != 1:
        _fail("selected RPC must define one primary google.api.http rule")
    option = options[0]  # adjacent aggregate
    opening_match = _PROTO_WHITESPACE_RE.match(masked, option.end()) or _fail(
        "selected google.api.http rule is malformed"
    )
    opening = opening_match.end()
    _require(masked.startswith("{", opening), "selected google.api.http rule is malformed")
    closing = _matching_brace(masked, opening) or len(masked)  # balance aggregate braces
    terminator_match = _PROTO_WHITESPACE_RE.match(masked, closing + 1) or _fail(
        "selected google.api.http rule is malformed"
    )
    terminator = terminator_match.end()
    _require(masked.startswith(";", terminator), "selected google.api.http rule is malformed")
    _validate_option_tail(source[terminator + 1 :])  # sibling statements
    return source[opening + 1 : closing], masked[opening + 1 : closing]


def _validate_option_tail(source_tail: str) -> None:
    tokens: list[str] = []
    position = 0
    for token in _PROTO_OPTION_TOKEN_RE.finditer(source_tail):
        _require(token.start() == position, _MALFORMED_OPTION_ERROR)
        position = token.end()
        value = token.group().strip()
        tokens.extend([value] if value else [])
    _require(position == len(source_tail), _MALFORMED_OPTION_ERROR)
    tokens.extend(("", "", "", ""))  # sentinels make truncation fail closed
    index = 0
    while tokens[index]:
        _require(tokens[index] == "option", _MALFORMED_OPTION_ERROR)
        option_name = tokens[index + 1].replace("(", "").replace(")", "").lstrip(".")
        _require(_PROTO_IDENTIFIER_RE.fullmatch(option_name) is not None, _MALFORMED_OPTION_ERROR)
        _require(tokens[index + 2] == "=", _MALFORMED_OPTION_ERROR)
        index = _consume_option_value(tokens, index + 3, 0)
        _require(tokens[index] == ";", _MALFORMED_OPTION_ERROR)
        index += 1


def _consume_option_value(tokens: list[str], index: int, depth: int) -> int:
    token = tokens[index]
    if token in {"{", "[", "<"}:
        _require(depth < 64, _MALFORMED_OPTION_ERROR)
        closing, index = _PROTO_COLLECTION_CLOSERS[token], index + 1  # one expected delimiter
        while tokens[index] != closing[0]:
            offset = 2 * (token in _MSG)
            if token in _MSG:
                valid_name = _PROTO_FIELD_NAME_RE.fullmatch(tokens[index]) is not None
                _require(valid_name, _MALFORMED_OPTION_ERROR)
                field, next_token = tokens[index + 1 : index + 3]
                offset -= int(field in _MSG) + int(field == "[" and next_token in _MSG.union({"]"}))
                _require(field == ":" or offset == 1, _MALFORMED_OPTION_ERROR)
            index = _consume_option_value(tokens, index + offset, depth + 1)
            object_field = token in _MSG
            object_field &= _PROTO_FIELD_NAME_RE.fullmatch(tokens[index]) is not None
            _require(tokens[index] in closing or object_field, _MALFORMED_OPTION_ERROR)
            index += tokens[index] in {",", ";"}
        return index + 1
    if token in {"+", "-"}:
        following = tokens[index + 1]
        eligible = following[:1] in "0123456789." or following in {"inf", "nan"}
        _require(eligible, _MALFORMED_OPTION_ERROR)
        return index + 2
    _require(token.startswith(tuple("_+-.\"'")) or token[:1].isalnum(), _MALFORMED_OPTION_ERROR)
    return index + 1


def _parse_http_fields(
    option_source: str,
    fields: tuple[re.Match[str], ...],
) -> tuple[list[tuple[str, str]], list[str], bool, bool]:
    keys = frozenset(field.group("key") for field in fields)
    has_unsupported_binding = bool(keys & {"additional_bindings", "custom"})
    has_unknown_field = bool(keys - _SUPPORTED_HTTP_FIELDS)
    if any((has_unsupported_binding, has_unknown_field)):
        return [], [], has_unsupported_binding, has_unknown_field
    methods: list[tuple[str, str]] = []
    body_values: list[str] = []
    for field in fields:
        key = field.group("key")
        value_match = _PROTO_HTTP_VALUE_RE.match(option_source, field.end()) or _fail(
            "selected google.api.http rule has an invalid literal"
        )
        method_field = (key.upper(), value := value_match.group("value"))
        field_methods, field_bodies = {"body": ((), (value,))}.get(key, ((method_field,), ()))
        methods.extend(field_methods)
        body_values.extend(field_bodies)
    return methods, body_values, False, False


def _validate_http_fields(
    methods: list[tuple[str, str]],
    body_values: list[str],
    *,
    has_unsupported_binding: bool,
    has_unknown_field: bool,
) -> tuple[str, str]:
    _require(not has_unsupported_binding, _UNSUPPORTED_BINDING_ERROR)
    _require(not has_unknown_field, _UNKNOWN_FIELD_ERROR)
    _require(len(methods) == 1 and len(body_values) <= 1, _DUPLICATE_BINDING_ERROR)
    return methods[0]


def _safe_declared_path(path: str) -> str:
    _require(
        not any(
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
        ),
        "selected google.api.http path is unsafe",
    )
    parts = urlsplit(path)
    _require(
        not any(
            (
                parts.scheme,
                parts.netloc,
                parts.query,
                parts.fragment,
                any(segment in {".", ".."} for segment in path.split("/")),
            )
        ),
        "selected google.api.http path is unsafe",
    )
    output, position = list[str](), 0
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


def _mask_proto_comments(proto_text: str) -> str:
    return _PROTO_COMMENT_TOKEN_RE.sub(
        lambda match: (
            match.group()
            if match.group().startswith(('"', "'"))
            else "".join("\n" if character == "\n" else " " for character in match.group())
        ),
        proto_text,
    )


def _mask_proto_strings(proto_text: str) -> str:
    return _PROTO_STRING_RE.sub(
        lambda match: "".join("\n" if character == "\n" else " " for character in match.group()),
        proto_text,
    )


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


def _safe_target_url(value: str) -> tuple[str, str]:
    _require(value != "", "gRPC HTTP target URL is required")
    _require(
        not contains_unsafe_target_authority(value),
        "gRPC HTTP target URL contains unsafe authority characters",
    )
    _require(
        _PROTO_DISALLOWED_CONTROL_RE.search(value) is None,
        "gRPC HTTP target URL contains control characters",
    )
    _require(
        not any(character.isspace() for character in value),
        "gRPC HTTP target URL must not contain whitespace",
    )
    _require(
        "{{" not in value and "}}" not in value,
        "gRPC HTTP target URL contains Hurl template delimiters",
    )
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    _require(scheme in {"http", "https"}, "gRPC HTTP target URL scheme must be http or https")
    _require(
        parts.username is None and parts.password is None,
        "gRPC HTTP target URL must not contain credentials",
    )
    _require(not parts.fragment, "gRPC HTTP target URL must not contain a fragment")
    try:
        port = parts.port
    except ValueError:
        _fail("gRPC HTTP target URL contains an invalid port")
    hostname = parts.hostname or _fail("gRPC HTTP target URL must include a host")
    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()  # normalize origin metadata
    normalized_netloc = host_with_port(normalized_host, port)
    normalized_path = parts.path or "/grpc-transcoding"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    _require(  # reject secrets before artifact creation
        contains_secret_like_value(normalized_url) is False,
        "gRPC HTTP target URL contains secret-like material",
    )
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            _fail(f"gRPC HTTP target URL contains sensitive query key {key!r}")
        if contains_secret_like_value(value):
            _fail(f"gRPC HTTP target URL contains secret-like query value for {key!r}")
