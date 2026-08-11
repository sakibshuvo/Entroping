"""Frozen agent control-plane documentation contracts."""

from agent_workflow_test_helpers import REPO_ROOT
from agent_workflow_test_helpers import concat_text as _concat_text


def test_agent_control_plane_documents_cross_agent_guardrails() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")

    assert "Codex owns factory design" in doc
    assert "Claude Code" in doc
    assert "OpenCode" in doc
    assert "Gemini" in doc
    assert "NotebookLM" in doc
    assert "local Qwen" in doc
    assert "scripts/context_pack.sh --mode implementation" in doc
    assert "scripts/opencode_readiness.py --mode implementation" in doc
    assert "scripts/agent_toolchain.py --mode implementation --format json" in doc
    assert "safe_default" in doc
    assert "guarded_local_only" in doc
    assert "manual_explicit" in doc
    assert "No helper agent is a source of truth" in doc


def test_agent_control_plane_documents_artifact_first_worker_review() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    handoff = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    review_request = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-codex-review-request.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{control_plane}\n{handoff}\n{review_request}".split())

    required_terms = [
        "artifact-first worker contract",
        "Do not run OpenCode interactively for routine cheap-worker work",
        "scripts/ai_jobs.py audit-routing",
        "scripts/factory_review_packet.py",
        _concat_text(
            "review only the job metadata, result summary, diff stat, git diff, changed",
            " files, and test output",
        ),
        _concat_text(
            "Do not read raw stdout, stderr, provider responses, or full transcripts",
            " unless the compact evidence is ambiguous",
        ),
        "ACCEPT",
        "REQUEST_SMALL_FIX",
        "REWRITE_WITH_CODEX",
        "ESCALATE_SCOPE",
    ]

    for term in required_terms:
        assert term in combined


def test_agent_control_plane_specifies_portable_role_metrics_boundary() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    role_registry = (REPO_ROOT / "docs" / "meta" / "AGENT_ROLE_REGISTRY.yaml").read_text(
        encoding="utf-8"
    )
    combined = " ".join(f"{control_plane}\n{role_registry}".split())

    required_terms = [
        "Portable role and metrics boundary",
        "Portable role fields",
        "Entroping-only role fields",
        "Portable metrics fields",
        "Entroping-only metrics fields",
        "Merge-trust evidence",
        "Privacy and security boundary",
        "provider lane",
        "model id",
        "No one model, host, or billing path is mandatory",
        "raw provider transcripts",
        "unredacted traffic",
        "Tier A/B/C",
    ]

    for term in required_terms:
        assert term in combined


def test_agent_toolchain_policy_is_linked_from_readiness_and_agent_rules() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    readiness = (REPO_ROOT / "scripts" / "opencode_readiness.py").read_text(encoding="utf-8")
    combined = " ".join(f"{agents}\n{control_plane}\n{readiness}".split())

    required_terms = [
        "scripts/agent_toolchain.py",
        "entroping.agent-toolchain.v1",
        "PATH lookup only",
        "safe_default",
        "guarded_local_only",
        "manual_explicit",
        "Do not run automatically",
        "not scan home directories",
        "provider config",
        "local secret stores",
        "act",
        "trufflehog",
        "semgrep",
        "trivy",
        "syft",
        "grype",
    ]

    for term in required_terms:
        assert term in combined


def test_agent_control_plane_documents_codex_outage_worker_queue() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")
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
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")

    required_terms = [
        "## Software Factory Operating Model",
        (
            _concat_text(
                "Codex owns factory design, Tier B/Tier C integration, and merge readiness",
                " for sensitive lanes.",
            )
        ),
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "OpenCode and free-model workers receive bounded issue prompts",
        "local Qwen/oMLX handles private summarization, triage, and low-risk review",
        "Generated graph, wiki, and compression output is evidence, not authority",
        "One write agent per issue-scoped worktree",
        "scripts/ai_jobs.py submit --autonomy-tier tier-a",
        "context-manifest command",
        "needed files/snippets",
        "Tier B and Tier C stay Codex/human reviewed",
    ]
    for term in required_terms:
        assert term in doc


