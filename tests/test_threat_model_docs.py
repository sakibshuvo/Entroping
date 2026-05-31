"""Documentation guardrails for the stable-core threat model."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
THREAT_MODEL = REPO_ROOT / "docs" / "technical" / "THREAT_MODEL.md"


def test_threat_model_covers_current_stable_core_security_boundaries() -> None:
    content = THREAT_MODEL.read_text(encoding="utf-8")

    required_phrases = (
        "Hurl subprocess boundary",
        "Traffic capture and redaction",
        "File writes and symlinks",
        "LiteLLM/provider boundaries",
        "Dependency policy",
        "SQLModel-backed SQLite",
        ".entroping/state.db",
        "No open validated security findings",
        "issue #96",
        "issue #198",
        "issue #227",
    )
    for phrase in required_phrases:
        assert phrase in content


def test_threat_model_is_visible_from_canonical_indexes() -> None:
    required_targets = {
        "docs/index.md": "technical/THREAT_MODEL.md",
        "00_INDEX.md": "[[docs/technical/THREAT_MODEL|THREAT_MODEL]]",
        "mkdocs.yml": "Threat Model: technical/THREAT_MODEL.md",
        "docs/meta/RELEASE_CHECKLIST.md": "docs/technical/THREAT_MODEL.md",
    }

    for relative_path, expected in required_targets.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
