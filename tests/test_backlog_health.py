"""Backlog health guard for issue marathons."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "script_safety.py"


SCRIPT = REPO_ROOT / "scripts" / "backlog_health.py"


def load_backlog_health_module() -> Any:
    scripts_root = SCRIPT.parent
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    spec = importlib.util.spec_from_file_location("backlog_health", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_backlog_health(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        env=env,
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
                },
                {
                    "number": 281,
                    "title": "factory: string label compatibility fixture",
                    "url": "https://github.com/sakibshuvo/Entroping/issues/281",
                    "labels": ["type:bug", "priority:p3", "status:blocked"],
                    "milestone": {"title": "v0.4.0-alpha integrations"},
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 0, result.stderr
    assert "Backlog health OK" in result.stdout
    assert "issues checked: 2" in result.stdout


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


def test_backlog_health_reports_malformed_input_without_traceback(tmp_path: Path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text("{not json", encoding="utf-8")

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert "invalid issue JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_backlog_health_reports_non_utf8_input_without_traceback(tmp_path: Path) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_bytes(b"\xff\xfe")

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert "issue JSON file is not valid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        ({"issues": []}, "issue payload must be a list"),
        (["not an issue object"], "issue payload item 0 must be an object"),
    ),
)
def test_backlog_health_reports_invalid_issue_payload_shape_without_traceback(
    tmp_path: Path,
    payload: object,
    expected: str,
) -> None:
    fixture = tmp_path / "issues.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    result = run_backlog_health("--input", str(fixture))

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert expected in result.stderr
    assert "Traceback" not in result.stderr


def test_backlog_health_reports_malformed_github_cli_json_without_traceback(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    fake_gh.write_text("#!/bin/sh\nprintf '{not json'\n", encoding="utf-8")
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    result = run_backlog_health("--repo", "sakibshuvo/Entroping", env=env)

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert "gh issue list returned invalid JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_backlog_health_reports_github_cli_failure_without_traceback(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    fake_gh.write_text("#!/bin/sh\necho 'auth failed' >&2\nexit 1\n", encoding="utf-8")
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    result = run_backlog_health("--repo", "sakibshuvo/Entroping", env=env)

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert "gh issue list failed: auth failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_backlog_health_reports_nonpositive_limit_without_traceback() -> None:
    result = run_backlog_health("--limit", "0")

    assert result.returncode == 1
    assert "Backlog health check failed:" in result.stderr
    assert "--limit must be greater than zero" in result.stderr
    assert "Traceback" not in result.stderr


def test_backlog_health_converts_github_cli_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_backlog_health_module()

    def raise_timeout(*_args: object, **_kwargs: object) -> NoReturn:
        raise module.ScriptSafetyError("command timed out after 30 seconds: gh")

    monkeypatch.setattr(module, "run_subprocess", raise_timeout)

    with pytest.raises(ValueError, match="gh issue list timed out after 30 seconds"):
        module._load_issues_from_gh(repo="sakibshuvo/Entroping", limit=200)


def test_backlog_health_decodes_github_cli_output_as_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_backlog_health_module()
    captured_kwargs: dict[str, object] = {}

    def complete(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_kwargs["args"] = args
        captured_kwargs.update(kwargs)
        command = args
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(module, "run_subprocess", complete)

    assert module._load_issues_from_gh(repo="sakibshuvo/Entroping", limit=200) == []
    assert captured_kwargs["args"] == [
        "gh",
        "issue",
        "list",
        "--repo",
        "sakibshuvo/Entroping",
        "--state",
        "all",
        "--limit",
        "200",
        "--json",
        "number,title,url,state,labels,milestone",
    ]


def test_backlog_health_help_documents_github_cli_mode() -> None:
    result = run_backlog_health("--help")

    assert result.returncode == 0
    assert "gh issue list" in result.stdout
    assert "--input" in result.stdout


def test_backlog_health_reports_closed_active_state_and_registered_worktree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    worktree = tmp_path / "Entroping-issue-302"
    subprocess.run(
        ["git", "worktree", "add", str(worktree), "-b", "feat/closed-302"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    fixture = tmp_path / "issues.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "number": 301,
                    "title": "closed active status",
                    "state": "CLOSED",
                    "labels": [
                        {"name": "type:bug"},
                        {"name": "priority:p2"},
                        {"name": "status:ready"},
                    ],
                    "milestone": {"title": "milestone"},
                },
                {
                    "number": 302,
                    "title": "closed retained worktree",
                    "state": "CLOSED",
                    "labels": [
                        {"name": "type:bug"},
                        {"name": "priority:p2"},
                        {"name": "status:blocked"},
                    ],
                    "milestone": {"title": "milestone"},
                },
            ]
        ),
        encoding="utf-8",
    )

    result = run_backlog_health(
        "--input",
        str(fixture),
        "--repo-root",
        str(repo),
    )

    assert result.returncode == 1
    assert result.stderr.splitlines() == [
        "Backlog health failed:",
        "  #301: closed issue retains active status label: status:ready",
        "  #302: closed issue retains registered issue worktree",
    ]
