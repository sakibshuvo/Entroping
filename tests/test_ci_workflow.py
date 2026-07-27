"""Regression tests for GitHub Actions workflow coverage."""

import os
import re
import subprocess
from pathlib import Path

import yaml

_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_SCORECARD_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "scorecard.yml"
)
_CODEQL_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "codeql.yml"
)
_PERFORMANCE_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "performance-smoke.yml"
)
_REPO_ROOT = Path(__file__).resolve().parents[1]

_CHECKOUT_PIN = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
_SETUP_PYTHON_PIN = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
_SETUP_UV_PIN = "astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39"
_SETUP_NODE_PIN = "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020"
_UPLOAD_ARTIFACT_PIN = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
_SCORECARD_PIN = "ossf/scorecard-action@4eaacf0543bb3f2c246792bd56e8cdeffafb205a"
_CODEQL_ACTION_PIN = "github/codeql-action/{action}@54f647b7e1bb85c95cddabcd46b0c578ec92bc1a"
_TAG_STYLE_ACTION_REF_RE = re.compile(r"uses:\s*[^@\s]+@(?:v[0-9]|release/|[0-9]+\.)")



def _run_git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _ci_pr_body_check_run_block() -> str:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["checks"]["steps"]:
        if step.get("name") == "Validate PR documentation impact declaration":
            return str(step["run"])
    raise AssertionError("Validate PR documentation impact declaration step not found")


def _write_pr_body_check_stub(repo: Path, args_path: Path) -> None:
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir()
    checker = scripts_dir / "pr_body_check.py"
    checker.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        "pathlib.Path(os.environ['ARGS_PATH']).write_text('\\n'.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    checker.chmod(0o755)
    (repo / "event.json").write_text('{"pull_request": {"body": ""}}', encoding="utf-8")
    args_path.write_text("", encoding="utf-8")


def _run_ci_pr_body_check_step(repo: Path, *, args_path: Path) -> list[str]:
    _write_pr_body_check_stub(repo, args_path)
    env = os.environ.copy()
    env.update(
        {
            "ARGS_PATH": str(args_path),
            "GITHUB_BASE_REF": "main",
            "GITHUB_EVENT_PATH": str(repo / "event.json"),
        },
    )
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _ci_pr_body_check_run_block()],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return args_path.read_text(encoding="utf-8").splitlines()


