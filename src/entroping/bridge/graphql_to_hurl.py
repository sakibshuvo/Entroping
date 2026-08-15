import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_GRAPHQL_IGNORED_LEXEME_RE: Final = re.compile(r'"""|"(?:\\.|[^"\\])*"|#[^\n]*')
_GRAPHQL_LINE_COMMENT_RE: Final = re.compile(r"(?m)#.*$")
_GRAPHQL_NAME_RE: Final = re.compile(r"[_A-Za-z][_0-9A-Za-z]{0,127}")
_GRAPHQL_ROOT_OPERATION_BLOCK_RE: Final = re.compile(
    r"\b(?:extend\s+)?type\s+(?P<root>Query|Mutation|Subscription)\b[^{]*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_GRAPHQL_ROOT_FIELD_RE: Final = re.compile(
    r"(?m)^[ \t]*[_A-Za-z][_0-9A-Za-z]*\s*(?:\([^{}]*\)\s*)?:",
)
_GRAPHQL_TOKEN_RE: Final = re.compile(
    r'"(?:\\.|[^"\\])*"|#[^\n]*|[_A-Za-z][_0-9A-Za-z]*|[{}()[\]!:$=@|&]',
)
_GRAPHQL_SMOKE_QUERY: Final = "query EntropingSmoke { __typename }"
_DISALLOWED_CONTROL_CHARACTERS: Final = "".join(
    map(chr, (*range(0, 9), *range(11, 13), *range(14, 32)))
)
_ROOT_OPERATION_TOKENS: Final = frozenset(
    {("type", "Query"), ("type", "Mutation"), ("type", "Subscription")}
)


class GraphqlHurlCompilationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedGraphqlHurlFile:
    relative_path: str
    content: str


def compile_graphql_sdl_to_hurl(
    schema_sdl: str,
    *,
    target_url: str,
    query_field: str | None = None,
) -> GeneratedGraphqlHurlFile:
    _validate_schema_sdl(schema_sdl)
    selected_query = _selected_query(schema_sdl, query_field)
    categories = (
        _operation_categories(schema_sdl)
        if query_field is None
        else _selected_operation_categories(schema_sdl)
    )
    if "query" not in categories:
        msg = "GraphQL SDL must define at least one Query field for smoke scaffolding"
        raise GraphqlHurlCompilationError(msg)

    normalized_url, target_origin = _safe_target_url(target_url)
    query_text = (
        _GRAPHQL_SMOKE_QUERY
        if selected_query is None
        else (f"query EntropingSmoke {{ {selected_query} }}")
    )
    lines = [
        "# entroping: tags=smoke,graphql",
        "# entroping: source=graphql-sdl",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: operation_categories={','.join(categories)}",
        "# entroping: scaffold=typename-smoke",
        "",
        f"POST {normalized_url}",
        "Content-Type: application/json",
        "{",
        f'  "query": "{query_text}"',
        "}",
        "HTTP 200",
        "[Asserts]",
        'jsonpath "$.errors" not exists',
        "",
    ]
    return GeneratedGraphqlHurlFile(
        relative_path=f"tests/generated/{_target_file_stem(normalized_url)}.hurl",
        content="\n".join(lines),
    )


def _selected_query(schema_sdl: str, query_field: str | None) -> str | None:
    if query_field is None:
        return None
    _raise_for_invalid(
        (
            (
                _GRAPHQL_NAME_RE.fullmatch(query_field) is None,
                "GraphQL query_field must be a GraphQL name",
            ),
        )
    )
    blocks = [
        (body, is_extension)
        for root, body, is_extension in _operation_root_blocks(schema_sdl)
        if root == "Query"
    ]
    _raise_for_invalid(
        (
            (
                sum(not is_extension for _, is_extension in blocks) != 1,
                "GraphQL SDL must define exactly one canonical Query root",
            ),
        )
    )
    matches = [
        (has_arguments, has_directive)
        for body, _ in blocks
        for name, has_arguments, has_directive in _query_fields(body)
        if name == query_field
    ]
    _raise_for_invalid(
        (
            (
                matches != [(False, False)],
                "GraphQL query_field must match one zero-argument directive-free Query field",
            ),
        )
    )
    return query_field


def _operation_root_blocks(
    schema_sdl: str,
) -> list[tuple[str, list[tuple[str, str]], bool]]:
    tokens = [*_graphql_tokens(schema_sdl), ("punctuation", "")]
    return [
        block
        for index in _top_level_indices(tokens)
        if (block := _root_block(tokens, index)) is not None
    ]


