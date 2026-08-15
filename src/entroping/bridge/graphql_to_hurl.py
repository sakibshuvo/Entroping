import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_GRAPHQL_BLOCK_STRING_RE: Final = re.compile(r'"""(?:.|\n)*?"""')
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
    r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\])*"|#[^\n]*|[_A-Za-z][_0-9A-Za-z]*|[{}()[\]!:$=@|&]',
)
_GRAPHQL_SMOKE_QUERY: Final = "query EntropingSmoke { __typename }"


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
    if _GRAPHQL_NAME_RE.fullmatch(query_field) is None:
        raise GraphqlHurlCompilationError("GraphQL query_field must be a GraphQL name")
    blocks = [
        (body, is_extension)
        for root, body, is_extension in _operation_root_blocks(schema_sdl)
        if root == "Query"
    ]
    if sum(not is_extension for _, is_extension in blocks) != 1:
        raise GraphqlHurlCompilationError(
            "GraphQL SDL must define exactly one canonical Query root",
        )
    matches = [
        (has_arguments, has_directive)
        for body, _ in blocks
        for name, has_arguments, has_directive in _query_fields(body)
        if name == query_field
    ]
    if len(matches) != 1 or matches[0] != (False, False):
        raise GraphqlHurlCompilationError(
            "GraphQL query_field must match one zero-argument directive-free Query field",
        )
    return query_field


def _operation_root_blocks(
    schema_sdl: str,
) -> list[tuple[str, list[tuple[str, str]], bool]]:
    tokens = _graphql_tokens(schema_sdl)
    blocks: list[tuple[str, list[tuple[str, str]], bool]] = []
    index = 0
    while index < len(tokens):
        value = tokens[index][1]
        if (
            value == "type"
            and index + 1 < len(tokens)
            and tokens[index + 1][1] in {"Query", "Mutation", "Subscription"}
        ):
            opening = index + 2
            while opening < len(tokens) and tokens[opening][1] != "{":
                if tokens[opening][1] == "(":
                    closing = _matching_token(tokens, opening, "(", ")")
                    opening = len(tokens) if closing is None else closing + 1
                else:
                    opening += 1
            opening = min(opening, len(tokens) - 1)
            closing = _matching_token(tokens, opening, "{", "}")
            if closing is not None:
                is_extension = index > 0 and tokens[index - 1][1] == "extend"
                blocks.append((tokens[index + 1][1], tokens[opening + 1 : closing], is_extension))
                index = closing
        elif value == "{":
            closing = _matching_token(tokens, index, "{", "}")
            if closing is not None:
                index = closing
        index += 1
    return blocks


def _graphql_tokens(schema_sdl: str) -> list[tuple[str, str]]:
    return [
        ("name" if value[0] == "_" or value[0].isalpha() else "punctuation", value)
        for match in _GRAPHQL_TOKEN_RE.finditer(schema_sdl)
        if (value := match.group())[0] not in '#"'
    ]


def _matching_token(
    tokens: list[tuple[str, str]],
    opening: int,
    open_value: str,
    close_value: str,
) -> int | None:
    depth = 0
    for index, (_, value) in enumerate(tokens[opening:], opening):
        depth += 1 if value == open_value else -1 if value == close_value else 0
        if depth == 0:
            return index
    return None


def _query_fields(body: list[tuple[str, str]]) -> list[tuple[str, bool, bool]]:
    fields: list[tuple[str, bool, bool]] = []
    index = 0
    depth = 0
    while index + 1 < len(body):
        value = body[index][1]
        if value in "([":
            depth += 1
        elif value in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and body[index][0] == "name" and body[index + 1][1] in {":", "("}:
            has_arguments = body[index + 1][1] == "("
            colon = index + 1
            if has_arguments:
                closing = _matching_token(body, colon, "(", ")")
                if closing is None:
                    index += 1
                    continue
                colon = closing + 1
            if colon + 1 < len(body) and body[colon][1] == ":":
                if body[colon + 1][1] == "[":
                    closing = _matching_token(body, colon + 1, "[", "]")
                    type_end = len(body) if closing is None else closing + 1
                else:
                    type_end = colon + 2
                type_end += type_end < len(body) and body[type_end][1] == "!"
                fields.append(
                    (value, has_arguments, type_end < len(body) and body[type_end][1] == "@")
                )
        index += 1
    return fields


def _validate_schema_sdl(schema_sdl: str) -> None:
    if schema_sdl.strip() == "":
        msg = "GraphQL SDL is required"
        raise GraphqlHurlCompilationError(msg)
    if _contains_disallowed_control(schema_sdl):
        msg = "GraphQL SDL contains disallowed control characters"
        raise GraphqlHurlCompilationError(msg)
    if contains_secret_like_value(schema_sdl):
        msg = "GraphQL SDL contains secret-like material"
        raise GraphqlHurlCompilationError(msg)


def _selected_operation_categories(schema_sdl: str) -> tuple[str, ...]:
    categories = {
        root.lower() for root, body, _ in _operation_root_blocks(schema_sdl) if _query_fields(body)
    }
    return tuple(sorted(categories))


def _operation_categories(schema_sdl: str) -> tuple[str, ...]:
    stripped = _strip_graphql_ignored_text(schema_sdl)
    categories: list[str] = []
    for match in _GRAPHQL_ROOT_OPERATION_BLOCK_RE.finditer(stripped):
        body = match.group("body")
        if _GRAPHQL_ROOT_FIELD_RE.search(body) is None:
            continue
        root = match.group("root").lower()
        if root not in categories:
            categories.append(root)
    categories.sort()
    return tuple(categories)


def _strip_graphql_ignored_text(schema_sdl: str) -> str:
    without_block_strings = _GRAPHQL_BLOCK_STRING_RE.sub("", schema_sdl)
    return _GRAPHQL_LINE_COMMENT_RE.sub("", without_block_strings)


def _safe_target_url(value: str) -> tuple[str, str]:
    if not value:
        msg = "GraphQL target URL is required"
        raise GraphqlHurlCompilationError(msg)
    if _contains_disallowed_control(value):
        msg = "GraphQL target URL contains control characters"
        raise GraphqlHurlCompilationError(msg)
    if any(character.isspace() for character in value):
        msg = "GraphQL target URL must not contain whitespace"
        raise GraphqlHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "GraphQL target URL contains Hurl template delimiters"
        raise GraphqlHurlCompilationError(msg)

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        msg = "GraphQL target URL scheme must be http or https"
        raise GraphqlHurlCompilationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "GraphQL target URL must not contain credentials"
        raise GraphqlHurlCompilationError(msg)
    if parts.fragment:
        msg = "GraphQL target URL must not contain a fragment"
        raise GraphqlHurlCompilationError(msg)

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
    if contains_secret_like_value(normalized_url):
        msg = "GraphQL target URL contains secret-like material"
        raise GraphqlHurlCompilationError(msg)
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


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
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
