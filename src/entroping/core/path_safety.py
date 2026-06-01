"""Shared path-safety helpers for filesystem adapters."""

from pathlib import Path


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
