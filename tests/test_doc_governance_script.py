"""Tests for executable documentation governance."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "doc_governance_check.sh"
PR_BODY_SCRIPT = REPO_ROOT / "scripts" / "pr_body_check.py"


def test_doc_governance_help_documents_control_plane() -> None:
    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "documentation control plane" in result.stdout
    assert "ROADMAP.md" in result.stdout
    assert "Documentation Impact Declaration" in result.stdout


def test_doc_governance_passes_current_repo() -> None:
    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Documentation governance OK" in result.stdout


def test_doc_governance_rejects_missing_required_marker(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / ".github").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "README.md").write_text("README without roadmap link\n", encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    (tmp_path / "00_INDEX.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / ".github" / "pull_request_template.md").write_text(
        "## Summary\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "feature_gate.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "docs" / "meta" / "FEATURE_DELIVERY_CHECKLIST.md").write_text(
        "# Checklist\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "meta" / "PROJECT_PROGRESS.md").write_text(
        "# Progress\n",
        encoding="utf-8",
    )
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "changelog.md").write_text("# Changelog\n", encoding="utf-8")

    result = subprocess.run(
        [str(DOC_GOVERNANCE_SCRIPT), "--root", str(tmp_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Documentation governance failed" in result.stderr
    assert "README.md" in result.stderr


def test_pr_body_check_accepts_documentation_impact_declaration(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "## Summary\n"
                        "Change\n\n"
                        "## Documentation Impact Declaration\n\n"
                        "- [x] Roadmap/progress updated: ROADMAP.md and PROJECT_PROGRESS.md\n"
                        "- [ ] No docs update needed. Reason:\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(PR_BODY_SCRIPT), str(event_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PR documentation impact declaration OK" in result.stdout


def test_pr_body_check_rejects_missing_declaration(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"body": "## Summary\nOnly summary"}}))

    result = subprocess.run(
        [str(PR_BODY_SCRIPT), str(event_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Documentation Impact Declaration" in result.stderr


def test_pr_body_check_skips_non_pr_events(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")

    result = subprocess.run(
        [str(PR_BODY_SCRIPT), str(event_path)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "No pull request payload" in result.stdout