def _root_block(
    tokens: list[tuple[str, str]], index: int
) -> tuple[str, list[tuple[str, str]], bool] | None:
    if (tokens[index][1], tokens[index + 1][1]) not in _ROOT_OPERATION_TOKENS:
        return None
    opening = _type_body_opening(tokens, index + 2)
    if opening is None:
        return None
    closing = _matching_token(tokens, opening, "{", "}")
    return (
        None
        if closing is None
        else (
            tokens[index + 1][1],
            tokens[opening + 1 : closing],
            tokens[index - 1 : index] == [("name", "extend")],
        )
    )


def _top_level_indices(tokens: list[tuple[str, str]]) -> list[int]:
    depth = 0
    indices: list[int] = []
    for index, (_, value) in enumerate(tokens[:-1]):
        if depth == 0:
            indices.append(index)
        depth += (value == "{") - (value == "}")
    return indices


# Only a complete canonical root header may lead the selector to a body.
def _type_body_opening(tokens: list[tuple[str, str]], opening: int) -> int | None:
    parsers = {"implements": _implements_end, "@": _directive_end}
    while tokens[opening][1] != "{":
        parser = parsers.get(tokens[opening][1])
        if parser is None:
            return None
        next_opening = parser(tokens, opening)
        if next_opening is None:
            return None
        opening = next_opening
        _ = parsers.pop("implements", None)
    return opening


def _implements_end(tokens: list[tuple[str, str]], opening: int) -> int | None:
    opening += 1 + (tokens[opening + 1][1] == "&")
    if tokens[opening][0] != "name":
        return None
    opening += 1
    while tokens[opening][1] == "&":
        opening += 1
        if tokens[opening][0] != "name":
            return None
        opening += 1
    return opening


def _directive_end(tokens: list[tuple[str, str]], opening: int) -> int | None:
    if tokens[opening + 1][0] != "name":
        return None
    opening += 2
    return _parenthesized_end(tokens, opening) if tokens[opening][1] == "(" else opening


def _parenthesized_end(tokens: list[tuple[str, str]], opening: int) -> int | None:
    closing = _matching_token(tokens, opening, "(", ")")
    return None if closing is None else closing + 1


def _graphql_tokens(schema_sdl: str) -> list[tuple[str, str]]:
    return [
        ("name" if value[0].isidentifier() else "punctuation", value)
        for match in _GRAPHQL_TOKEN_RE.finditer(_strip_graphql_block_strings(schema_sdl))
        if (value := match.group())[0] not in '#"'
    ]


def _matching_token(
    tokens: list[tuple[str, str]],
    opening: int,
    open_value: str,
    close_value: str,
) -> int | None:
    depth = 0
    for index in range(opening, len(tokens)):
        value = tokens[index][1]
        depth += (value == open_value) - (value == close_value)
        if depth == 0:
            return index
    return None


# A field candidate must consume its return type before another token can begin.
def _query_fields(body: list[tuple[str, str]]) -> list[tuple[str, bool, bool]]:
    fields: list[tuple[str, bool, bool]] = []
    index = 0
    tokens = [*body, ("punctuation", ""), ("punctuation", "@")]
    while index < len(body):
        kind, value = tokens[index]
        separator = tokens[index + 1][1]
        if (kind, separator) not in {("name", ":"), ("name", "(")}:
            index += 1
            continue
        has_arguments = separator == "("
        colon = _matching_token(tokens, index + 1, "(", ")") if has_arguments else index
        if colon is None:
            return []
        colon += 1
        if tokens[colon][1] != ":":
            index = colon
            continue
        tail = _field_tail(tokens, colon + 1)
        if tail is None:
            return []
        type_end, has_directive = tail
        fields.append((value, has_arguments, has_directive))
        index = type_end
    return fields


def _field_tail(tokens: list[tuple[str, str]], type_start: int) -> tuple[int, bool] | None:
    type_end = _return_type_end(tokens, type_start)
    if type_end is None:
        return None
    has_directive = {"@": True, "": False}.get(tokens[type_end][1])
    if has_directive is not None:
        return type_end, has_directive
    return (
        (type_end, False)
        if (tokens[type_end][0], tokens[type_end + 1][1]) in {("name", ":"), ("name", "(")}
        else None
    )


def _return_type_end(tokens: list[tuple[str, str]], type_start: int) -> int | None:
    if {"name": False, "punctuation": tokens[type_start][1] != "["}[tokens[type_start][0]]:
        return None
    type_end = (
        _matching_token(tokens, type_start, "[", "]")
        if tokens[type_start][1] == "["
        else type_start
    )
    return None if type_end is None else type_end + 1 + (tokens[type_end + 1][1] == "!")


def _validate_schema_sdl(schema_sdl: str) -> None:
    _raise_for_invalid(
        (
            (schema_sdl.strip() == "", "GraphQL SDL is required"),
            (
                _contains_disallowed_control(schema_sdl),
                "GraphQL SDL contains disallowed control characters",
            ),
        )
    )
    _strip_graphql_block_strings(schema_sdl)
    _raise_for_invalid(
        ((contains_secret_like_value(schema_sdl), "GraphQL SDL contains secret-like material"),)
    )


