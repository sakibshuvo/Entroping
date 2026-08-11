"""Frozen prompt-library documentation contracts."""

import re

from agent_workflow_test_helpers import REPO_ROOT
from agent_workflow_test_helpers import concat_text as _concat_text


def test_worker_prompts_define_codex_pickup_handoff_and_shortcut_guards() -> None:
    pickup_prompt_paths = [
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-one-shot.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-week-monitoring.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "model-comparison-trial.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "codex-outage-daily-operations.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "multi-agent-marathon.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "deepseek-opencode-review.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-codex-review-request.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "model-output-acceptance-gate.md",
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md",
    ]
    pickup_terms = [
        ".entroping/ai-reviews/issue-<issue-number>-<short-slug>/",
        "metadata.json",
        "ready_for_codex",
        "result.md",
        "tests.txt",
        "proposal.diff",
        "scripts/factory_review_packet.py --artifact-dir",
        "scripts/factory_inbox.py next --json",
    ]

    for prompt_path in pickup_prompt_paths:
        prompt = prompt_path.read_text(encoding="utf-8")
        normalized_prompt = " ".join(prompt.split())
        missing = [term for term in pickup_terms if " ".join(term.split()) not in normalized_prompt]
        assert not missing, f"{prompt_path} missing {missing}"

    shortcut_prompt_paths = [
        *pickup_prompt_paths,
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "architecture-boundary-brief.md",
    ]
    shortcut_terms = [
        "`exec()`",
        "dynamic source-file execution",
        "import-time code generation",
        "mypy ignore_errors",
        "F821",
        "normal importable modules",
        "explicit dependencies",
    ]

    for prompt_path in shortcut_prompt_paths:
        prompt = prompt_path.read_text(encoding="utf-8")
        normalized_prompt = " ".join(prompt.split())
        missing = [
            term for term in shortcut_terms if " ".join(term.split()) not in normalized_prompt
        ]
        assert not missing, f"{prompt_path} missing {missing}"


def test_prompt_library_includes_architecture_boundary_brief_template() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "architecture-boundary-brief.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "Ownership Boundary",
        "Allowed Files",
        "Forbidden Files",
        "Architecture Invariants",
        "Tests To Run",
        "Architecture Tests",
        "Provider And Runtime Constraints",
        "Stop Conditions",
        "hexagonal architecture",
        "deterministic Hurl execution",
        "QAnstitution branding",
        "`entroping run` provider-free",
        "local files, tests, ADRs, and GitHub evidence",
        "not model summaries",
        "docs/meta/AGENT_ROLE_REGISTRY.yaml",
        "AGENT_CONTROL_PLANE.md",
        "LiteLLM",
        "Do not send secrets",
        "redaction",
        "proxy",
        "release publishing",
        "architecture boundary",
        "scripts/feature_gate.sh",
        "scripts/regression.sh --security",
    ]

    for term in required_terms:
        assert term in combined

    required_stop_terms = [
        "Tier A into Tier B or Tier C scope",
        "outside the Allowed Files list",
        "weakens hexagonal architecture",
        "deterministic Hurl execution",
        "QAnstitution branding",
        "`entroping run` provider-free",
        "model summaries",
        "local repo files",
        "security gate",
        "GitHub CI",
        "secrets",
        "raw traffic",
        "provider transcripts",
    ]
    stop_section = prompt.split("## Stop Conditions", maxsplit=1)[1]
    normalized_stop_section = " ".join(stop_section.split())
    stop_bullets = re.findall(r"(?m)^- .+$", stop_section)
    assert len(stop_bullets) >= 7
    for term in required_stop_terms:
        assert term in normalized_stop_section

    assert "| [Architecture boundary brief](architecture-boundary-brief.md) |" in readme


