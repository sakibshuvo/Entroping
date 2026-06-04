"""Tests for lossless decision memory and source-preservation guardrails."""

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "docs" / "meta" / "DECISION_REGISTRY.yaml"
PRESERVATION_SCRIPT = REPO_ROOT / "scripts" / "source_preservation_check.py"
CONTEXT_PACK_SCRIPT = REPO_ROOT / "scripts" / "context_pack.sh"


def run_preservation_check(*args: str, root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(PRESERVATION_SCRIPT), "--root", str(root), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_decision_registry_is_structured_seeded_and_lossless() -> None:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))

    assert data["schema_version"] == "entroping.decision-registry.v1"
    assert data["preservation_policy"]["archive_means"] == "lower-default-reading-priority"
    assert data["preservation_policy"]["summaries_replace_sources"] is False
    assert data["preservation_policy"]["raw_sources_retained"] is True

    decisions = data["decisions"]
    assert len(decisions) >= 12
    assert len({decision["id"] for decision in decisions}) == len(decisions)

    required_fields = {
        "id",
        "title",
        "status",
        "date",
        "summary",
        "tags",
        "source_links",
        "related_docs",
        "related_issues",
        "supersedes",
        "superseded_by",
    }
    for decision in decisions:
        assert required_fields <= set(decision)
        assert decision["source_links"], decision["id"]
        assert decision["summary"].strip(), decision["id"]
        for source_link in decision["source_links"]:
            if source_link.get("external"):
                continue
            assert (REPO_ROOT / source_link["path"]).is_file(), (
                decision["id"],
                source_link["path"],
            )

    assert any("context-preservation" in decision["tags"] for decision in decisions)


def test_source_preservation_check_passes_current_repo() -> None:
    result = run_preservation_check()

    assert result.returncode == 0, result.stderr
    assert "Source preservation OK" in result.stdout
    assert "DECISION_REGISTRY.yaml" in result.stdout


def test_source_preservation_check_rejects_missing_registry_link(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / "docs" / "evolution").mkdir(parents=True)
    (tmp_path / "sources").mkdir()
    for relative_path in (
        "sources/SOURCE_MAP.md",
        "docs/evolution/REQUIREMENTS_ANALYSIS.md",
        "docs/evolution/EVOLUTION_TIMELINE.md",
        "docs/evolution/CREATOR_INTENT_AUDIT.md",
        "docs/meta/VAULT_INDEX.md",
        "docs/meta/CONTEXT_MANAGEMENT.md",
        "docs/meta/KNOWLEDGE_BASE_WORKFLOW.md",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.name}\n", encoding="utf-8")

    (tmp_path / "docs" / "meta" / "DECISION_REGISTRY.yaml").write_text(
        """
schema_version: entroping.decision-registry.v1
preservation_policy:
  archive_means: lower-default-reading-priority
  summaries_replace_sources: false
  raw_sources_retained: true
decisions:
  - id: ENT-DEC-9999
    title: Broken registry entry
    status: accepted
    date: 2026-06-04
    summary: This entry intentionally points to a missing file.
    tags: [context-preservation]
    source_links:
      - path: docs/missing/source.md
        role: missing
    related_docs: []
    related_issues: []
    supersedes: []
    superseded_by: null
""",
        encoding="utf-8",
    )

    result = run_preservation_check(root=tmp_path)

    assert result.returncode == 1
    assert "docs/missing/source.md" in result.stderr


def test_context_pack_surfaces_decision_registry_for_source_and_handoff() -> None:
    for mode in ("source", "handoff"):
        result = subprocess.run(
            [str(CONTEXT_PACK_SCRIPT), "--mode", mode],
            check=False,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "### docs/meta/DECISION_REGISTRY.yaml" in result.stdout
        assert "ENT-DEC-" in result.stdout
