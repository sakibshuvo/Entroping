"""Shared selected-file safety checks for maintainer AI worker harnesses."""

from __future__ import annotations

import re
from pathlib import Path

SENSITIVE_EXACT_NAMES = frozenset(
    {
        ".env",
        ".envrc",
        ".dockercfg",
        ".netrc",
        ".npmrc",
        ".pgpass",
        ".pypirc",
        "_netrc",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
)
SENSITIVE_KEY_CERT_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx"})
SENSITIVE_CONFIG_SUFFIXES = frozenset(
    {
        ".cfg",
        ".conf",
        ".config",
        ".env",
        ".envrc",
        ".ini",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
    }
)
SENSITIVE_BACKUP_SUFFIXES = frozenset(
    {".backup", ".bak", ".old", ".orig", ".prod", ".production", ".local", ".tmp"}
)
SENSITIVE_CONFIG_STEMS = frozenset(
    {
        "api-key",
        "api_key",
        "apikey",
        "client-secret",
        "client_secret",
        "credential",
        "credentials",
        "private-key",
        "private_key",
        "secret",
        "secrets",
        "service-account",
        "service_account",
        "token",
        "tokens",
    }
)
SECRET_LIKE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private key block",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "credential assignment",
        re.compile(
            r"(?i)(?:^|[^A-Z0-9_-])['\"]?"
            r"(?:[A-Z0-9_-]*API[_-]?KEY|[A-Z0-9_-]*TOKEN|"
            r"[A-Z0-9_-]*SECRET|PASSWORD|PRIVATE[_-]?KEY|PRIVATEKEY)"
            r"['\"]?\s*[:=]\s*['\"]?[^\s'\"(),]{16,}"
        ),
    ),
    (
        "bearer token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]{16,}"),
    ),
    (
        "provider token",
        re.compile(
            r"(?<![A-Za-z0-9_-])"
            r"(?:"
            r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|"
            r"ghp_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|"
            r"glpat-[A-Za-z0-9_-]{12,}|"
            r"hf_[A-Za-z0-9_-]{12,}|"
            r"xox[abprs]-[A-Za-z0-9-]{10,}|"
            r"AIza[A-Za-z0-9_-]{16,}|"
            r"ya29\.[A-Za-z0-9._-]{20,}|"
            r"A[KS]IA[A-Z0-9]{16}"
            r")"
            r"(?![A-Za-z0-9_-])"
        ),
    ),
)


def sensitive_selected_path_reason(relative_path: str) -> str | None:
    """Return a short reason when a selected repo path looks credential-like."""

    parts = [part.lower() for part in Path(relative_path).parts]
    for part in parts:
        if _looks_sensitive_part(part):
            return "looks like a sensitive credential file"
    return None


def secret_like_content_reason(content: str) -> str | None:
    """Return the matched secret-like category for selected file content."""

    for label, pattern in SECRET_LIKE_PATTERNS:
        if pattern.search(content):
            return label
    return None


def _looks_sensitive_part(name: str) -> bool:
    if name in SENSITIVE_EXACT_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if name.startswith(("id_dsa.", "id_ecdsa.", "id_ed25519.", "id_rsa.")):
        return True

    suffixes = frozenset(Path(name).suffixes)
    if suffixes & SENSITIVE_KEY_CERT_SUFFIXES:
        return True

    return _has_sensitive_config_stem(name) and bool(
        suffixes & (SENSITIVE_CONFIG_SUFFIXES | SENSITIVE_BACKUP_SUFFIXES)
    )


def _has_sensitive_config_stem(name: str) -> bool:
    for segment in name.split("."):
        if segment in SENSITIVE_CONFIG_STEMS:
            return True
        tokens = tuple(token for token in re.split(r"[-_]+", segment) if token)
        if any(token in SENSITIVE_CONFIG_STEMS for token in tokens):
            return True
        if tokens:
            for start in range(len(tokens)):
                for end in range(start + 2, len(tokens) + 1):
                    window = tokens[start:end]
                    if "-".join(window) in SENSITIVE_CONFIG_STEMS:
                        return True
                    if "_".join(window) in SENSITIVE_CONFIG_STEMS:
                        return True
    return False
