"""Guardrails for agent workflow and growth documentation."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_control_plane_documents_cross_agent_guardrails() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )

    assert "Codex owns factory design" in doc
    assert "Claude Code" in doc
    assert "OpenCode" in doc
    assert "Gemini" in doc
    assert "NotebookLM" in doc
    assert "local Qwen" in doc
    assert "scripts/context_pack.sh --mode implementation" in doc
    assert "No helper agent is a source of truth" in doc


def test_prompt_library_includes_architecture_boundary_brief_template() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "architecture-boundary-brief.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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


def test_opencode_desktop_handoff_documents_tooling_setup_checklist() -> None:
    doc = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-handoff.md"
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
    ]

    for term in required_terms:
        assert term in normalized


def test_prompt_library_includes_model_comparison_trial_prompt() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "model-comparison-trial.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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


def test_prompt_library_includes_codex_outage_daily_operations_prompt() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "codex-outage-daily-operations.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
    ]

    for term in required_terms:
        assert term in normalized

    assert (
        "| [Codex-outage daily operations](codex-outage-daily-operations.md) |"
        in readme
    )


def test_prompt_library_includes_opencode_week_monitoring_prompt() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-week-monitoring.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
            "Do not claim launch, stable-core, package-index, enterprise, "
            "security, or adoption readiness"
        ),
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
    ]

    for term in required_terms:
        assert term in normalized

    assert (
        "| [OpenCode-only week monitoring](opencode-week-monitoring.md) |"
        in readme
    )


def test_agent_control_plane_documents_codex_outage_worker_queue() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    required_terms = [
        "## Codex-Outage OpenCode/DeepSeek Work Queue",
        "#702",
        "one-week Codex-low-availability queue",
        "OpenCode Desktop",
        "OpenCode Go",
        "paid DeepSeek API",
        "queue index",
        "Child issues own implementation",
        "Codex produces guardrails, backlog packets, architecture boundaries, and review prompts",
        "scripts/start_issue.sh",
        "one issue per worktree",
        "Tier A",
        "Tier B",
        "Tier C",
        "opencode/native-deepseek",
        "deepseek-api/direct",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "provider host",
        "billing path",
        "concrete model id",
        "opencode-desktop-handoff.md",
        "issue-worker.md",
        "GitHub issue state remains authoritative",
        "#703",
        "#704",
        "#705",
        "#708",
        "#709",
        "#706",
        "#707",
        "#710",
        "allowed files",
        "forbidden files",
        "focused tests",
        "gates",
        "merge authority",
        "GitHub CI",
        "scripts/finish_issue.sh",
        "Closes #<issue>",
        "entroping run",
        "Hurl runner behavior",
        "redaction",
        "proxy capture",
        "provider runtime boundaries",
        "release publishing",
        "secrets",
        "dependencies",
        "audit evidence",
        "issue outcome, diff quality, tests, CI, and review findings",
        "model-comparison-trial.md",
        "scripts/factory_metrics.py report",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_defines_risk_tiered_software_factory() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "## Software Factory Operating Model",
        (
            "Codex owns factory design, Tier B/Tier C integration, and merge "
            "readiness for sensitive lanes."
        ),
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "OpenCode and free-model workers receive bounded issue prompts",
        "local Qwen/oMLX handles private summarization, triage, and low-risk review",
        "Generated codegraph, Graphify, and Obsidian graph output is evidence, not authority",
        "One write agent per issue-scoped worktree",
    ]
    for term in required_terms:
        assert term in doc


def test_agent_control_plane_defines_autonomous_shipping_lane_limits() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    required_terms = [
        "## Autonomous OpenCode Shipping Lanes",
        "Tier A autonomous lane",
        "low-risk docs, tests, guard tests, prompt-library maintenance, and non-runtime scripts",
        (
            "may implement, push, open a PR, wait for GitHub CI, merge, and run "
            "`scripts/finish_issue.sh` without Codex"
        ),
        "Tier B assisted lane",
        "requires human or Codex review before merge",
        "Tier C restricted lane",
        "must never merge autonomously",
        "Hurl runner",
        "`entroping run`",
        "redaction",
        "proxy",
        "provider boundary",
        "release publishing",
        "architecture boundary",
        "secrets",
        "`scripts/start_issue.sh`",
        "`scripts/regression.sh --security`",
        "`Closes #<issue>`",
        "Agent Autonomy Declaration",
    ]

    for term in required_terms:
        assert term in normalized


def test_agents_md_allows_only_documented_tier_a_autonomy() -> None:
    doc = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "OpenCode/DeepSeek may independently implement and merge only Tier A autonomous lanes",
        "Tier B and Tier C remain human/Codex-reviewed",
        (
            "Do not let any unattended agent push to `main` outside a documented "
            "Tier A autonomous lane"
        ),
    ]

    for term in required_terms:
        assert term in normalized


def test_decision_registry_indexes_autonomous_opencode_lane() -> None:
    registry = (REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(registry.split())

    required_terms = [
        "ENT-DEC-0019",
        "OpenCode autonomy is risk-tiered, not unrestricted",
        "Tier A autonomous lanes",
        "PR autonomy declaration",
        "green CI",
        (
            "Tier C runtime, Hurl, redaction, proxy, provider-boundary, release, "
            "architecture, secrets, security, and audit-evidence work must never "
            "merge autonomously"
        ),
        "docs/meta/AGENT_CONTROL_PLANE.md",
        ".github/pull_request_template.md",
        "#648",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_routes_opencode_through_bounded_worker() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/ai_jobs.py" in doc
    assert ".entroping/ai-jobs/" in doc
    assert "flash-free" in doc
    assert "deepseek/deepseek-v4-pro" in doc
    assert "scripts/opencode_worker.py" in doc
    assert "patch proposal" in doc
    assert "Codex validates and applies" in doc
    assert "raw `opencode run`" in doc


def test_factory_metrics_docs_wire_opt_in_script_recording() -> None:
    context_doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    control_doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    combined = f"{context_doc}\n{control_doc}"

    required_terms = [
        "scripts/context_pack.sh --mode implementation --record-factory-metrics",
        "scripts/ai_jobs.py run-next --record-factory-metrics",
        "scripts/opencode_worker.py",
        "scripts/deepseek_worker.py",
        "--record-factory-metrics",
        "--factory-metrics-ledger",
        "opt-in",
        "raw prompts",
        "provider transcripts",
        "not release proof",
    ]
    for term in required_terms:
        assert term in combined


def test_factory_metrics_docs_wire_per_issue_report_export() -> None:
    context_doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    control_doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    combined = f"{context_doc}\n{control_doc}"

    required_terms = [
        "scripts/factory_metrics.py report --format json",
        "scripts/factory_metrics.py report --format md --output "
        ".entroping/factory-metrics/factory-report.md",
        "entroping.factory-metrics-report.v1",
        "model_comparison",
        "provider lane",
        "per-issue",
        "future extraction",
    ]
    for term in required_terms:
        assert term in combined


def test_context_tool_scorecard_docs_define_measurement_gate() -> None:
    context_doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    control_doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{context_doc}\n{control_doc}".split())

    required_terms = [
        "scripts/factory_metrics.py context-scorecard validate",
        "scripts/factory_metrics.py context-scorecard report --format json",
        "entroping.context-tool-scorecard.v1",
        "entroping.context-tool-scorecard-report.v1",
        "grounded_file_hit_rate",
        "nonexistent_reference_count",
        "forbidden_scope_incidents",
        "retrieval_precision",
        "retrieval_recall",
        "stale_claim_count",
        "context_recovery_time_seconds",
        "review_correction_count",
        "human_steering_count",
        "accepted_output_ratio",
        "context_bytes",
        "estimated_tokens",
        "active only when measured evidence improves at least two metrics",
        "Obsidian workspace/cache/plugin state is not scorecard evidence",
        "raw prompts, provider transcripts, secrets, raw traffic, or product runtime evidence",
    ]
    for term in required_terms:
        assert term in combined


def test_agent_control_plane_documents_direct_deepseek_worker_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    assert "scripts/deepseek_worker.py" in doc
    assert "--engine deepseek-api" in doc
    assert "DEEPSEEK_API_KEY" in doc
    assert "bounded UTF-8 prompt context" in doc
    assert "Before any artifact is written or provider request is made" in normalized
    assert "secret-like content" in normalized
    assert "Before generated output artifacts are written" in normalized
    assert "withholds secret-like stdout/stderr" in normalized
    assert "serialized response payloads" in normalized
    assert "skips raw response/proposal artifacts" in normalized
    assert "maintainer-only local development tooling" in doc
    assert "--thinking disabled" in doc
    assert "--thinking enabled --reasoning-effort high|max" in doc
    assert "does not replace Entroping's LiteLLM product boundary" in doc
    assert "never applies patches" in doc


def test_agent_control_plane_documents_opencode_hosted_deepseek_tool_lane() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    assert "OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane" in doc
    assert "OpenCode-configured agents, plugins, MCP servers, hooks" in doc
    assert "Codex-native plugins, skills, Codex Security, Browser, Computer Use" in doc
    assert "unless the OpenCode host exposes equivalent capabilities" in normalized
    assert "--dangerously-skip-permissions" in doc
    assert "OpenCode Host Capability Context" in doc


def test_agent_control_plane_distinguishes_provider_host_billing_model_lanes() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    required_terms = [
        "deepseek-api/direct",
        "opencode/native-deepseek",
        "opencode-go/kimi-k2.7-code",
        "opencode-go/qwen3.7-max",
        "opencode-go/other",
        "local/offline",
        "OpenCode Go is the Kimi/Qwen/model-variety lane",
        "not the default DeepSeek lane",
        "Direct DeepSeek API remains the default cheap queued worker lane",
        "provider host, billing path, and concrete model id",
    ]

    for term in required_terms:
        assert term in normalized


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

    documented_commands = set(
        re.findall(r"python scripts/ai_jobs\.py\s+([a-z][a-z-]*)", prompt)
    )

    assert "status" in documented_commands
    assert "list" not in documented_commands
    assert documented_commands <= supported_commands


def test_public_repo_surface_classifies_ai_workers_as_maintainer_only() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "PUBLIC_REPO_SURFACE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    assert "scripts/ai_jobs.py" in doc
    assert "scripts/opencode_worker.py" in doc
    assert "scripts/deepseek_worker.py" in doc
    assert "Maintainer-only AI worker tooling" in doc
    assert "not product APIs, user commands, or automatic patch applicators" in doc
    assert (
        "do not change Entroping's user-facing CLI or product provider boundary"
        in normalized
    )


def test_knowledge_base_workflow_documents_source_promotion() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "KNOWLEDGE_BASE_WORKFLOW.md").read_text(
        encoding="utf-8"
    )

    assert "Git-backed Markdown knowledge base is the first brain" in doc
    assert "OBSIDIAN_CONTEXT_ENGINE_GUIDE" in doc
    assert "notebookLM/2026-05-29 NotebookLM Specs.md" in doc
    assert "Promote source evidence through one of four gates" in doc
    assert "GitHub issue" in doc
    assert "ADR" in doc
    assert "canonical product or technical doc" in doc
    assert "hallucination" in doc.lower()
    assert "OBSIDIAN_VS_GITHUB owns day-to-day placement rules" in doc
    assert "KNOWLEDGE_BASE_WORKFLOW owns source promotion" in doc


def test_vault_index_marks_archival_context_and_history() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    zero_config = (
        REPO_ROOT / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md"
    ).read_text(encoding="utf-8")

    assert "historical source evidence, not current product truth" in index
    assert "Archived Decision Notes" in index
    assert "status: archival" in zero_config
    assert "Archived outcome" in zero_config


def test_obsidian_context_engine_documents_project_evolution_loop() -> None:
    doc = (
        REPO_ROOT / "docs" / "meta" / "OBSIDIAN_CONTEXT_ENGINE_GUIDE.md"
    ).read_text(encoding="utf-8")
    start_here = (
        REPO_ROOT / "docs" / "meta" / "OBSIDIAN_START_HERE.md"
    ).read_text(encoding="utf-8")
    obsidian_vs_github = (
        REPO_ROOT / "docs" / "meta" / "OBSIDIAN_VS_GITHUB.md"
    ).read_text(encoding="utf-8")

    assert "Start Analyzing And Evolving" in doc
    assert "Second Brain Discipline" in doc
    assert "Capture -> connect -> distill -> retrieve -> promote" in doc
    assert "Brainstorm in Obsidian" in doc
    assert "Promote actionable work to GitHub issue" in doc
    assert "GitHub is the factory floor" in doc
    assert "Obsidian is the memory palace" in doc
    assert 'What "Second Brain" Means Here' in start_here
    assert "Obsidian is where you think" in start_here
    assert "GitHub Issues are where work executes" in start_here
    assert "Start Analyzing And Evolving" in start_here
    assert "Promoted to: https://github.com/sakibshuvo/Entroping/issues/<number>" in (
        obsidian_vs_github
    )
    assert "After promotion, stop managing the task in Obsidian" in obsidian_vs_github


def test_growth_and_monetization_plan_keeps_open_core_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "product" / "GROWTH_AND_MONETIZATION.md").read_text(
        encoding="utf-8"
    )

    assert "open-core" in doc.lower()
    assert "Apache-2.0" in doc
    assert "GitHub Sponsors" in doc
    assert "premium policy packs" in doc
    assert "hosted team dashboard" in doc
    assert "Do not weaken the public core" in doc


def test_index_and_readme_link_agent_and_growth_docs() -> None:
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "[[docs/meta/AGENT_CONTROL_PLANE|AGENT_CONTROL_PLANE]]" in index
    assert "[[docs/meta/KNOWLEDGE_BASE_WORKFLOW|KNOWLEDGE_BASE_WORKFLOW]]" in index
    assert "[[docs/product/GROWTH_AND_MONETIZATION|GROWTH_AND_MONETIZATION]]" in index
    assert "scripts/context_pack.sh --mode implementation" in readme
    assert "GROWTH_AND_MONETIZATION.md" in readme


def test_community_health_files_exist_and_reference_project_gates() -> None:
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    conduct = (REPO_ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")

    assert "scripts/regression.sh" in contributing
    assert "docs/meta/FEATURE_DELIVERY_CHECKLIST.md" in contributing
    assert "security/advisories/new" in security
    assert "scripts/regression.sh --security" in security
    assert "respectful" in conduct.lower()


def test_good_first_issue_walkthrough_is_linked_and_actionable() -> None:
    walkthrough_path = (
        REPO_ROOT / "docs" / "meta" / "GOOD_FIRST_ISSUE_WALKTHROUGH.md"
    )
    walkthrough = walkthrough_path.read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert "[GOOD_FIRST_ISSUE_WALKTHROUGH.md]" in contributing
    assert "GOOD_FIRST_ISSUE_WALKTHROUGH.md" in readme
    assert "[[docs/meta/GOOD_FIRST_ISSUE_WALKTHROUGH|GOOD_FIRST_ISSUE_WALKTHROUGH]]" in index

    required_terms = [
        "good first issue",
        "status:ready",
        "milestone",
        "scripts/start_issue.sh",
        "--dry-run",
        "scripts/feature_gate.sh",
        "scripts/regression.sh",
        "scripts/doc_governance_check.sh",
        "docs/technical/TDS.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "Documentation Impact Declaration",
    ]

    for term in required_terms:
        assert term in walkthrough

    assert walkthrough.index("## The Small Path") < walkthrough.index("## Labels")
    assert walkthrough.index("## Labels") < walkthrough.index("## Validation")


def test_agent_workflow_docs_use_portable_repo_and_source_placeholders() -> None:
    docs = [
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md",
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md",
        REPO_ROOT / "docs" / "meta" / "KNOWLEDGE_BASE_WORKFLOW.md",
        REPO_ROOT / "docs" / "meta" / "OBSIDIAN_START_HERE.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)

    assert "/Users/sakibshuvo/projects/Entroping" not in combined
    assert "/Users/sakibshuvo/projects/entroping-specs" not in combined
    assert "<repo-root>" in combined
    assert "<source-archive>" in combined
    assert "ENTROPING_SOURCE_ROOT" in combined


def test_context_management_records_graph_context_pilot_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    assert "2026-06-12 issue #602 pilot" in doc
    assert (
        "Graphify did not beat `rg`, `scripts/context_pack.sh`, and "
        "`docs/meta/DECISION_REGISTRY.yaml`"
    ) in normalized
    assert "symbol-known impact analysis" in normalized
    assert (
        "ordinary contributors must not be required to install Graphify"
        in normalized
    )
    assert "graphify update . --no-cluster" in doc


def test_context_engineering_factory_boundary_is_canonical() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    context_management = (
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{control_plane}\n{context_management}".split())

    required_terms = [
        "## Context Engineering Factory Boundary",
        (
            "GitHub Issues, PRs, CI, source files, tests, ADRs, the decision "
            "registry, and QAnstitution/Hurl evidence remain the "
            "source-of-truth layer"
        ),
        "Obsidian, the LLM wiki, and curated source exports are the memory layer",
        (
            "Graphify, Understand Anything, CodeGraph, and Obsidian graph views "
            "are comprehension and retrieval aids"
        ),
        "Headroom and other compression tools are economic tooling",
        (
            "must not hide exact diffs, failing test output, security findings, "
            "audit evidence, or secrets-sensitive material"
        ),
        (
            "`entroping run` remains deterministic, Hurl-based, "
            "QAnstitution-governed, and provider-free"
        ),
        (
            "Codex remains the factory architect and Tier B/Tier C merge owner, "
            "while Tier A autonomous workers can merge only under the documented "
            "shipping lanes"
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_context_factory_rollout_order_is_documented() -> None:
    doc = (
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "## Context Factory Rollout Order",
        "Phase 1 - Obsidian vault discipline",
        "Phase 2 - LLM wiki plus Graphify over the repo and vault",
        "Phase 3 - Understand Anything for human comprehension and onboarding",
        "Phase 4 - CodeGraph for `src/` and `tests/` impact analysis",
        "Phase 5 - Headroom around Codex and OpenCode after retrieval behavior is stable",
        (
            "Phase 6 - bounded cheap, Chinese, and local model workers behind "
            "Codex-owned validation"
        ),
        (
            "Do not advance a layer until the previous layer has a documented "
            "owner, ignored generated-output path, and reviewable promotion path"
        ),
        (
            "No rollout layer may require ordinary contributors to install "
            "graph, wiki, compression, or model-worker tooling"
        ),
    ]

    for term in required_terms:
        assert term in normalized


def test_context_tool_generated_outputs_stay_local_and_ignored() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    context_management = (
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{control_plane}\n{context_management}".split())

    required_terms = [
        "## Generated Context Tool Output Paths",
        "`graphify-out/`",
        "`llm-wiki-out/`",
        "`understand-anything-out/`",
        "`codegraph-out/`",
        "`headroom-out/`",
        "`agent-context-out/`",
        (
            "Generated context outputs must remain ignored/local unless "
            "intentionally promoted into curated Markdown"
        ),
        (
            "Do not delete, archive, or rewrite context-preservation material "
            "just because generated output is noisy"
        ),
        (
            "ordinary contributors must not be required to install Graphify, "
            "CodeGraph, Headroom, Obsidian plugins, LLM wiki tooling, or "
            "Understand Anything"
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_graph_assisted_agent_context_probe_is_optional_and_advisory() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    context_management = (
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md"
    ).read_text(encoding="utf-8")
    issue_worker = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(
        f"{control_plane}\n{context_management}\n{issue_worker}".split()
    )

    required_terms = [
        "scripts/agent_context_probe.py",
        "scripts/context_pack.sh --mode implementation --with-local-graphs",
        "--graph-query",
        "agent-context-out/",
        "optional graph-assisted agent context",
        "Graphify/CodeGraph evidence is not authority",
        "must not replace source reading, focused tests, or CI",
        "skip cleanly when Graphify or CodeGraph output is absent",
    ]

    for term in required_terms:
        assert term in combined


def test_factory_role_registry_and_metrics_ledger_are_portable_guardrails() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    context_management = (
        REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md"
    ).read_text(encoding="utf-8")
    prompt_library = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
    vault_index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(
        f"{control_plane}\n{context_management}\n{prompt_library}\n{vault_index}".split()
    )

    required_terms = [
        "docs/meta/AGENT_ROLE_REGISTRY.yaml",
        "scripts/factory_metrics.py",
        ".entroping/factory-metrics/",
        "entroping.factory-metrics.v1",
        "portable software-factory protocol",
        "Product Manager, Architect, Dev Agent, QA Agent, Code Review Agent, "
        "Security Agent, Monitoring Agent, and Integrator",
        "Codex, Claude Code, OpenCode, DeepSeek, Gemini, Spark, and local models",
        "must not store raw prompts, provider transcripts, secrets, raw traffic, "
        "or product runtime evidence",
        "The factory framework owns workflow, context, metrics, and guardrails; "
        "the project owns product truth.",
    ]

    for term in required_terms:
        assert term in combined


def test_prompt_library_contains_autonomous_tier_a_worker_prompt() -> None:
    prompt = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    catalog = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{prompt}\n{catalog}".split())

    required_terms = [
        "Autonomous Tier A OpenCode/DeepSeek Worker Prompt",
        "Do not use this mode for Tier B or Tier C work.",
        "`scripts/start_issue.sh <issue-number> <type>/<short-kebab-description>`",
        "Agent Autonomy Declaration",
        "`scripts/regression.sh --security`",
        "`Closes #<issue-number>`",
        "`scripts/finish_issue.sh <issue-number>`",
        "CI is green",
    ]

    for term in required_terms:
        assert term in combined


def test_prompt_library_contains_opencode_desktop_handoff_prompts() -> None:
    prompt_path = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-handoff.md"
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    catalog = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
        "scripts/context_pack.sh --mode implementation --with-local-graphs",
        "Graphify/CodeGraph evidence is not authority",
        "scripts/factory_metrics.py",
        "Agent Autonomy Declaration",
        "Tier B/Tier C requires Codex or human review before merge",
        "Closes #<issue-number>",
    ]

    for term in required_terms:
        assert term in combined


def test_pull_request_template_requires_agent_autonomy_declaration() -> None:
    template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(template.split())

    required_terms = [
        "## Agent Autonomy Declaration",
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "Merge authority:",
        "CI passed before merge",
        "`Closes #<issue>`",
    ]

    for term in required_terms:
        assert term in normalized
