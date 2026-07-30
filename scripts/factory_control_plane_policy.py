#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Final

AUTONOMY_LABEL_TIERS: Final[dict[str, str]] = {
    "autonomy:tier-a": "Tier A autonomous lane",
    "autonomy:tier-b": "Tier B assisted lane",
    "autonomy:tier-c": "Tier C restricted lane",
}

_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:/")
_PROTECTED_SURFACES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "budget-governor",
        (
            "scripts/factory_budget_ledger*.py",
            "scripts/factory_cost_policy*.py",
            "scripts/update_factory_cost_policy_schema.py",
            "tests/test_factory_budget_ledger*.py",
            "tests/test_factory_cost_policy*.py",
            "docs/meta/FACTORY_COST_POLICY*",
            "docs/meta/factory-cost-policy*.json",
        ),
    ),
    (
        "provider-routing",
        (
            "scripts/provider_capability_*.py",
            "scripts/update_provider_capability_schema.py",
            "scripts/opencode_*.py",
            "scripts/deepseek_*.py",
            "tests/test_provider_capability_*.py",
            "tests/test_opencode_*.py",
            "tests/test_deepseek_*.py",
            "docs/meta/provider-capability-registry*",
        ),
    ),
    (
        "factory-scheduler",
        (
            "scripts/factory_scheduler*.py",
            "scripts/factoryctl.py",
            "scripts/factory_issue_selector*.py",
            "scripts/ai_jobs.py",
            "scripts/ai_job_*.py",
            "scripts/ai_job_*/*",
            "scripts/factory_tick_runner.py",
            "tests/test_ai_jobs*.py",
            "tests/test_ai_job_*.py",
            "tests/test_factory_tick_runner.py",
            "tests/test_factory_scheduler*.py",
            "tests/test_factoryctl.py",
            "tests/test_factory_issue_selector*.py",
        ),
    ),
    (
        "repository-authority",
        (
            "AGENTS.md",
            ".git*",
            ".git/*",
            ".github/*",
            ".entroping/*",
            "decisions/*",
            "pyproject.toml",
            "uv.lock",
            "package*.json",
            "prompts/*",
            "site/package*.json",
            "scripts/architecture_integrity.sh",
            "scripts/agent_toolchain.py",
            "scripts/ai_artifact_hygiene.py",
            "scripts/*gate*.py",
            "scripts/*gate*.sh",
            "scripts/audit_quality.sh",
            "scripts/backlog_health.py",
            "scripts/bounded_process.py",
            "scripts/check.sh",
            "scripts/context_pack.sh",
            "scripts/doc_governance_check.sh",
            "scripts/factory_control_plane_policy.py",
            "scripts/factory_*.py",
            "scripts/factory_*/*",
            "scripts/feature_gate.sh",
            "scripts/finish_issue.sh",
            "scripts/launch_readiness.py",
            "scripts/pr_body_check.py",
            "scripts/regression.sh",
            "scripts/repo_hygiene.sh",
            "scripts/script_safety.py",
            "scripts/start_issue.sh",
            "tests/test_agent_workflow_docs.py",
            "tests/test_architecture_*.py",
            "tests/test_*gate*.py",
            "tests/test_ci_workflow.py",
            "tests/test_doc_governance_script.py",
            "tests/test_factory_control_plane_policy.py",
            "tests/test_factory_*.py",
            "tests/test_pr_body_provider_registry.py",
            "docs/meta/AGENT_CONTROL_PLANE.md",
            "docs/meta/AGENT_ROLE_REGISTRY.yaml",
            "docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md",
            "docs/meta/CONTEXT_MANAGEMENT.md",
            "docs/meta/DECISION_REGISTRY.yaml",
            "docs/meta/DOCS_GOVERNANCE.md",
            "docs/meta/FACTORY_OPERATIONS.md",
            "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
            "docs/meta/prompt-library/*",
            "docs/technical/TDS.md",
        ),
    ),
    (
        "runtime-security",
        (
            "src/entroping/brain/*",
            "src/entroping/bridge/traffic_*",
            "src/entroping/cli/report.py",
            "src/entroping/cli/run.py",
            "src/entroping/core/hurl_runner.py",
            "src/entroping/core/litellm_client.py",
            "src/entroping/core/redaction*.py",
            "src/entroping/core/report_writer.py",
            "src/entroping/core/run_workflow.py",
            "src/entroping/eye/*",
            "src/entroping/reports/*",
            "tests/test_brain_*.py",
            "tests/test_capture*.py",
            "tests/test_cli_run_command.py",
            "tests/test_hurl_runner.py",
            "tests/test_litellm_client.py",
            "tests/test_report*.py",
            "tests/test_run_workflow*.py",
            "tests/test_traffic*.py",
        ),
    ),
    (
        "credential-boundary",
        (
            "SECURITY.md",
            "scripts/ai_worker_file_safety.py",
            "tests/test_ai_worker_file_safety.py",
            ".env*",
            "*.env",
            "*.pem",
            "*.key",
            "*secret*",
            "*credential*",
        ),
    ),
)


def normalize_repo_path(raw_path: str) -> str | None:
    candidate = raw_path.strip().replace("\\", "/")
    if (
        not candidate
        or candidate.startswith("/")
        or candidate.startswith("//")
        or _WINDOWS_ABSOLUTE_RE.match(candidate)
        or any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in candidate)
    ):
        return None
    parts = candidate.split("/")
    if any(part == ".." for part in parts):
        return None
    normalized_parts = [part for part in parts if part not in ("", ".")]
    if not normalized_parts:
        return None
    return PurePosixPath(*normalized_parts).as_posix()


def protected_surface_reason(
    raw_path: str,
    *,
    repo_root: Path | None = None,
) -> str | None:
    normalized = normalize_repo_path(raw_path)
    if normalized is None:
        return "invalid-path"
    if repo_root is not None and _has_symlink_component(repo_root, normalized):
        return "symlink-path"
    folded = normalized.casefold()
    for reason, patterns in _PROTECTED_SURFACES:
        if any(fnmatch.fnmatchcase(folded, pattern.casefold()) for pattern in patterns):
            return reason
    return None


def protected_paths(
    paths: Iterable[str],
    *,
    repo_root: Path | None = None,
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for raw_path in paths:
        reason = protected_surface_reason(raw_path, repo_root=repo_root)
        if reason is not None:
            normalized = normalize_repo_path(raw_path) or raw_path
            violations.append((normalized, reason))
    return list(dict.fromkeys(violations))


def autonomy_tier_from_labels(labels: object) -> str:
    if not isinstance(labels, list):
        raise ValueError("trusted issue metadata must include exactly one autonomy label")
    matched: list[str] = []
    for label in labels:
        name = _label_name(label)
        if name is not None:
            tier = AUTONOMY_LABEL_TIERS.get(name.casefold())
            if tier is not None:
                matched.append(tier)
    if len(matched) != 1:
        raise ValueError("trusted issue metadata must include exactly one autonomy label")
    return matched[0]


def _label_name(label: object) -> str | None:
    if isinstance(label, str):
        return label
    if not isinstance(label, dict):
        return None
    name = label.get("name")
    return name if isinstance(name, str) else None


def _has_symlink_component(repo_root: Path, relative_path: str) -> bool:
    candidate = repo_root
    for component in PurePosixPath(relative_path).parts:
        candidate /= component
        if candidate.is_symlink():
            return True
    return False
