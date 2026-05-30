"""Prompt rendering for issue-scoped Entroping development sessions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

SessionMode = Literal["write", "review"]


@dataclass(frozen=True, slots=True)
class IssueSessionPrompt:
    """Inputs needed to render a deterministic child-session prompt."""

    issue_number: int
    issue_title: str
    issue_url: str
    worktree_path: Path
    branch_name: str
    repository: str = "sakibshuvo/Entroping"
    mode: SessionMode = "write"

    def __post_init__(self) -> None:
        if self.issue_number <= 0:
            msg = "issue_number must be positive"
            raise ValueError(msg)
        if self.issue_title.strip() == "":
            msg = "issue_title must not be empty"
            raise ValueError(msg)
        if self.issue_url.strip() == "":
            msg = "issue_url must not be empty"
            raise ValueError(msg)
        if self.branch_name.strip() == "":
            msg = "branch_name must not be empty"
            raise ValueError(msg)
        if self.repository.strip() == "":
            msg = "repository must not be empty"
            raise ValueError(msg)


def render_issue_session_prompt(session: IssueSessionPrompt) -> str:
    """Render the instructions for one issue-scoped Codex or OpenCode session."""

    mode_instructions = _mode_instructions(session)
    context_pack_mode = _context_pack_mode(session)
    return f"""# Entroping Issue Session: #{session.issue_number}

Repository: {session.repository}
Issue: {session.issue_title}
Issue URL: {session.issue_url}
Worktree: {session.worktree_path}
Branch: {session.branch_name}
Mode: {session.mode}
Context pack: `scripts/context_pack.sh --mode {context_pack_mode}`

## Mission

Implement only GitHub issue #{session.issue_number}: {session.issue_title}

{mode_instructions}

## Read First

Read these files before editing or reviewing:

1. `AGENTS.md`
2. `.context/plan.md`
3. `docs/meta/PROJECT_PROGRESS.md`
4. `docs/meta/FEATURE_DELIVERY_CHECKLIST.md`
5. `docs/meta/AUTONOMOUS_DEVELOPMENT.md`
6. `docs/product/MVP_PLAN.md`
7. `docs/technical/TDS.md`
8. `docs/technical/QANSTITUTION_REFERENCE.md`
9. `docs/meta/TEST_STRATEGY.md`
10. The GitHub issue body: {session.issue_url}

## Guardrails

- Stay inside `{session.worktree_path}`.
- Use TDD where behavior can be expressed before implementation.
- Preserve the locked Entroping v4.1 command surface.
- Preserve hexagonal dependencies: domain and bridge code must not import adapters.
- Do not call an LLM from `entroping run`.
- Do not execute API requests through Python HTTP clients.
- Keep Hurl as the deterministic execution boundary.
- Keep source `.hurl` files immutable during gate injection.
- Validate boundary inputs and report explicit errors.
- Do not stage local Obsidian UI state, `.entroping/`, reports, caches, secrets, or env files.
- Do not modify unrelated GitHub issues, branches, worktrees, or project-board items.

## Required Workflow

1. Inspect the current code and issue before editing.
2. Write or update the failing test first when practical.
3. Implement the smallest scoped change that satisfies the issue.
4. Run targeted tests as you work.
5. Update docs and `.context/` when behavior, workflow, or lessons changed.
6. Review the diff for architecture drift, secrets, generated noise, and unrelated edits.
7. Run `scripts/regression.sh --security` before asking to merge.

## Handoff

Return a concise handoff with:

- What changed.
- Tests and security checks run.
- Docs or context files updated.
- Known gaps or skipped checks.
- Commit hash if you committed.
"""


def _mode_instructions(session: IssueSessionPrompt) -> str:
    if session.mode == "review":
        return (
            "This is a read-only review session. Do not edit files in review mode. "
            "Return findings first, ordered by severity, with file and line evidence."
        )

    return (
        "This is a write session. You may edit files only for this issue, then commit a "
        "single verified Conventional Commit on the issue branch."
    )


def _context_pack_mode(session: IssueSessionPrompt) -> str:
    if session.mode == "review":
        return "review"
    return "implementation"


def main() -> None:
    """CLI entrypoint used by scripts/start_issue.sh."""

    parser = argparse.ArgumentParser(
        description="Render an Entroping issue-session prompt.",
    )
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--repo", default="sakibshuvo/Entroping")
    parser.add_argument("--mode", choices=("write", "review"), default="write")
    namespace = parser.parse_args()

    session = IssueSessionPrompt(
        issue_number=_get_required_int(namespace, "issue"),
        issue_title=_get_required_str(namespace, "title"),
        issue_url=_get_required_str(namespace, "url"),
        worktree_path=_get_required_path(namespace, "worktree"),
        branch_name=_get_required_str(namespace, "branch"),
        repository=_get_required_str(namespace, "repo"),
        mode=_get_mode(namespace),
    )
    print(render_issue_session_prompt(session))


def _get_required_str(namespace: argparse.Namespace, name: str) -> str:
    value: object = getattr(namespace, name)
    if not isinstance(value, str):
        msg = f"{name} must be a string"
        raise TypeError(msg)
    return value


def _get_required_int(namespace: argparse.Namespace, name: str) -> int:
    value: object = getattr(namespace, name)
    if not isinstance(value, int):
        msg = f"{name} must be an integer"
        raise TypeError(msg)
    return value


def _get_required_path(namespace: argparse.Namespace, name: str) -> Path:
    value: object = getattr(namespace, name)
    if not isinstance(value, Path):
        msg = f"{name} must be a path"
        raise TypeError(msg)
    return value


def _get_mode(namespace: argparse.Namespace) -> SessionMode:
    value = _get_required_str(namespace, "mode")
    if value not in ("write", "review"):
        msg = "mode must be write or review"
        raise ValueError(msg)
    return cast(SessionMode, value)


if __name__ == "__main__":  # pragma: no cover
    main()
