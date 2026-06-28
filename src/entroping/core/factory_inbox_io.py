from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class InboxError(ValueError):
    pass


def repo_root() -> Path:
    try:
        completed = subprocess.run(  # nosec B603
            [git_executable(), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        msg = "run this from inside the Entroping git repository"
        raise InboxError(msg) from exc
    return Path(completed.stdout.strip()).resolve()


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        msg = "git executable not found on PATH"
        raise InboxError(msg)
    return git


def resolve_root(repo_root_path: Path, raw_root: Path, purpose: str) -> Path:
    root = raw_root.expanduser()
    relative_root = not root.is_absolute()
    if relative_root:
        root = repo_root_path / root
    if has_symlink_component(root):
        msg = f"{purpose} must not use symlink components"
        raise InboxError(msg)
    resolved = root.resolve()
    if relative_root and not path_is_relative_to(resolved, repo_root_path):
        msg = f"{purpose} must stay inside repository"
        raise InboxError(msg)
    if not relative_root and not (
        path_is_relative_to(resolved, repo_root_path)
        or path_is_relative_to(resolved, system_temp_root())
    ):
        msg = f"{purpose} must stay inside repository or system temp directory"
        raise InboxError(msg)
    return resolved


def resolve_artifact_dir(artifact_root: Path, raw_artifact_dir: Path) -> Path:
    artifact_dir = raw_artifact_dir.expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = artifact_root / artifact_dir
    if has_symlink_component(artifact_dir):
        msg = "artifact directory must not use symlink components"
        raise InboxError(msg)
    resolved = artifact_dir.resolve()
    if not path_is_relative_to(resolved, artifact_root):
        msg = "artifact directory must stay under artifact root"
        raise InboxError(msg)
    if not resolved.is_dir():
        msg = f"artifact directory does not exist: {resolved}"
        raise InboxError(msg)
    return resolved


def review_packet(repo_root_path: Path, artifact_root: Path, artifact_dir: Path) -> JsonObject:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "factory_review_packet.py"
    try:
        completed = subprocess.run(  # nosec B603
            [
                sys.executable,
                str(script_path),
                "--artifact-dir",
                str(artifact_dir),
                "--artifact-root",
                str(artifact_root),
                "--json",
            ],
            cwd=repo_root_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        msg = "could not run factory_review_packet.py"
        raise InboxError(msg) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        msg = f"factory_review_packet.py failed: {detail}"
        raise InboxError(msg)
    return json_object_from_text(completed.stdout, source="factory review packet")


def read_json_object(path: Path) -> JsonObject:
    try:
        return json_object_from_text(path.read_text(encoding="utf-8"), source=str(path))
    except OSError as exc:
        msg = f"could not read JSON object: {path}"
        raise InboxError(msg) from exc


def json_object_from_text(content: str, *, source: str) -> JsonObject:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        msg = f"could not parse JSON object: {source}"
        raise InboxError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"JSON payload is not an object: {source}"
        raise InboxError(msg)
    for key in payload:
        if not isinstance(key, str):
            msg = f"JSON object contains a non-string key: {source}"
            raise InboxError(msg)
    return payload


def write_json_object(path: Path, payload: JsonObject) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except OSError as exc:
        msg = f"could not write metadata: {path}"
        raise InboxError(msg) from exc


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def system_temp_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def has_symlink_component(path: Path) -> bool:
    return any(candidate.is_symlink() for candidate in (path, *path.parents))
