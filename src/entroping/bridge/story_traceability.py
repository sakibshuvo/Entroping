"""Story and external business-truth traceability helpers."""

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

from entroping.models.hurl import HurlTest

TraceabilityFindingKind = Literal[
    "missing_story_id",
    "duplicate_doc_url",
    "missing_story",
    "story_without_tests",
    "duplicate_story_id",
    "malformed_story_metadata",
    "unsafe_story_path",
]
TRACEABILITY_REPORT_SCHEMA_VERSION = "entroping.traceability-report.v1"


@dataclass(frozen=True, slots=True)
class StoryTraceabilityDocument:
    """Local Markdown story document discovered by a filesystem adapter."""

    story_id: str
    path: Path
    title: str | None = None


@dataclass(frozen=True, slots=True)
class StoryTraceabilityStory:
    """Tests linked to one story identifier."""

    story_id: str
    test_paths: tuple[Path, ...]
    story_paths: tuple[Path, ...] = ()
    titles: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    doc_urls: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoryTraceabilityFinding:
    """Traceability problem discovered from Hurl metadata."""

    kind: TraceabilityFindingKind
    message: str
    test_path: Path | None = None
    story_path: Path | None = None
    doc_url: str | None = None
    story_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StoryTraceabilityReport:
    """Compiled story-to-test traceability report."""

    stories: tuple[StoryTraceabilityStory, ...]
    findings: tuple[StoryTraceabilityFinding, ...] = ()

    @property
    def passed(self) -> bool:
        """Return true when traceability metadata has no findings."""

        return not self.findings


def compile_story_traceability(
    hurl_tests: Sequence[HurlTest],
    *,
    story_documents: Sequence[StoryTraceabilityDocument] = (),
    story_findings: Sequence[StoryTraceabilityFinding] = (),
    story_document_scope_present: bool = False,
) -> StoryTraceabilityReport:
    """Compile discovered Hurl metadata into a story traceability report.

    This bridge intentionally does not call Jira, Notion, Linear, or any other
    business system. External URLs are treated as metadata identifiers only.
    """

    test_paths: dict[str, set[Path]] = {}
    story_owners: dict[str, set[str]] = {}
    story_doc_urls: dict[str, set[str]] = {}
    story_tags: dict[str, set[str]] = {}
    doc_url_story_ids: dict[str, set[str]] = {}
    story_paths: dict[str, set[Path]] = {}
    story_titles: dict[str, set[str]] = {}
    findings: list[StoryTraceabilityFinding] = list(story_findings)

    for hurl_test in sorted(hurl_tests, key=lambda item: str(item.path)):
        story_id = hurl_test.metadata.story_id
        if story_id is None:
            findings.append(
                StoryTraceabilityFinding(
                    kind="missing_story_id",
                    test_path=hurl_test.path,
                    message=f"{hurl_test.path} has no # entroping: story_id metadata.",
                ),
            )
            continue

        test_paths.setdefault(story_id, set()).add(hurl_test.path)
        story_tags.setdefault(story_id, set()).update(hurl_test.tags)

        owner = hurl_test.metadata.meta.get("owner")
        if owner is not None:
            story_owners.setdefault(story_id, set()).add(owner)

        doc_url = hurl_test.metadata.meta.get("doc_url")
        if doc_url is not None:
            story_doc_urls.setdefault(story_id, set()).add(doc_url)
            doc_url_story_ids.setdefault(doc_url, set()).add(story_id)

    for document in sorted(story_documents, key=lambda item: (item.story_id, str(item.path))):
        story_paths.setdefault(document.story_id, set()).add(document.path)
        if document.title is not None:
            story_titles.setdefault(document.story_id, set()).add(document.title)

    for doc_url, story_ids in sorted(doc_url_story_ids.items()):
        if len(story_ids) <= 1:
            continue
        sorted_story_ids = tuple(sorted(story_ids))
        findings.append(
            StoryTraceabilityFinding(
                kind="duplicate_doc_url",
                doc_url=doc_url,
                story_ids=sorted_story_ids,
                message=(
                    f"External doc URL {doc_url} is linked to multiple story IDs: "
                    f"{', '.join(sorted_story_ids)}."
                ),
            ),
        )

    for story_id, paths in sorted(story_paths.items()):
        sorted_paths = tuple(sorted(paths, key=lambda path: str(path)))
        if len(sorted_paths) > 1:
            findings.append(
                StoryTraceabilityFinding(
                    kind="duplicate_story_id",
                    story_path=sorted_paths[0],
                    story_ids=(story_id,),
                    message=(
                        f"Story ID {story_id} is defined by multiple Markdown files: "
                        f"{', '.join(str(path) for path in sorted_paths)}."
                    ),
                ),
            )

    if story_document_scope_present or story_documents or story_findings:
        for story_id in sorted(test_paths):
            if story_id not in story_paths:
                sorted_tests = tuple(sorted(test_paths[story_id], key=lambda path: str(path)))
                findings.append(
                    StoryTraceabilityFinding(
                        kind="missing_story",
                        test_path=sorted_tests[0] if sorted_tests else None,
                        story_ids=(story_id,),
                        message=(
                            f"Story ID {story_id} is referenced by Hurl tests but has no "
                            "matching Markdown story under docs/stories."
                        ),
                    ),
                )

        for story_id in sorted(story_paths):
            if story_id in test_paths:
                continue
            sorted_paths = tuple(sorted(story_paths[story_id], key=lambda path: str(path)))
            findings.append(
                StoryTraceabilityFinding(
                    kind="story_without_tests",
                    story_path=sorted_paths[0] if sorted_paths else None,
                    story_ids=(story_id,),
                    message=(
                        f"Story ID {story_id} is defined in Markdown but has no linked "
                        "Hurl tests."
                    ),
                ),
            )

    all_story_ids = sorted(set(test_paths) | set(story_paths))
    stories = tuple(
        StoryTraceabilityStory(
            story_id=story_id,
            test_paths=tuple(
                sorted(test_paths.get(story_id, set()), key=lambda path: str(path)),
            ),
            story_paths=tuple(
                sorted(story_paths.get(story_id, set()), key=lambda path: str(path)),
            ),
            titles=tuple(sorted(story_titles.get(story_id, set()))),
            owners=tuple(sorted(story_owners.get(story_id, set()))),
            doc_urls=tuple(sorted(story_doc_urls.get(story_id, set()))),
            tags=tuple(sorted(story_tags.get(story_id, set()))),
        )
        for story_id in all_story_ids
    )
    return StoryTraceabilityReport(stories=stories, findings=tuple(findings))


