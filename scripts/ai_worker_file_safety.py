"""Shared selected-file safety checks for maintainer AI worker harnesses."""

from __future__ import annotations

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


def sensitive_selected_path_reason(relative_path: str) -> str | None:
    """Return a short reason when a selected repo path looks credential-like."""

    parts = [part.lower() for part in Path(relative_path).parts]
    for part in parts:
        if _looks_sensitive_part(part):
            return "looks like a sensitive credential file"
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

    first_segment = name.split(".", maxsplit=1)[0]
    return first_segment in SENSITIVE_CONFIG_STEMS and bool(
        suffixes & (SENSITIVE_CONFIG_SUFFIXES | SENSITIVE_BACKUP_SUFFIXES)
    )
