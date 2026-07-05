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
    for key in list(command_env):
        if key.startswith("ENTROPING_CONTEXT_PACK_BUDGET_"):
            del command_env[key]
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
    assert "--manifest" in result.stdout
    assert "--strict-budget" in result.stdout
    assert "--with-local-graphs" not in result.stdout
    assert "--graph-query" not in result.stdout
    assert "Graph" + "ify" not in result.stdout
    assert "Code" + "Graph" not in result.stdout
    assert "--record-factory-metrics" in result.stdout
    assert "--factory-metrics-ledger" in result.stdout
    assert "NotebookLM" in result.stdout
    assert "Codex" in result.stdout


def test_context_pack_manifest_reports_budgeted_file_inventory_without_pack_body() -> None:
    result = run_context_pack("--mode", "implementation", "--manifest")

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["schema"] == "entroping.context-pack-manifest.v1"
    assert manifest["mode"] == "implementation"
    assert manifest["repo"] == str(REPO_ROOT)
    assert manifest["branch"]
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["file_count"] >= 1
    assert manifest["context_bytes"] > 0
    assert manifest["estimated_tokens"] == (manifest["context_bytes"] + 3) // 4
    assert manifest["budget_bytes"] >= manifest["context_bytes"]
    assert manifest["budget_status"] == "pass"
    assert manifest["generated_at"].endswith("Z")
    assert manifest["recommended_next_action"] == {
        "action": "targeted_file_reads",
        "full_pack_allowed": True,
        "reason": (
            "Manifest is within the mode budget; read only files relevant to "
            "the issue before loading the full pack."
        ),
        "steps": [
            "Start from the named issue or review question.",
            "Use files[].path and files[].reason to choose the smallest useful read set.",
            "Use rg and the decision registry before opening broad historical docs.",
            "Load the full context pack only when targeted reads are insufficient.",
        ],
    }

    by_path = {entry["path"]: entry for entry in manifest["files"]}
    assert "AGENTS.md" in by_path
    assert by_path["AGENTS.md"]["bytes"] > 0
    assert by_path["AGENTS.md"]["reason"] == "agent-rules"
    assert "docs/meta/DECISION_REGISTRY.yaml" in by_path
    assert by_path["docs/meta/DECISION_REGISTRY.yaml"]["reason"] == "decision-registry"
    assert "README.md" not in by_path
    assert "docs/meta/VAULT_INDEX.md" not in by_path

    assert "# Entroping Agent Context Pack" not in result.stdout
    assert "Required Agent Rules" not in result.stdout
    assert "Current Git Status" not in result.stdout
    assert "content" not in manifest["files"][0]


def test_context_pack_manifest_uses_python39_compatible_datetime_api() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "from datetime import UTC" not in script
    assert "timezone.utc" in script


def test_context_pack_manifest_rejects_unexplained_file_reasons() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "mode-%s-context" not in script


def test_context_pack_strict_budget_passes_for_default_implementation_budget() -> None:
    result = run_context_pack("--mode", "implementation", "--strict-budget")

    assert result.returncode == 0, result.stderr
    assert "# Entroping Agent Context Pack" in result.stdout


def test_context_pack_limits_large_git_status_listing() -> None:
    marker = f"context-pack-status-{uuid.uuid4().hex}"
    paths = [REPO_ROOT / f".{marker}-{index}.tmp" for index in range(90)]
    try:
        for path in paths:
            path.write_text("temporary status fixture\n", encoding="utf-8")

        result = run_context_pack("--mode", "implementation")
        strict_result = run_context_pack(
            "--mode",
            "implementation",
            "--strict-budget",
        )

        assert result.returncode == 0, result.stderr
        assert strict_result.returncode == 0, strict_result.stderr
        assert "additional status line(s) omitted; run git status --short" in result.stdout
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def test_context_pack_strict_budget_rejects_over_budget_override() -> None:
    result = run_context_pack(
        "--mode",
        "implementation",
        "--manifest",
        "--strict-budget",
        env={"ENTROPING_CONTEXT_PACK_BUDGET_IMPLEMENTATION": "1"},
    )

    assert result.returncode == 2
    assert "implementation context pack exceeds budget" in result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["budget_bytes"] == 1
    assert manifest["budget_status"] == "fail"
    assert manifest["recommended_next_action"] == {
        "action": "reduce_scope",
        "full_pack_allowed": False,
        "reason": "Manifest exceeds the mode budget; do not load the full context pack.",
        "steps": [
            "Switch to a narrower mode or a smaller issue question.",
            "Read only files[].path entries that match the issue scope.",
            "Use rg for exact symbol or phrase lookup before broad file reads.",
            "Record the budget failure in factory metrics or the worker handoff.",
        ],
    }


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
    assert "graph" + "ify-out/" not in result.stdout
    assert "agent-context-out/" not in result.stdout


def test_context_pack_implementation_mode_prunes_reference_navigation_docs() -> None:
    result = run_context_pack("--mode", "implementation")

    assert result.returncode == 0, result.stderr
    assert "### README.md" not in result.stdout
    assert "### docs/meta/VAULT_INDEX.md" not in result.stdout
    assert "### docs/meta/DECISION_REGISTRY.yaml" in result.stdout
    assert "### docs/meta/PROJECT_PROGRESS.md" in result.stdout
    assert "### .context/plan.md" in result.stdout


def test_context_pack_handoff_mode_includes_review_checklist() -> None:
    result = run_context_pack("--mode", "handoff")

    assert result.returncode == 0, result.stderr
    assert "### docs/meta/VAULT_INDEX.md" in result.stdout
    assert "### docs/meta/FEATURE_DELIVERY_CHECKLIST.md" in result.stdout
    assert "### .context/changelog.md" in result.stdout


def test_context_pack_rejects_removed_graph_assisted_probe_option() -> None:
    result = run_context_pack("--with-local-graphs")

    assert result.returncode == 2
    assert "unknown option: --with-local-graphs" in result.stderr


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
