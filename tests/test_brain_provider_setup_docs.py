"""Guardrails for Brain provider setup documentation."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_GUIDE = REPO_ROOT / "docs" / "user" / "AI_PROVIDER_SETUP.md"


def test_ai_provider_setup_guide_covers_local_cloud_and_no_provider_paths() -> None:
    guide = PROVIDER_GUIDE.read_text(encoding="utf-8")

    required_terms = [
        "LiteLLM",
        "Ollama",
        "Qwen",
        "oMLX",
        "OpenAI-compatible",
        "api_base",
        "api_key_env",
        "uv sync --extra ai",
        "entroping config set --agent builder --model",
        "entroping architect build --prompt",
        "entroping run --ci",
        "LLM-free",
        "No API keys in qanstitution.yaml",
    ]

    for term in required_terms:
        assert term in guide

    assert guide.index("## The Boundary") < guide.index("## Install The AI Extra")
    assert guide.index("## Local Qwen Through Ollama") < guide.index(
        "## Local Qwen Through oMLX"
    )
    assert guide.index("## No-Provider CI") < guide.index("## Secret Rules")


def test_ai_provider_setup_documents_secret_free_doctor_references() -> None:
    guide = PROVIDER_GUIDE.read_text(encoding="utf-8")

    assert "## Doctor Local Setup References" in guide
    assert "docs/user/AI_PROVIDER_SETUP.md#local-qwen-through-ollama" in guide
    assert "docs/user/AI_PROVIDER_SETUP.md#local-openai-compatible-runtime" in guide
    assert "agent `message`" in guide
    assert "does not inspect a provider" in guide
    assert "does not print" in guide


def test_ai_provider_setup_is_linked_from_canonical_docs() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    user_guide = (REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    strategy = (
        REPO_ROOT / "docs" / "evolution" / "BRAIN_PROVIDER_STRATEGY.md"
    ).read_text(encoding="utf-8")

    assert "AI_PROVIDER_SETUP.md" in readme
    assert "[[docs/user/AI_PROVIDER_SETUP|AI_PROVIDER_SETUP]]" in index
    assert "docs/user/AI_PROVIDER_SETUP.md" in user_guide
    assert "docs/user/AI_PROVIDER_SETUP.md" in strategy


def test_qanstitution_docs_include_provider_connection_metadata() -> None:
    tds = (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    reference = (
        REPO_ROOT / "docs" / "technical" / "QANSTITUTION_REFERENCE.md"
    ).read_text(encoding="utf-8")

    for doc in (tds, reference):
        assert "api_base" in doc
        assert "api_key_env" in doc
        assert "OpenAI-compatible" in doc
        assert "No API keys in qanstitution.yaml" in doc
