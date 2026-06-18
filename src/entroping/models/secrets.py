"""Pure credential detection and redaction helpers."""

import re

REDACTED = "[REDACTED]"

_TOKEN_SECRET_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]+"),
    re.compile(r"sk_proj_[A-Za-z0-9_-]+"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"\bA[KS]IA[A-Z0-9]{16}\b"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
)
_JWT_LIKE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"(?![A-Za-z0-9_-])"
)
_OPAQUE_BASE64_RE = re.compile(
    r"(?<![A-Za-z0-9+_-])[A-Za-z0-9+_-]{32,}={0,2}(?![A-Za-z0-9+_=-])"
)
_PAN_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
}
_HEADER_OWNED_KEY_VALUES = _SENSITIVE_HEADER_NAMES | {
    "api-key",
    "access-token",
    "refresh-token",
}
_SENSITIVE_KEY_PARTS = (
    "access_token",
    "api_key",
    "apikey",
    "auth",
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
_HEADER_SECRET_RE = re.compile(
    r"(?im)\b("
    r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|api-key|access-token|refresh-token"
    r")\s*:\s*([^\r\n]+)"
)
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b("
    r"access_token|api[_-]?key|authorization|client_secret|cookie|csrf[_-]?token|"
    r"jwt|password|passwd|refresh_token|secret|session[_-]?id|token"
    r")(\s*[:=]\s*)([^\s&;,\"]+)"
)
_JSON_PAIR_SECRET_RE = re.compile(
    r'(?i)("(?:access_token|api[_-]?key|authorization|client_secret|cookie|jwt|'
    r'password|passwd|refresh_token|secret|session[_-]?id|csrf[_-]?token|token)"\s*:\s*)"[^"]*"'
)
_AUTH_VALUE_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+([A-Za-z0-9._~+/=-]{10,})")


def contains_secret_like_value(value: str) -> bool:
    """Return true when text contains common token-shaped credentials."""

    if any(pattern.search(value) is not None for pattern in _TOKEN_SECRET_PATTERNS):
        return True
    if _contains_sensitive_data_shape(value):
        return True
    if any(_header_value_is_secret(match.group(2)) for match in _HEADER_SECRET_RE.finditer(value)):
        return True
    return any(
        _key_value_match_is_secret(match)
        for match in _KEY_VALUE_SECRET_RE.finditer(value)
    )


def redact_secret_like_values(value: str) -> str:
    """Redact common token-shaped credentials from text."""

    redacted = value
    for pattern in _TOKEN_SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    redacted = _redact_sensitive_data_shapes(redacted)
    redacted = _HEADER_SECRET_RE.sub(_redact_header_secret, redacted)
    redacted = _AUTH_VALUE_RE.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = _KEY_VALUE_SECRET_RE.sub(_redact_key_value_secret, redacted)
    return _JSON_PAIR_SECRET_RE.sub(lambda match: f'{match.group(1)}"{REDACTED}"', redacted)


def is_sensitive_header_name(name: str) -> bool:
    """Return true when an HTTP header name normally carries credentials."""

    normalized = name.lower()
    return normalized in _SENSITIVE_HEADER_NAMES or is_sensitive_key(normalized)


def is_sensitive_key(key: str) -> bool:
    """Return true when a structured key name normally carries credentials."""

    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def has_disallowed_control(value: str) -> bool:
    """Reject binary/control text while allowing normal Markdown whitespace."""

    allowed = {"\n", "\r", "\t"}
    return any(character not in allowed and ord(character) < 32 for character in value)


def _contains_sensitive_data_shape(value: str) -> bool:
    return (
        _JWT_LIKE_RE.search(value) is not None
        or any(_opaque_base64_match_is_secret(match) for match in _OPAQUE_BASE64_RE.finditer(value))
        or any(_pan_match_is_secret(match) for match in _PAN_CANDIDATE_RE.finditer(value))
        or _SSN_RE.search(value) is not None
        or _EMAIL_RE.search(value) is not None
    )


def _redact_sensitive_data_shapes(value: str) -> str:
    redacted = _JWT_LIKE_RE.sub(REDACTED, value)
    redacted = _OPAQUE_BASE64_RE.sub(_redact_opaque_base64, redacted)
    redacted = _PAN_CANDIDATE_RE.sub(_redact_pan_candidate, redacted)
    redacted = _SSN_RE.sub(REDACTED, redacted)
    return _EMAIL_RE.sub(REDACTED, redacted)


def _redact_opaque_base64(match: re.Match[str]) -> str:
    if _opaque_base64_match_is_secret(match):
        return REDACTED
    return match.group(0)


def _opaque_base64_match_is_secret(match: re.Match[str]) -> bool:
    value = match.group(0).rstrip("=")
    has_lower = any(character.islower() for character in value)
    has_upper = any(character.isupper() for character in value)
    has_digit = any(character.isdigit() for character in value)
    if not (has_lower and has_upper and has_digit):
        return False

    unique_ratio = len(set(value)) / len(value)
    return unique_ratio >= 0.20


def _redact_pan_candidate(match: re.Match[str]) -> str:
    if _pan_match_is_secret(match):
        return REDACTED
    return match.group(0)


def _pan_match_is_secret(match: re.Match[str]) -> bool:
    digits = "".join(character for character in match.group(0) if character.isdigit())
    return 13 <= len(digits) <= 19 and _luhn_valid(digits)


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        value = int(character)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _redact_header_secret(match: re.Match[str]) -> str:
    value = match.group(2)
    if not _header_value_is_secret(value):
        return match.group(0)
    return f"{match.group(1)}: {REDACTED}"


def _redact_key_value_secret(match: re.Match[str]) -> str:
    if not _key_value_match_is_secret(match):
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{REDACTED}"


def _key_value_match_is_secret(match: re.Match[str]) -> bool:
    raw_key = match.group(1).lower()
    separator = match.group(2)
    value = match.group(3)
    if ":" in separator and raw_key in _HEADER_OWNED_KEY_VALUES:
        return False
    return _secret_value_is_literal(value)


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
    if not stripped or stripped == REDACTED:
        return False
    return not (stripped.startswith("{{") and stripped.endswith("}}"))
