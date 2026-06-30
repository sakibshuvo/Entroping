"""Staged filesystem writes for validated Architect Hurl edits."""

import codecs
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from entroping.core.path_safety import first_symlink_path_component
from entroping.models import ArchitectEdit, ArchitectEditSet

_ARCHITECT_SOURCE_MARKER = "# entroping: source=architect"
_OWNERSHIP_HEADER_READ_LIMIT_BYTES = 4096
_OWNERSHIP_HEADER_UTF8_LOOKAHEAD_BYTES = 4


class ArchitectWriteError(ValueError):
    """Raised when validated Architect edits cannot be written safely."""


@dataclass(frozen=True)
class PreparedHurlWrite:
    """One validated refactor write prepared by the Architect orchestrator."""

    path: str
    content: str
    require_architect_header: bool


def write_architect_edits(
    edit_set: ArchitectEditSet,
    *,
    project_root: str | Path = ".",
) -> tuple[Path, ...]:
    """Write validated Architect Hurl edits under ``project_root``."""

    root = Path(project_root).expanduser().resolve()
    staged: list[tuple[Path, str]] = []
    for edit in edit_set.edits:
        staged.append(
            (
                _resolve_output_path(edit, root=root),
                _architect_owned_content(edit.content),
            )
        )

    for output_path, _content in staged:
        _validate_existing_target(output_path)

    written: list[Path] = []
    for output_path, content in staged:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomically(output_path, content)
        written.append(output_path)
    return tuple(written)


def write_refactor_hurl_edits(
    writes: Sequence[PreparedHurlWrite],
    *,
    project_root: str | Path = ".",
) -> tuple[Path, ...]:
    """Write already-validated refactor results without changing ownership mode."""

    root = Path(project_root).expanduser().resolve()
    staged: list[tuple[Path, str, bool]] = []
    for write in writes:
        staged.append(
            (
                _resolve_refactor_path(write.path, root=root),
                _prepared_refactor_content(write),
                write.require_architect_header,
            )
        )

    for output_path, _content, require_architect_header in staged:
        _validate_existing_refactor_target(
            output_path,
            require_architect_header=require_architect_header,
        )

    written: list[Path] = []
    for output_path, content, _require_architect_header in staged:
        _write_text_atomically(output_path, content)
        written.append(output_path)
    return tuple(written)


def _resolve_output_path(edit: ArchitectEdit, *, root: Path) -> Path:
    candidate = root / edit.path
    _reject_symlink_path(candidate, root=root)
    output_path = candidate.resolve()
    if not output_path.is_relative_to(root):
        msg = f"Architect Hurl path must stay under project root: {edit.path}"
        raise ArchitectWriteError(msg)
    return output_path


def _resolve_refactor_path(display_path: str, *, root: Path) -> Path:
    path = display_path.strip()
    if not path:
        msg = "Refactor Hurl path must not be empty"
        raise ArchitectWriteError(msg)
    if _has_path_control(path):
        msg = "Refactor Hurl path must not contain control characters"
        raise ArchitectWriteError(msg)
    if "\\" in path:
        msg = "Refactor Hurl path must use POSIX separators"
        raise ArchitectWriteError(msg)
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        msg = f"Refactor Hurl path must stay under project root: {display_path}"
        raise ArchitectWriteError(msg)
    if not parsed.parts or parsed.parts[0] != "tests" or parsed.suffix != ".hurl":
        msg = f"Refactor Hurl path must be a tests/ .hurl file: {display_path}"
        raise ArchitectWriteError(msg)

    candidate = root / path
    _reject_symlink_path(candidate, root=root)
    output_path = candidate.resolve()
    if not output_path.is_relative_to(root):
        msg = f"Refactor Hurl path must stay under project root: {display_path}"
        raise ArchitectWriteError(msg)
    return output_path


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    symlink_component = first_symlink_path_component(candidate, root=root)
    if symlink_component is not None:
        msg = f"Refusing to write symlinked Hurl file: {symlink_component}"
        raise ArchitectWriteError(msg)


def _architect_owned_content(content: str) -> str:
    if _has_architect_header(content):
        return _ensure_trailing_newline(content)
    return f"{_ARCHITECT_SOURCE_MARKER}\n{_ensure_trailing_newline(content)}"


def _has_architect_header(content: str) -> bool:
    for line in content.splitlines():
        if not line.strip():
            continue
        return line.strip() == _ARCHITECT_SOURCE_MARKER
    return False


def _read_ownership_header_prefix(path: Path) -> str:
    decode_limit = _OWNERSHIP_HEADER_READ_LIMIT_BYTES + _OWNERSHIP_HEADER_UTF8_LOOKAHEAD_BYTES
    with path.open("rb") as handle:
        raw_prefix = handle.read(decode_limit + 1)
    file_continues = len(raw_prefix) > decode_limit
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    return decoder.decode(raw_prefix[:decode_limit], final=not file_continues)


def _ensure_trailing_newline(content: str) -> str:
    if content.endswith("\n"):
        return content
    return f"{content}\n"


def _has_path_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _prepared_refactor_content(write: PreparedHurlWrite) -> str:
    if write.require_architect_header:
        return _architect_owned_content(write.content)
    return _ensure_trailing_newline(write.content)


def _validate_existing_target(path: Path) -> None:
    if path.is_symlink():
        msg = f"Refusing to write symlinked Hurl file: {path}"
        raise ArchitectWriteError(msg)
    if not path.exists():
        return
    if not path.is_file():
        msg = f"Refusing to overwrite non-file Hurl target: {path}"
        raise ArchitectWriteError(msg)
    existing = _read_ownership_header_prefix(path)
    if not _has_architect_header(existing):
        msg = f"Refusing to overwrite non-Architect Hurl file: {path}"
        raise ArchitectWriteError(msg)


def _validate_existing_refactor_target(path: Path, *, require_architect_header: bool) -> None:
    if path.is_symlink():
        msg = f"Refusing to write symlinked Hurl file: {path}"
        raise ArchitectWriteError(msg)
    if not path.exists():
        msg = f"Refusing to create missing refactor target: {path}"
        raise ArchitectWriteError(msg)
    if not path.is_file():
        msg = f"Refusing to overwrite non-file Hurl target: {path}"
        raise ArchitectWriteError(msg)
    if not require_architect_header:
        return

    existing = _read_ownership_header_prefix(path)
    if not _has_architect_header(existing):
        msg = f"Refusing to overwrite non-Architect Hurl file: {path}"
        raise ArchitectWriteError(msg)


def _write_text_atomically(path: Path, content: str) -> None:
    temporary_path = _write_temporary_file(path, content)
    try:
        temporary_path.replace(path)
    except OSError as exc:
        msg = f"Could not write Architect Hurl file {path}: {exc}"
        raise ArchitectWriteError(msg) from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _write_temporary_file(path: Path, content: str) -> Path:
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            return temporary_path
    except OSError as exc:
        msg = f"Could not write temporary Architect Hurl file for {path}: {exc}"
        raise ArchitectWriteError(msg) from exc
