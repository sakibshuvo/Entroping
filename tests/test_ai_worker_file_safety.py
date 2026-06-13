"""Tests for shared maintainer AI worker selected-file safety checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_worker_file_safety.py"


def _load_file_safety_module() -> Any:
    spec = importlib.util.spec_from_file_location("ai_worker_file_safety", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sensitive_selected_path_reason_rejects_credential_variants() -> None:
    module = _load_file_safety_module()

    sensitive_paths = (
        ".env.backup",
        ".dockercfg",
        ".pgpass",
        "config/client.key.bak",
        "certs/internal.pem.old",
        "secrets.production",
        "secret.env.prod",
        "secret.envrc",
        "secret.config",
        "config/my-secret.config.yaml",
        "service-account.json",
    )

    for relative_path in sensitive_paths:
        assert (
            module.sensitive_selected_path_reason(relative_path)
            == "looks like a sensitive credential file"
        )


def test_sensitive_selected_path_reason_allows_ordinary_source_and_docs() -> None:
    module = _load_file_safety_module()

    allowed_paths = (
        "docs/security-review.md",
        "docs/token-budget.md",
        "examples/config.sample.json",
        "scripts/key_rotation_notes.py",
        "src/entroping/core/config_loader.py",
        "tests/test_secret_redaction.py",
    )

    for relative_path in allowed_paths:
        assert module.sensitive_selected_path_reason(relative_path) is None


def test_secret_like_content_reason_rejects_secret_shapes() -> None:
    module = _load_file_safety_module()

    secret_content_by_label = (
        ("private key block", "-----BEGIN PRIVATE KEY-----\nnot-real\n"),
        (
            "credential assignment",
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n"
        ),
        (
            "credential assignment",
            "PASSWORD=abc!def456ghi!klmno\n",
        ),
        (
            "credential assignment",
            '{"api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz123456"}\n',
        ),
        (
            "credential assignment",
            '{"access_token": "ghp_abcdefghijklmnopqrstuvwxyz123456"}\n',
        ),
        (
            "credential assignment",
            '{"client_secret": "xoxb-abcdefghijklmnopqrstuvwxyz123456"}\n',
        ),
        ("bearer token", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"),
    )

    for label, content in secret_content_by_label:
        assert module.secret_like_content_reason(content) == label


def test_secret_like_content_reason_allows_non_secret_security_text() -> None:
    module = _load_file_safety_module()

    allowed_content = "\n".join(
        [
            "Document the bearer token flow without sample credentials.",
            "TOKEN budget should stay under 4000.",
            "PASSWORD must be configured outside source control.",
            '{"api_key": "read from ENTROPING_API_KEY at runtime"}',
            '{"access_token": "<redacted>"}',
            '{"client_secret": "placeholder"}',
            "The redaction test checks placeholder values only.",
        ]
    )

    assert module.secret_like_content_reason(allowed_content) is None