def test_prompt_library_includes_engineering_health_review_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "engineering-health-review.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "Review first",
        "Do not edit files",
        "architectural drift",
        "anti-patterns",
        "code smells",
        "documentation health",
        "code quality",
        "testability",
        "debugging ergonomics",
        "security",
        "maintainability",
        "regression risk",
        "hexagonal architecture",
        "deterministic Hurl execution",
        "QAnstitution branding",
        "`entroping run` provider-free",
        "provider/runtime boundaries",
        "repo evidence",
        "file/line references",
        "severity",
        "verified",
        "stale",
        "opinion",
        "unsafe",
        "GitHub Issues",
        "not source of truth",
    ]

    for term in required_terms:
        assert term in combined

    assert "| [Engineering health review](engineering-health-review.md) |" in readme


def test_prompt_library_includes_claude_code_review_prompt() -> None:
    prompt = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "claude-code-review.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(prompt.split())

    required_terms = [
        "Claude Code Review Prompt",
        "Review first",
        "Do not edit files",
        "source-pinned",
        "file/line evidence",
        "verified",
        "stale",
        "opinion",
        "unsafe",
        "P0/P1/P2/P3",
        "GitHub issue candidates",
        "QAnstitution branding",
        "deterministic Hurl execution",
        "`entroping run` LLM-free",
        "hexagonal architecture",
        "docs governance",
        "100 percent meaningful coverage",
        "external Claude output is advisory",
        "not merge authority",
        "not source of truth",
        "scripts/context_pack.sh --mode review --manifest",
    ]

    for term in required_terms:
        assert term in combined

    assert "| [Claude code review](claude-code-review.md) |" in readme


def test_prompt_library_documents_self_contained_worker_packets() -> None:
    issue_worker = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    opencode_handoff = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{issue_worker}\n{opencode_handoff}\n{readme}".split())

    required_terms = [
        "Self-Contained OpenCode/DeepSeek Work Packet",
        "Issue scope",
        "Allowed files",
        "Forbidden files",
        "Verification lane",
        "Exact tests/gates",
        "Stop conditions",
        "PR body requirements",
        "CI/merge/finish expectations",
        "Ask Codex only when",
        "Do not ask Codex for routine Tier A implementation details",
        "scripts/start_issue.sh",
        "scripts/finish_issue.sh",
        "scripts/pr_body_check.py",
        "Closes #<issue-number>",
        "Agent Autonomy Declaration",
        "OpenCode Provider Lane Evidence",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "security-runtime",
        "release-ci-architecture",
        "Tier B or Tier C",
        "secrets",
        "raw traffic",
        "provider transcripts",
    ]

    for term in required_terms:
        assert term in combined


def test_opencode_desktop_handoff_requires_artifact_first_fields() -> None:
    opencode_handoff = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(opencode_handoff.split())

    required_terms = [
        "For run-repeatability, hand off artifact-first outputs from",
        "`scripts/ai_jobs.py`, `scripts/opencode_worker.py`, or `scripts/deepseek_worker.py`",
        "Review those artifact fields before raw transcripts.",
        "Add and inspect artifact-first handoff fields before finalizing:",
        "`git diff --stat`",
        "artifact handoff summary",
        "test output",
    ]

    for term in required_terms:
        assert term in normalized


def test_opencode_codex_review_request_enforces_artifact_first_review_sequence() -> None:
    review_prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-codex-review-request.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(review_prompt.split())

    required_terms = [
        "Artifact-first review protocol (before raw transcript output):",
        "Review worker job metadata.",
        "Review result summary.",
        "Review `git diff --stat`.",
        "Review changed files list.",
        "Inspect raw transcripts only if any of the above is missing or ambiguous.",
        _concat_text(
            "Does the handoff include job metadata, result summary, diff stat, changed",
            " files, and test output?",
        ),
        _concat_text(
            "Confirm artifact-first handoff evidence is complete: job metadata, result",
            " summary, diff stat, changed files, and test output.",
        ),
    ]

    for term in required_terms:
        assert term in normalized


