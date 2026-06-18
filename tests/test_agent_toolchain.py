"""Guardrails for local agent CLI toolchain policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_agent_toolchain() -> ModuleType:
    module_path = REPO_ROOT / "scripts" / "agent_toolchain.py"
    spec = importlib.util.spec_from_file_location("agent_toolchain", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_toolchain_classifies_tools_without_executing_scanners() -> None:
    agent_toolchain = _load_agent_toolchain()

    fake_paths = {
        "fd": "/tools/fd",
        "sg": "/tools/sg",
        "gitleaks": "/tools/gitleaks",
        "actionlint": "/tools/actionlint",
        "act": "/tools/act",
        "trufflehog": "/tools/trufflehog",
    }

    report = agent_toolchain.build_report(
        mode="implementation",
        require_recommended=False,
        which=lambda command: fake_paths.get(command),
    )

    tools = {tool["command"]: tool for tool in report["tools"]}

    assert report["schema_version"] == "entroping.agent-toolchain.v1"
    assert report["probe_mode"] == "path_lookup_only"
    assert report["scanner_execution"] is False
    assert report["network_execution"] is False
    assert tools["fd"]["policy"] == "safe_default"
    assert tools["sg"]["policy"] == "safe_default"
    assert tools["actionlint"]["policy"] == "guarded_local_only"
    assert tools["gitleaks"]["policy"] == "guarded_local_only"
    assert tools["act"]["policy"] == "manual_explicit"
    assert tools["trufflehog"]["policy"] == "manual_explicit"
    assert tools["trufflehog"]["agent_rule"].startswith("Do not run automatically")


def test_agent_toolchain_strict_mode_fails_only_when_requested() -> None:
    agent_toolchain = _load_agent_toolchain()

    report = agent_toolchain.build_report(
        mode="security",
        require_recommended=False,
        which=lambda _command: None,
    )
    strict_report = agent_toolchain.build_report(
        mode="security",
        require_recommended=True,
        which=lambda _command: None,
    )

    assert report["overall_status"] == "warn"
    assert strict_report["overall_status"] == "fail"
    assert strict_report["missing_recommended"]
    assert "gitleaks" in strict_report["missing_recommended"]