def test_agent_control_plane_defines_autonomous_shipping_lane_limits() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "## Autonomous OpenCode Shipping Lanes",
        "Tier A autonomous lane",
        "low-risk docs, tests, guard tests, prompt-library maintenance, and non-runtime scripts",
        (
            _concat_text(
                "may implement, push, open a PR, wait for GitHub CI, merge, and run",
                " `scripts/finish_issue.sh` without Codex",
            )
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


def test_decision_registry_indexes_autonomous_opencode_lane() -> None:
    registry = (REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml").read_text(encoding="utf-8")
    normalized = " ".join(registry.split())

    required_terms = [
        "ENT-DEC-0019",
        "OpenCode autonomy is risk-tiered, not unrestricted",
        "Tier A autonomous lanes",
        "PR autonomy declaration",
        "green CI",
        (
            _concat_text(
                "Tier C runtime, Hurl, redaction, proxy, provider-boundary, release,",
                " architecture, secrets, security, and audit-evidence work must never merge",
                " autonomously",
            )
        ),
        "docs/meta/AGENT_CONTROL_PLANE.md",
        ".github/pull_request_template.md",
        "#648",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_routes_opencode_through_bounded_worker() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")

    assert "scripts/ai_jobs.py" in doc
    assert ".entroping/ai-jobs/" in doc
    assert "flash-free" in doc
    assert "deepseek/deepseek-v4-pro" in doc
    assert "scripts/opencode_worker.py" in doc
    assert "patch proposal" in doc
    assert "Codex validates and applies" in doc
    assert "raw `opencode run`" in doc


def test_unattended_opencode_isolation_decision_and_control_plane_are_indexed() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    tds = (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    registry = (REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml").read_text(encoding="utf-8")
    adr = (REPO_ROOT / "decisions" / "ADR-0027-opencode-unattended-isolation.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(f"{control_plane}\n{tds}\n{registry}\n{adr}".split())

    required_terms = [
        "ENT-DEC-0027",
        "entroping.opencode-unattended-review.v1",
        "entroping.opencode-unattended-patch-proposal.v1",
        "entroping.opencode-unattended-capability-receipt.v1",
        "private ephemeral `HOME`",
        "`XDG_CONFIG_HOME`",
        "`OPENCODE_DISABLE_PROJECT_CONFIG=1`",
        "`--pure`",
        "`--agent`",
        "`--dir`",
        "deny-first",
        "denies every model-issued tool",
        "explicit `--file` snapshots",
        "subagent depth zero",
        "20-second",
        "without any provider credential",
        "raw prompts",
        "trusted executable",
        "digest and version binding",
        "OS or container isolation",
        "same-UID",
        "unrestricted egress",
    ]
    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_documents_direct_deepseek_worker_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")
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
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    assert "OpenCode-hosted DeepSeek V4 Pro is the tool-enabled DeepSeek lane" in doc
    assert "unattended runs do not inherit host agents, plugins, MCP servers" in (normalized)
    assert "Interactive maintainer sessions remain a separate surface" in normalized
    assert "`OPENCODE_DISABLE_PROJECT_CONFIG=1`" in doc
    assert "`--pure debug config`" in doc


def test_agent_control_plane_distinguishes_provider_host_billing_model_lanes() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(encoding="utf-8")
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
        "CLI's default engine remains OpenCode",
        "provider host, billing path, and concrete model id",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_inventories_factory_template_primitives() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(control_plane.split())

    required_terms = [
        "## Factory Template Extraction Inventory",
        "Workflow primitives to evaluate for extraction",
        "candidates for extraction after proof",
        "issue templates",
        "`scripts/start_issue.sh` and `scripts/finish_issue.sh`",
        _concat_text(
            "`scripts/check.sh`, `scripts/feature_gate.sh`, `scripts/regression.sh`,",
            " and `scripts/audit_quality.sh`",
        ),
        "`scripts/context_pack.sh --manifest`",
        "`scripts/factory_metrics.py readiness`",
        "unknowns stay unknown",
        "Entroping-specific product contracts",
        "QAnstitution governance",
        "deterministic Hurl execution",
        "`entroping run` remains deterministic and LLM-free",
        "Blocked before generalizing",
        "Unsafe to generalize",
        "raw provider transcripts",
        "raw traffic",
        "Tier B/Tier C merge authority",
        "model summaries as source of truth",
        "future template scaffold",
    ]

    for term in required_terms:
        assert term in normalized

    section = control_plane.split("## Factory Template Extraction Inventory", maxsplit=1)[1].split(
        "## Autonomous OpenCode Shipping Lanes", maxsplit=1
    )[0]
    expected_subsections = [
        "### Workflow primitives to evaluate for extraction",
        "### Entroping-specific product contracts",
        "### Blocked before generalizing",
        "### Unsafe to generalize",
    ]
    positions = [section.index(subsection) for subsection in expected_subsections]
    assert positions == sorted(positions)

    extraction_candidates = section.split(
        "### Workflow primitives to evaluate for extraction", maxsplit=1
    )[1].split("### Entroping-specific product contracts", maxsplit=1)[0]
    normalized_extraction_candidates = " ".join(extraction_candidates.split())
    for term in [
        "issue templates",
        "`scripts/start_issue.sh` and `scripts/finish_issue.sh`",
        "`scripts/context_pack.sh --manifest`",
        "`scripts/factory_metrics.py readiness`",
    ]:
        assert term in normalized_extraction_candidates


def test_agent_control_plane_defines_portable_context_evidence_protocol() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(control_plane.split())

    required_terms = [
        "### Portable context-as-evidence protocol",
        "source-of-truth priority",
        "local repo files and tests",
        "GitHub Issues, PRs, CI",
        "decision registry and ADRs",
        "product and technical docs",
        "external source/reference material",
        "chat memory last",
        "manifest-only context",
        "full context pack",
        "stale claim rate",
        "wrong-file references",
        "human steering",
        "context bytes/tokens",
        "review correction count",
        "accepted output ratio",
        "generated local context",
        "ignored artifacts",
        "stale Markdown",
        "Retired graph/compression tools and Obsidian",
        "optional aids, not default dependencies",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_defines_minimal_seed_repo_contract() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(control_plane.split())

    required_terms = [
        "### Minimal seed-repo contract",
        "agent instructions",
        "issue lifecycle",
        "gate ladder",
        "context pack",
        "decision registry",
        "role registry",
        "metrics",
        "Required CI evidence",
        "local verification expectations",
        "project-local rather than template-global",
        "no Entroping runtime behavior",
        "no QAnstitution branding reuse",
        "no provider secrets",
        "no generated vendor lock-in",
        "Tier A/B/C autonomy assumptions",
        "required stop conditions",
        "Do not create an external template repo",
    ]

    for term in required_terms:
        assert term in normalized


def test_agent_control_plane_defines_portable_anti_slop_gate_ladder() -> None:
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(control_plane.split())

    required_terms = [
        "### Portable anti-slop gate ladder",
        "quick local checks",
        "focused tests",
        "docs governance",
        "standard quality gate",
        "security/regression gate",
        "quality audit",
        "Required PR evidence",
        "architecture",
        "security",
        "test coverage",
        "model output is advisory",
        "deterministic gates",
        "human/Codex review",
        "portable gates",
        "project-specific gates",
        "Tier A minimum",
        "Tier B/C work",
        "scope creep",
        "flaky tests",
        "missing evidence",
        "forbidden provider use",
        "context drift",
    ]

    for term in required_terms:
        assert term in normalized