def test_opencode_desktop_handoff_documents_tooling_setup_checklist() -> None:
    doc = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "## OpenCode Desktop Tooling Setup Checklist",
        "Codex-native tools are not automatically available inside OpenCode",
        "OpenCode-exposed equivalents",
        "Codex Security",
        "Browser",
        "Computer Use",
        "thread tools",
        "Codex-specific MCP state",
        "OpenCode MCP servers are not Codex MCP state",
        "the worker must say so instead of implying Codex tool access",
        "Start with narrow read-only MCP access",
        "GitHub MCP",
        "filesystem MCP",
        "hooks",
        "branch/no-main",
        "dirty worktree",
        "secrets",
        "local state",
        "PR-body",
        "CI",
        "scripts/factory_metrics.py",
        "scripts/opencode_worker.py",
        "scripts/ai_jobs.py run-next",
        "MCP credentials",
        "provider keys",
        "`.opencode` state",
        "Do not commit local OpenCode config",
        "opencode/native-deepseek",
        "deepseek/deepseek-v4-pro",
        "OpenCode Go is the Kimi/Qwen/model-variety lane",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
        "## Independent Session Preflight",
        "scripts/opencode_readiness.py --mode implementation --require-clean --format json",
        "scripts/opencode_readiness.py --mode verification --format json",
        "does not read provider keys",
        "MCP credentials",
        "--stale-repo-path",
        "--expected-repo-prefix",
        "ENTROPING_STALE_REPO_PATHS",
        "ENTROPING_EXPECTED_REPO_PREFIX",
        "Failing status means stop",
        ".codex",
        "Passing preflight is not merge authority",
    ]

    for term in required_terms:
        assert term in normalized


def test_opencode_desktop_handoff_deepseek_v4_pro_issue_launch_checklist() -> None:
    doc_path = REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    doc = doc_path.read_text(encoding="utf-8")
    section_match = re.search(
        r"## DeepSeek V4 Pro Issue-Launch Checklist(.*?)## OpenCode Desktop PR Verification Prompt",
        doc,
        re.S,
    )
    assert section_match is not None

    section = " ".join(section_match.group(1).split())
    required_terms = [
        "`scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>`",
        _concat_text(
            "`uv run python scripts/opencode_readiness.py --mode implementation",
            " --require-clean --format json`",
        ),
        "`scripts/context_pack.sh --mode implementation --manifest`",
        "Follow the manifest `recommended_next_action` before loading broader context",
        "OpenCode Provider Lane Evidence in packet/PR body includes:",
        "- Lane",
        "- Provider host",
        "- Billing path",
        "- Model id",
        "- Role",
        "- Autonomy tier",
        "- Merge authority",
        "`scripts/regression.sh --security`",
        "Do not route normal work through retired generated-context tooling",
        "Before merge, require Codex/human validation for Tier B/Tier C",
        "Tier A may merge only under documented autonomous-lane rules",
        "green CI",
        "declared authority",
        "`scripts/finish_issue.sh <issue-number>` cleanup after merge",
    ]

    for term in required_terms:
        assert term in section


