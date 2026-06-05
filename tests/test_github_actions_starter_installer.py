"""Tests for installing the downstream GitHub Actions starter workflow."""

from pathlib import Path

import pytest

import entroping.core.github_actions_starter as github_actions_starter
from entroping.core.github_actions_starter import (
    GITHUB_ACTIONS_STARTER_TEMPLATE,
    GitHubActionsStarterError,
    install_github_actions_starter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER_WORKFLOW = REPO_ROOT / "examples" / "github-actions" / "entroping-ci.yml"


def test_packaged_starter_template_matches_reviewed_example() -> None:
    assert STARTER_WORKFLOW.read_text(encoding="utf-8") == GITHUB_ACTIONS_STARTER_TEMPLATE


def test_install_github_actions_starter_creates_reviewed_workflow(tmp_path: Path) -> None:
    result = install_github_actions_starter(project_root=tmp_path)

    target = tmp_path / ".github" / "workflows" / "entroping.yml"
    assert result.path == target.resolve()
    assert target.read_text(encoding="utf-8") == STARTER_WORKFLOW.read_text(encoding="utf-8")


def test_install_github_actions_starter_refuses_existing_workflow(tmp_path: Path) -> None:
    target = tmp_path / ".github" / "workflows" / "entroping.yml"
    target.parent.mkdir(parents=True)
    target.write_text("name: existing\n", encoding="utf-8")

    with pytest.raises(GitHubActionsStarterError, match="already exists"):
        install_github_actions_starter(project_root=tmp_path)

    assert target.read_text(encoding="utf-8") == "name: existing\n"


def test_install_github_actions_starter_refuses_symlinked_workflow_parent(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".github").symlink_to(outside, target_is_directory=True)

    with pytest.raises(GitHubActionsStarterError, match="symlinked path component"):
        install_github_actions_starter(project_root=tmp_path)

    assert not (outside / "workflows" / "entroping.yml").exists()


def test_install_github_actions_starter_refuses_symlinked_workflow_target(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim.yml"
    victim.write_text("name: victim\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "entroping.yml"
    workflow.parent.mkdir(parents=True)
    workflow.symlink_to(victim)

    with pytest.raises(GitHubActionsStarterError, match="symlinked"):
        install_github_actions_starter(project_root=tmp_path)

    assert victim.read_text(encoding="utf-8") == "name: victim\n"


def test_install_github_actions_starter_wraps_parent_directory_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".github" / "workflows" / "entroping.yml"
    original_mkdir = Path.mkdir

    def fail_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if self == target.parent:
            raise OSError("mkdir failed")
        original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(GitHubActionsStarterError, match="mkdir failed"):
        install_github_actions_starter(project_root=tmp_path)


def test_starter_create_rejects_paths_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-starter.yml"

    with pytest.raises(GitHubActionsStarterError, match="must stay under"):
        github_actions_starter._safe_create_text(
            outside,
            "name: outside\n",
            artifact="GitHub Actions starter workflow",
            root=tmp_path,
        )

    assert not outside.exists()


def test_starter_create_wraps_link_file_exists_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".github" / "workflows" / "entroping.yml"

    def fail_link(source: Path, destination: Path) -> None:
        raise FileExistsError(destination)

    monkeypatch.setattr("entroping.core.github_actions_starter.os.link", fail_link)

    with pytest.raises(GitHubActionsStarterError, match="already exists"):
        install_github_actions_starter(project_root=tmp_path)

    assert not target.exists()
    assert not list(target.parent.glob(".entroping.yml.*.tmp"))


def test_starter_create_wraps_link_os_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".github" / "workflows" / "entroping.yml"

    def fail_link(source: Path, destination: Path) -> None:
        raise OSError("link failed")

    monkeypatch.setattr("entroping.core.github_actions_starter.os.link", fail_link)

    with pytest.raises(GitHubActionsStarterError, match="link failed"):
        install_github_actions_starter(project_root=tmp_path)

    assert not target.exists()
    assert not list(target.parent.glob(".entroping.yml.*.tmp"))


def test_starter_create_wraps_temporary_file_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_named_temporary_file(*args: object, **kwargs: object) -> object:
        raise OSError("temp failed")

    monkeypatch.setattr(
        "entroping.core.github_actions_starter.tempfile.NamedTemporaryFile",
        fail_named_temporary_file,
    )

    with pytest.raises(GitHubActionsStarterError, match="temp failed"):
        install_github_actions_starter(project_root=tmp_path)
