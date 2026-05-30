"""Staged filesystem writes for validated Architect Hurl edits."""

import os
import tempfile
from pathlib import Path

from entroping.models import ArchitectEdit, ArchitectEditSet

_ARCHITECT_SOURCE_MARKER = "# entroping: source=architect"


class ArchitectWriteError(ValueError):
    """Raised when validated Architect edits cannot be written safely."""


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


def _resolve_output_path(edit: ArchitectEdit, *, root: Path) -> Path:
    candidate = root / edit.path
    _reject_symlink_path(candidate, root=root)
    output_path = candidate.resolve()
    if not output_path.is_relative_to(root):
        msg = f"Architect Hurl path must stay under project root: {edit.path}"
        raise ArchitectWriteError(msg)
    return output_path


def _reject_symlink_path(candidate: Path, *, root: Path) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            msg = f"Refusing to write symlinked Hurl file: {current}"
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


def _ensure_trailing_newline(content: str) -> str:
    if content.endswith("\n"):
        return content
    return f"{content}\n"


def _validate_existing_target(path: Path) -> None:
    if path.is_symlink():
        msg = f"Refusing to write symlinked Hurl file: {path}"
        raise ArchitectWriteError(msg)
    if not path.exists():
        return
    if not path.is_file():
        msg = f"Refusing to overwrite non-file Hurl target: {path}"
        raise ArchitectWriteError(msg)
    existing = path.read_text(encoding="utf-8")
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
