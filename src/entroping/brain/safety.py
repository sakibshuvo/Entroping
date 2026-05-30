"""Safety helpers for local Brain inputs."""

import re

_SECRET_PATTERNS = (
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
    re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
)


def contains_secret_like_value(value: str) -> bool:
    """Return true when text contains common token-shaped credentials."""

    return any(pattern.search(value) is not None for pattern in _SECRET_PATTERNS)


def redact_secret_like_values(value: str) -> str:
    """Redact common token-shaped credentials from provider errors."""

    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def has_disallowed_control(value: str) -> bool:
    """Reject binary/control text while allowing normal Markdown whitespace."""

    allowed = {"\n", "\r", "\t"}
    return any(character not in allowed and ord(character) < 32 for character in value)
