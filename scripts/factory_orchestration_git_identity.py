"""Registered-worktree and active-operation Git identity helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.factory_orchestration_git_process import git_text


def worktree_records(repo_root: Path) -> tuple[tuple[Path, str, str], ...]:
    raw = git_text(repo_root, "worktree", "list", "--porcelain", "-z")
    records: list[tuple[Path, str, str]] = []
    fields: dict[str, str] = {}
    for item in raw.split("\0"):
        if not item:
            if fields:
                if set(fields) >= {"worktree", "HEAD", "branch"}:
                    records.append(
                        (
                            Path(fields["worktree"]).resolve(),
                            fields["HEAD"],
                            fields["branch"].removeprefix("refs/heads/"),
                        )
                    )
                fields = {}
            continue
        key, _, value = item.partition(" ")
        fields[key] = value
    return tuple(records)


def operation_active(worktree: Path) -> bool:
    names = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")
    for name in names:
        candidate = Path(git_text(worktree, "rev-parse", "--git-path", name))
        if not candidate.is_absolute():
            candidate = worktree / candidate
        if candidate.exists():
            return True
    return False
