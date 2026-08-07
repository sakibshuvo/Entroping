"""Frozen factory-artifact documentation contracts."""

import subprocess

from agent_workflow_test_helpers import REPO_ROOT
from agent_workflow_test_helpers import concat_text as _concat_text


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
        _concat_text(
            "scripts/factory_metrics.py report --format md --output",
            " .entroping/factory-metrics/factory-report.md",
        ),
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


def test_knowledge_base_workflow_documents_source_promotion() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "KNOWLEDGE_BASE_WORKFLOW.md").read_text(encoding="utf-8")

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


def test_vault_index_marks_archival_context_and_active_decisions() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    zero_config = (REPO_ROOT / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md").read_text(
        encoding="utf-8"
    )

    assert "historical source evidence, not current product truth" in index
    assert "Archived Decision Notes" in index
    assert "status: active" in zero_config
    assert "Current Outcome" in zero_config
    assert "entroping demo --project <path>" in zero_config


def test_obsidian_context_engine_documents_project_evolution_loop() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "OBSIDIAN_CONTEXT_ENGINE_GUIDE.md").read_text(
        encoding="utf-8"
    )
    start_here = (REPO_ROOT / "docs" / "meta" / "OBSIDIAN_START_HERE.md").read_text(
        encoding="utf-8"
    )
    obsidian_vs_github = (REPO_ROOT / "docs" / "meta" / "OBSIDIAN_VS_GITHUB.md").read_text(
        encoding="utf-8"
    )

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


def test_context_management_records_retired_context_tool_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    assert "Issue #712's full trial" in doc
    assert "Issue #724 converts that evidence into cleanup" in doc
    assert "Retired generated context tooling is not part of active agent workflow" in doc
    assert "Remove retired generated context tooling from active workflow" in doc
    assert "ordinary contributors must not be required to install external graph" in normalized
    assert "Agents should use `rg`, source reads, tests, and measured factory metrics" in normalized


def test_context_management_does_not_frame_graph_tools_as_rehydration_path() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    stale_phrases = [
        "future graph tooling can rehydrate the project",
        "before adding generated graphs or model summaries",
        "without a restart and generated graph",
    ]
    for phrase in stale_phrases:
        assert phrase not in normalized

    required_terms = [
        "Entroping uses layered, repo-native context",
        (
            _concat_text(
                "Optional graph, wiki, comprehension, or compression tooling is not part of",
                " normal rehydration",
            )
        ),
        "must earn promotion through measured scorecard evidence",
        (
            _concat_text(
                "Keep curated Markdown, source links, ADR pointers, and lessons accurate",
                " before adding generated or model-authored summaries",
            )
        ),
        (
            _concat_text(
                "not active in this Codex session without a restart; generated graph output",
                " remains outside active workflow",
            )
        ),
    ]
    for term in required_terms:
        assert term in normalized


