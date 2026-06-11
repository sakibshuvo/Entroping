"""Select changed Hurl files from Git diff output."""

import shutil
import subprocess  # nosec B404
from pathlib import Path


class GitChangedHurlError(ValueError):
    """Raised when changed Hurl selection cannot be computed safely."""


GIT_DIFF_TIMEOUT_SECONDS = 30


def select_changed_hurl_tests(*, project_root: Path, base_ref: str) -> tuple[Path, ...]:
    """Return existing changed Hurl files relative to a Git base ref."""

    root = project_root.expanduser().resolve()
    safe_ref = _validate_base_ref(base_ref)
    git_binary = shutil.which("git")
    if git_binary is None:
        msg = "Could not inspect git diff: git executable not found"
        raise GitChangedHurlError(msg)

    try:
        diff = subprocess.run(  # nosec B603
            [git_binary, "-C", str(root), "diff", "--name-status", "-z", safe_ref, "--"],
            capture_output=True,
            check=False,
            timeout=GIT_DIFF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (
            f"Could not inspect git diff from {base_ref!r}: timed out after "
            f"{GIT_DIFF_TIMEOUT_SECONDS} seconds"
        )
        raise GitChangedHurlError(msg) from exc
    if diff.returncode != 0:
        stderr = diff.stderr.decode("utf-8", errors="replace").strip()
        detail = f": {stderr}" if stderr else ""
        msg = f"Could not inspect git diff from {base_ref!r}{detail}"
        raise GitChangedHurlError(msg)

    selected: set[Path] = set()
    for relative_path in _parse_changed_paths(diff.stdout):
        path = _resolve_project_path(root, relative_path)
        if path.suffix != ".hurl":
            continue
        if not path.exists() or not path.is_file() or path.is_symlink():
            continue
        selected.add(path)

    return tuple(sorted(selected, key=lambda path: str(path)))


def _parse_changed_paths(output: bytes) -> tuple[str, ...]:
    tokens = [token.decode("utf-8", errors="replace") for token in output.split(b"\0") if token]
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                msg = "Malformed git diff rename/copy record."
                raise GitChangedHurlError(msg)
            index += 1
            paths.append(tokens[index])
            index += 1
            continue
        if index >= len(tokens):
            msg = "Malformed git diff name-status record."
            raise GitChangedHurlError(msg)
        path = tokens[index]
        index += 1
        if status.startswith("D"):
            continue
        paths.append(path)
    return tuple(paths)


def _validate_base_ref(base_ref: str) -> str:
    if (
        not base_ref
        or base_ref != base_ref.strip()
        or base_ref.startswith("-")
        or ":" in base_ref
        or "\\" in base_ref
        or ".." in base_ref
        or "@{" in base_ref
        or any(character.isspace() for character in base_ref)
        or any(ord(character) < 32 or ord(character) == 127 for character in base_ref)
    ):
        msg = f"unsafe Git base ref: {base_ref!r}"
        raise GitChangedHurlError(msg)
    return base_ref


def _resolve_project_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        msg = f"Git diff path is outside the project root: {relative_path}"
        raise GitChangedHurlError(msg) from exc
    return path
