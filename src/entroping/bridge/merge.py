"""Hurl merge/refactor boundary for preserving manual edits."""

import re
from dataclasses import dataclass
from typing import Literal

_MARKER_PATTERN = re.compile(
    r"^#\s*entroping:\s*managed-(?P<kind>begin|end)\s+(?P<id>[A-Za-z0-9_.:-]+)$"
)


class HurlMergeError(ValueError):
    """Raised when a managed Hurl merge cannot be applied safely."""


@dataclass(frozen=True)
class HurlMergeResult:
    """Result of replacing explicit managed Hurl blocks."""

    content: str
    replaced_blocks: tuple[str, ...]


@dataclass(frozen=True)
class ManagedBlock:
    """A delimited block that Entroping is allowed to replace."""

    block_id: str
    start: int
    end: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ManagedMarker:
    """A parsed managed-block marker."""

    kind: Literal["begin", "end"]
    block_id: str


def merge_managed_hurl_blocks(existing_content: str, generated_content: str) -> HurlMergeResult:
    """Replace generated managed blocks while preserving all manual content."""

    existing_lines, existing_blocks = _parse_managed_blocks(existing_content, label="existing Hurl")
    _generated_lines, generated_blocks = _parse_managed_blocks(
        generated_content,
        label="generated Hurl",
    )
    if not existing_blocks:
        msg = "existing Hurl does not contain managed blocks"
        raise HurlMergeError(msg)
    if not generated_blocks:
        msg = "generated Hurl does not contain managed blocks"
        raise HurlMergeError(msg)

    unknown_blocks = tuple(
        block_id for block_id in generated_blocks if block_id not in existing_blocks
    )
    if unknown_blocks:
        msg = f"generated block is not present in existing Hurl: {unknown_blocks[0]}"
        raise HurlMergeError(msg)

    output: list[str] = []
    replaced_blocks: list[str] = []
    index = 0
    block_by_start = {block.start: block for block in existing_blocks.values()}
    while index < len(existing_lines):
        existing_block = block_by_start.get(index)
        if existing_block is None:
            output.append(existing_lines[index])
            index += 1
            continue

        generated_block = generated_blocks.get(existing_block.block_id)
        if generated_block is None:
            output.extend(existing_block.lines)
        else:
            output.extend(generated_block.lines)
            replaced_blocks.append(existing_block.block_id)
        index = existing_block.end + 1

    return HurlMergeResult(content="".join(output), replaced_blocks=tuple(replaced_blocks))


def _parse_managed_blocks(content: str, *, label: str) -> tuple[list[str], dict[str, ManagedBlock]]:
    lines = content.splitlines(keepends=True)
    blocks: dict[str, ManagedBlock] = {}
    current_id: str | None = None
    current_start: int | None = None

    for index, line in enumerate(lines):
        marker = _parse_marker(line)
        if marker is None:
            continue
        if marker.kind == "begin":
            if current_id is not None:
                msg = f"nested managed block in {label}: {marker.block_id}"
                raise HurlMergeError(msg)
            if marker.block_id in blocks:
                msg = f"duplicate managed block id: {marker.block_id}"
                raise HurlMergeError(msg)
            current_id = marker.block_id
            current_start = index
            continue

        if current_id is None or current_start is None:
            msg = f"managed-end without managed-begin in {label}: {marker.block_id}"
            raise HurlMergeError(msg)
        if marker.block_id != current_id:
            msg = f"managed-end {marker.block_id} does not match managed-begin {current_id}"
            raise HurlMergeError(msg)
        blocks[current_id] = ManagedBlock(
            block_id=current_id,
            start=current_start,
            end=index,
            lines=tuple(lines[current_start : index + 1]),
        )
        current_id = None
        current_start = None

    if current_id is not None:
        msg = f"missing managed-end for block {current_id}"
        raise HurlMergeError(msg)
    return lines, blocks


def _parse_marker(line: str) -> ManagedMarker | None:
    match = _MARKER_PATTERN.match(line.strip())
    if match is None:
        return None
    raw_kind = match.group("kind")
    if raw_kind == "begin":
        kind: Literal["begin", "end"] = "begin"
    elif raw_kind == "end":
        kind = "end"
    else:
        return None
    return ManagedMarker(kind=kind, block_id=match.group("id"))
