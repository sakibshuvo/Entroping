"""Shared path-safety helpers for filesystem adapters."""

from pathlib import Path


def display_path(path: Path, root: Path | None = None) -> str:
    resolved_path = path.expanduser().resolve(strict=False)
    if root is None:
        return resolved_path.as_posix()

    resolved_root = root.expanduser().resolve(strict=False)
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def first_symlink_path_component(path: Path, *, root: Path | None = None) -> Path | None:
    """Return the first symlink component in ``path`` without resolving it."""

    if root is not None:
        current = root
        parts = path.relative_to(root).parts
    elif path.is_absolute():
        current = Path(path.anchor)
        parts = path.parts[1:]
    else:
        current = Path(".")
        parts = path.parts

    for part in parts:
        current = current / part
        if current.is_symlink():
            return current
    return None
