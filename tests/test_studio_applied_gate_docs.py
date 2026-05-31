"""Documentation guardrails for read-only Studio applied-gate drilldowns."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_studio_applied_gate_drilldown_is_documented_without_mutation_claims() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    tds = (_REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    progress = (_REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "applied-gate drilldowns",
        "latest-run report rule IDs",
        "QAnstitution gate definitions",
        "does not run Hurl",
        "does not edit tests or config",
    ]
    for term in required_terms:
        assert term in user_guide
        assert term in tds

    assert "applied-gate drilldowns" in readme
    assert "[Read-only Studio applied-gate drilldowns]" in progress
    assert "entroping studio --edit" not in readme
