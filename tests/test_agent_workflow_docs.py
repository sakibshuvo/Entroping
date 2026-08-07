"""Guardrails for agent workflow and growth documentation."""

import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

def _concat_text(*parts: str) -> str:
    """Join text fragments without implicit concatenation."""
    return "".join(parts)



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
    assert "scripts/opencode_readiness.py --mode implementation" in doc
    assert "scripts/agent_toolchain.py --mode implementation --format json" in doc
    assert "safe_default" in doc
    assert "guarded_local_only" in doc
    assert "manual_explicit" in doc
    assert "No helper agent is a source of truth" in doc


def test_agent_control_plane_documents_artifact_first_worker_review() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    handoff = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    review_request = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-codex-review-request.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{control_plane}\n{handoff}\n{review_request}".split())

    required_terms = [
        "artifact-first worker contract",
        "Do not run OpenCode interactively for routine cheap-worker work",
        "scripts/ai_jobs.py audit-routing",
        "scripts/factory_review_packet.py",
        _concat_text(
            'review only the job metadata, result summary, diff stat, git diff, changed',
            ' files, and test output',
        ),
        _concat_text(
            'Do not read raw stdout, stderr, provider responses, or full transcripts',
            ' unless the compact evidence is ambiguous',
        ),
        "ACCEPT",
        "REQUEST_SMALL_FIX",
        "REWRITE_WITH_CODEX",
        "ESCALATE_SCOPE",
    ]

    for term in required_terms:
        assert term in combined


def test_agent_control_plane_specifies_portable_role_metrics_boundary() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    role_registry = (
        REPO_ROOT / "docs" / "meta" / "AGENT_ROLE_REGISTRY.yaml"
    ).read_text(encoding="utf-8")
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


def test_worker_prompts_define_codex_pickup_handoff_and_shortcut_guards() -> None:
    pickup_prompt_paths = [
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-handoff.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-one-shot.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-week-monitoring.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "model-comparison-trial.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "codex-outage-daily-operations.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "multi-agent-marathon.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "deepseek-opencode-review.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-codex-review-request.md",
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "model-output-acceptance-gate.md",
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
        missing = [
            term for term in pickup_terms if " ".join(term.split()) not in normalized_prompt
        ]
        assert not missing, f"{prompt_path} missing {missing}"

    shortcut_prompt_paths = [
        *pickup_prompt_paths,
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "architecture-boundary-brief.md",
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
            term
            for term in shortcut_terms
            if " ".join(term.split()) not in normalized_prompt
        ]
        assert not missing, f"{prompt_path} missing {missing}"


def test_agent_toolchain_policy_is_linked_from_readiness_and_agent_rules() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    control_plane = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    readiness = (REPO_ROOT / "scripts" / "opencode_readiness.py").read_text(
        encoding="utf-8"
    )
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


def test_prompt_library_includes_engineering_health_review_prompt() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "engineering-health-review.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "claude-code-review.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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


def test_backlog_triage_prompt_requires_status_ready_open_code_fields() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "backlog-triage.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    required_terms = [
        "status:ready",
        "OpenCode",
        "DeepSeek",
        "provider lane",
        "model id",
        "autonomy tier",
        "allowed files",
        "forbidden scope, including the minimum Tier A exclusions below",
        "required focused tests",
        "required full gate",
        "merge authority",
        "stop conditions",
        "acceptance criteria as deterministic pass/fail bullets",
        "OpenCode/DeepSeek Status-Ready Issue Guard",
        "GitHub Issues",
        "Avoid Markdown backlog sprawl",
        "do not create or mutate Markdown issue trackers as a backlog system",
        "Tier A autonomous lane",
        "Tier B assisted lane",
        "Tier C restricted lane",
        "Hurl runner",
        "`entroping run`",
        "redaction",
        "proxy",
        "provider runtime",
        "dependencies",
        "release publishing",
        "secrets",
        "raw traffic",
        "audit evidence",
        "architecture boundary changes",
        "must include at least those Tier A exclusions",
        "add narrower exclusions for the specific issue when needed",
        "forbidden scope: <exact exclusions, including the minimum Tier A exclusions>",
        "entroping.user-evidence.v1",
        "Sanitized User-Evidence Packet",
        "evidence_status",
        "affected_journey",
        "severity",
        "source_classification",
        "verification_receipt",
        "evidence:user-verified",
        "Internal observations are not user evidence",
        "Provider dispatch may receive only the sanitized issue packet",
        "priority:p0",
        "ascending issue number",
        "most recent 20",
        "must not affect selection",
        "fixed percentage",
    ]

    for term in required_terms:
        assert term in normalized


