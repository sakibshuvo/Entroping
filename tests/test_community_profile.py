"""Community-profile trust-signal guardrails."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_community_profile_audit_script_passes_for_required_health_files() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "community_profile_audit.sh")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Community profile OK" in result.stdout
    assert ".github/workflows/scorecard.yml" in result.stdout


def test_readme_and_growth_docs_explain_scorecard_signal() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    growth = (REPO_ROOT / "docs" / "product" / "GROWTH_AND_MONETIZATION.md").read_text(
        encoding="utf-8"
    )

    assert "OpenSSF Scorecard" in readme
    assert "api.scorecard.dev/projects/github.com/sakibshuvo/Entroping/badge" in readme
    assert "scripts/community_profile_audit.sh" in growth
    assert ".github/workflows/scorecard.yml" in growth
    assert "scheduled/manual" in growth
