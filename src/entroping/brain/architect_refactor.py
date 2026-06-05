"""Architect refactor orchestration for existing Architect-owned Hurl files."""

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from entroping.brain.architect_writer import PreparedHurlWrite, write_refactor_hurl_edits
from entroping.brain.litellm_client import LiteLLMClient, LiteLLMCostEstimate, LiteLLMUsage
from entroping.brain.output_parser import parse_architect_edit_set
from entroping.brain.persona_loader import load_agent_persona
from entroping.brain.prompt_builder import build_architect_prompt_package
from entroping.brain.safety import has_disallowed_control, redact_secret_like_values
from entroping.bridge.merge import (
    HurlMergeError,
    list_managed_hurl_block_ids,
    merge_managed_hurl_blocks,
)
from entroping.core.agent_manifest import (
    AgentRunCostEvidence,
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
    provider: str | None = None
    cost: LiteLLMCostEstimate = field(default_factory=LiteLLMCostEstimate.empty)
    preview: bool = False
    preview_paths: tuple[str, ...] = ()
    preview_diff: str = ""


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
    preview: bool = False,
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
    if preview:
        written_paths: tuple[Path, ...] = ()
        preview_paths = tuple(write.path for write in writes)
        preview_diff = _render_refactor_preview_diff(writes, targets=targets)
    else:
        written_paths = write_refactor_hurl_edits(writes, project_root=root)
        preview_paths = ()
        preview_diff = ""
    manifest = write_agent_run_manifest(
        AgentRunManifestInput(
            project_root=root,
            command="architect refactor",
            mode="refactor",
            agent="builder",
            model=completion.model,
            provider=completion.provider,
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
            cost=AgentRunCostEvidence(
                estimated_usd=completion.cost.estimated_usd,
                input_cost_per_1m_tokens_usd=completion.cost.input_cost_per_1m_tokens_usd,
                output_cost_per_1m_tokens_usd=completion.cost.output_cost_per_1m_tokens_usd,
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
        provider=completion.provider,
        cost=completion.cost,
        preview=preview,
        preview_paths=preview_paths,
        preview_diff=preview_diff,
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


def _render_refactor_preview_diff(
    writes: tuple[PreparedHurlWrite, ...],
    *,
    targets: tuple[RefactorTarget, ...],
) -> str:
    targets_by_path = {target.display_path: target for target in targets}
    rendered: list[str] = []
    for write in writes:
        target = targets_by_path[write.path]
        diff_lines = difflib.unified_diff(
            target.content.splitlines(),
            write.content.splitlines(),
            fromfile=f"a/{write.path}",
            tofile=f"b/{write.path}",
            lineterm="",
        )
        rendered.extend(redact_secret_like_values(line) for line in diff_lines)
    if not rendered:
        return ""
    return "\n".join(rendered) + "\n"


def _display_path(path: Path, *, root: Path) -> str:
    return path.relative_to(root).as_posix()
