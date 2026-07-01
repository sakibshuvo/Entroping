"""Shared path-safety helpers for filesystem adapters."""

from pathlib import Path
from typing import Final

IGNORED_PATH_COMPONENTS: Final[frozenset[str]] = frozenset(
    {
        ".entroping",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reports",
        "venv",
    },
)


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


def is_ignored_project_path(path: Path, *, root: Path) -> bool:
    """Return true when a path should be skipped under Entroping local scanning."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    for part in relative.parts[:-1]:
        if part in IGNORED_PATH_COMPONENTS or part.startswith("."):
            return True
    return False
