"""Durable local artifact writes with symlink-safe path handling."""

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from entroping.core.path_safety import first_symlink_path_component


class SafeWriteError(ValueError):
    """Raised when an artifact cannot be written safely."""


def safe_write_text(
    path: Path,
    content: str,
    *,
    artifact: str,
    root: Path | None = None,
) -> Path:
    """Write UTF-8 text through a flushed temporary file and atomic replace."""

    return _safe_write(path, content.encode("utf-8"), artifact=artifact, root=root)


def safe_write_bytes(
    path: Path,
    content: bytes,
    *,
    artifact: str,
    root: Path | None = None,
) -> Path:
    """Write bytes through a flushed temporary file and atomic replace."""

    return _safe_write(path, content, artifact=artifact, root=root)


def safe_append_text(
    path: Path,
    content: str,
    *,
    artifact: str,
    root: Path | None = None,
) -> Path:
    """Append UTF-8 text after validating the destination path is safe."""

    root_path = root.expanduser().resolve() if root is not None else None
    destination = _prepare_destination(path, artifact=artifact, root=root_path)
    try:
        _reject_symlink_path_components(destination, artifact=artifact, root=root_path)
        _ensure_under_root(destination, root_path, artifact=artifact)
        with destination.open("ab") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        msg = f"Could not append {artifact} {destination}: {exc}"
        raise SafeWriteError(msg) from exc
    return destination


def safe_report_output_path(
    path: Path,
    *,
    root: Path,
    artifact: str,
    forbidden_components: Iterable[str] = (".entroping", "envs"),
    forbid_components_anywhere: bool = True,
) -> Path:
    """Validate a report output path without resolving away symlink evidence."""

    root_path = root.expanduser().resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root_path / candidate

    try:
        relative_parts = candidate.resolve(strict=False).relative_to(root_path).parts
    except ValueError as exc:
        msg = f"{artifact} output path must stay under the project root"
        raise SafeWriteError(msg) from exc

    symlink_component = first_symlink_path_component(candidate, root=root_path)
    if symlink_component is not None:
        display = _relative_display(symlink_component, root=root_path)
        msg = f"{artifact} output path uses symlinked component: {display}"
        raise SafeWriteError(msg)

    forbidden = frozenset(part.lower() for part in forbidden_components)
    checked_parts = relative_parts if forbid_components_anywhere else relative_parts[:1]
    if any(part.lower() in forbidden for part in checked_parts):
        names = " or ".join(sorted(forbidden))
        msg = f"{artifact} must not be written into {names}"
        raise SafeWriteError(msg)

    return candidate


def _safe_write(
    path: Path,
    content: bytes,
    *,
    artifact: str,
    root: Path | None,
) -> Path:
    root_path = root.expanduser().resolve() if root is not None else None
    destination = _prepare_destination(path, artifact=artifact, root=root_path)
    temporary_path = _write_temporary_file(destination, content)
    try:
        _reject_symlink_path_components(destination, artifact=artifact, root=root_path)
        _ensure_under_root(destination, root_path, artifact=artifact)
        temporary_path.replace(destination)
    except OSError as exc:
        msg = f"Could not write {artifact} {destination}: {exc}"
        raise SafeWriteError(msg) from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return destination


def _relative_display(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _prepare_destination(path: Path, *, artifact: str, root: Path | None) -> Path:
    root_path = root
    expanded = path.expanduser()
    if root_path is not None and not expanded.is_absolute():
        expanded = root_path / expanded

    _ensure_under_root(expanded, root_path, artifact=artifact)
    _reject_symlink_path_components(expanded, artifact=artifact, root=root_path)

    try:
        expanded.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"Could not create parent directory for {artifact} {expanded}: {exc}"
        raise SafeWriteError(msg) from exc

    _reject_symlink_path_components(expanded, artifact=artifact, root=root_path)
    _ensure_under_root(expanded, root_path, artifact=artifact)
    if expanded.exists() and not expanded.is_file():
        msg = f"Refusing to overwrite non-file {artifact}: {expanded}"
        raise SafeWriteError(msg)
    return expanded.resolve()


def _ensure_under_root(path: Path, root: Path | None, *, artifact: str) -> None:
    if root is None:
        return
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"{artifact} path must stay under {root}: {path}"
        raise SafeWriteError(msg) from exc


def _reject_symlink_path_components(
    path: Path,
    *,
    artifact: str,
    root: Path | None,
) -> None:
    symlink_component = first_symlink_path_component(path, root=root)
    if symlink_component is None:
        return
    if symlink_component == path:
        msg = f"Refusing to overwrite symlinked {artifact}: {symlink_component}"
    else:
        msg = (
            f"Refusing to write {artifact} through symlinked path component: "
            f"{symlink_component}"
        )
    raise SafeWriteError(msg)


def _write_temporary_file(path: Path, content: bytes) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
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
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        msg = f"Could not write temporary artifact next to {path}: {exc}"
        raise SafeWriteError(msg) from exc
