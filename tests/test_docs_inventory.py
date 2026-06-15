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


def test_docs_inventory_markdown_output_lists_budget_and_each_file() -> None:
    result = run_docs_inventory("--format", "md")

    assert result.returncode == 0, result.stderr
    assert "# Documentation Inventory" in result.stdout
    assert "Default agent context budget" in result.stdout
    assert "| `AGENTS.md` | active | agent-rules | maintainer | yes |" in result.stdout
    assert "| `README.md` | reference | root | public | no |" in result.stdout


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
