"""Guardrails for real downstream feedback evidence docs."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_downstream_feedback_kit_collects_required_safe_evidence() -> None:
    kit = (REPO_ROOT / "docs" / "meta" / "DOWNSTREAM_FEEDBACK_KIT.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "install path",
        "operating system",
        "Python version",
        "Hurl version",
        "command used",
        "success or failure",
        "friction",
        "sanitized logs",
        "Do not include secrets",
        "private URLs",
        "raw traffic",
        "proprietary API payloads",
        "maintainer-controlled local smoke is not real downstream user feedback",
    ]
    for term in required_terms:
        assert term in kit


def test_downstream_feedback_kit_is_linked_from_stable_core_and_contributor_docs() -> None:
    required_links = {
        "docs/meta/RELEASE_EVIDENCE.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/DOWNSTREAM_SMOKE_EVIDENCE.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/VAULT_INDEX.md": "[[docs/meta/DOWNSTREAM_FEEDBACK_KIT|DOWNSTREAM_FEEDBACK_KIT]]",
        "docs/index.md": "meta/DOWNSTREAM_FEEDBACK_KIT.md",
        "mkdocs.yml": "Downstream Feedback Kit: meta/DOWNSTREAM_FEEDBACK_KIT.md",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content
