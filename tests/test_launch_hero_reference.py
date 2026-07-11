from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HERO_SECTION = REPO_ROOT / "src" / "components" / "HeroSection.astro"


def test_hero_keeps_reference_speed_annotation() -> None:
    hero_source = HERO_SECTION.read_text(encoding="utf-8")
    annotation_lines = ("// write fast", "verify faster")

    assert 'class="hero__speed-note"' in hero_source
    assert all(line in hero_source for line in annotation_lines)
