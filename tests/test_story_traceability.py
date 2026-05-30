"""Unit tests for Hurl story traceability compilation."""

from pathlib import Path

from entroping.bridge.story_traceability import (
    compile_story_traceability,
    render_story_traceability_markdown,
)
from entroping.models.hurl import HurlMetadata, HurlTest


def _test(
    path: str,
    *,
    tags: frozenset[str] = frozenset(),
    meta: dict[str, str] | None = None,
) -> HurlTest:
    return HurlTest(
        path=Path(path),
        metadata=HurlMetadata(tags=tags, meta=meta or {}),
    )


def test_compile_story_traceability_links_stories_to_tests_and_metadata() -> None:
    report = compile_story_traceability(
        [
            _test(
                "tests/checkout/smoke.hurl",
                tags=frozenset({"smoke", "checkout"}),
                meta={
                    "story_id": "CHK-001",
                    "owner": "payments",
                    "doc_url": "https://jira.example.com/browse/CHK-001",
                },
            ),
            _test(
                "tests/checkout/regression.hurl",
                tags=frozenset({"regression"}),
                meta={
                    "story_id": "CHK-001",
                    "owner": "payments",
                    "doc_url": "https://jira.example.com/browse/CHK-001",
                },
            ),
        ],
    )

    assert report.passed
    assert len(report.stories) == 1
    story = report.stories[0]
    assert story.story_id == "CHK-001"
    assert story.test_paths == (
        Path("tests/checkout/regression.hurl"),
        Path("tests/checkout/smoke.hurl"),
    )
    assert story.owners == ("payments",)
    assert story.doc_urls == ("https://jira.example.com/browse/CHK-001",)
    assert story.tags == ("checkout", "regression", "smoke")


def test_compile_story_traceability_reports_missing_story_ids() -> None:
    report = compile_story_traceability(
        [
            _test("tests/checkout/smoke.hurl", tags=frozenset({"smoke"})),
        ],
    )

    assert not report.passed
    assert len(report.findings) == 1
    assert report.findings[0].kind == "missing_story_id"
    assert report.findings[0].test_path == Path("tests/checkout/smoke.hurl")


def test_compile_story_traceability_reports_duplicate_external_links() -> None:
    report = compile_story_traceability(
        [
            _test(
                "tests/checkout.hurl",
                meta={
                    "story_id": "CHK-001",
                    "doc_url": "https://jira.example.com/browse/shared",
                },
            ),
            _test(
                "tests/refund.hurl",
                meta={
                    "story_id": "PAY-002",
                    "doc_url": "https://jira.example.com/browse/shared",
                },
            ),
        ],
    )

    assert not report.passed
    assert len(report.findings) == 1
    assert report.findings[0].kind == "duplicate_doc_url"
    assert report.findings[0].doc_url == "https://jira.example.com/browse/shared"
    assert report.findings[0].story_ids == ("CHK-001", "PAY-002")


def test_render_story_traceability_markdown_escapes_table_cells() -> None:
    report = compile_story_traceability(
        [
            _test(
                "tests/checkout.hurl",
                meta={
                    "story_id": "CHK|001<img>",
                    "owner": "payments|checkout<svg>",
                    "doc_url": "https://jira.example.com/browse/CHK-001",
                },
            ),
        ],
    )

    markdown = render_story_traceability_markdown(report)

    assert "CHK\\|001&lt;img&gt;" in markdown
    assert "payments\\|checkout&lt;svg&gt;" in markdown
    assert "<img>" not in markdown
    assert "<svg>" not in markdown


def test_render_story_traceability_markdown_handles_no_story_linked_tests() -> None:
    report = compile_story_traceability([])

    markdown = render_story_traceability_markdown(report)

    assert "No story-linked tests found." in markdown
    assert "No traceability findings." in markdown


def test_render_story_traceability_markdown_renders_findings_table() -> None:
    report = compile_story_traceability(
        [
            _test("tests/checkout.hurl"),
            _test(
                "tests/refund.hurl",
                meta={
                    "story_id": "PAY-002",
                    "doc_url": "https://jira.example.com/browse/shared|doc",
                },
            ),
            _test(
                "tests/void.hurl",
                meta={
                    "story_id": "PAY-003",
                    "doc_url": "https://jira.example.com/browse/shared|doc",
                },
            ),
        ],
    )

    markdown = render_story_traceability_markdown(report)

    assert "| Kind | Location | Message |" in markdown
    assert "missing_story_id" in markdown
    assert "tests/checkout.hurl" in markdown
    assert "duplicate_doc_url" in markdown
    assert "https://jira.example.com/browse/shared\\|doc" in markdown
