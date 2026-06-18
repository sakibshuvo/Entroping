"""Tests for the OpenCode independent-session readiness preflight."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "opencode_readiness.py"


def load_readiness_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("opencode_readiness_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_opencode(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    binary = path / "opencode"
    binary.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == '--version' ]]; then\n"
        "  printf '%s\\n' 'opencode 1.17.3'\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' \"unexpected opencode args: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def run_readiness(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=command_env,
    )


def checks_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = cast(list[dict[str, Any]], payload["checks"])
    return {str(check["name"]): check for check in checks}


def test_opencode_readiness_help_documents_preflight_scope() -> None:
    result = run_readiness("--help")

    assert result.returncode == 0
    assert "--opencode-bin" in result.stdout
    assert "--stale-repo-path" in result.stdout
    assert "--expected-repo-prefix" in result.stdout
    assert "--mode" in result.stdout
    assert "--require-clean" in result.stdout
    assert "--format" in result.stdout
    assert "does not read provider keys" in result.stdout


def test_opencode_readiness_json_preflight_passes_with_fake_opencode(
    tmp_path: Path,
) -> None:
    fake_opencode = write_fake_opencode(tmp_path)

    result = run_readiness(
        "--opencode-bin",
        str(fake_opencode),
        "--expected-repo-prefix",
        str(REPO_ROOT.parent),
        "--mode",
        "verification",
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    checks = checks_by_name(payload)

    assert payload["schema_version"] == "entroping.opencode-readiness.v1"
    assert payload["overall_status"] in {"pass", "warn"}
    assert checks["active_repo_path"]["status"] == "pass"
    assert checks["git_repository"]["status"] == "pass"
    assert checks["opencode_binary"]["status"] == "pass"
    assert "1.17.3" in checks["opencode_binary"]["message"]
    assert checks["required_workflow_files"]["status"] == "pass"
    assert checks["prompt_library_guardrails"]["status"] == "pass"
    assert checks["command_help_surfaces"]["status"] == "pass"
    assert (
        "scripts/architecture_integrity.sh --help"
        in checks["command_help_surfaces"]["details"]["commands"]
    )
    assert checks["agent_toolchain_policy"]["status"] in {"pass", "warn"}
    assert (
        checks["agent_toolchain_policy"]["details"]["schema_version"]
        == "entroping.agent-toolchain.v1"
    )
    assert checks["agent_toolchain_policy"]["details"]["scanner_execution"] is False
    assert checks["agent_toolchain_policy"]["details"]["network_execution"] is False
    assert checks["local_artifact_ignore_rules"]["status"] == "pass"
    assert checks["tracked_local_artifacts"]["status"] == "pass"
    assert "DEEPSEEK_API_KEY" not in result.stdout


def test_opencode_readiness_requires_architecture_integrity_gate_script(
    tmp_path: Path,
) -> None:
    module = load_readiness_module()
    required_without_architecture_gate = (
        "AGENTS.md",
        "docs/meta/AGENT_CONTROL_PLANE.md",
        "docs/meta/DOCS_GOVERNANCE.md",
        "docs/meta/FEATURE_DELIVERY_CHECKLIST.md",
        "docs/meta/prompt-library/opencode-desktop-handoff.md",
        "docs/meta/prompt-library/codex-outage-daily-operations.md",
        "docs/meta/prompt-library/issue-worker.md",
        "scripts/start_issue.sh",
        "scripts/finish_issue.sh",
        "scripts/context_pack.sh",
        "scripts/agent_toolchain.py",
        "scripts/opencode_worker.py",
        "scripts/deepseek_worker.py",
        "scripts/ai_jobs.py",
        "scripts/pr_body_check.py",
        "scripts/factory_metrics.py",
    )
    for relative_path in required_without_architecture_gate:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")

    result = module._check_required_files(tmp_path)

    assert result.status == "fail"
    assert "scripts/architecture_integrity.sh" in result.details["missing"]


def test_opencode_readiness_reports_unrunnable_architecture_gate_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_readiness_module()
    script = tmp_path / "scripts" / "architecture_integrity.sh"
    script.parent.mkdir(parents=True)
    script.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'architecture integrity provider-free access the network read secrets\\n'\n",
        encoding="utf-8",
    )
    script.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setattr(
        module,
        "COMMAND_HELP_CHECKS",
        ((("scripts/architecture_integrity.sh", "--help"), ("architecture integrity",)),),
    )

    result = module._check_command_help_surfaces(tmp_path)

    assert result.status == "fail"
    failure = result.details["failures"]["scripts/architecture_integrity.sh --help"]
    assert failure["returncode"] is None
    assert "could not execute command" in str(failure["error"])


def test_opencode_readiness_implementation_mode_rejects_main_branch(
    tmp_path: Path,
) -> None:
    fake_opencode = write_fake_opencode(tmp_path / "bin")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    result = run_readiness(
        "--repo-root",
        str(repo),
        "--expected-repo-prefix",
        str(tmp_path),
        "--opencode-bin",
        str(fake_opencode),
        "--format",
        "json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    checks = checks_by_name(payload)

    assert payload["overall_status"] == "fail"
    assert checks["git_branch"]["status"] == "fail"
    assert "scripts/start_issue.sh" in checks["git_branch"]["message"]


def test_opencode_readiness_fails_for_stale_documents_repo_path(
    tmp_path: Path,
) -> None:
    fake_opencode = write_fake_opencode(tmp_path / "bin")
    stale_repo = tmp_path / "Documents" / "Entroping"
    stale_repo.mkdir(parents=True)

    result = run_readiness(
        "--repo-root",
        str(stale_repo),
        "--stale-repo-path",
        str(stale_repo),
        "--opencode-bin",
        str(fake_opencode),
        "--format",
        "json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    checks = checks_by_name(payload)

    assert payload["overall_status"] == "fail"
    assert checks["active_repo_path"]["status"] == "fail"
    assert "stale Documents/Entroping path" in checks["active_repo_path"]["message"]


def test_opencode_readiness_does_not_emit_local_config_secret_values(
    tmp_path: Path,
) -> None:
    fake_opencode = write_fake_opencode(tmp_path / "bin")
    home = tmp_path / "home"
    config = home / ".config" / "opencode" / "opencode.json"
    config.parent.mkdir(parents=True)
    secret_value = "sk-opencode-test-secret-abcdefghijklmnopqrstuvwxyz"
    config.write_text(
        json.dumps({"provider": {"deepseek": {"api_key": secret_value}}}),
        encoding="utf-8",
    )

    result = run_readiness(
        "--opencode-bin",
        str(fake_opencode),
        "--mode",
        "verification",
        "--format",
        "json",
        env={
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "DEEPSEEK_API_KEY": "sk-env-secret-abcdefghijklmnopqrstuvwxyz",
        },
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    checks = checks_by_name(payload)

    assert checks["local_opencode_config"]["status"] == "warn"
    assert "opencode.json" in checks["local_opencode_config"]["message"]
    assert checks["local_opencode_config"]["details"]["values_read"] is False
    assert checks["local_opencode_config"]["details"]["content_inspected"] is False
    assert secret_value not in result.stdout
    assert "sk-env-secret" not in result.stdout
    assert secret_value not in result.stderr
    assert "sk-env-secret" not in result.stderr
