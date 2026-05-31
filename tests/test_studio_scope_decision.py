"""Regression tests for the near-term Studio scope decision."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_studio_scope_decision_is_recorded_as_an_adr() -> None:
    adr = (
        _REPO_ROOT / "decisions" / "ADR-0010-studio-cli-report-first-boundary.md"
    ).read_text(encoding="utf-8")

    assert "Studio remains optional and read-only" in adr
    assert "CLI and reports remain the primary workflow" in adr
    assert "#190" in adr
    assert "#192" in adr
    assert "#196" in adr


def test_roadmap_frames_studio_as_report_backed_secondary_surface() -> None:
    roadmap = (_REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "CLI/report-first product depth" in roadmap
    assert "Studio stays optional, read-only, and report-backed" in roadmap
    assert "No Studio mutation implementation is planned for v0.3" in roadmap


def test_user_guide_does_not_promote_alpha_studio_mutations() -> None:
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )

    assert "Studio should not rerun suites, edit tests, or change config in the alpha" in user_guide
    assert "Future Studio work should add rerun/action workflows" not in user_guide
