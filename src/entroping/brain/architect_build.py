"""Architect prompt-build orchestration."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from entroping.brain.architect_writer import write_architect_edits
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMUsage
from entroping.brain.output_parser import parse_architect_edit_set
from entroping.brain.persona_loader import load_agent_persona
from entroping.brain.prompt_builder import build_architect_prompt_package
from entroping.models import ArchitectEdit, ArchitectEditSet, parse_hurl_metadata
from entroping.models.qanstitution import Qanstitution

_ARCHITECT_SOURCE_MARKER = "# entroping: source=architect"


@dataclass(frozen=True)
class ArchitectPromptBuildResult:
    """Result of a validated Architect prompt build."""

    summary: str
    warnings: tuple[str, ...]
    written_paths: tuple[Path, ...]
    model: str
    latency_ms: int
    usage: LiteLLMUsage


def run_architect_prompt_build(
    *,
    law: Qanstitution,
    intent: str,
    tags: Sequence[str] = (),
    project_root: str | Path = ".",
    config_path: str | Path = "qanstitution.yaml",
    client: LiteLLMClient | None = None,
) -> ArchitectPromptBuildResult:
    """Generate Architect-owned Hurl files from a Builder prompt."""

    persona = load_agent_persona(law, "builder", config_path=config_path)
    package = build_architect_prompt_package(
        law=law,
        persona=persona,
        intent=_render_prompt_intent(intent, tags=tags),
        source_context={},
    )
    completion = (client or LiteLLMClient()).complete(package)
    edit_set = parse_architect_edit_set(completion.content)
    edit_set = _apply_requested_tags(edit_set, tags=tags)
    written_paths = write_architect_edits(edit_set, project_root=project_root)
    return ArchitectPromptBuildResult(
        summary=edit_set.summary,
        warnings=tuple(edit_set.warnings),
        written_paths=written_paths,
        model=completion.model,
        latency_ms=completion.latency_ms,
        usage=completion.usage,
    )


def _render_prompt_intent(intent: str, *, tags: Sequence[str]) -> str:
    if not tags:
        return intent
    return "\n\n".join([intent, f"Requested Entroping tags: {', '.join(tags)}"])


def _apply_requested_tags(edit_set: ArchitectEditSet, *, tags: Sequence[str]) -> ArchitectEditSet:
    requested_tags = tuple(sorted(set(tags)))
    if not requested_tags:
        return edit_set

    return ArchitectEditSet(
        summary=edit_set.summary,
        warnings=list(edit_set.warnings),
        edits=[
            ArchitectEdit(
                path=edit.path,
                content=_content_with_requested_tags(edit.content, requested_tags),
                rationale=edit.rationale,
            )
            for edit in edit_set.edits
        ],
    )


def _content_with_requested_tags(content: str, requested_tags: Sequence[str]) -> str:
    metadata = parse_hurl_metadata(content)
    merged_tags = tuple(sorted({*metadata.tags, *requested_tags}))
    tag_line = f"# entroping: tags={','.join(merged_tags)}"

    lines = content.splitlines()
    for index, line in enumerate(lines):
        if _is_tags_metadata_line(line):
            lines[index] = tag_line
            return _join_hurl_lines(lines, trailing_newline=content.endswith("\n"))

    insert_at = _tag_insert_index(lines)
    lines.insert(insert_at, tag_line)
    return _join_hurl_lines(lines, trailing_newline=content.endswith("\n"))


def _is_tags_metadata_line(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped.startswith("# entroping:"):
        return False
    payload = stripped.removeprefix("# entroping:").strip()
    if "=" not in payload:
        return False
    key = payload.split("=", maxsplit=1)[0].strip()
    return key == "tags"


def _tag_insert_index(lines: Sequence[str]) -> int:
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.strip() == _ARCHITECT_SOURCE_MARKER:
            return index + 1
        return index
    return 0


def _join_hurl_lines(lines: Sequence[str], *, trailing_newline: bool) -> str:
    content = "\n".join(lines)
    if trailing_newline:
        return f"{content}\n"
    return content
