"""Validated deterministic PATH construction for maintainer orchestration."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Final

from scripts.factory_orchestration_errors import OrchestrationServiceError

_TRUSTED_TOOL_DIRS: Final = (
    Path("/usr/bin"),
    Path("/bin"),
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/home/linuxbrew/.linuxbrew/bin"),
)
_SYSTEM_DIRS = (Path("/usr/bin"), Path("/bin"))
_HOMEBREW_DIRS = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))


def trusted_executable(name: str) -> Path:
    """Resolve a tool only from the fixed cross-platform system contract."""

    if not name or "/" in name or name in {".", ".."}:
        raise OrchestrationServiceError("tool-unavailable")
    for directory in _TRUSTED_TOOL_DIRS:
        if not _safe_directory(directory):
            continue
        candidate = directory / name
        try:
            return _validated_executable(candidate)
        except OrchestrationServiceError:
            continue
    raise OrchestrationServiceError("tool-unavailable")


def trusted_tool_path(required: tuple[str, ...]) -> str:
    """Resolve required tools and allow only privately or root-owned safe parents."""

    directories = [directory for directory in _SYSTEM_DIRS if _safe_directory(directory)]
    directories.extend(
        directory
        for directory in _HOMEBREW_DIRS
        if _safe_directory(directory) and directory not in directories
    )
    resolved: dict[str, Path] = {}
    for name in required:
        candidate = shutil.which(name)
        if candidate is None:
            raise OrchestrationServiceError("tool-unavailable")
        executable = _validated_executable(Path(candidate))
        if not _safe_directory(executable.parent):
            raise OrchestrationServiceError("tool-unavailable")
        resolved[name] = executable
        if executable.parent not in directories:
            directories.append(executable.parent)
    trusted_path = os.pathsep.join(str(directory) for directory in directories)
    for name, executable in resolved.items():
        selected = shutil.which(name, path=trusted_path)
        if selected is None or Path(selected).resolve(strict=True) != executable:
            raise OrchestrationServiceError("tool-unavailable")
    return trusted_path


def _safe_directory(path: Path) -> bool:
    try:
        metadata = path.stat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and not metadata.st_mode & 0o022
    )


def _validated_executable(path: Path) -> Path:
    try:
        executable = path.resolve(strict=True)
        metadata = executable.stat()
    except OSError as exc:
        raise OrchestrationServiceError("tool-unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in {0, os.geteuid()}
        or metadata.st_mode & 0o022
        or not os.access(executable, os.X_OK)
    ):
        raise OrchestrationServiceError("tool-unavailable")
    return executable
