"""Frozen issue-lifecycle documentation contracts."""

import re

import yaml
from agent_workflow_test_helpers import REPO_ROOT
from agent_workflow_test_helpers import concat_text as _concat_text


def test_backlog_triage_prompt_requires_status_ready_open_code_fields() -> None:
    prompt = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "backlog-triage.md").read_text(
        encoding="utf-8"
    )
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
        "User-Evidence Metadata Contract": REPO_ROOT / "docs" / "meta" / "ISSUE_TRACKING.md",
        "GitHub User-Evidence Metadata": REPO_ROOT / "docs" / "meta" / "DOWNSTREAM_FEEDBACK_KIT.md",
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
                "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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

    issue_tracking = documents["User-Evidence Metadata Contract"].read_text(encoding="utf-8")
    normalized_issue_tracking = " ".join(issue_tracking.split())
    assert "exactly one YAML block" in normalized_issue_tracking
    assert "unknown or repeated fields are invalid" in normalized_issue_tracking
    assert "selector safety boundary implemented by issue #1567" in (normalized_issue_tracking)
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
    assert "Later GitHub label edits do not rewrite the snapshot" in (normalized_issue_tracking)
    assert "must not change selection" in normalized_issue_tracking


def test_agent_workflow_docs_document_verification_lanes() -> None:
    pr_template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    checklist = (REPO_ROOT / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md").read_text(
        encoding="utf-8"
    )
    issue_worker = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
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


def test_issue_worker_prompt_enforces_artifact_first_handoff_contract() -> None:
    issue_worker = (REPO_ROOT / "docs" / "meta" / "prompt-library" / "issue-worker.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(issue_worker.split())

    required_terms = [
        "For repeatable hands-off runs, use the artifact scripts:",
        "`scripts/ai_jobs.py`, `scripts/opencode_worker.py`, or `scripts/deepseek_worker.py`",
        _concat_text(
            "Inspect job metadata, result summary, diff stat, and changed files before",
            " any raw transcripts",
        ),
        "For worker-assisted artifact-first passes, inspect in order",
        "`git diff --stat`",
        "If this run used script workers, include artifact-first fields in the handoff:",
        "The handoff omits required artifact-first review fields from the worker output.",
        "before any raw transcripts",
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
                "Do not let any unattended agent push to `main` outside a documented Tier A",
                " autonomous lane",
            )
        ),
    ]

    for term in required_terms:
        assert term in normalized


def test_public_repo_surface_classifies_ai_workers_as_maintainer_only() -> None:
    doc = (REPO_ROOT / "docs" / "meta" / "PUBLIC_REPO_SURFACE.md").read_text(encoding="utf-8")
    normalized = " ".join(doc.split())

    assert "scripts/ai_jobs.py" in doc
    assert "scripts/opencode_worker.py" in doc
    assert "scripts/deepseek_worker.py" in doc
    assert "Maintainer-only AI worker tooling" in doc
    assert "not product APIs, user commands, or automatic patch applicators" in doc
    assert "do not change Entroping's user-facing CLI or product provider boundary" in normalized


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
    walkthrough_path = REPO_ROOT / "docs" / "meta" / "GOOD_FIRST_ISSUE_WALKTHROUGH.md"
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


def test_pull_request_template_requires_agent_autonomy_declaration() -> None:
    template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
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
