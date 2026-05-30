"""Release-readiness documentation guardrails."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_links_alpha_release_gate_and_checklist() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "scripts/release_check.sh" in readme
    assert "docs/meta/RELEASE_CHECKLIST.md" in readme


def test_alpha_release_checklist_documents_required_evidence() -> None:
    checklist = (REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "v0.1.0-alpha" in checklist
    assert "scripts/regression.sh --security" in checklist
    assert "scripts/live_demo_smoke.sh" in checklist
    assert "Not Built Yet" in checklist