def render_story_traceability_markdown(report: StoryTraceabilityReport) -> str:
    """Render a human-readable traceability report."""

    lines: list[str] = ["# Story Traceability", ""]
    if report.stories:
        lines.extend(
            [
                "## Stories",
                "",
                "| Story | Titles | Owners | Docs | Story Files | Tests | Tags |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ],
        )
        for story in report.stories:
            lines.append(
                " | ".join(
                    [
                        f"| {_table_cell(story.story_id)}",
                        _table_cell(", ".join(story.titles) or "-"),
                        _table_cell(", ".join(story.owners) or "-"),
                        _table_cell(", ".join(story.doc_urls) or "-"),
                        _table_cell(", ".join(str(path) for path in story.story_paths) or "-"),
                        _table_cell(", ".join(str(path) for path in story.test_paths) or "-"),
                        f"{_table_cell(', '.join(story.tags) or '-')} |",
                    ],
                ),
            )
    else:
        lines.extend(["## Stories", "", "No story-linked tests found."])

    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No traceability findings.")
        return "\n".join(lines) + "\n"

    lines.extend(["| Kind | Location | Message |", "| --- | --- | --- |"])
    for finding in report.findings:
        location = _finding_location(finding)
        lines.append(
            " | ".join(
                [
                    f"| {_table_cell(finding.kind)}",
                    _table_cell(str(location) if location is not None else "-"),
                    f"{_table_cell(finding.message)} |",
                ],
            ),
        )

    return "\n".join(lines) + "\n"


def story_traceability_report_to_dict(report: StoryTraceabilityReport) -> dict[str, object]:
    """Return the versioned JSON-serializable traceability report payload."""

    return {
        "schema_version": TRACEABILITY_REPORT_SCHEMA_VERSION,
        "summary": {
            "stories": len(report.stories),
            "findings": len(report.findings),
            "passed": report.passed,
        },
        "stories": [_story_to_dict(story) for story in report.stories],
        "findings": [_finding_to_dict(finding) for finding in report.findings],
    }


def _story_to_dict(story: StoryTraceabilityStory) -> dict[str, object]:
    return {
        "story_id": story.story_id,
        "test_paths": [str(path) for path in story.test_paths],
        "story_paths": [str(path) for path in story.story_paths],
        "titles": list(story.titles),
        "owners": list(story.owners),
        "doc_urls": list(story.doc_urls),
        "tags": list(story.tags),
    }


def _finding_to_dict(finding: StoryTraceabilityFinding) -> dict[str, object]:
    return {
        "kind": finding.kind,
        "message": finding.message,
        "test_path": str(finding.test_path) if finding.test_path is not None else None,
        "story_path": str(finding.story_path) if finding.story_path is not None else None,
        "doc_url": finding.doc_url,
        "story_ids": list(finding.story_ids),
    }


def _finding_location(finding: StoryTraceabilityFinding) -> Path | str | None:
    if finding.test_path is not None:
        return finding.test_path
    if finding.story_path is not None:
        return finding.story_path
    if finding.doc_url is not None:
        return finding.doc_url
    if finding.story_ids:
        return ", ".join(finding.story_ids)
    return None


def _table_cell(value: str) -> str:
    return escape(value, quote=True).replace("|", "\\|").replace("\n", " ")
