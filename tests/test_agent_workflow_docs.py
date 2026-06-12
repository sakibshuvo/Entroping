"""Guardrails for agent workflow and growth documentation."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_control_plane_documents_cross_agent_guardrails() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )

    assert "Codex is the primary integrator" in doc
    assert "Claude Code" in doc
    assert "OpenCode" in doc
    assert "Gemini" in doc
    assert "NotebookLM" in doc
    assert "local Qwen" in doc
    assert "scripts/context_pack.sh --mode implementation" in doc
    assert "No helper agent is a source of truth" in doc


def test_agent_control_plane_defines_codex_first_software_factory() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )

    required_terms = [
        "## Software Factory Operating Model",
        "Codex owns integration and merge readiness",
        "OpenCode and free-model workers receive bounded issue prompts",
        "local Qwen/oMLX handles private summarization, triage, and low-risk review",
        "Generated codegraph, Graphify, and Obsidian graph output is evidence, not authority",
        "One write agent per issue-scoped worktree",
    ]
    for term in required_terms:
        assert term in doc


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
    assert "maintainer-only local development tooling" in doc
    assert "--thinking disabled" in doc
    assert "--thinking enabled --reasoning-effort high|max" in doc
    assert "does not replace Entroping's LiteLLM product boundary" in doc
    assert "never applies patches" in doc


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
        "Codex remains the integrator and merge owner",
    ]

    for term in required_terms:
        assert term in combined
