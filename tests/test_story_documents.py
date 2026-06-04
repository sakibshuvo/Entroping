"""Adapter tests for local Markdown story discovery."""

from pathlib import Path

from entroping.core import story_documents
from entroping.core.story_documents import discover_story_documents


def test_discover_story_documents_reads_frontmatter_story_ids(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "checkout.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "---\n"
        "story_id: CHK-001\n"
        "title: Checkout accepts payment\n"
        "---\n"
        "\n"
        "# Checkout accepts payment\n",
        encoding="utf-8",
    )

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents[0].story_id == "CHK-001"
    assert result.documents[0].title == "Checkout accepts payment"
    assert result.documents[0].path == Path("docs/stories/checkout.md")
    assert result.findings == ()
    assert result.scope_present


def test_discover_story_documents_uses_heading_when_title_is_missing(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "checkout.md"
    story.parent.mkdir(parents=True)
    story.write_text("story_id: CHK-001\n\n# Checkout accepts payment\n", encoding="utf-8")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents[0].title == "Checkout accepts payment"


def test_discover_story_documents_allows_missing_title(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "checkout.md"
    story.parent.mkdir(parents=True)
    story.write_text("story_id: CHK-001\n", encoding="utf-8")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents[0].title is None


def test_discover_story_documents_reports_malformed_story_metadata(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "missing.md"
    story.parent.mkdir(parents=True)
    story.write_text("# Missing story ID\n", encoding="utf-8")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "malformed_story_metadata"
    assert result.findings[0].story_path == Path("docs/stories/missing.md")
    assert "story_id" in result.findings[0].message


def test_discover_story_documents_reports_control_character_story_ids(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "bad.md"
    story.parent.mkdir(parents=True)
    story.write_text("story_id: CHK-\x1b001\n", encoding="utf-8")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "malformed_story_metadata"
    assert "control characters" in result.findings[0].message


def test_discover_story_documents_reports_control_character_titles(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "bad-title.md"
    story.parent.mkdir(parents=True)
    story.write_text("story_id: CHK-001\ntitle: Bad\x1bTitle\n", encoding="utf-8")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "malformed_story_metadata"
    assert "title" in result.findings[0].message


def test_discover_story_documents_reports_invalid_utf8_story_files(tmp_path: Path) -> None:
    story = tmp_path / "docs" / "stories" / "bad.md"
    story.parent.mkdir(parents=True)
    story.write_bytes(b"story_id: CHK-001\n\xff")

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "malformed_story_metadata"
    assert "valid UTF-8" in result.findings[0].message


def test_discover_story_documents_reports_symlinked_story_files(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("story_id: OUT-001\n", encoding="utf-8")
    story = tmp_path / "docs" / "stories" / "linked.md"
    story.parent.mkdir(parents=True)
    story.symlink_to(outside)

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "unsafe_story_path"
    assert result.findings[0].story_path == Path("docs/stories/linked.md")


def test_discover_story_documents_reports_symlinked_story_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    stories_dir = tmp_path / "docs" / "stories"
    stories_dir.parent.mkdir()
    stories_dir.symlink_to(outside, target_is_directory=True)

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings[0].kind == "unsafe_story_path"
    assert result.findings[0].story_path == Path("docs/stories")


def test_discover_story_documents_skips_markdown_directories(tmp_path: Path) -> None:
    story_dir = tmp_path / "docs" / "stories" / "directory.md"
    story_dir.mkdir(parents=True)

    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings == ()


def test_discover_story_documents_returns_empty_result_when_directory_is_missing(
    tmp_path: Path,
) -> None:
    result = discover_story_documents(project_root=tmp_path)

    assert result.documents == ()
    assert result.findings == ()
    assert not result.scope_present


def test_display_path_falls_back_when_path_is_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"

    assert story_documents._display_path(outside, tmp_path) == outside
