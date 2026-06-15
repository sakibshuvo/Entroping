"""Guardrails for Markdown inventory and active context budgets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "docs_inventory.py"
DOC_GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "doc_governance_check.sh"


def run_docs_inventory(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_docs_inventory_json_reports_current_repo_tiers_and_budget() -> None:
    result = run_docs_inventory("--format", "json", "--strict")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema"] == "entroping.docs-inventory.v1"
    assert report["summary"]["total_markdown_files"] >= 100
    assert report["summary"]["default_agent_context_count"] <= 5
    assert report["summary"]["llm_wiki_active_count"] == 0
    assert report["summary"]["duplicate_active_title_count"] == 0

    files = {entry["path"]: entry for entry in report["files"]}
    assert files["AGENTS.md"]["tier"] == "active"
    assert files["AGENTS.md"]["default_agent_context"] is True
    assert files["AGENTS.md"]["owner"] == "agent-rules"
    assert files["docs/meta/PROJECT_PROGRESS.md"]["default_agent_context"] is True
    assert files[".context/plan.md"]["default_agent_context"] is True
    assert files["README.md"]["tier"] == "reference"
    assert files["README.md"]["default_agent_context"] is False
    assert files["docs/meta/VAULT_INDEX.md"]["tier"] == "reference"
    assert files["docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md"]["tier"] == "archive"
    assert files["docs/meta/prompt-library/issue-worker.md"]["owner"] == "prompt-library"
    assert isinstance(report["prune_candidates"], list)
    assert "by_prune_candidate_category" in report["summary"]


def test_docs_inventory_markdown_output_lists_budget_and_each_file() -> None:
    result = run_docs_inventory("--format", "md")

    assert result.returncode == 0, result.stderr
    assert "# Documentation Inventory" in result.stdout
    assert "Default agent context budget" in result.stdout
    assert "## Prune Candidates" in result.stdout
    assert "| `AGENTS.md` | active | agent-rules | maintainer | yes |" in result.stdout
    assert "| `README.md` | reference | root | public | no |" in result.stdout


def test_docs_inventory_reports_non_destructive_prune_candidates(
    tmp_path: Path,
) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / "docs" / "meta" / "archive").mkdir(parents=True)
    (tmp_path / "docs" / "product").mkdir(parents=True)
    (tmp_path / "sources").mkdir()
    (tmp_path / "AGENTS.md").write_text(
        "# Agent Rules\n\nLLM wiki should not be in active context.\n",
        encoding="utf-8",
    )
    (tmp_path / ".context" / "plan.md").write_text("# Active Plan\n", encoding="utf-8")
    (tmp_path / "docs" / "meta" / "PROJECT_PROGRESS.md").write_text(
        "# Project Progress\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md").write_text(
        "# Feature Delivery Checklist\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Shared Title\n", encoding="utf-8")
    (tmp_path / "docs" / "product" / "duplicate.md").write_text(
        "# Shared Title\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "without-frontmatter.md").write_text(
        "# Meta Without Frontmatter\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "archive" / "old.md").write_text(
        "---\ntitle: Old Note\ntype: note\nstatus: archived\n---\n# Old Note\n",
        encoding="utf-8",
    )
    (tmp_path / "sources" / "source-map.md").write_text(
        "# Source Map\n",
        encoding="utf-8",
    )

    result = run_docs_inventory("--root", str(tmp_path), "--format", "json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    candidates = {
        (candidate["path"], candidate["category"]): candidate
        for candidate in report["prune_candidates"]
    }

    active_risk = candidates[("AGENTS.md", "default-agent-risk")]
    assert active_risk["action"] == "review-default-agent-context"
    assert "default agent context" in active_risk["reason"]
    assert active_risk["evidence_paths"] == ["AGENTS.md"]

    stale_reference = candidates[
        ("docs/meta/without-frontmatter.md", "stale-reference")
    ]
    assert stale_reference["action"] == "review-for-archive-or-canonical-update"
    assert "canonical docs" in stale_reference["reason"]
    assert "docs/meta/DOCS_GOVERNANCE.md" in stale_reference["evidence_paths"]

    archive_candidate = candidates[("docs/meta/archive/old.md", "archive-reference")]
    assert archive_candidate["action"] == "keep-out-of-default-context"
    assert "archive/source status" in archive_candidate["reason"]

    source_candidate = candidates[("sources/source-map.md", "archive-reference")]
    assert "archive/source status" in source_candidate["reason"]

    duplicate_candidate = candidates[
        ("docs/product/duplicate.md", "duplicate-title")
    ]
    assert duplicate_candidate["action"] == "review-duplicate-title"
    assert "canonical docs" in duplicate_candidate["reason"]
    assert duplicate_candidate["evidence_paths"] == ["README.md"]

    assert report["summary"]["by_prune_candidate_category"]["archive-reference"] == 2
    assert all(candidate["action"] != "delete" for candidate in report["prune_candidates"])


def test_docs_inventory_docs_index_public_audience_is_exact(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md-extra.md").write_text(
        "# Not The Public Index\n",
        encoding="utf-8",
    )

    result = run_docs_inventory("--root", str(tmp_path), "--format", "json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    files = {entry["path"]: entry for entry in report["files"]}
    assert files["docs/index.md-extra.md"]["audience"] == "maintainer"


def test_docs_inventory_strict_rejects_missing_default_context(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    result = run_docs_inventory("--root", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "missing default agent context path" in result.stderr
    assert "AGENTS.md" in result.stderr


def test_docs_inventory_strict_rejects_duplicate_active_titles(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("# Duplicate\n", encoding="utf-8")
    (tmp_path / ".context" / "plan.md").write_text("# Duplicate\n", encoding="utf-8")
    (tmp_path / "docs" / "meta" / "PROJECT_PROGRESS.md").write_text(
        "# Project Progress\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md").write_text(
        "# Feature Delivery Checklist\n",
        encoding="utf-8",
    )

    result = run_docs_inventory("--root", str(tmp_path), "--strict")

    assert result.returncode == 1
    assert "duplicate active Markdown title" in result.stderr
    assert "Duplicate" in result.stderr


def test_docs_inventory_is_part_of_documentation_governance() -> None:
    doc_governance = DOC_GOVERNANCE_SCRIPT.read_text(encoding="utf-8")

    assert "scripts/docs_inventory.py" in doc_governance
