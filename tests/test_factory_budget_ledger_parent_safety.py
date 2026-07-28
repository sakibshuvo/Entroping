from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.factory_budget_ledger import (  # noqa: E402
    FactoryBudgetLedger,
    FactoryBudgetLedgerError,
)


def test_open_accepts_existing_owner_controlled_shared_state(tmp_path: Path) -> None:
    shared_state = tmp_path / ".entroping"
    shared_state.mkdir(mode=0o755)
    os.chmod(shared_state, 0o755)  # codeql[py/overly-permissive-file]

    ledger = FactoryBudgetLedger.open_project(tmp_path)

    assert stat.S_IMODE(shared_state.stat().st_mode) == 0o755
    assert stat.S_IMODE(ledger.db_path.parent.stat().st_mode) == 0o700


def test_open_rejects_symlinked_state_directory_without_writing_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".entroping").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger state path is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)

    assert tuple(outside.iterdir()) == ()


def test_open_rejects_group_writable_repository_root(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o770)  # codeql[py/overly-permissive-file]

    with pytest.raises(FactoryBudgetLedgerError, match="root must be owner-controlled"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_rejects_repository_root_owned_by_another_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1)

    with pytest.raises(
        FactoryBudgetLedgerError,
        match="cross-account replacement|root must be owner-controlled",
    ):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_rejects_group_writable_state_directory(tmp_path: Path) -> None:
    ledger = FactoryBudgetLedger.open_project(tmp_path)
    shared_state = ledger.db_path.parents[1]
    os.chmod(shared_state, 0o770)  # codeql[py/overly-permissive-file]

    with pytest.raises(FactoryBudgetLedgerError, match="state directory is unsafe"):
        FactoryBudgetLedger.open_project(tmp_path)


def test_open_rejects_nonsticky_writable_repository_ancestor(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o777)  # codeql[py/overly-permissive-file]
    repo = shared / "repo"
    repo.mkdir(mode=0o755)

    with pytest.raises(FactoryBudgetLedgerError, match="cross-account replacement"):
        FactoryBudgetLedger.open_project(repo)


def test_open_accepts_sticky_writable_repository_ancestor(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o1777)  # codeql[py/overly-permissive-file]
    repo = shared / "repo"
    repo.mkdir(mode=0o755)

    ledger = FactoryBudgetLedger.open_project(repo)

    assert ledger.project_root == repo


def test_open_rejects_symlinked_repository_ancestor(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    repo = real_parent / "repo"
    repo.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(FactoryBudgetLedgerError, match="ledger state path is unsafe"):
        FactoryBudgetLedger.open_project(alias / "repo")


def test_open_rejects_repository_root_parent_traversal(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    ambiguous_root = sibling / ".."

    with pytest.raises(FactoryBudgetLedgerError, match="must not contain parent traversal"):
        FactoryBudgetLedger.open_project(ambiguous_root)
