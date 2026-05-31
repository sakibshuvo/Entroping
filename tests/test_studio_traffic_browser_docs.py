"""Documentation tests for the Studio traffic browser boundary."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_studio_traffic_browser_is_documented_as_read_only_and_redacted() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    tds = (_REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    progress = (_REPO_ROOT / "docs" / "meta" / "PROJECT_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([readme, tds, user_guide, progress])

    assert "read-only traffic session browser" in combined
    assert "redacted SQLModel-backed state" in combined
    assert "target/dependency grouping" in combined
    assert "safe redaction categories and counts" in combined
    assert "does not start `watch`" in combined
    assert "raw URLs with query values, headers, bodies, cookies, tokens, or secrets" in combined
    assert "entroping studio --edit" not in combined
