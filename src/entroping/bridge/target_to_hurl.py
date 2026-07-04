import re
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from entroping.models.secrets import contains_secret_like_value, is_sensitive_key

_ALLOWED_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
_SAFE_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_-]+")


class TargetHurlCompilationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedTargetHurlFile:
    relative_path: str
    content: str


def compile_target_url_to_hurl(
    target_url: str,
    *,
    method: str = "GET",
) -> GeneratedTargetHurlFile:
    normalized_method = _safe_method(method)
    normalized_url, target_origin = _safe_target_url(target_url)
    lines = [
        "# entroping: tags=target,smoke",
        "# entroping: source=target-url",
        f"# entroping: target_origin={target_origin}",
        "",
        f"{normalized_method} {normalized_url}",
        "HTTP 200",
        "",
    ]
    return GeneratedTargetHurlFile(
        relative_path=f"tests/generated/{_target_file_stem(normalized_url)}.hurl",
        content="\n".join(lines),
    )


def _safe_method(value: str) -> str:
    if _contains_control(value):
        msg = "target method contains control characters"
        raise TargetHurlCompilationError(msg)
    stripped = value.strip()
    if any(character.isspace() for character in stripped):
        msg = "target method must be one HTTP method token"
        raise TargetHurlCompilationError(msg)
    method = stripped.upper()
    if method not in _ALLOWED_METHODS:
        msg = f"target method must be one of {', '.join(sorted(_ALLOWED_METHODS))}"
        raise TargetHurlCompilationError(msg)
    return method


def _safe_target_url(value: str) -> tuple[str, str]:
    if not value:
        msg = "target URL is required"
        raise TargetHurlCompilationError(msg)
    if _contains_control(value):
        msg = "target URL contains control characters"
        raise TargetHurlCompilationError(msg)
    if any(character.isspace() for character in value):
        msg = "target URL must not contain whitespace"
        raise TargetHurlCompilationError(msg)
    if _has_hurl_template_delimiter(value):
        msg = "target URL contains Hurl template delimiters"
        raise TargetHurlCompilationError(msg)

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        msg = "target URL scheme must be http or https"
        raise TargetHurlCompilationError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "target URL must not contain credentials"
        raise TargetHurlCompilationError(msg)
    if parts.fragment:
        msg = "target URL must not contain a fragment"
        raise TargetHurlCompilationError(msg)

    try:
        port = parts.port
    except ValueError as exc:
        msg = "target URL contains an invalid port"
        raise TargetHurlCompilationError(msg) from exc

    hostname = parts.hostname
    if hostname is None:
        msg = "target URL must include a host"
        raise TargetHurlCompilationError(msg)

    _reject_sensitive_query(parts.query)
    normalized_host = hostname.lower()
    normalized_netloc = _host_with_port(normalized_host, port)
    normalized_path = parts.path or "/"
    normalized_url = urlunsplit(
        (scheme, normalized_netloc, normalized_path, parts.query, ""),
    )
    if contains_secret_like_value(normalized_url):
        msg = "target URL contains secret-like material"
        raise TargetHurlCompilationError(msg)
    return normalized_url, urlunsplit((scheme, normalized_netloc, "", "", ""))


def _reject_sensitive_query(query: str) -> None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if is_sensitive_key(key):
            msg = f"target URL contains sensitive query key {key!r}"
            raise TargetHurlCompilationError(msg)
        if contains_secret_like_value(value):
            msg = f"target URL contains secret-like query value for {key!r}"
            raise TargetHurlCompilationError(msg)


def _host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None:
        return host
    return f"{host}:{port}"


def _target_file_stem(target_url: str) -> str:
    parts = urlsplit(target_url)
    path = parts.path.strip("/") or "root"
    raw_stem = f"target-{parts.hostname or 'target'}-{path}"
    return _SAFE_STEM_RE.sub("-", raw_stem).strip(".-_").lower()


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _has_hurl_template_delimiter(value: str) -> bool:
    return "{{" in value or "}}" in value
