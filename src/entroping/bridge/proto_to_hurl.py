import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")
_PROTO_STRING_RE: Final = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_PROTO_BLOCK_COMMENT_RE: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_PROTO_LINE_COMMENT_RE: Final = re.compile(r"(?m)//.*$")
_PROTO_RPC_RE: Final = re.compile(r"(?m)^[ \t]*rpc\s+[_A-Za-z][_0-9A-Za-z]*\s*\(")
_PROTO_HTTP_RULE_RE: Final = re.compile(r"\boption\s*\(\s*google\.api\.http\s*\)\s*=")
_PROTO_HTTP_VERB_RE: Final = re.compile(r"\b(?P<verb>get|post|put|patch|delete)\s*:")
_BODY_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})


class ProtoHurlCompilationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedProtoHurlFile:
    relative_path: str
    content: str


def compile_proto_http_transcoding_to_hurl(
    proto_text: str,
    *,
    target_url: str,
) -> GeneratedProtoHurlFile:
    _validate_proto_text(proto_text)
    normalized_proto = _strip_proto_ignored_text(proto_text)
    rpc_count = len(_PROTO_RPC_RE.findall(normalized_proto))
    if rpc_count == 0:
        msg = "proto document must define at least one rpc declaration"
        raise ProtoHurlCompilationError(msg)

    http_rule_count = len(_PROTO_HTTP_RULE_RE.findall(normalized_proto))
    if http_rule_count == 0:
        msg = "proto document must define at least one google.api.http rule"
        raise ProtoHurlCompilationError(msg)

    method = _first_http_rule_method(normalized_proto)
    normalized_url, target_origin = _safe_target_url(target_url)
    lines = [
        "# entroping: tags=smoke,grpc,transcoding",
        "# entroping: source=proto",
        f"# entroping: target_origin={target_origin}",
        f"# entroping: rpc_count={rpc_count}",
        f"# entroping: http_rule_count={http_rule_count}",
        "# entroping: scaffold=http-transcoding-smoke",
        "# entroping: native_grpc_streaming=future",
        "",
        f"{method} {normalized_url}",
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
        relative_path=f"tests/generated/{_target_file_stem(normalized_url)}.hurl",
        content="\n".join(lines),
    )


def _validate_proto_text(proto_text: str) -> None:
    if proto_text.strip() == "":
        msg = "proto document is required"
        raise ProtoHurlCompilationError(msg)
    if _contains_disallowed_control(proto_text):
        msg = "proto document contains disallowed control characters"
        raise ProtoHurlCompilationError(msg)
    if contains_secret_like_value(proto_text):
        msg = "proto document contains secret-like material"
        raise ProtoHurlCompilationError(msg)


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
    if not value:
        msg = "gRPC HTTP target URL is required"
        raise ProtoHurlCompilationError(msg)
    if _contains_disallowed_control(value):
        msg = "gRPC HTTP target URL contains control characters"
        raise ProtoHurlCompilationError(msg)
    if any(character.isspace() for character in value):
        msg = "gRPC HTTP target URL must not contain whitespace"
        raise ProtoHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "gRPC HTTP target URL contains Hurl template delimiters"
        raise ProtoHurlCompilationError(msg)

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        msg = "gRPC HTTP target URL scheme must be http or https"
        raise ProtoHurlCompilationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "gRPC HTTP target URL must not contain credentials"
        raise ProtoHurlCompilationError(msg)
    if parts.fragment:
        msg = "gRPC HTTP target URL must not contain a fragment"
        raise ProtoHurlCompilationError(msg)

    try:
        port = parts.port
    except ValueError as exc:
        msg = "gRPC HTTP target URL contains an invalid port"
        raise ProtoHurlCompilationError(msg) from exc

    hostname = parts.hostname
    if hostname is None:
        msg = "gRPC HTTP target URL must include a host"
        raise ProtoHurlCompilationError(msg)

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/grpc-transcoding"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    if contains_secret_like_value(normalized_url):
        msg = "gRPC HTTP target URL contains secret-like material"
        raise ProtoHurlCompilationError(msg)
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            msg = f"gRPC HTTP target URL contains sensitive query key {key!r}"
            raise ProtoHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = f"gRPC HTTP target URL contains secret-like query value for {key!r}"
            raise ProtoHurlCompilationError(msg)


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "grpc-transcoding"
    raw_stem = f"grpc-{parts.hostname or 'target'}-{path}-smoke"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _contains_disallowed_control(value: str) -> bool:
    return any(ord(character) < 32 and character not in "\n\r\t" for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