def test_prompt_library_includes_opencode_desktop_one_shot_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-one-shot.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())

    required_terms = [
        "OpenCode Desktop One-Shot Prompt",
        "type: prompt",
        "status: active",
        "Do everything through OpenCode Desktop tools",
        "Do not ask me to run terminal commands unless OpenCode cannot run them",
        "opencode/native-deepseek",
        "OpenCode Desktop",
        "paid DeepSeek API key inside OpenCode",
        "deepseek/deepseek-v4-pro",
        "Pick the highest-value Tier A issue",
        "Self-Contained OpenCode/DeepSeek Work Packet",
        "Issue scope",
        "Allowed files",
        "Forbidden files",
        "Verification lane",
        "Exact tests/gates",
        "Stop conditions",
        "PR body requirements",
        "CI/merge/finish expectations",
        "Ask Codex only when",
        "scripts/start_issue.sh <issue-number>",
        "/Users/sakibshuvo/projects/Entroping-issue-<issue-number>",
        (
            _concat_text(
                "uv run python scripts/opencode_readiness.py --mode implementation",
                " --require-clean --format json",
            )
        ),
        "scripts/context_pack.sh --mode implementation --manifest",
        (
            _concat_text(
                "uv run python scripts/pr_body_check.py --body-file <body.md>",
                " --require-opencode-evidence",
                " --issue <issue-number> --issue-metadata-file <issue.json>",
            )
        ),
        "gh api repos/sakibshuvo/Entroping/issues/<issue-number>",
        "gh pr checks <pr-number> --repo sakibshuvo/Entroping --watch",
        "scripts/finish_issue.sh <issue-number>",
        "Do not ask Codex for routine Tier A implementation details",
        "security-runtime",
        "release-ci-architecture",
        "entroping run",
        "Hurl runner",
        "protected-run safety",
        "redaction",
        "proxy/traffic capture",
        "provider/LiteLLM boundaries",
        "release publishing",
        "dependencies",
        "secrets",
        "raw traffic",
        "audit evidence",
        "security fixes",
        "architecture boundary changes",
        "Closes #<issue-number>",
        "Verification lane:",
        "Documentation Impact Declaration",
        "Agent Autonomy Declaration",
        "OpenCode Provider Lane Evidence",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [OpenCode Desktop one-shot](opencode-desktop-one-shot.md) |" in readme


def test_prompt_library_includes_prompt_selection_matrix() -> None:
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(readme.split())

    required_terms = [
        "## Prompt Selection Matrix",
        "| Prompt | Use When | Runner |",
        "`codex-session-handoff.md`",
        "`issue-worker.md`",
        "`opencode-desktop-one-shot.md`",
        "`opencode-desktop-handoff.md`",
        "`opencode-codex-review-request.md`",
        "`deepseek-opencode-review.md`",
        "`model-output-acceptance-gate.md`",
        "`model-comparison-trial.md`",
        "`codex-outage-daily-operations.md`",
        "`opencode-week-monitoring.md`",
        "`multi-agent-marathon.md`",
        "`spark-safe-worker.md`",
        "`architecture-boundary-brief.md`",
        "`engineering-health-review.md`",
        "`claude-code-review.md`",
        "`gemini-review.md`",
        "`security-review.md`",
        "`pr-review-merge-gate.md`",
        "`ci-failure-debug.md`",
        "`bug-bash.md`",
        "`backlog-triage.md`",
        "`after-sleep-status.md`",
        "`thread-steering.md`",
        "`roadmap-progress-refresh.md`",
        "`launch-readiness-review.md`",
        "`stable-core-audit.md`",
        "`context-reconciliation.md`",
        "## Quick Selection Rules",
        "I want OpenCode Desktop + DeepSeek to just work",
        "`opencode-desktop-one-shot.md`",
        "A cheap model produced a large patch or review; should I trust it?",
        "`model-output-acceptance-gate.md`",
        "Codex limit is low; keep moving safely",
        "`codex-outage-daily-operations.md`",
        "Before merge, is this PR safe?",
        "`pr-review-merge-gate.md`",
        "Find code quality, design, security, and documentation problems",
        "`engineering-health-review.md`",
    ]

    for term in required_terms:
        assert term in normalized


def test_prompt_library_includes_persistent_codex_marathon_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "codex-persistent-marathon.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())
    catalog = " ".join(readme.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "Persistent Codex Marathon Prompt",
        "You are the Entroping Codex marathon integrator",
        "Do not stop after the first issue",
        "Repeat Loop",
        "git pull --ff-only",
        "git status --short",
        "gh issue list",
        "scripts/start_issue.sh",
        "run required gates",
        "open a PR",
        "wait for CI",
        "merge only if green",
        "scripts/finish_issue.sh",
        "Then continue to the next issue",
        "Stop only when",
        "N issues are merged",
        "verified blocker",
        "CI fails and cannot be fixed safely",
        "user interrupts",
        "tool/runtime limit prevents continuation",
        "one write agent per issue-scoped worktree",
        "Tier B/Tier C",
        "Codex owns integration and merge readiness",
        "Current-state refresh",
        "Safe checkpoint output",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [Codex persistent marathon](codex-persistent-marathon.md) |" in readme
    assert "`codex-persistent-marathon.md`" in catalog
    assert "I want a Codex session to keep shipping issues" in catalog


def test_prompt_library_includes_model_comparison_trial_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "model-comparison-trial.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "## Trial Prompt",
        "## Evidence Rules",
        "## Scoring",
        "Codex",
        "OpenCode native DeepSeek",
        "direct DeepSeek API",
        "OpenCode Go Kimi",
        "OpenCode Go Qwen",
        "local/offline",
        "issue number",
        "provider lane",
        "provider host",
        "billing path",
        "model id",
        "role",
        "autonomy tier",
        "files changed",
        "files read",
        "tests/gates",
        "CI status",
        "cost/token/context evidence",
        "accepted findings",
        "rejected findings",
        "stale findings",
        "reviewer overrides",
        "Do not score models by confidence or style alone",
        "tests, diffs, CI, security/architecture review, and reviewer effort",
        "No model output is source of truth",
        "Codex Cloud or another host",
        "scripts/factory_metrics.py report",
        ".entroping/factory-metrics/",
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
        "fewer mismatched or missing issue/PR references",
        "Unknown cost or token values do not disqualify",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [Model-comparison trial](model-comparison-trial.md) |" in readme


def test_model_comparison_trial_documents_deepseek_cost_example() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "model-comparison-trial.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    required_terms = [
        "## Concrete OpenCode/DeepSeek Evidence Example",
        "issue: `774`",
        "provider lane: `opencode/native-deepseek`",
        "provider host: `OpenCode Desktop`",
        "billing path: `paid DeepSeek inside OpenCode`",
        "model id: `deepseek/deepseek-v4-pro`",
        "role: `code_review_agent`",
        "autonomy tier: `Tier A autonomous lane`",
        "context-pack mode:",
        "context-pack manifest:",
        "commands run:",
        "accepted findings:",
        "rejected findings:",
        "stale findings:",
        "reviewer overrides:",
        "final decision:",
        "files changed:",
        "files read:",
        "- docs/meta/prompt-library/opencode-desktop-handoff.md",
        "- tests/test_agent_workflow_docs.py",
        "context-pack mode: `implementation`",
        "context-pack manifest: `generated`",
        _concat_text(
            "context-pack estimated tokens: `<manifest-estimated-tokens>` from",
            " `scripts/context_pack.sh --mode implementation --manifest`",
        ),
        _concat_text(
            "context-pack bytes: `<manifest-context-bytes>` from",
            " `scripts/context_pack.sh --mode implementation --manifest`",
        ),
        "commands run:",
        "git pull --ff-only",
        "scripts/context_pack.sh --mode implementation --manifest",
        "scripts/factory_metrics.py report --format json",
        _concat_text(
            "scripts/factory_metrics.py report --format md --output",
            " .entroping/factory-metrics/factory-report.md",
        ),
        "scripts/factory_metrics.py readiness --issue 774 --format json",
        "cost/token/context evidence:",
        "provider_input_tokens: `unknown`",
        "provider_output_tokens: `unknown`",
        "cost_usd: `unknown`",
        "duration_seconds: `unknown`",
        "context_bytes: `<manifest-context-bytes>`",
        "`P3 merge-authority wording clarified`",
        "`No runtime or provider-boundary change requested`",
        "`none`",
        "`kept issue-required scripts/regression.sh --security gate`",
        "final decision: `accepted after local tests, Codex review, and CI`",
        "review effort:",
        "codex_review_rounds: `1`",
        "reviewer_corrections: `2`",
        "status: `accepted`",
        "Unknown token/cost values are allowed, but they must be marked `unknown`",
        "do not infer, estimate, or backfill provider token or cost values",
    ]

    for term in required_terms:
        assert term in normalized


def test_prompt_library_includes_model_output_acceptance_gate_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "model-output-acceptance-gate.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "cheap models may generate aggressively",
        "deterministic gates accept selectively",
        "No model output is source of truth",
        "provider lane",
        "provider host",
        "billing path",
        "model id",
        "autonomy tier",
        "merge authority",
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "scripts/context_pack.sh --mode implementation --manifest",
        "scripts/start_issue.sh",
        (
            _concat_text(
                "uv run python scripts/pr_body_check.py --body-file <body.md>",
                " --require-opencode-evidence",
                " --issue <issue>",
            )
        ),
        "scripts/regression.sh --security",
        "GitHub CI is green",
        "scripts/finish_issue.sh",
        "accepted",
        "needs Codex or human review",
        "convert to GitHub issue",
        "reject as stale, opinion, or unsafe",
        "architecture boundary",
        "entroping run",
        "Hurl runner",
        "redaction",
        "proxy",
        "provider runtime",
        "dependencies",
        "release publishing",
        "secrets",
        "raw traffic",
        "audit evidence",
        "QAnstitution branding",
        "deterministic Hurl execution",
        "factory metrics",
        "do not infer missing token or cost values",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [Model-output acceptance gate](model-output-acceptance-gate.md) |" in readme


def test_prompt_library_includes_after_sleep_status_prompt() -> None:
    prompt = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "after-sleep-status.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split()).lower()

    required_terms = [
        "type: prompt",
        "status: active",
        "use this when returning after an unattended or multi-session run.",
        "current repo commit",
        "provider lane",
        "provider host",
        "billing path",
        "model id",
        "autonomy tier",
        "recently merged prs and closed issues",
        "failed or stuck actions runs",
        "docs/progress drift",
        "unsafe or duplicate agent work",
        "issues ready next only when no stop condition applies",
        "open prs",
        "ci status",
        "issue worktrees",
        "dirty files",
        "commands run",
        "safe next action",
        "ci pending",
        "ci failed",
        "merged but finish cleanup pending",
        "blocked by tier b/tier c scope",
        "skipped gates",
        "skipped gates and why",
        "skipped gates and rationale",
        "status is clear only when every check item has a concrete answer",
        "any pending or failed ci has a stated reason",
        "safe next action is a concrete command or an explicit stop",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [After-sleep status](after-sleep-status.md) |" in readme


def test_prompt_library_includes_codex_outage_daily_operations_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "codex-outage-daily-operations.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "## Daily Loop",
        "git pull --ff-only",
        "git status --short",
        "gh pr list",
        "gh issue list",
        "status:ready",
        "scripts/start_issue.sh",
        "provider lanes",
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "focused tests/gates",
        "scripts/feature_gate.sh already includes scripts/architecture_integrity.sh",
        "scripts/architecture_integrity.sh directly as a fast preflight",
        "reviewing possible architecture drift",
        "gh pr checks",
        "scripts/finish_issue.sh",
        "after-sleep status",
        "Tier B/Tier C PRs must wait for Codex or human review before merge",
        "opencode-desktop-handoff.md",
        "issue-worker.md",
        "after-sleep-status.md",
        "pr-review-merge-gate.md",
        "failing security gate",
        "forbidden file touched",
        "ambiguous scope",
        "secret exposure risk",
        "CI red",
        "merge conflict",
        "stale main",
        "missing close keyword",
        "Emergency Stop Conditions",
        "Tier A work expanding into Tier B/Tier C scope",
        "Hurl runner behavior",
        "`entroping run`",
        "provider runtime boundary",
    ]

    for term in required_terms:
        assert term in normalized

    work_steps = prompt.split("Then:", maxsplit=1)[1].split("## Reference Prompts", maxsplit=1)[0]
    normalized_work_steps = " ".join(work_steps.split())
    architecture_gate_terms = [
        "scripts/feature_gate.sh already includes scripts/architecture_integrity.sh",
        "scripts/architecture_integrity.sh directly as a fast preflight",
        "reviewing possible architecture drift",
    ]
    for term in architecture_gate_terms:
        assert term in normalized_work_steps

    stop_section = prompt.split("## Emergency Stop Conditions", maxsplit=1)[1].split(
        "## After-Sleep Status", maxsplit=1
    )[0]
    normalized_stop_section = " ".join(stop_section.split())
    required_stop_terms = [
        "weakens hexagonal architecture",
        "QAnstitution branding",
        "model summaries as source of truth",
    ]
    for term in required_stop_terms:
        assert term in normalized_stop_section

    assert "| [Codex-outage daily operations](codex-outage-daily-operations.md) |" in readme


def test_prompt_library_includes_opencode_week_monitoring_prompt() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-week-monitoring.md"
    ).read_text(encoding="utf-8")
    readme = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(prompt.split())

    required_terms = [
        "type: prompt",
        "status: active",
        "read-only by default",
        "Do not mutate issues, pull requests, branches, or main",
        "Do not run git pull",
        "gh pr list",
        "isDraft,mergeStateStatus,statusCheckRollup,closingIssuesReferences",
        "statusCheckRollup",
        "gh run list",
        "workflowName,headBranch",
        "gh issue list",
        "status:ready",
        "merged PRs needing `scripts/finish_issue.sh`",
        "scripts/factory_metrics.py report --include-finished-issues",
        "factory_metrics.py unavailable",
        "continue with the remaining read-only checks",
        "after-sleep status",
        "blockers",
        "safe next actions",
        "failing CI",
        "missing close keywords",
        "block merge or cleanup",
        (
            _concat_text(
                "Do not claim launch, stable-core, package-index, enterprise, security, or",
                " adoption readiness",
            )
        ),
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
    ]

    for term in required_terms:
        assert term in normalized

    assert "| [OpenCode-only week monitoring](opencode-week-monitoring.md) |" in readme


