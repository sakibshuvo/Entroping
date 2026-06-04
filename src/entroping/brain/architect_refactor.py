"""Architect refactor orchestration for existing Architect-owned Hurl files."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from entroping.brain.architect_writer import PreparedHurlWrite, write_refactor_hurl_edits
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMUsage
from entroping.brain.output_parser import parse_architect_edit_set
from entroping.brain.persona_loader import load_agent_persona
from entroping.brain.prompt_builder import build_architect_prompt_package
from entroping.brain.safety import has_disallowed_control
from entroping.bridge.merge import (
    HurlMergeError,
    list_managed_hurl_block_ids,
    merge_managed_hurl_blocks,
)
from entroping.core.agent_manifest import (
    AgentRunManifestInput,
    AgentRunUsageEvidence,
    write_agent_run_manifest,
)
from entroping.core.hurl_validator import validate_hurl_content
from entroping.core.path_safety import first_symlink_path_component
from entroping.models import ArchitectEditSet
from entroping.models.qanstitution import Qanstitution

_ARCHITECT_SOURCE_MARKER = "# entroping: source=architect"
_MAX_TARGET_BYTES = 256_000
HurlValidator = Callable[[str, str], None]


class ArchitectRefactorError(ValueError):
    """Raised when an Architect refactor request is unsafe or invalid."""


@dataclass(frozen=True)
class ArchitectRefactorResult:
    """Result of a validated Architect refactor."""

    summary: str
    warnings: tuple[str, ...]
    written_paths: tuple[Path, ...]
    model: str
    latency_ms: int
    usage: LiteLLMUsage
    manifest_path: Path


@dataclass(frozen=True)
class RefactorTarget:
    """A local Architect-owned Hurl file selected for refactor."""

    display_path: str
    path: Path
    content: str
    ownership: Literal["architect", "managed_blocks"]
    managed_block_ids: tuple[str, ...] = ()


def run_architect_refactor(
    *,
    law: Qanstitution,
    target_glob: str,
    prompt: str,
    project_root: str | Path = ".",
    config_path: str | Path = "qanstitution.yaml",
    client: LiteLLMClient | None = None,
    hurl_validator: HurlValidator | None = None,
) -> ArchitectRefactorResult:
    """Refactor selected Architect-owned Hurl files through the Builder agent."""

    root = Path(project_root).expanduser().resolve()
    targets = discover_refactor_targets(target_glob, project_root=root)
    source_context = {target.display_path: target.content for target in targets}
    persona = load_agent_persona(law, "builder", config_path=config_path)
    package = build_architect_prompt_package(
        law=law,
        persona=persona,
        intent=_render_refactor_intent(prompt, targets=targets),
        source_context=source_context,
    )
    completion = (client or LiteLLMClient()).complete(package)
    edit_set = parse_architect_edit_set(completion.content)
    _validate_selected_edits(edit_set, selected_paths={target.display_path for target in targets})
    writes = _prepare_refactor_writes(edit_set, targets=targets)
    _validate_refactored_hurl(writes, hurl_validator=hurl_validator or validate_hurl_content)
    written_paths = write_refactor_hurl_edits(writes, project_root=root)
    manifest = write_agent_run_manifest(
        AgentRunManifestInput(
            project_root=root,
            command="architect refactor",
            mode="refactor",
            agent="builder",
            model=completion.model,
            persona_source_path=persona.source_path,
            persona_content=persona.content,
            prompt_intent=prompt,
            prompt_package_messages=tuple(message.content for message in package.messages),
            output_paths=written_paths,
            tags=(),
            validation_status="passed",
            structured_output_validated=True,
            hurl_validated=True,
            latency_ms=completion.latency_ms,
            usage=AgentRunUsageEvidence(
                prompt_tokens=completion.usage.prompt_tokens,
                completion_tokens=completion.usage.completion_tokens,
                total_tokens=completion.usage.total_tokens,
            ),
        )
    )
    return ArchitectRefactorResult(
        summary=edit_set.summary,
        warnings=tuple(edit_set.warnings),
        written_paths=written_paths,
        model=completion.model,
        latency_ms=completion.latency_ms,
        usage=completion.usage,
        manifest_path=manifest.manifest_path,
    )


def discover_refactor_targets(
    target_glob: str,
    *,
    project_root: str | Path = ".",
) -> tuple[RefactorTarget, ...]:
    """Load and validate Architect-owned Hurl files selected by a local glob."""

    root = Path(project_root).expanduser().resolve()
    glob_pattern = _validate_target_glob(target_glob)
    matches = sorted(root.glob(glob_pattern))
    if not matches:
        msg = f"No Hurl targets matched: {target_glob}"
        raise ArchitectRefactorError(msg)

    targets = [_load_refactor_target(match, root=root) for match in matches]
    return tuple(targets)


def _validate_target_glob(value: str) -> str:
    glob_pattern = value.strip()
    if not glob_pattern:
        msg = "Refactor target glob must not be empty"
        raise ArchitectRefactorError(msg)
    if "\\" in glob_pattern:
        msg = "Refactor target glob must use POSIX separators"
        raise ArchitectRefactorError(msg)
    if has_disallowed_control(glob_pattern):
        msg = "Refactor target glob must not contain control characters"
        raise ArchitectRefactorError(msg)

    parsed = PurePosixPath(glob_pattern)
    if parsed.is_absolute() or ".." in parsed.parts:
        msg = "Refactor target glob must stay under project root"
        raise ArchitectRefactorError(msg)
    return glob_pattern


def _load_refactor_target(path: Path, *, root: Path) -> RefactorTarget:
    _reject_symlink_path(path, root=root)
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Refactor target must stay under project root: {_display_path(path, root=root)}"
        raise ArchitectRefactorError(msg)
    if resolved.suffix.lower() != ".hurl":
        msg = f"Refactor target must be a Hurl file: {_display_path(resolved, root=root)}"
        raise ArchitectRefactorError(msg)
    if not resolved.is_file():
        msg = f"Refactor target must be a file: {_display_path(resolved, root=root)}"
        raise ArchitectRefactorError(msg)

    display_path = _display_path(resolved, root=root)
    content = _read_refactor_target(resolved, display_path=display_path)
    if _has_architect_header(content):
        return RefactorTarget(
            display_path=display_path,
            path=resolved,
            content=content,
            ownership="architect",
        )

    try:
        managed_block_ids = list_managed_hurl_block_ids(content)
    except HurlMergeError as exc:
        msg = f"Invalid managed blocks in refactor target {display_path}: {exc}"
        raise ArchitectRefactorError(msg) from exc
    if not managed_block_ids:
        msg = f"Refactor target must be Architect-owned or contain managed blocks: {display_path}"
        raise ArchitectRefactorError(msg)
    return RefactorTarget(
        display_path=display_path,
        path=resolved,
        content=content,
        ownership="managed_blocks",
        managed_block_ids=managed_block_ids,
    )


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = (
            "Refactor target must not use symlinks: "
            f"{_display_path(symlink_component, root=root)}"
        )
        raise ArchitectRefactorError(msg)


def _read_refactor_target(path: Path, *, display_path: str) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        msg = f"Could not inspect refactor target {display_path}: {exc}"
        raise ArchitectRefactorError(msg) from exc
    if size > _MAX_TARGET_BYTES:
        msg = f"Refactor target is too large: {display_path}"
        raise ArchitectRefactorError(msg)

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Refactor target must be UTF-8 Hurl: {display_path}"
        raise ArchitectRefactorError(msg) from exc
    except OSError as exc:
        msg = f"Could not read refactor target {display_path}: {exc}"
        raise ArchitectRefactorError(msg) from exc
    if not content.strip():
        msg = f"Refactor target must not be empty: {display_path}"
        raise ArchitectRefactorError(msg)
    return content


def _has_architect_header(content: str) -> bool:
    for line in content.splitlines():
        if not line.strip():
            continue
        return line.strip() == _ARCHITECT_SOURCE_MARKER
    return False


def _render_refactor_intent(prompt: str, *, targets: tuple[RefactorTarget, ...]) -> str:
    target_lines = "\n".join(_render_target_line(target) for target in targets)
    return "\n\n".join(
        [
            "Refactor only the selected Hurl files.",
            f"Instruction:\n{prompt}",
            f"Selected targets:\n{target_lines}",
            (
                "Return full Hurl content for Architect-owned whole-file targets. "
                "For managed-block manual targets, return only matching managed block "
                "sections and do not include or modify content outside those markers."
            ),
            "Return a JSON edit for each modified target and do not create new files.",
        ]
    )


def _render_target_line(target: RefactorTarget) -> str:
    if target.ownership == "architect":
        return f"- {target.display_path} (Architect-owned whole-file target)"
    block_ids = ", ".join(target.managed_block_ids)
    return f"- {target.display_path} (Managed-block manual target; block IDs: {block_ids})"


def _validate_selected_edits(
    edit_set: ArchitectEditSet,
    *,
    selected_paths: set[str],
) -> None:
    for edit in edit_set.edits:
        if edit.path not in selected_paths:
            msg = f"Architect refactor may only modify selected targets: {edit.path}"
            raise ArchitectRefactorError(msg)


def _prepare_refactor_writes(
    edit_set: ArchitectEditSet,
    *,
    targets: tuple[RefactorTarget, ...],
) -> tuple[PreparedHurlWrite, ...]:
    targets_by_path = {target.display_path: target for target in targets}
    writes: list[PreparedHurlWrite] = []
    for edit in edit_set.edits:
        target = targets_by_path[edit.path]
        if target.ownership == "architect":
            writes.append(
                PreparedHurlWrite(
                    path=edit.path,
                    content=edit.content,
                    require_architect_header=True,
                )
            )
            continue

        try:
            merged = merge_managed_hurl_blocks(target.content, edit.content)
        except HurlMergeError as exc:
            msg = f"Could not merge managed blocks for {target.display_path}: {exc}"
            raise ArchitectRefactorError(msg) from exc
        writes.append(
            PreparedHurlWrite(
                path=edit.path,
                content=merged.content,
                require_architect_header=False,
            )
        )
    return tuple(writes)


def _validate_refactored_hurl(
    writes: tuple[PreparedHurlWrite, ...],
    *,
    hurl_validator: HurlValidator,
) -> None:
    for write in writes:
        hurl_validator(write.content, write.path)


def _display_path(path: Path, *, root: Path) -> str:
    return path.relative_to(root).as_posix()
