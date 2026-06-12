"""Smoke tests for deterministic agent context-pack tooling."""

import json
import os
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "context_pack.sh"


def run_context_pack(
    *args: str,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env is not None:
        command_env.update(env)
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=command_env,
    )


def test_context_pack_help_documents_modes() -> None:
    result = run_context_pack("--help")

    assert result.returncode == 0
    assert "--mode implementation|review|source|growth|handoff" in result.stdout
    assert "--with-local-graphs" in result.stdout
    assert "--graph-query" in result.stdout
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout
    assert "NotebookLM" in result.stdout
    assert "Codex" in result.stdout


def test_context_pack_implementation_mode_includes_required_sources() -> None:
    result = run_context_pack("--mode", "implementation")

    assert result.returncode == 0, result.stderr
    assert "# Entroping Agent Context Pack" in result.stdout
    assert "Mode: implementation" in result.stdout
    assert "## Required Agent Rules" in result.stdout
    assert "### AGENTS.md" in result.stdout
    assert "### docs/technical/TDS.md" in result.stdout
    assert "### docs/meta/FEATURE_DELIVERY_CHECKLIST.md" in result.stdout
    assert "### docs/meta/archive/AUTONOMOUS_DEVELOPMENT.md" in result.stdout
    assert "### docs/meta/AUTONOMOUS_DEVELOPMENT.md" not in result.stdout
    assert ".entroping/state.db" in result.stdout
    assert "graphify-out/" not in result.stdout
    assert "agent-context-out/" not in result.stdout


def test_context_pack_can_include_optional_graph_assisted_probe() -> None:
    result = run_context_pack(
        "--mode",
        "implementation",
        "--with-local-graphs",
        "--graph-query",
        "safe mode reports",
    )

    assert result.returncode == 0, result.stderr
    assert "## Optional Graph-Assisted Agent Context" in result.stdout
    assert "schema: entroping.agent-context-probe.v1" in result.stdout
    assert "Graphify: missing" in result.stdout
    assert "CodeGraph: missing" in result.stdout
    assert "Graph output is retrieval evidence, not authority." in result.stdout
    assert "Verify every candidate against source files and tests" in result.stdout
    assert "agent-context-out/" in result.stdout


def test_context_pack_records_opt_in_factory_metrics_without_persisting_pack() -> None:
    ledger = (
        Path(".entroping")
        / "factory-metrics"
        / "tests"
        / f"context-pack-{uuid.uuid4().hex}.jsonl"
    )
    full_ledger = REPO_ROOT / ledger

    try:
        result = run_context_pack(
            "--mode",
            "handoff",
            "--record-factory-metrics",
            "--factory-role",
            "integrator",
            "--factory-metrics-ledger",
            ledger.as_posix(),
        )

        assert result.returncode == 0, result.stderr
        assert "# Entroping Agent Context Pack" in result.stdout
        events = [
            json.loads(line)
            for line in full_ledger.read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "context_pack"
        assert event["role"] == "integrator"
        assert event["agent"] == "Codex"
        assert event["tool"] == "scripts/context_pack.sh"
        assert event["outcome"] == "success"
        assert event["decision"] == "not_applicable"
        assert event["metrics"]["context_bytes"] == len(result.stdout.encode("utf-8"))
        assert event["metrics"]["estimated_tokens"] >= 1
        assert event["metrics"]["candidate_files"] >= 1
        assert event["metrics"]["files_read"] == event["metrics"]["candidate_files"]
        ledger_text = full_ledger.read_text(encoding="utf-8")
        assert "Required Agent Rules" not in ledger_text
        assert "Current Git Status" not in ledger_text
    finally:
        full_ledger.unlink(missing_ok=True)


def test_autonomous_development_has_single_canonical_archive_entrypoint() -> None:
    assert not (REPO_ROOT / "docs" / "meta" / "AUTONOMOUS_DEVELOPMENT.md").exists()
    assert (
        REPO_ROOT / "docs" / "meta" / "archive" / "AUTONOMOUS_DEVELOPMENT.md"
    ).exists()


def test_context_pack_source_mode_keeps_source_archive_as_evidence_not_truth() -> None:
    result = run_context_pack("--mode", "source")

    assert result.returncode == 0, result.stderr
    assert "Mode: source" in result.stdout
    assert "NotebookLM Markdown export is the primary current source snapshot" in result.stdout
    assert "Historical source material is evidence, not automatic current truth" in result.stdout
    assert "### sources/SOURCE_MAP.md" in result.stdout
    assert "### docs/evolution/REQUIREMENTS_ANALYSIS.md" in result.stdout
    assert "### docs/meta/OBSIDIAN_CONTEXT_ENGINE_GUIDE.md" in result.stdout


def test_context_pack_source_root_can_be_overridden_without_hardcoded_maintainer_path() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    source_root = "/tmp/entroping-specs-fixture"

    result = run_context_pack(
        "--mode",
        "source",
        env={"ENTROPING_SOURCE_ROOT": source_root},
    )

    assert result.returncode == 0, result.stderr
    assert '/Users/sakibshuvo/projects/entroping-specs"' not in script
    assert f"- Source archive: {source_root}" in result.stdout
    assert f"{source_root}/notebookLM/2026-05-29 NotebookLM Specs.md" in result.stdout


def test_context_pack_rejects_unknown_mode() -> None:
    result = run_context_pack("--mode", "chaos")

    assert result.returncode == 2
    assert "unknown mode" in result.stderr
