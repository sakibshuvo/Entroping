"""Smoke tests for deterministic agent context-pack tooling."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "context_pack.sh"


def run_context_pack(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_context_pack_help_documents_modes() -> None:
    result = run_context_pack("--help")

    assert result.returncode == 0
    assert "--mode implementation|review|source|growth|handoff" in result.stdout
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
    assert ".entroping/state.db" in result.stdout
    assert "graphify-out/" not in result.stdout


def test_context_pack_source_mode_keeps_source_archive_as_evidence_not_truth() -> None:
    result = run_context_pack("--mode", "source")

    assert result.returncode == 0, result.stderr
    assert "Mode: source" in result.stdout
    assert "NotebookLM Markdown export is the primary current source snapshot" in result.stdout
    assert "Historical source material is evidence, not automatic current truth" in result.stdout
    assert "### sources/SOURCE_MAP.md" in result.stdout
    assert "### docs/evolution/REQUIREMENTS_ANALYSIS.md" in result.stdout


def test_context_pack_rejects_unknown_mode() -> None:
    result = run_context_pack("--mode", "chaos")

    assert result.returncode == 2
    assert "unknown mode" in result.stderr