def _selected_operation_categories(schema_sdl: str) -> tuple[str, ...]:
    categories = {
        root.lower() for root, body, _ in _operation_root_blocks(schema_sdl) if _query_fields(body)
    }
    return tuple(sorted(categories))


def _operation_categories(schema_sdl: str) -> tuple[str, ...]:
    categories = _legacy_operation_categories(schema_sdl)
    return _without_query(categories) if _has_invalid_query_header(schema_sdl) else categories


def _legacy_operation_categories(schema_sdl: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                match.group("root").lower()
                for match in _GRAPHQL_ROOT_OPERATION_BLOCK_RE.finditer(
                    _strip_graphql_ignored_text(schema_sdl)
                )
                if _GRAPHQL_ROOT_FIELD_RE.search(match.group("body")) is not None
            }
        )
    )


def _without_query(categories: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(category for category in categories if category != "query")


def _has_invalid_query_header(schema_sdl: str) -> bool:
    blocks = _operation_root_blocks(schema_sdl)
    tokens = [*_graphql_tokens(schema_sdl), ("punctuation", "")]
    return any(
        (tokens[index][1], tokens[index + 1][1]) == ("type", "Query")
        for index in range(len(tokens) - 1)
    ) and not any(root == "Query" for root, _, _ in blocks)


def _strip_graphql_ignored_text(schema_sdl: str) -> str:
    return _GRAPHQL_LINE_COMMENT_RE.sub("", _strip_graphql_block_strings(schema_sdl))


# Descriptions are removed before structural tokenization, never interpreted as SDL.
def _strip_graphql_block_strings(schema_sdl: str) -> str:
    parts: list[str] = []
    start = index = 0
    while (marker := _GRAPHQL_IGNORED_LEXEME_RE.search(schema_sdl, index)) is not None:
        start, index = _advance_ignored_segment(parts, schema_sdl, marker, start)
    parts.append(schema_sdl[start:])
    return "".join(parts)


def _advance_ignored_segment(
    parts: list[str], schema_sdl: str, marker: re.Match[str], start: int
) -> tuple[int, int]:
    if marker.group() != '"""':
        return start, marker.end()
    parts.append(schema_sdl[start : marker.start()])
    closing = _block_string_end(schema_sdl, marker.end())
    return closing + 3, closing + 3


def _block_string_end(schema_sdl: str, index: int) -> int:
    while (closing := schema_sdl.find('"""', index)) != -1:
        if schema_sdl[closing - 1] != "\\":
            return closing
        index = closing + 3
    raise GraphqlHurlCompilationError("GraphQL SDL contains an unterminated block string")


def _safe_target_url(value: str) -> tuple[str, str]:
    _raise_for_invalid(
        (
            (not value, "GraphQL target URL is required"),
            (_contains_disallowed_control(value), "GraphQL target URL contains control characters"),
            (
                any(character.isspace() for character in value),
                "GraphQL target URL must not contain whitespace",
            ),
            (
                _has_hurl_template_delimiter(value),
                "GraphQL target URL contains Hurl template delimiters",
            ),
        )
    )

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    _raise_for_invalid(
        (
            (scheme not in {"http", "https"}, "GraphQL target URL scheme must be http or https"),
            (
                parts.username is not None or parts.password is not None,
                "GraphQL target URL must not contain credentials",
            ),
            (bool(parts.fragment), "GraphQL target URL must not contain a fragment"),
        )
    )

    try:
        port = parts.port
    except ValueError as exc:
        msg = "GraphQL target URL contains an invalid port"
        raise GraphqlHurlCompilationError(msg) from exc

    hostname = parts.hostname
    if hostname is None:
        msg = "GraphQL target URL must include a host"
        raise GraphqlHurlCompilationError(msg)

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/graphql"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    _raise_for_invalid(
        (
            (
                contains_secret_like_value(normalized_url),
                "GraphQL target URL contains secret-like material",
            ),
        )
    )
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _raise_for_invalid(checks: tuple[tuple[bool, str], ...]) -> None:
    for invalid, message in checks:
        if invalid:
            raise GraphqlHurlCompilationError(message)


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            msg = f"GraphQL target URL contains sensitive query key {key!r}"
            raise GraphqlHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = f"GraphQL target URL contains secret-like query value for {key!r}"
            raise GraphqlHurlCompilationError(msg)


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "graphql"
    raw_stem = f"graphql-{parts.hostname or 'target'}-{path}-smoke"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _contains_disallowed_control(value: str) -> bool:
    return any(character in _DISALLOWED_CONTROL_CHARACTERS for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
