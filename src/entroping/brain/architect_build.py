"""Architect prompt-build orchestration."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from entroping.brain.architect_writer import (
    PreparedHurlWrite,
    write_architect_edits,
    write_refactor_hurl_edits,
)
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMUsage
from entroping.brain.output_parser import parse_architect_edit_set
from entroping.brain.persona_loader import load_agent_persona
from entroping.brain.prompt_builder import build_architect_prompt_package
from entroping.bridge.merge import (
    HurlMergeError,
    list_managed_hurl_block_ids,
    merge_managed_hurl_blocks,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.core.path_safety import first_symlink_path_component
from entroping.models import ArchitectEdit, ArchitectEditSet, parse_hurl_metadata
from entroping.models.qanstitution import Qanstitution

_ARCHITECT_SOURCE_MARKER = "# entroping: source=architect"
_MAX_MERGE_TARGET_BYTES = 256_000
HurlValidator = Callable[[str, str], None]
BuildStrategy = Literal["create", "merge"]
ArchitectBuildAgent = Literal["builder", "breaker"]


@dataclass(frozen=True)
class ArchitectPromptBuildResult:
    """Result of a validated Architect prompt build."""

    summary: str
    warnings: tuple[str, ...]
    written_paths: tuple[Path, ...]
    model: str
    latency_ms: int
    usage: LiteLLMUsage
    agent: ArchitectBuildAgent


def run_architect_prompt_build(
    *,
    law: Qanstitution,
    intent: str,
    agent: ArchitectBuildAgent = "builder",
    tags: Sequence[str] = (),
    strategy: BuildStrategy = "create",
    project_root: str | Path = ".",
    config_path: str | Path = "qanstitution.yaml",
    client: LiteLLMClient | None = None,
    hurl_validator: HurlValidator | None = None,
) -> ArchitectPromptBuildResult:
    """Generate Architect-owned Hurl files from a Builder or Breaker prompt."""

    persona = load_agent_persona(law, agent, config_path=config_path)
    package = build_architect_prompt_package(
        law=law,
        persona=persona,
        intent=_render_prompt_intent(intent, agent=agent, tags=tags, strategy=strategy),
        source_context={},
    )
    completion = (client or LiteLLMClient()).complete(package)
    edit_set = parse_architect_edit_set(completion.content)
    edit_set = _apply_requested_tags(edit_set, tags=tags, agent=agent)
    if strategy == "merge":
        writes = _prepare_merge_writes(edit_set, project_root=project_root)
        _validate_prepared_hurl(writes, hurl_validator=hurl_validator or validate_hurl_content)
        written_paths = write_refactor_hurl_edits(writes, project_root=project_root)
    else:
        _validate_architect_hurl(edit_set, hurl_validator=hurl_validator or validate_hurl_content)
        written_paths = write_architect_edits(edit_set, project_root=project_root)
    return ArchitectPromptBuildResult(
        summary=edit_set.summary,
        warnings=tuple(edit_set.warnings),
        written_paths=written_paths,
        model=completion.model,
        latency_ms=completion.latency_ms,
        usage=completion.usage,
        agent=agent,
    )


def _render_prompt_intent(
    intent: str,
    *,
    agent: ArchitectBuildAgent = "builder",
    tags: Sequence[str],
    strategy: BuildStrategy,
) -> str:
    parts = [intent]
    if agent == "breaker":
        parts.append(
            "Breaker role: generate negative, abuse-case, authorization, boundary, "
            "and policy-bypass tests. Prefer hostile inputs, missing or invalid "
            "credentials, tenant-boundary checks, malformed payloads, and security "
            "regression cases. Do not invent secrets or print sensitive values. "
            "Keep every edit valid Hurl and distinguish generated tests with the "
            "`breaker` Entroping tag."
        )
    if strategy == "merge":
        parts.append(
            "Merge strategy: return edits for existing Hurl files only. "
            "For Architect-owned files, return full Hurl content. For manual files, "
            "return only matching managed blocks and do not include content outside "
            "`# entroping: managed-begin/end` markers."
        )
    if tags:
        parts.append(f"Requested Entroping tags: {', '.join(tags)}")
    return "\n\n".join(parts)


def _apply_requested_tags(
    edit_set: ArchitectEditSet,
    *,
    tags: Sequence[str],
    agent: ArchitectBuildAgent = "builder",
) -> ArchitectEditSet:
    requested_tags = tuple(sorted({*tags, *(("breaker",) if agent == "breaker" else ())}))
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


def _validate_architect_hurl(
    edit_set: ArchitectEditSet,
    *,
    hurl_validator: HurlValidator,
) -> None:
    for edit in edit_set.edits:
        hurl_validator(edit.content, edit.path)


def _prepare_merge_writes(
    edit_set: ArchitectEditSet,
    *,
    project_root: str | Path,
) -> tuple[PreparedHurlWrite, ...]:
    root = Path(project_root).expanduser().resolve()
    writes: list[PreparedHurlWrite] = []
    for edit in edit_set.edits:
        existing_content = _read_merge_target(edit.path, root=root)
        if _has_architect_header(existing_content):
            writes.append(
                PreparedHurlWrite(
                    path=edit.path,
                    content=edit.content,
                    require_architect_header=True,
                )
            )
            continue

        try:
            managed_block_ids = list_managed_hurl_block_ids(existing_content)
        except HurlMergeError as exc:
            msg = f"Invalid managed blocks in merge target {edit.path}: {exc}"
            raise ValueError(msg) from exc
        if not managed_block_ids:
            msg = f"Merge target must be Architect-owned or contain managed blocks: {edit.path}"
            raise ValueError(msg)
        try:
            merged = merge_managed_hurl_blocks(existing_content, edit.content)
        except HurlMergeError as exc:
            msg = f"Could not merge managed blocks for {edit.path}: {exc}"
            raise ValueError(msg) from exc
        writes.append(
            PreparedHurlWrite(
                path=edit.path,
                content=merged.content,
                require_architect_header=False,
            )
        )
    return tuple(writes)


def _validate_prepared_hurl(
    writes: tuple[PreparedHurlWrite, ...],
    *,
    hurl_validator: HurlValidator,
) -> None:
    for write in writes:
        hurl_validator(write.content, write.path)


def _has_architect_header(content: str) -> bool:
    for line in content.splitlines():
        if not line.strip():
            continue
        return line.strip() == _ARCHITECT_SOURCE_MARKER
    return False


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


def _read_merge_target(display_path: str, *, root: Path) -> str:
    candidate = root / display_path
    _reject_symlink_path(candidate, root=root)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Merge target must stay under project root: {display_path}"
        raise ValueError(msg)
    if not resolved.exists():
        msg = f"Merge target does not exist: {display_path}"
        raise ValueError(msg)
    if not resolved.is_file():
        msg = f"Merge target must be a file: {display_path}"
        raise ValueError(msg)
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        msg = f"Could not inspect merge target {display_path}: {exc}"
        raise ValueError(msg) from exc
    if size > _MAX_MERGE_TARGET_BYTES:
        msg = f"Merge target is too large: {display_path}"
        raise ValueError(msg)
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Merge target must be UTF-8 Hurl: {display_path}"
        raise ValueError(msg) from exc
    except OSError as exc:
        msg = f"Could not read merge target {display_path}: {exc}"
        raise ValueError(msg) from exc


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = (
            "Merge target must not use symlinks: "
            f"{symlink_component.relative_to(root).as_posix()}"
        )
        raise ValueError(msg)
