import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_GRAPHQL_BLOCK_STRING_RE: Final = re.compile(r'"""(?:.|\n)*?"""')
_GRAPHQL_LINE_COMMENT_RE: Final = re.compile(r"(?m)#.*$")
_GRAPHQL_ROOT_OPERATION_BLOCK_RE: Final = re.compile(
    r"\b(?:extend\s+)?type\s+(?P<root>Query|Mutation|Subscription)\b[^{]*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_GRAPHQL_ROOT_FIELD_RE: Final = re.compile(
    r"(?m)^[ \t]*[_A-Za-z][_0-9A-Za-z]*\s*(?:\([^{}]*\)\s*)?:",
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
) -> GeneratedGraphqlHurlFile:
    _validate_schema_sdl(schema_sdl)
    categories = _operation_categories(schema_sdl)
    if "query" not in categories:
        msg = "GraphQL SDL must define at least one Query field for smoke scaffolding"
        raise GraphqlHurlCompilationError(msg)

    normalized_url, target_origin = _safe_target_url(target_url)
    category_text = ",".join(categories)
    lines = [
        "# entroping: tags=smoke,graphql",
        "# entroping: source=graphql-sdl",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: operation_categories={category_text}",
        "# entroping: scaffold=typename-smoke",
        "",
        f"POST {normalized_url}",
        "Content-Type: application/json",
        "{",
        f'  "query": "{_GRAPHQL_SMOKE_QUERY}"',
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