def test_deepseek_opencode_prompt_uses_supported_ai_job_commands() -> None:
    prompt = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "deepseek-opencode-review.md"
    ).read_text(encoding="utf-8")
    ai_jobs_source = (REPO_ROOT / "scripts" / "ai_jobs.py").read_text(encoding="utf-8")
    supported_commands = {"submit", "status", "run-next", "collect"}
    actual_commands = set(
        re.findall(r"subparsers\.add_parser\(\s*\"([a-z][a-z-]*)\"", ai_jobs_source)
    )

    assert supported_commands <= actual_commands

    documented_commands = set(re.findall(r"python scripts/ai_jobs\.py\s+([a-z][a-z-]*)", prompt))

    assert "status" in documented_commands
    assert "list" not in documented_commands
    assert documented_commands <= supported_commands


def test_prompt_library_contains_autonomous_tier_a_worker_prompt() -> None:
    prompt = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    catalog = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{prompt}\n{catalog}".split())

    required_terms = [
        "Autonomous Tier A OpenCode/DeepSeek Worker Prompt",
        "Do not use this mode for Tier B or Tier C work.",
        "`scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>`",
        "Agent Autonomy Declaration",
        "`scripts/regression.sh --security`",
        "`Closes #<issue-number>`",
        "`scripts/finish_issue.sh <issue-number>`",
        "scripts/context_pack.sh --mode implementation --manifest",
        "needed files/snippets",
        "CI is green",
    ]

    for term in required_terms:
        assert term in combined


def test_prompt_library_contains_opencode_desktop_handoff_prompts() -> None:
    prompt_path = REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    catalog = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{prompt}\n{catalog}".split())

    required_terms = [
        "OpenCode Desktop Handoff Prompt",
        "OpenCode Desktop Implementation Worker Prompt",
        "OpenCode Desktop PR Verification Prompt",
        "opencode/native-deepseek",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "provider host, billing path, and concrete model id",
        "paid DeepSeek inside OpenCode",
        "OpenCode Go is the Kimi/Qwen/model-variety lane",
        "Autonomy tier",
        "Merge authority",
        "Allowed files",
        "Forbidden files",
        "scripts/start_issue.sh",
        "Retired generated context tooling is not part of active Entroping agent workflow",
        "Do not route normal OpenCode work through external context tools",
        "scripts/factory_metrics.py",
        "Agent Autonomy Declaration",
        "Tier B/Tier C requires Codex or human review before merge",
        "Closes #<issue-number>",
    ]

    for term in required_terms:
        assert term in combined
