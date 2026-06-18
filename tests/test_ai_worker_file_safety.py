"""Tests for shared maintainer AI worker selected-file safety checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ai_worker_file_safety.py"


def _fixture_token(*parts: str) -> str:
    return "".join(parts)


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
        "config/prod-api-key.toml",
        "config/dev_client_secret.yaml",
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


@pytest.mark.parametrize(
    "content",
    [
        _fixture_token("sk-", "abcdefghijklmnopqrstuvwxyz123456"),
        _fixture_token("sk-proj-", "abcdefghijklmnopqrstuvwxyz123456"),
        _fixture_token("ghp_", "abcdefghijklmnopqrstuvwxyz123456"),
        _fixture_token("github_pat_", "abcdefghijklmnopqrstuvwxyz123456"),
        _fixture_token("glpat-", "abcdefghijklmnopqrstuvwxyz"),
        _fixture_token("hf_", "abcdefghijklmnopqrstuv"),
        _fixture_token("xoxb-", "1234567890-", "abcdefghijklmnopqrstuvwxyz"),
        _fixture_token("AIza", "abcdefghijklmnopqrstuvwxyz1234"),
        _fixture_token("ya29.", "abcdefghijklmnopqrstuvwxyz123456"),
        _fixture_token("AKIA", "ABCDEFGHIJKLMNOP"),
    ],
)
def test_secret_like_content_reason_rejects_bare_provider_tokens(content: str) -> None:
    module = _load_file_safety_module()

    assert module.secret_like_content_reason(content) == "provider token"


def test_secret_like_content_reason_rejects_lowercase_private_key_blocks() -> None:
    module = _load_file_safety_module()

    assert module.secret_like_content_reason("-----begin private key-----") == "private key block"


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
            "token={{api_token}}",
            "token=[REDACTED]",
            "The redaction test checks placeholder values only.",
            'api_key = os.environ.get(env_name, "").strip()',
        ]
    )

    assert module.secret_like_content_reason(allowed_content) is None
