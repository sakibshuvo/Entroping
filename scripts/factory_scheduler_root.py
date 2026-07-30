from __future__ import annotations

from pathlib import Path

from scripts.bounded_process import BoundedProcessError, run_bounded_process

GIT_EXECUTABLE = Path("/usr/bin/git")
GIT_OUTPUT_BYTES = 4_096
GIT_TIMEOUT_SECONDS = 5.0


class SchedulerRootError(RuntimeError):
    pass


def resolve_scheduler_root(project_root: Path) -> Path:
    root = project_root.expanduser()
    if not root.is_absolute():
        root = root.absolute()
    if _has_symlink_component(root) or not root.is_dir():
        raise SchedulerRootError("project root must be a non-symlink directory")
    resolved = root.resolve(strict=True)
    git_marker = _nearest_git_marker(resolved)
    if git_marker is not None and git_marker.is_symlink():
        raise SchedulerRootError("git metadata must not be symlinked")
    try:
        result = run_bounded_process(
            [
                GIT_EXECUTABLE,
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-common-dir",
            ],
            cwd=resolved,
            timeout_seconds=GIT_TIMEOUT_SECONDS,
            max_output_bytes=GIT_OUTPUT_BYTES,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except BoundedProcessError as exc:
        raise SchedulerRootError("shared git root is unavailable") from exc
    if result.timed_out or result.output_limit_exceeded or result.returncode != 0:
        if git_marker is None:
            return resolved
        raise SchedulerRootError("shared git root is unavailable")
    output_lines = result.stdout.splitlines()
    if len(output_lines) != 2:
        raise SchedulerRootError("shared git root is unavailable")
    top_level = Path(output_lines[0])
    common = Path(output_lines[1])
    if (
        not top_level.is_absolute()
        or _has_symlink_component(top_level)
        or not top_level.is_dir()
        or not resolved.is_relative_to(top_level)
        or not common.is_absolute()
        or common.name != ".git"
        or _has_symlink_component(common)
        or not common.is_dir()
    ):
        raise SchedulerRootError("shared git metadata is unsafe")
    shared_root = common.parent.resolve(strict=True)
    if not shared_root.is_dir() or shared_root.is_symlink():
        raise SchedulerRootError("shared factory root is unsafe")
    return shared_root


def _nearest_git_marker(path: Path) -> Path | None:
    for directory in (path, *path.parents):
        marker = directory / ".git"
        if marker.exists() or marker.is_symlink():
            return marker
    return None


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False
