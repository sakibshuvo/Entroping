"""Safety helpers for local Brain inputs."""

import re

_TOKEN_SECRET_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]+"),
    re.compile(r"sk_proj_[A-Za-z0-9_-]+"),
    re.compile(r"ghp_[A-Za-z0-9_]+"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"glpat-[A-Za-z0-9_-]+"),
    re.compile(r"hf_[A-Za-z0-9_-]+"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]+"),
    re.compile(r"AIza[A-Za-z0-9_-]+"),
    re.compile(r"ya29\.[A-Za-z0-9._-]+"),
    re.compile(r"\bA[KS]IA[A-Z0-9]{8,}\b"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
)
_HEADER_SECRET_RE = re.compile(
    r"(?im)\b("
    r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|api-key|access-token|refresh-token"
    r")\s*:\s*([^\r\n]+)"
)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b("
    r"access_token|api[_-]?key|client_secret|jwt|password|passwd|refresh_token|"
    r"secret|session[_-]?id|token"
    r")(\s*[:=]\s*)([^\s&;,\"]+)"
)


def contains_secret_like_value(value: str) -> bool:
    """Return true when text contains common token-shaped credentials."""

    if any(pattern.search(value) is not None for pattern in _TOKEN_SECRET_PATTERNS):
        return True
    if any(_header_value_is_secret(match.group(2)) for match in _HEADER_SECRET_RE.finditer(value)):
        return True
    return any(
        _secret_value_is_literal(match.group(3))
        for match in _KEY_VALUE_SECRET_RE.finditer(value)
    )


def redact_secret_like_values(value: str) -> str:
    """Redact common token-shaped credentials from provider errors."""

    redacted = value
    for pattern in _TOKEN_SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _HEADER_SECRET_RE.sub(_redact_header_secret, redacted)
    redacted = _KEY_VALUE_SECRET_RE.sub(_redact_key_value_secret, redacted)
    return redacted


def has_disallowed_control(value: str) -> bool:
    """Reject binary/control text while allowing normal Markdown whitespace."""

    allowed = {"\n", "\r", "\t"}
    return any(character not in allowed and ord(character) < 32 for character in value)


def _redact_header_secret(match: re.Match[str]) -> str:
    value = match.group(2)
    if not _header_value_is_secret(value):
        return match.group(0)
    return f"{match.group(1)}: [REDACTED]"


def _redact_key_value_secret(match: re.Match[str]) -> str:
    value = match.group(3)
    if not _secret_value_is_literal(value):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _header_value_is_secret(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False

    lower = stripped.lower()
    for scheme in ("bearer ", "basic "):
        if lower.startswith(scheme):
            return _secret_value_is_literal(stripped[len(scheme) :].strip())

    if "=" in stripped:
        for part in stripped.split(";"):
            cookie_value = part.split("=", maxsplit=1)[-1].strip()
            if _secret_value_is_literal(cookie_value):
                return True
        return False

    return _secret_value_is_literal(stripped)


def _secret_value_is_literal(value: str) -> bool:
    stripped = value.strip().strip("'\"")
    if not stripped or stripped == "[REDACTED]":
        return False
    return not (stripped.startswith("{{") and stripped.endswith("}}"))
