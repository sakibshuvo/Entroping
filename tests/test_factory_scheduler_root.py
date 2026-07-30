from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_scheduler import FactoryScheduler  # noqa: E402
from scripts.factory_scheduler_models import (  # noqa: E402
    AssignmentRequest,
    LeaseOwner,
)
from scripts.factory_scheduler_root import (  # noqa: E402
    SchedulerRootError,
    resolve_scheduler_root,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def test_sibling_worktree_resolves_to_shared_factory_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "factory@example.invalid")
    _git(repository, "config", "user.name", "Factory Test")
    (repository / "README.md").write_text("factory\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "test: initialize fixture")
    worktree = tmp_path / "issue-worktree"
    _git(repository, "worktree", "add", "-b", "test/issue-worktree", str(worktree))

    assert resolve_scheduler_root(repository) == repository.resolve()
    assert resolve_scheduler_root(worktree) == repository.resolve()

    request = AssignmentRequest(
        request_id="shared-request",
        job_id="shared-job",
        issue_number=1569,
        worktree_id=f"wt_{'1' * 64}",
        worker_class="free-local",
        access_mode="read-only",
    )
    receipt = FactoryScheduler(repository).tick(
        request=request,
        owner=LeaseOwner(
            owner_id="shared-owner",
            pid=1,
            process_start_token=f"proc_{1:064x}",
        ),
        as_of=datetime(2026, 7, 29, 22, 30, tzinfo=UTC),
        lease_seconds=30,
        plan_only=False,
        owner_health=lambda _owner: False,
    )

    assert receipt.decision == "assigned"
    assert FactoryScheduler(worktree).snapshot().active_assignment_count == 1


def test_git_subdirectory_resolves_to_repository_scheduler_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested = repository / "packages" / "worker"
    nested.mkdir(parents=True)
    _git(repository, "init")

    assert resolve_scheduler_root(nested) == repository.resolve()


def test_non_git_fixture_remains_an_explicit_isolated_root(tmp_path: Path) -> None:
    assert resolve_scheduler_root(tmp_path) == tmp_path.resolve()


def test_nested_non_git_fixture_remains_its_own_isolated_root(tmp_path: Path) -> None:
    nested = tmp_path / "packages" / "worker"
    nested.mkdir(parents=True)

    assert resolve_scheduler_root(nested) == nested.resolve()


def test_symlinked_project_root_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(SchedulerRootError):
        _ = resolve_scheduler_root(alias)
