"""Guardrails for real downstream feedback evidence docs."""

from pathlib import Path

from _public_docs import public_doc_sources

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_downstream_feedback_kit_collects_required_safe_evidence() -> None:
    kit = (REPO_ROOT / "docs" / "meta" / "DOWNSTREAM_FEEDBACK_KIT.md").read_text(
        encoding="utf-8"
    )

    normalized = " ".join(kit.split())
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
        assert term in normalized


def test_downstream_feedback_kit_tracks_user_evidence_metadata() -> None:
    kit = (REPO_ROOT / "docs" / "meta" / "DOWNSTREAM_FEEDBACK_KIT.md").read_text(
        encoding="utf-8"
    )

    normalized = " ".join(kit.split())
    required_terms = [
        "GitHub User-Evidence Metadata",
        "entroping.user-evidence.v1",
        "evidence_status",
        "affected_journey",
        "severity",
        "source_classification",
        "verification_receipt",
        "evidence:user-verified",
        "verified user demand",
        "human review",
        "manual redaction",
        "manual review before provider dispatch",
        "Internal observations are not user evidence",
        "Provider dispatch may receive only the sanitized issue packet",
    ]

    for term in required_terms:
        assert term in normalized


def test_downstream_feedback_kit_is_linked_from_stable_core_and_contributor_docs() -> None:
    required_links = {
        "docs/meta/RELEASE_EVIDENCE.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/DOWNSTREAM_SMOKE_EVIDENCE.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH.md": "DOWNSTREAM_FEEDBACK_KIT.md",
        "docs/meta/VAULT_INDEX.md": "[[docs/meta/DOWNSTREAM_FEEDBACK_KIT|DOWNSTREAM_FEEDBACK_KIT]]",
        "docs/index.md": "meta/DOWNSTREAM_FEEDBACK_KIT.md",
    }

    for relative_path, expected in required_links.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert expected in content

    assert "docs/meta/DOWNSTREAM_FEEDBACK_KIT.md" in public_doc_sources()