def test_user_evidence_contract_is_closed_consistent_and_fail_closed() -> None:
    documents = {
        "User-Evidence Metadata Contract": REPO_ROOT
        / "docs"
        / "meta"
        / "ISSUE_TRACKING.md",
        "GitHub User-Evidence Metadata": REPO_ROOT
        / "docs"
        / "meta"
        / "DOWNSTREAM_FEEDBACK_KIT.md",
        "Sanitized User-Evidence Packet": REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "backlog-triage.md",
    }
    expected = {
        "user_evidence": {
            "schema_version": "entroping.user-evidence.v1",
            "evidence_status": "verified",
            "affected_journey": "first_run",
            "severity": "blocker",
            "source_classification": "design_partner",
            "verification_receipt": (
                "sha256:0123456789abcdef0123456789abcdef"
                "0123456789abcdef0123456789abcdef"
            ),
        }
    }
    required_safety_terms = [
        "evidence:user-verified",
        "never put raw feedback",
        "provider dispatch may receive only the sanitized issue packet",
        "internal observations are not user evidence",
    ]

    for heading, path in documents.items():
        content = path.read_text(encoding="utf-8")
        match = re.search(
            rf"## {re.escape(heading)}.*?```yaml\n(.*?)\n```",
            content,
            flags=re.DOTALL,
        )
        assert match is not None
        assert yaml.safe_load(match.group(1)) == expected
        normalized = " ".join(content.split()).lower()
        for term in required_safety_terms:
            assert term in normalized

    issue_tracking = documents["User-Evidence Metadata Contract"].read_text(
        encoding="utf-8"
    )
    normalized_issue_tracking = " ".join(issue_tracking.split())
    assert "exactly one YAML block" in normalized_issue_tracking
    assert "unknown or repeated fields are invalid" in normalized_issue_tracking
    assert "selector safety boundary implemented by issue #1567" in (
        normalized_issue_tracking
    )
    assert "ownership, active branch, worktree, PR, lease, explicit file scope" in (
        normalized_issue_tracking
    )
    assert "exactly one `status:ready` label" in normalized_issue_tracking
    assert "have no unresolved `Blocked by` dependency" in normalized_issue_tracking
    assert "must fail closed from user-evidence priority" in normalized_issue_tracking
    assert "20 most recent counted receipts" in normalized_issue_tracking
    assert "snapshot exactly one `work:*` value" in normalized_issue_tracking
    assert "Missing or conflicting work labels snapshot as `unclassified`" in (
        normalized_issue_tracking
    )
    assert "retries and repeated selections" in normalized_issue_tracking
    assert "when fewer than 20 exist" in normalized_issue_tracking
    assert "together with `sample_size`" in normalized_issue_tracking
    assert "Later GitHub label edits do not rewrite the snapshot" in (
        normalized_issue_tracking
    )
    assert "must not change selection" in normalized_issue_tracking


def test_agent_workflow_docs_document_verification_lanes() -> None:
    pr_template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    checklist = (
        REPO_ROOT / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    issue_worker = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md"
    ).read_text(encoding="utf-8")
    combined = " ".join(f"{pr_template}\n{checklist}\n{issue_worker}".split())

    required_terms = [
        "Verification lane",
        "tiny-docs",
        "docs-guardrail",
        "tests-only",
        "normal-code",
        "security-runtime",
        "release-ci-architecture",
        "proportional verification",
        "scripts/pr_body_check.py",
        "scripts/doc_governance_check.sh",
        "uv run pytest tests/",
        "scripts/feature_gate.sh",
        "scripts/regression.sh --security",
        "scripts/audit_quality.sh",
    ]

    for term in required_terms:
        assert term in combined


def test_prompt_library_documents_self_contained_worker_packets() -> None:
    issue_worker = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md"
    ).read_text(encoding="utf-8")
    opencode_handoff = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-handoff.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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