def test_context_engineering_factory_boundary_is_canonical() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    context_management = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{control_plane}\n{context_management}".split())

    required_terms = [
        "## Context Engineering Factory Boundary",
        (
            _concat_text(
                "GitHub Issues, PRs, CI, source files, tests, ADRs, the decision registry,",
                " and QAnstitution/Hurl evidence remain the source-of-truth layer",
            )
        ),
        "Obsidian, the LLM wiki, and curated source exports are the memory layer",
        ("Retired generated context tooling is not part of active agent workflow"),
        "Understand Anything remains optional for human comprehension",
        (
            _concat_text(
                "must not hide exact diffs, failing test output, security findings, audit",
                " evidence, or secrets-sensitive material",
            )
        ),
        (
            _concat_text(
                "`entroping run` remains deterministic, Hurl-based, QAnstitution-governed,",
                " and provider-free",
            )
        ),
        (
            _concat_text(
                "Codex remains the factory architect and Tier B/Tier C merge owner, while",
                " Tier A autonomous workers can merge only under the documented shipping",
                " lanes",
            )
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_context_factory_rollout_order_is_documented() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "## Context Factory Rollout Order",
        "Phase 1 - Obsidian vault discipline",
        "Phase 2 - curated Markdown and LLM-wiki style source maps",
        "Phase 3 - Understand Anything for human comprehension and onboarding",
        "Phase 4 - bounded cheap, Chinese, and local model workers behind Codex-owned validation",
        (
            _concat_text(
                "Do not advance a layer until the previous layer has a documented owner,",
                " ignored generated-output path, and reviewable promotion path",
            )
        ),
        (
            _concat_text(
                "No rollout layer may require ordinary contributors to install graph, wiki,",
                " compression, or model-worker tooling",
            )
        ),
    ]

    for term in required_terms:
        assert term in normalized


def test_context_tool_generated_outputs_stay_local_and_ignored() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    context_management = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{control_plane}\n{context_management}".split())

    required_terms = [
        "## Generated Context Tool Output Paths",
        "`llm-wiki-out/`",
        "`understand-anything-out/`",
        (
            _concat_text(
                "Generated context outputs must remain ignored/local unless intentionally",
                " promoted into curated Markdown",
            )
        ),
        (
            _concat_text(
                "Do not delete, archive, or rewrite context-preservation material just",
                " because generated output is noisy",
            )
        ),
        (
            _concat_text(
                "ordinary contributors must not be required to install external graph,",
                " compression, Obsidian plugin, LLM wiki, or comprehension tools",
            )
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_unproven_context_tools_are_not_active_agent_dependencies() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    context_management = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    issue_worker = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{control_plane}\n{context_management}\n{issue_worker}".split())

    required_terms = [
        "Retired generated context tooling is not part of active agent workflow",
        (
            _concat_text(
                "Do not route normal Codex, OpenCode, DeepSeek, or Spark sessions through",
                " external context tools",
            )
        ),
        (
            _concat_text(
                "Use `rg`, `scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`,",
                " GitHub issues, source files, tests, and CI first",
            )
        ),
        "Understand Anything remains optional for human comprehension",
    ]

    for term in required_terms:
        assert term in combined

    forbidden_terms = [
        "scripts/context_pack.sh --mode implementation --with-local-graphs",
        "scripts/agent_context_probe.py",
        "--graph-query",
        "optional graph-assisted agent context",
    ]

    for term in forbidden_terms:
        assert term not in combined


def test_repo_native_context_budget_baseline_is_canonical() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    context_management = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    issue_worker = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{control_plane}\n{context_management}\n{issue_worker}".split())

    required_terms = [
        "## Repo-Native Context Budget Baseline",
        "Context is evidence, not memory",
        (
            _concat_text(
                "Start each issue with one named question: what local evidence is needed to",
                " change, review, or merge this issue?",
            )
        ),
        (
            _concat_text(
                "`rg`, `scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`,",
                " GitHub issues, source files, focused tests, CI, and",
                " `scripts/factory_metrics.py report` are the active context-cost baseline",
            )
        ),
        (
            _concat_text(
                "Do not add generated context because it is interesting, visual, popular,",
                " or already installed",
            )
        ),
        (
            _concat_text(
                "Load extra context only when it answers the named issue question and",
                " records an evidence pointer",
            )
        ),
        (
            _concat_text(
                "Use `scripts/context_pack.sh --record-factory-metrics` and",
                " `scripts/factory_metrics.py report` when token or cost claims matter",
            )
        ),
        (
            _concat_text(
                "No token-saving claim is accepted without measured local evidence from the",
                " current workflow lane",
            )
        ),
    ]

    for term in required_terms:
        assert term in combined

    help_result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "context_pack.sh"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    help_text = " ".join(help_result.stdout.split())
    for term in [
        "repo-native context budget baseline",
        "Do not add generated context because it is interesting",
        "--record-factory-metrics",
    ]:
        assert term in help_text


def test_retired_context_tools_are_not_named_in_active_workflow_surfaces() -> None:
    active_paths = [
        "AGENTS.md",
        "CONTRIBUTING.md",
        "README.md",
        "scripts/deepseek_worker.py",
        "scripts/factory_metrics.py",
        "scripts/public_claims_audit.py",
        "scripts/repo_hygiene.sh",
        "src/entroping/core/hurl_discovery.py",
        "docs/meta/AGENT_CONTROL_PLANE.md",
        "docs/meta/CONTEXT_MANAGEMENT.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "docs/meta/KNOWLEDGE_BASE_WORKFLOW.md",
        "docs/meta/OBSIDIAN_START_HERE.md",
        "docs/meta/OBSIDIAN_VS_GITHUB.md",
        "docs/meta/PROJECT_PROGRESS.md",
        "docs/meta/PUBLIC_DOCS_SITE_DECISION.md",
        "docs/meta/PUBLIC_REPO_SURFACE.md",
        "docs/meta/PYPI_RELEASE_RUNBOOK.md",
        "docs/meta/RELEASE_CHECKLIST.md",
        "docs/meta/prompt-library/README.md",
        "docs/meta/prompt-library/architecture-boundary-brief.md",
        "docs/meta/prompt-library/codex-outage-daily-operations.md",
        "docs/meta/prompt-library/context-reconciliation.md",
        "docs/meta/prompt-library/issue-worker.md",
        "docs/meta/prompt-library/model-comparison-trial.md",
        "docs/meta/prompt-library/multi-agent-marathon.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
        "tests/test_deepseek_worker.py",
        "tests/test_factory_metrics.py",
        "tests/test_public_claims_audit.py",
        "tests/test_repo_hygiene_script.py",
    ]
    retired_terms = [
        "Graph" + "ify",
        "graph" + "ify",
        "Code" + "Graph",
        "code" + "graph",
        "Head" + "room",
        "head" + "room",
        "." + "code" + "graph",
        "graph" + "ify-out",
        "code" + "graph-out",
        "head" + "room-out",
    ]

    violations: list[str] = []
    for path in active_paths:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        for term in retired_terms:
            if term in text:
                violations.append(f"{path}: {term}")

    assert violations == []


def test_factory_role_registry_and_metrics_ledger_are_portable_guardrails() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    context_management = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    prompt_library = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md").read_text(
        encoding="utf-8"
    )
    vault_index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    combined = " ".join(
        f"{control_plane}\n{context_management}\n{prompt_library}\n{vault_index}".split()
    )

    required_terms = [
        "docs/meta/AGENT_ROLE_REGISTRY.yaml",
        "scripts/factory_metrics.py",
        ".entroping/factory-metrics/",
        "entroping.factory-metrics.v1",
        "portable software-factory protocol",
        _concat_text(
            "Product Manager, Architect, Dev Agent, QA Agent, Code Review Agent,",
            " Security Agent, Monitoring Agent, and Integrator",
        ),
        "Codex, Claude Code, OpenCode, DeepSeek, Gemini, Spark, and local models",
        _concat_text(
            "must not store raw prompts, provider transcripts, secrets, raw traffic, or",
            " product runtime evidence",
        ),
        _concat_text(
            "The factory framework owns workflow, context, metrics, and guardrails; the",
            " project owns product truth.",
        ),
    ]

    for term in required_terms:
        assert term in combined
