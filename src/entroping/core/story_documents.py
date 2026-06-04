"""Filesystem discovery for local Markdown story documents."""

from dataclasses import dataclass
from pathlib import Path

from entroping.bridge.story_traceability import (
    StoryTraceabilityDocument,
    StoryTraceabilityFinding,
    TraceabilityFindingKind,
)
from entroping.core.path_safety import first_symlink_path_component


@dataclass(frozen=True, slots=True)
class StoryDocumentDiscoveryResult:
    """Discovered local story documents plus non-fatal findings."""

    documents: tuple[StoryTraceabilityDocument, ...] = ()
    findings: tuple[StoryTraceabilityFinding, ...] = ()
    scope_present: bool = False


def discover_story_documents(*, project_root: Path) -> StoryDocumentDiscoveryResult:
    """Discover story Markdown files under the documented ``docs/stories`` convention."""

    root = project_root.expanduser().resolve()
    stories_root = root / "docs" / "stories"
    if not stories_root.exists():
        return StoryDocumentDiscoveryResult()

    root_symlink = first_symlink_path_component(stories_root, root=root)
    if root_symlink is not None:
        display_path = _display_path(root_symlink, root)
        return StoryDocumentDiscoveryResult(
            findings=(
                _finding(
                    kind="unsafe_story_path",
                    story_path=display_path,
                    message=f"Story document path must not use symlinks: {display_path}.",
                ),
            ),
            scope_present=True,
        )

    documents: list[StoryTraceabilityDocument] = []
    findings: list[StoryTraceabilityFinding] = []
    for path in sorted(stories_root.rglob("*.md"), key=lambda item: item.as_posix()):
        relative_path = _display_path(path, root)
        symlink_component = first_symlink_path_component(path, root=root)
        if symlink_component is not None:
            findings.append(
                _finding(
                    kind="unsafe_story_path",
                    story_path=relative_path,
                    message=(
                        "Story document path must not use symlinks: "
                        f"{_display_path(symlink_component, root)}."
                    ),
                ),
            )
            continue
        if not path.is_file():
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    kind="malformed_story_metadata",
                    story_path=relative_path,
                    message=f"{relative_path} is not valid UTF-8.",
                ),
            )
            continue

        parsed = _parse_story_document(content, path=relative_path)
        if isinstance(parsed, StoryTraceabilityFinding):
            findings.append(parsed)
        else:
            documents.append(parsed)

    return StoryDocumentDiscoveryResult(
        documents=tuple(documents),
        findings=tuple(findings),
        scope_present=True,
    )


def _parse_story_document(
    content: str,
    *,
    path: Path,
) -> StoryTraceabilityDocument | StoryTraceabilityFinding:
    story_id: str | None = None
    title: str | None = None
    heading: str | None = None

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and heading is None:
            heading = stripped.removeprefix("# ").strip()
        if ":" not in stripped:
            continue
        key, raw_value = (part.strip() for part in stripped.split(":", maxsplit=1))
        if key == "story_id" and story_id is None:
            story_id = raw_value
        elif key == "title" and title is None:
            title = raw_value

    if story_id is None or story_id == "":
        return _finding(
            kind="malformed_story_metadata",
            story_path=path,
            message=f"{path} must declare story_id: <id>.",
        )
    if _has_control_character(story_id):
        return _finding(
            kind="malformed_story_metadata",
            story_path=path,
            message=f"{path} story_id must not contain control characters.",
        )

    normalized_title = _first_non_empty(title, heading)
    if normalized_title is not None and _has_control_character(normalized_title):
        return _finding(
            kind="malformed_story_metadata",
            story_path=path,
            message=f"{path} title must not contain control characters.",
        )

    return StoryTraceabilityDocument(
        story_id=story_id,
        path=path,
        title=normalized_title,
    )


def _finding(
    *,
    kind: TraceabilityFindingKind,
    story_path: Path,
    message: str,
) -> StoryTraceabilityFinding:
    return StoryTraceabilityFinding(
        kind=kind,
        story_path=story_path,
        message=message,
    )


def _display_path(path: Path, root: Path) -> Path:
    try:
        return Path(path.relative_to(root))
    except ValueError:
        return path


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