def test_issue_worker_prompt_enforces_artifact_first_handoff_contract() -> None:
    issue_worker = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(issue_worker.split())

    required_terms = [
        "For repeatable hands-off runs, use the artifact scripts:",
        "`scripts/ai_jobs.py`, `scripts/opencode_worker.py`, or `scripts/deepseek_worker.py`",
        _concat_text(
            'Inspect job metadata, result summary, diff stat, and changed files before',
            ' any raw transcripts',
        ),
        "For worker-assisted artifact-first passes, inspect in order",
        "`git diff --stat`",
        "If this run used script workers, include artifact-first fields in the handoff:",
        "The handoff omits required artifact-first review fields from the worker output.",
        "before any raw transcripts",
    ]

    for term in required_terms:
        assert term in normalized


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
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-codex-review-request.md"
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
            'Does the handoff include job metadata, result summary, diff stat, changed',
            ' files, and test output?',
        ),
        _concat_text(
            'Confirm artifact-first handoff evidence is complete: job metadata, result',
            ' summary, diff stat, changed files, and test output.',
        ),
    ]

    for term in required_terms:
        assert term in normalized


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
    doc_path = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "opencode-desktop-handoff.md"
    )
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
            '`uv run python scripts/opencode_readiness.py --mode implementation',
            ' --require-clean --format json`',
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
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "opencode-desktop-one-shot.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
                'uv run python scripts/opencode_readiness.py --mode implementation',
                ' --require-clean --format json',
            )
        ),
        "scripts/context_pack.sh --mode implementation --manifest",
        (
            _concat_text(
                'uv run python scripts/pr_body_check.py --body-file <body.md>',
                ' --require-opencode-evidence',
                ' --issue <issue-number> --issue-metadata-file <issue.json>',
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

    assert (
        "| [OpenCode Desktop one-shot](opencode-desktop-one-shot.md) |"
        in readme
    )


def test_prompt_library_includes_prompt_selection_matrix() -> None:
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "codex-persistent-marathon.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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


def test_model_comparison_trial_documents_deepseek_cost_example() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "model-comparison-trial.md"
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
            'context-pack estimated tokens: `<manifest-estimated-tokens>` from',
            ' `scripts/context_pack.sh --mode implementation --manifest`',
        ),
        _concat_text(
            'context-pack bytes: `<manifest-context-bytes>` from',
            ' `scripts/context_pack.sh --mode implementation --manifest`',
        ),
        "commands run:",
        "git pull --ff-only",
        "scripts/context_pack.sh --mode implementation --manifest",
        "scripts/factory_metrics.py report --format json",
        _concat_text(
            'scripts/factory_metrics.py report --format md --output',
            ' .entroping/factory-metrics/factory-report.md',
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
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "model-output-acceptance-gate.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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
                'uv run python scripts/pr_body_check.py --body-file <body.md>',
                ' --require-opencode-evidence',
                ' --issue <issue>',
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

    assert (
        "| [Model-output acceptance gate](model-output-acceptance-gate.md) |"
        in readme
    )


def test_prompt_library_includes_after_sleep_status_prompt() -> None:
    prompt = (
        REPO_ROOT
        / "docs"
        / "meta"
        / "prompt-library"
        / "after-sleep-status.md"
    ).read_text(encoding="utf-8")
    readme = (
        REPO_ROOT / "docs" / "meta" / "prompt-library" / "README.md"
    ).read_text(encoding="utf-8")
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

    work_steps = prompt.split("Then:", maxsplit=1)[1].split(
        "## Reference Prompts", maxsplit=1
    )[0]
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
            _concat_text(
                'Do not claim launch, stable-core, package-index, enterprise, security, or',
                ' adoption readiness',
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
            _concat_text(
                'Codex owns factory design, Tier B/Tier C integration, and merge readiness',
                ' for sensitive lanes.',
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
    doc = (REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    required_terms = [
        "## Autonomous OpenCode Shipping Lanes",
        "Tier A autonomous lane",
        "low-risk docs, tests, guard tests, prompt-library maintenance, and non-runtime scripts",
        (
            _concat_text(
                'may implement, push, open a PR, wait for GitHub CI, merge, and run',
                ' `scripts/finish_issue.sh` without Codex',
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


def test_agents_md_allows_only_documented_tier_a_autonomy() -> None:
    doc = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    required_terms = [
        "OpenCode/DeepSeek may independently implement and merge only Tier A autonomous lanes",
        "Tier B and Tier C remain human/Codex-reviewed",
        (
            _concat_text(
                'Do not let any unattended agent push to `main` outside a documented Tier A',
                ' autonomous lane',
            )
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
            _concat_text(
                'Tier C runtime, Hurl, redaction, proxy, provider-boundary, release,',
                ' architecture, secrets, security, and audit-evidence work must never merge',
                ' autonomously',
            )
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


def test_unattended_opencode_isolation_decision_and_control_plane_are_indexed() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    tds = (REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(
        encoding="utf-8"
    )
    registry = (REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml").read_text(
        encoding="utf-8"
    )
    adr = (
        REPO_ROOT / "decisions" / "ADR-0027-opencode-unattended-isolation.md"
    ).read_text(encoding="utf-8")
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
            'scripts/factory_metrics.py report --format md --output',
            ' .entroping/factory-metrics/factory-report.md',
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
    assert "unattended runs do not inherit host agents, plugins, MCP servers" in (
        normalized
    )
    assert "Interactive maintainer sessions remain a separate surface" in normalized
    assert "`OPENCODE_DISABLE_PROJECT_CONFIG=1`" in doc
    assert "`--pure debug config`" in doc


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
        "CLI's default engine remains OpenCode",
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


def test_vault_index_marks_archival_context_and_active_decisions() -> None:
    index = (REPO_ROOT / "docs" / "meta" / "VAULT_INDEX.md").read_text(encoding="utf-8")
    zero_config = (
        REPO_ROOT / "docs" / "meta" / "ZERO_CONFIG_DEMO_ENTRYPOINT.md"
    ).read_text(encoding="utf-8")

    assert "historical source evidence, not current product truth" in index
    assert "Archived Decision Notes" in index
    assert "status: active" in zero_config
    assert "Current Outcome" in zero_config
    assert "entroping demo --project <path>" in zero_config


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


def test_context_management_records_retired_context_tool_boundary() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(doc.split())

    assert "Issue #712's full trial" in doc
    assert "Issue #724 converts that evidence into cleanup" in doc
    assert "Retired generated context tooling is not part of active agent workflow" in doc
    assert "Remove retired generated context tooling from active workflow" in doc
    assert (
        "ordinary contributors must not be required to install external graph"
        in normalized
    )
    assert (
        "Agents should use `rg`, source reads, tests, and measured factory metrics"
        in normalized
    )


def test_context_management_does_not_frame_graph_tools_as_rehydration_path() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "CONTEXT_MANAGEMENT.md").read_text(
        encoding="utf-8"
    )
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
                'Optional graph, wiki, comprehension, or compression tooling is not part of',
                ' normal rehydration',
            )
        ),
        "must earn promotion through measured scorecard evidence",
        (
            _concat_text(
                'Keep curated Markdown, source links, ADR pointers, and lessons accurate',
                ' before adding generated or model-authored summaries',
            )
        ),
        (
            _concat_text(
                'not active in this Codex session without a restart; generated graph output',
                ' remains outside active workflow',
            )
        ),
    ]
    for term in required_terms:
        assert term in normalized


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
            _concat_text(
                'GitHub Issues, PRs, CI, source files, tests, ADRs, the decision registry,',
                ' and QAnstitution/Hurl evidence remain the source-of-truth layer',
            )
        ),
        "Obsidian, the LLM wiki, and curated source exports are the memory layer",
        (
            'Retired generated context tooling is not part of active agent workflow'
        ),
        "Understand Anything remains optional for human comprehension",
        (
            _concat_text(
                'must not hide exact diffs, failing test output, security findings, audit',
                ' evidence, or secrets-sensitive material',
            )
        ),
        (
            _concat_text(
                '`entroping run` remains deterministic, Hurl-based, QAnstitution-governed,',
                ' and provider-free',
            )
        ),
        (
            _concat_text(
                'Codex remains the factory architect and Tier B/Tier C merge owner, while',
                ' Tier A autonomous workers can merge only under the documented shipping',
                ' lanes',
            )
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
        "Phase 2 - curated Markdown and LLM-wiki style source maps",
        "Phase 3 - Understand Anything for human comprehension and onboarding",
        "Phase 4 - bounded cheap, Chinese, and local model workers behind Codex-owned validation",
        (
            _concat_text(
                'Do not advance a layer until the previous layer has a documented owner,',
                ' ignored generated-output path, and reviewable promotion path',
            )
        ),
        (
            _concat_text(
                'No rollout layer may require ordinary contributors to install graph, wiki,',
                ' compression, or model-worker tooling',
            )
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
        "`llm-wiki-out/`",
        "`understand-anything-out/`",
        (
            _concat_text(
                'Generated context outputs must remain ignored/local unless intentionally',
                ' promoted into curated Markdown',
            )
        ),
        (
            _concat_text(
                'Do not delete, archive, or rewrite context-preservation material just',
                ' because generated output is noisy',
            )
        ),
        (
            _concat_text(
                'ordinary contributors must not be required to install external graph,',
                ' compression, Obsidian plugin, LLM wiki, or comprehension tools',
            )
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_unproven_context_tools_are_not_active_agent_dependencies() -> None:
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
        "Retired generated context tooling is not part of active agent workflow",
        (
            _concat_text(
                'Do not route normal Codex, OpenCode, DeepSeek, or Spark sessions through',
                ' external context tools',
            )
        ),
        (
            _concat_text(
                'Use `rg`, `scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`,',
                ' GitHub issues, source files, tests, and CI first',
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
        "## Repo-Native Context Budget Baseline",
        "Context is evidence, not memory",
        (
            _concat_text(
                'Start each issue with one named question: what local evidence is needed to',
                ' change, review, or merge this issue?',
            )
        ),
        (
            _concat_text(
                '`rg`, `scripts/context_pack.sh`, `docs/meta/DECISION_REGISTRY.yaml`,',
                ' GitHub issues, source files, focused tests, CI, and',
                ' `scripts/factory_metrics.py report` are the active context-cost baseline',
            )
        ),
        (
            _concat_text(
                'Do not add generated context because it is interesting, visual, popular,',
                ' or already installed',
            )
        ),
        (
            _concat_text(
                'Load extra context only when it answers the named issue question and',
                ' records an evidence pointer',
            )
        ),
        (
            _concat_text(
                'Use `scripts/context_pack.sh --record-factory-metrics` and',
                ' `scripts/factory_metrics.py report` when token or cost claims matter',
            )
        ),
        (
            _concat_text(
                'No token-saving claim is accepted without measured local evidence from the',
                ' current workflow lane',
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
        _concat_text(
            'Product Manager, Architect, Dev Agent, QA Agent, Code Review Agent,',
            ' Security Agent, Monitoring Agent, and Integrator',
        ),
        "Codex, Claude Code, OpenCode, DeepSeek, Gemini, Spark, and local models",
        _concat_text(
            'must not store raw prompts, provider transcripts, secrets, raw traffic, or',
            ' product runtime evidence',
        ),
        _concat_text(
            'The factory framework owns workflow, context, metrics, and guardrails; the',
            ' project owns product truth.',
        ),
    ]

    for term in required_terms:
        assert term in combined


def test_agent_control_plane_inventories_factory_template_primitives() -> None:
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(control_plane.split())

    required_terms = [
        "## Factory Template Extraction Inventory",
        "Workflow primitives to evaluate for extraction",
        "candidates for extraction after proof",
        "issue templates",
        "`scripts/start_issue.sh` and `scripts/finish_issue.sh`",
        _concat_text(
            '`scripts/check.sh`, `scripts/feature_gate.sh`, `scripts/regression.sh`,',
            ' and `scripts/audit_quality.sh`',
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

    section = control_plane.split("## Factory Template Extraction Inventory", maxsplit=1)[
        1
    ].split("## Autonomous OpenCode Shipping Lanes", maxsplit=1)[0]
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
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
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
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
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
    control_plane = (
        REPO_ROOT / "docs" / "meta" / "AGENT_CONTROL_PLANE.md"
    ).read_text(encoding="utf-8")
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
        "scripts/context_pack.sh --mode implementation --manifest",
        "needed files/snippets",
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
        "Retired generated context tooling is not part of active Entroping agent workflow",
        "Do not route normal OpenCode work through external context tools",
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
