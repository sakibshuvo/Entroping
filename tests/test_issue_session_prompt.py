"""Unit tests for issue-scoped multi-session prompt generation."""

from pathlib import Path

from entroping.core.session_prompt import IssueSessionPrompt, render_issue_session_prompt


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
