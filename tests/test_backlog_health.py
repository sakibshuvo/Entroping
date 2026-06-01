"""Backlog health guard for issue marathons."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "backlog_health.py"


def run_backlog_health(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_backlog_health_accepts_well_labeled_issue_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "number": 279,
                    "title": "report: add effective QAnstitution policy evidence",
                    "url": "https://github.com/sakibshuvo/Entroping/issues/279",
                    "labels": [
                        {"name": "type:feature"},
                        {"name": "priority:medium"},
                        {"name": "status:in-progress"},
                    ],
                    "milestone": {"title": "v0.4.0-alpha integrations"},
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 0, result.stderr
    assert "Backlog health OK" in result.stdout
    assert "issues checked: 1" in result.stdout


def test_backlog_health_rejects_untriaged_issue_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "number": 280,
                    "title": "missing labels",
                    "url": "https://github.com/sakibshuvo/Entroping/issues/280",
                    "labels": [{"name": "type:feature"}],
                    "milestone": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 1
    assert "Backlog health failed" in result.stderr
    assert "#280: missing status:* label" in result.stderr
    assert "#280: missing priority:* label" in result.stderr
    assert "#280: missing milestone" in result.stderr


def test_backlog_health_help_documents_github_cli_mode() -> None:
    result = run_backlog_health("--help")

    assert result.returncode == 0
    assert "gh issue list" in result.stdout
    assert "--input" in result.stdout
