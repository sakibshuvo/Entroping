"""Unit tests for issue-scoped multi-session prompt generation."""

import argparse
from pathlib import Path

import pytest

from entroping.core.session_prompt import (
    IssueSessionPrompt,
    _get_mode,
    _get_required_int,
    _get_required_path,
    _get_required_str,
    main,
    render_issue_session_prompt,
)


def test_render_issue_session_prompt_includes_issue_context_and_required_repo_sources() -> None:
    prompt = render_issue_session_prompt(
        IssueSessionPrompt(
            issue_number=3,
            issue_title="Phase 2B: QAnstitution gate matching and temporary Hurl injection",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/3",
            worktree_path=Path("/Users/sakibshuvo/projects/Entroping-issue-3"),
            branch_name="feat/gate-injection",
        )
    )

    assert "# Entroping Issue Session: #3" in prompt
    assert "Phase 2B: QAnstitution gate matching and temporary Hurl injection" in prompt
    assert "https://github.com/sakibshuvo/Entroping/issues/3" in prompt
    assert "/Users/sakibshuvo/projects/Entroping-issue-3" in prompt
    assert "feat/gate-injection" in prompt

    required_sources = [
        "AGENTS.md",
        ".context/plan.md",
        "docs/meta/PROJECT_PROGRESS.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "docs/meta/AUTONOMOUS_DEVELOPMENT.md",
        "docs/product/MVP_PLAN.md",
        "docs/technical/TDS.md",
        "docs/technical/QANSTITUTION_REFERENCE.md",
        "docs/meta/TEST_STRATEGY.md",
    ]
    for source in required_sources:
        assert source in prompt


def test_render_issue_session_prompt_states_multi_agent_guardrails_and_quality_gates() -> None:
    prompt = render_issue_session_prompt(
        IssueSessionPrompt(
            issue_number=4,
            issue_title="Phase 2C: deterministic Hurl subprocess runner",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/4",
            worktree_path=Path("/tmp/Entroping-issue-4"),
            branch_name="feat/hurl-runner",
            mode="write",
        )
    )

    required_guardrails = [
        "Implement only GitHub issue #4",
        "Use TDD where behavior can be expressed before implementation",
        "Do not call an LLM from `entroping run`",
        "Do not execute API requests through Python HTTP clients",
        "Keep source `.hurl` files immutable during gate injection",
        "Update docs and `.context/` when behavior, workflow, or lessons changed",
        "Run `scripts/regression.sh --security` before asking to merge",
        "Do not stage local Obsidian UI state",
    ]
    for guardrail in required_guardrails:
        assert guardrail in prompt


def test_render_issue_session_prompt_write_mode_points_to_implementation_context_pack() -> None:
    prompt = render_issue_session_prompt(
        IssueSessionPrompt(
            issue_number=107,
            issue_title="Wire context packs into issue-session prompts",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/107",
            worktree_path=Path("/tmp/Entroping-issue-107"),
            branch_name="feat/context-pack-session-prompts",
            mode="write",
        )
    )

    assert "scripts/context_pack.sh --mode implementation" in prompt
    assert "scripts/context_pack.sh --mode review" not in prompt


def test_render_issue_session_prompt_review_mode_is_read_only() -> None:
    prompt = render_issue_session_prompt(
        IssueSessionPrompt(
            issue_number=5,
            issue_title="Phase 3A: JSON and JUnit reports",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/5",
            worktree_path=Path("/tmp/Entroping-issue-5"),
            branch_name="feat/reports",
            mode="review",
        )
    )

    assert "Mode: review" in prompt
    assert "Do not edit files in review mode" in prompt
    assert "Return findings first, ordered by severity" in prompt
    assert "scripts/context_pack.sh --mode review" in prompt
    assert "scripts/context_pack.sh --mode implementation" not in prompt


def test_issue_session_prompt_rejects_invalid_issue_number() -> None:
    with pytest.raises(ValueError, match="issue_number must be positive"):
        IssueSessionPrompt(
            issue_number=0,
            issue_title="Title",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/1",
            worktree_path=Path("/tmp/Entroping-issue-1"),
            branch_name="feat/example",
        )


def test_issue_session_prompt_rejects_blank_title_url_branch_and_repository() -> None:
    with pytest.raises(ValueError, match="issue_title must not be empty"):
        IssueSessionPrompt(
            issue_number=1,
            issue_title="  ",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/1",
            worktree_path=Path("/tmp/Entroping-issue-1"),
            branch_name="feat/example",
        )
    with pytest.raises(ValueError, match="issue_url must not be empty"):
        IssueSessionPrompt(
            issue_number=1,
            issue_title="Title",
            issue_url="  ",
            worktree_path=Path("/tmp/Entroping-issue-1"),
            branch_name="feat/example",
        )
    with pytest.raises(ValueError, match="branch_name must not be empty"):
        IssueSessionPrompt(
            issue_number=1,
            issue_title="Title",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/1",
            worktree_path=Path("/tmp/Entroping-issue-1"),
            branch_name="  ",
        )
    with pytest.raises(ValueError, match="repository must not be empty"):
        IssueSessionPrompt(
            issue_number=1,
            issue_title="Title",
            issue_url="https://github.com/sakibshuvo/Entroping/issues/1",
            worktree_path=Path("/tmp/Entroping-issue-1"),
            branch_name="feat/example",
            repository="  ",
        )


def test_session_prompt_cli_renders_prompt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "session_prompt",
            "--issue",
            "107",
            "--title",
            "Wire context packs into issue-session prompts",
            "--url",
            "https://github.com/sakibshuvo/Entroping/issues/107",
            "--worktree",
            "/tmp/Entroping-issue-107",
            "--branch",
            "feat/context-pack-session-prompts",
            "--mode",
            "review",
        ],
    )

    main()

    output = capsys.readouterr().out
    assert "Entroping Issue Session: #107" in output
    assert "Mode: review" in output
    assert "scripts/context_pack.sh --mode review" in output


def test_session_prompt_getters_reject_wrong_types() -> None:
    namespace = argparse.Namespace(name=123, issue="1", path="tmp", mode="other")

    with pytest.raises(TypeError, match="name must be a string"):
        _get_required_str(namespace, "name")
    with pytest.raises(TypeError, match="issue must be an integer"):
        _get_required_int(namespace, "issue")
    with pytest.raises(TypeError, match="path must be a path"):
        _get_required_path(namespace, "path")
    with pytest.raises(ValueError, match="mode must be write or review"):
        _get_mode(namespace)
