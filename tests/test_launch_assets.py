"""Guardrails for public launch demo assets."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_DIR = REPO_ROOT / "docs" / "assets" / "launch"


def test_readme_links_two_minute_launch_assets() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "[Two-Minute Demo Assets](docs/assets/launch/README.md)" in readme
    assert "docs/assets/launch/terminal-demo-screenshot.png" in readme
    assert "docs/assets/launch/html-report-screenshot.png" in readme
    assert "docs/assets/launch/dependency-map-screenshot.png" in readme
    assert "scripts/live_demo_smoke.sh" in readme


def test_launch_asset_kit_is_curated_and_reproducible() -> None:
    expected_files = {
        "README.md",
        "terminal-demo-screenshot-set.md",
        "terminal-demo-screenshot.png",
        "html-report-screenshot.png",
        "dependency-map-screenshot.png",
        "dependency-map-example.md",
    }
    discovered = {path.name for path in LAUNCH_DIR.iterdir() if path.is_file()}

    assert expected_files <= discovered

    allowed_suffixes = {".md", ".png"}
    for path in LAUNCH_DIR.rglob("*"):
        if not path.is_file():
            continue
        assert path.suffix in allowed_suffixes, f"unexpected launch asset type: {path}"
        content = path.read_bytes()
        assert len(content) < 200_000, f"launch asset is too large for Git: {path}"
        if path.suffix == ".png":
            assert content.startswith(b"\x89PNG\r\n\x1a\n"), f"invalid PNG launch asset: {path}"
        else:
            assert b"\x00" not in content, f"binary launch asset needs explicit review: {path}"

    asset_readme = (LAUNCH_DIR / "README.md").read_text(encoding="utf-8")
    terminal_demo = (LAUNCH_DIR / "terminal-demo-screenshot-set.md").read_text(
        encoding="utf-8"
    )
    dependency_map = (LAUNCH_DIR / "dependency-map-example.md").read_text(
        encoding="utf-8"
    )

    assert "Generated from real checkout fixture output" in asset_readme
    assert "Curated PNG" in asset_readme
    assert "scripts/live_demo_smoke.sh" in terminal_demo
    assert "Hurl run: 4 passed, 0 failed" in terminal_demo
    assert (LAUNCH_DIR / "terminal-demo-screenshot.png").stat().st_size > 50_000
    assert (LAUNCH_DIR / "html-report-screenshot.png").stat().st_size > 50_000
    assert (LAUNCH_DIR / "dependency-map-screenshot.png").stat().st_size > 50_000
    assert "flowchart LR" in dependency_map
    assert "api.example.test" in dependency_map


def test_growth_plan_has_concrete_launch_publish_order() -> None:
    growth = (REPO_ROOT / "docs" / "product" / "GROWTH_AND_MONETIZATION.md").read_text(
        encoding="utf-8"
    )

    assert "## Launch Asset Checklist" in growth
    assert "docs/assets/launch/README.md" in growth
    assert "Publish order:" in growth

    ordered_steps = [
        "community health and Scorecard evidence",
        "two-minute README demo links",
        "terminal screenshot",
        "HTML report screenshot",
        "dependency map example",
        "release notes",
        "launch post",
    ]
    positions = [growth.index(step) for step in ordered_steps]
    assert positions == sorted(positions)


def test_checkout_demo_docs_point_to_launch_asset_generation() -> None:
    demo_readme = (REPO_ROOT / "examples" / "checkout-api" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/live_demo_smoke.sh" in demo_readme
    assert "ENTROPING_LIVE_DEMO_ARTIFACT_DIR" in demo_readme
    assert "docs/assets/launch/README.md" in demo_readme


def test_launch_rebuild_commands_avoid_maintainer_local_temp_paths() -> None:
    public_docs = [
        LAUNCH_DIR / "README.md",
        LAUNCH_DIR / "terminal-demo-screenshot-set.md",
        REPO_ROOT / "examples" / "checkout-api" / "README.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in public_docs)

    assert "/Users/sakibshuvo" not in combined
    assert "ENTROPING_DEMO_TMP_BASE" in combined
    assert "$HOME/.cache/entroping-demo" in combined
