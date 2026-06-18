"""Documentation guardrails for the read-only Studio evidence viewer."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_studio_evidence_viewer_documents_stable_ids_and_safety_boundary() -> None:
    product_spec = (_REPO_ROOT / "docs" / "product" / "PRODUCT_SPEC.md").read_text(
        encoding="utf-8"
    )
    tds = (_REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    progress = (_REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([product_spec, tds, user_guide, progress])

    assert "read-only evidence viewer" in combined
    assert "stable evidence IDs" in combined
    assert "`run-json`" in tds
    assert "`capture-summary-json`" in tds
    assert "`runtime-card-json`" in tds
    assert "does not render raw report contents" in combined
    assert "does not edit tests, QAnstitution, reports, traffic state, or runtime state" in combined
    assert "does not upload artifacts" in combined
