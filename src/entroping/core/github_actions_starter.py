"""Install the reviewed downstream GitHub Actions starter workflow."""

import os
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from entroping.core.path_safety import first_symlink_path_component

GITHUB_ACTIONS_STARTER_TEMPLATE = files("entroping").joinpath(
    "templates",
    "github-actions",
    "entroping-ci.yml",
).read_text(encoding="utf-8")
GITHUB_ACTIONS_STARTER_RELATIVE_PATH = Path(".github") / "workflows" / "entroping.yml"


class GitHubActionsStarterError(ValueError):
    """Raised when the GitHub Actions starter workflow cannot be installed."""


@dataclass(frozen=True, slots=True)
class GitHubActionsStarterInstallResult:
    """Result of installing the starter workflow."""

    path: Path


def install_github_actions_starter(*, project_root: Path) -> GitHubActionsStarterInstallResult:
    """Install the reviewed starter workflow into a downstream project."""

    root = project_root.expanduser().resolve()
    target = root / GITHUB_ACTIONS_STARTER_RELATIVE_PATH
    written = _safe_create_text(
        target,
        GITHUB_ACTIONS_STARTER_TEMPLATE,
        artifact="GitHub Actions starter workflow",
        root=root,
    )
    return GitHubActionsStarterInstallResult(path=written)


def _safe_create_text(path: Path, content: str, *, artifact: str, root: Path) -> Path:
    _ensure_under_root(path, root=root, artifact=artifact)
    _reject_symlink_path_components(path, root=root, artifact=artifact)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"Could not create parent directory for {artifact} {path}: {exc}"
        raise GitHubActionsStarterError(msg) from exc

    _ensure_under_root(path, root=root, artifact=artifact)
    _reject_symlink_path_components(path, root=root, artifact=artifact)
    _reject_existing_target(path, artifact=artifact)

    temporary_path = _write_temporary_file(path, content.encode("utf-8"), artifact=artifact)
    try:
        _reject_symlink_path_components(path, root=root, artifact=artifact)
        _reject_existing_target(path, artifact=artifact)
        os.link(temporary_path, path)
    except FileExistsError as exc:
        msg = f"{artifact} already exists; left unchanged: {path}"
        raise GitHubActionsStarterError(msg) from exc
    except OSError as exc:
        msg = f"Could not create {artifact} {path}: {exc}"
        raise GitHubActionsStarterError(msg) from exc
    finally:
        temporary_path.unlink(missing_ok=True)

    return path.resolve(strict=True)


def _ensure_under_root(path: Path, *, root: Path, artifact: str) -> None:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        msg = f"{artifact} path must stay under {root}: {path}"
        raise GitHubActionsStarterError(msg) from exc


def _reject_symlink_path_components(path: Path, *, root: Path, artifact: str) -> None:
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
    raise GitHubActionsStarterError(msg)


def _reject_existing_target(path: Path, *, artifact: str) -> None:
    if path.exists() or path.is_symlink():
        msg = f"{artifact} already exists; left unchanged: {path}"
        raise GitHubActionsStarterError(msg)


def _write_temporary_file(path: Path, content: bytes, *, artifact: str) -> Path:
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
        msg = f"Could not write temporary {artifact} next to {path}: {exc}"
        raise GitHubActionsStarterError(msg) from exc