def test_ci_workflow_runs_on_pull_requests_and_main_pushes_only() -> None:
    workflow = yaml.load(_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert "pull_request" in triggers
    assert triggers["push"] == {"branches": ["main"]}


def test_ci_workflow_declares_minimum_permissions() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert workflow["permissions"] == {"contents": "read"}


def test_codeql_workflow_runs_tracked_code_scanning_with_minimum_permissions() -> None:
    workflow = yaml.load(_CODEQL_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    analyze = workflow["jobs"]["analyze"]
    steps = analyze["steps"]
    step_uses = [step.get("uses") for step in steps]

    assert "pull_request" in triggers
    assert triggers["push"] == {"branches": ["main"]}
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {
        "actions": "read",
        "contents": "read",
        "security-events": "write",
    }
    assert analyze["strategy"]["fail-fast"] == "false"
    assert analyze["strategy"]["matrix"]["language"] == ["python", "actions"]
    assert _CHECKOUT_PIN in step_uses
    assert _CODEQL_ACTION_PIN.format(action="init") in step_uses
    assert _CODEQL_ACTION_PIN.format(action="analyze") in step_uses
    assert steps[0]["with"]["persist-credentials"] == "false"


def test_tracked_workflows_pin_actions_by_commit_sha() -> None:
    failures: list[str] = []

    for workflow_path in sorted((_REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        relative = workflow_path.relative_to(_REPO_ROOT)
        for line_number, line in enumerate(
            workflow_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if _TAG_STYLE_ACTION_REF_RE.search(line):
                failures.append(f"{relative}:{line_number}: {line.strip()}")

    assert failures == []


def test_ci_workflow_enforces_security_and_quality_gates() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    checks = workflow["jobs"]["checks"]
    quality_audit = workflow["jobs"]["quality-audit"]
    checks_run_blocks = "\n".join(str(step.get("run", "")) for step in checks["steps"])
    quality_run_blocks = "\n".join(str(step.get("run", "")) for step in quality_audit["steps"])
    checkout_step = next(
        step
        for step in checks["steps"]
        if step.get("uses") == _CHECKOUT_PIN
    )

    assert checkout_step["with"]["fetch-depth"] == 0
    assert "scripts/regression.sh --security" in checks_run_blocks
    assert 'scripts/pr_body_check.py "$GITHUB_EVENT_PATH"' in checks_run_blocks
    assert "--changed-file" in checks_run_blocks
    assert "git diff --name-only" in checks_run_blocks
    assert "git merge-base" in checks_run_blocks
    assert "--depth=1" not in checks_run_blocks
    assert 'diff_range="origin/$GITHUB_BASE_REF...HEAD"' in checks_run_blocks
    assert 'diff_range="origin/$GITHUB_BASE_REF..HEAD"' in checks_run_blocks
    assert "GITHUB_BASE_REF" in checks_run_blocks
    assert "scripts/regression.sh\n" not in checks_run_blocks
    assert quality_audit["needs"] == "checks"
    assert "scripts/audit_quality.sh" in quality_run_blocks
    assert any(
        step.get("uses") == _UPLOAD_ARTIFACT_PIN
        and step.get("with", {}).get("path") == "reports"
        for step in quality_audit["steps"]
    )


def test_ci_workflow_runs_live_demo_smoke_with_pinned_hurl() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    live_demo = workflow["jobs"]["live-demo-smoke"]
    steps = live_demo["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
    live_demo_env = live_demo["env"]

    assert live_demo["needs"] == "checks"
    assert live_demo_env["HURL_VERSION"] == "8.0.1"
    assert len(live_demo_env["HURL_SHA256"]) == 64
    assert all(character in "0123456789abcdef" for character in live_demo_env["HURL_SHA256"])
    assert "sha256sum \"$archive\"" in run_blocks
    assert "HURL_SHA256" in run_blocks
    assert "download_with_retry()" in run_blocks
    assert "for attempt in 1 2 3" in run_blocks
    assert "sleep $((attempt * 2))" in run_blocks
    assert 'download_with_retry "$base_url/$archive" "$RUNNER_TEMP/$archive"' in run_blocks
    assert 'export PATH="$hurl_bin:$PATH"' in run_blocks
    assert "$archive.sha256" not in run_blocks
    assert "scripts/live_demo_smoke.sh" in run_blocks
    workflow_text = _WORKFLOW_PATH.read_text(encoding="utf-8")
    assert _CHECKOUT_PIN in workflow_text
    assert _SETUP_PYTHON_PIN in workflow_text
    assert _SETUP_UV_PIN in workflow_text
    assert _UPLOAD_ARTIFACT_PIN in workflow_text


def test_ci_pr_body_check_step_handles_shallow_diff_without_merge_base(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    source = tmp_path / "source"
    checkout = tmp_path / "checkout"
    args_path = tmp_path / "args.txt"

    _run_git(["init", "--bare", str(origin)], cwd=tmp_path)
    _run_git(["clone", str(origin), str(source)], cwd=tmp_path)
    _run_git(["config", "user.email", "ci@example.test"], cwd=source)
    _run_git(["config", "user.name", "CI Test"], cwd=source)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(["add", "README.md"], cwd=source)
    _run_git(["commit", "-m", "base"], cwd=source)
    _run_git(["branch", "-M", "main"], cwd=source)
    _run_git(["push", "origin", "main"], cwd=source)
    _run_git(["checkout", "--orphan", "feature"], cwd=source)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    (source / "uv.lock").write_text("dependency update\n", encoding="utf-8")
    _run_git(["add", "README.md", "uv.lock"], cwd=source)
    _run_git(["commit", "-m", "orphan dependency update"], cwd=source)
    _run_git(["push", "origin", "feature"], cwd=source)
    _run_git(
        ["clone", "--depth=1", "--branch", "feature", f"file://{origin}", str(checkout)],
        cwd=tmp_path,
    )

    args = _run_ci_pr_body_check_step(checkout, args_path=args_path)

    assert str(checkout / "event.json") in args
    assert args[-2:] == ["--changed-file", "uv.lock"]


def test_ci_pr_body_check_step_handles_diff_with_merge_base(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    source = tmp_path / "source"
    checkout = tmp_path / "checkout"
    args_path = tmp_path / "args.txt"

    _run_git(["init", "--bare", str(origin)], cwd=tmp_path)
    _run_git(["clone", str(origin), str(source)], cwd=tmp_path)
    _run_git(["config", "user.email", "ci@example.test"], cwd=source)
    _run_git(["config", "user.name", "CI Test"], cwd=source)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    _run_git(["add", "README.md"], cwd=source)
    _run_git(["commit", "-m", "base"], cwd=source)
    _run_git(["branch", "-M", "main"], cwd=source)
    _run_git(["push", "origin", "main"], cwd=source)
    _run_git(["checkout", "-b", "feature"], cwd=source)
    (source / "pyproject.toml").write_text("[project]\nname = \"fixture\"\n", encoding="utf-8")
    _run_git(["add", "pyproject.toml"], cwd=source)
    _run_git(["commit", "-m", "dependency update"], cwd=source)
    _run_git(["push", "origin", "feature"], cwd=source)
    _run_git(["clone", "--branch", "feature", str(origin), str(checkout)], cwd=tmp_path)

    args = _run_ci_pr_body_check_step(checkout, args_path=args_path)

    assert str(checkout / "event.json") in args
    assert args[-2:] == ["--changed-file", "pyproject.toml"]


def test_ci_workflow_runs_optional_extras_runtime_smoke() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    optional_smoke = workflow["jobs"]["optional-extras-smoke"]
    steps = optional_smoke["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert optional_smoke["needs"] == "checks"
    assert "uv sync --dev --all-extras" in run_blocks
    assert "scripts/optional_extras_smoke.py" in run_blocks
    assert "pip-audit" not in run_blocks


def test_ci_workflow_runs_checked_astro_public_site_build() -> None:
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))

    docs_site = workflow["jobs"]["docs-site"]
    steps = docs_site["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)

    assert docs_site["runs-on"] == "ubuntu-latest"
    assert docs_site["needs"] == "checks"
    assert "npm ci" in run_blocks
    assert "npm run test:deps" in run_blocks
    assert "npm run test:security" in run_blocks
    assert "npm run format:check" in run_blocks
    assert "npm run check" in run_blocks
    assert "npm run build" in run_blocks
    assert "mkdocs" not in run_blocks.lower()
    assert any(step.get("uses") == _CHECKOUT_PIN for step in steps)
    assert any(
        step.get("uses") == _SETUP_NODE_PIN
        and step.get("with", {}).get("node-version") == "24"
        and step.get("with", {}).get("cache") == "npm"
        and step.get("with", {}).get("cache-dependency-path") == "package-lock.json"
        for step in steps
    )


def test_optional_extras_smoke_script_exercises_optional_runtime_boundaries() -> None:
    script = (_REPO_ROOT / "scripts" / "optional_extras_smoke.py").read_text(
        encoding="utf-8"
    )

    assert "_load_completion_func" in script
    assert "load_mitmproxy_runtime" in script
    assert "ensure_studio_available" in script
    assert "textual.app" in script
    assert "OPENAI_API_KEY" not in script


def test_docs_explain_ci_enforced_and_local_only_gates() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    test_strategy = (_REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )

    assert "CI enforces `scripts/regression.sh --security`" in readme
    assert "CI enforces `scripts/audit_quality.sh`" in readme
    assert "CI quality-audit runs `uv run python scripts/performance_smoke.py`" in readme
    assert "Local-only before release:" in readme
    assert "GitHub Actions Enforcement" in test_strategy
    assert "`scripts/regression.sh --security`" in test_strategy
    assert "`scripts/audit_quality.sh`" in test_strategy
    assert "quality-audit job also runs `uv run python scripts/performance_smoke.py`" in (
        test_strategy
    )
    assert "optional-extras-smoke" in test_strategy
    assert "scheduled/manual CI" in test_strategy
    assert "performance-smoke" in test_strategy


def test_release_docs_explain_hurl_checksum_bump_process() -> None:
    checklist = (_REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md").read_text(
        encoding="utf-8"
    )

    assert "HURL_SHA256" in checklist
    assert "sha256sum" in checklist
    assert "Update `.github/workflows/ci.yml`" in checklist


def test_scorecard_workflow_is_non_blocking_and_least_privilege() -> None:
    workflow = yaml.safe_load(_SCORECARD_WORKFLOW_PATH.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert "pull_request" not in triggers
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "17 9 * * 1"}]

    scorecard = workflow["jobs"]["scorecard"]
    assert scorecard["runs-on"] == "ubuntu-latest"
    assert scorecard["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }

    steps = scorecard["steps"]
    assert any(
        step.get("uses") == _CHECKOUT_PIN
        and step.get("with", {}).get("persist-credentials") is False
        for step in steps
    )
    assert any(
        step.get("uses") == _SCORECARD_PIN
        and step.get("with", {}).get("publish_results") is True
        and step.get("with", {}).get("results_file") == "scorecard-results.json"
        and step.get("with", {}).get("results_format") == "json"
        for step in steps
    )
    assert any(
        step.get("uses") == _UPLOAD_ARTIFACT_PIN
        and step.get("with", {}).get("path") == "scorecard-results.json"
        for step in steps
    )


def test_performance_smoke_workflow_is_scheduled_manual_and_non_blocking() -> None:
    workflow = yaml.safe_load(_PERFORMANCE_WORKFLOW_PATH.read_text(encoding="utf-8"))

    triggers = workflow["on"]
    assert "pull_request" not in triggers
    assert "push" not in triggers
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "43 8 * * 2"}]

    performance_smoke = workflow["jobs"]["performance-smoke"]
    assert performance_smoke["runs-on"] == "ubuntu-latest"
    assert performance_smoke["permissions"] == {"contents": "read"}

    steps = performance_smoke["steps"]
    run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
    assert "uv sync --dev" in run_blocks
    assert "uv run python scripts/performance_smoke.py" in run_blocks
    assert any(
        step.get("uses") == _CHECKOUT_PIN
        and step.get("with", {}).get("persist-credentials") is False
        for step in steps
    )
    assert any(step.get("uses") == _SETUP_PYTHON_PIN for step in steps)
    assert any(step.get("uses") == _SETUP_UV_PIN for step in steps)
    assert any(
        step.get("uses") == _UPLOAD_ARTIFACT_PIN
        and step.get("with", {}).get("path") == "reports/performance-smoke.json"
        for step in steps
    )
