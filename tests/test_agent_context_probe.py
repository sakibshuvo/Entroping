"""Tests for optional graph-assisted agent context probes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "agent_context_probe.py"


def run_probe(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_agent_context_probe_skips_cleanly_without_generated_outputs(
    tmp_path: Path,
) -> None:
    result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "safe mode reports",
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)

    assert manifest["schema_version"] == "entroping.agent-context-probe.v1"
    assert manifest["query_terms"] == ["safe", "mode", "reports"]
    assert manifest["candidates"] == []
    assert (
        "Graph output is retrieval evidence, not authority."
        in manifest["guardrails"]
    )
    assert (
        "Verify every candidate against source files and tests before patching."
        in manifest["verification_warnings"]
    )

    statuses = {entry["tool"]: entry for entry in manifest["generated_context"]}
    assert statuses["Graphify"]["path"] == "graphify-out/"
    assert statuses["Graphify"]["status"] == "missing"
    assert statuses["Graphify"]["candidate_count"] == 0
    assert statuses["CodeGraph"]["path"] == "codegraph-out/"
    assert statuses["CodeGraph"]["status"] == "missing"
    assert statuses["CodeGraph"]["candidate_count"] == 0


def test_agent_context_probe_extracts_candidates_from_local_graph_outputs(
    tmp_path: Path,
) -> None:
    graphify_report = tmp_path / "graphify-out" / "report.md"
    graphify_report.parent.mkdir()
    graphify_report.write_text(
        "\n".join(
            [
                "# Graphify report",
                "src/entroping/core/report_writer.py builds safe mode report evidence",
                "tests/test_report_writer.py covers safe mode report summaries",
            ]
        ),
        encoding="utf-8",
    )
    codegraph_report = tmp_path / "codegraph-out" / "src-tests.json"
    codegraph_report.parent.mkdir()
    codegraph_report.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "path": "src/entroping/core/run_workflow.py",
                        "summary": "safe mode protected run report accounting",
                    },
                    {
                        "path": "tests/test_run_workflow.py",
                        "summary": "safe mode workflow regression tests",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "safe mode report",
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    candidates = manifest["candidates"]

    assert {candidate["tool"] for candidate in candidates} == {
        "Graphify",
        "CodeGraph",
    }
    assert {
        referenced
        for candidate in candidates
        for referenced in candidate["referenced_paths"]
    } >= {
        "src/entroping/core/report_writer.py",
        "tests/test_report_writer.py",
        "src/entroping/core/run_workflow.py",
        "tests/test_run_workflow.py",
    }
    assert all(
        not candidate["artifact_path"].startswith(str(tmp_path))
        for candidate in candidates
    )

    statuses = {entry["tool"]: entry for entry in manifest["generated_context"]}
    assert statuses["Graphify"]["status"] == "present"
    assert statuses["CodeGraph"]["status"] == "present"
    assert statuses["Graphify"]["candidate_count"] == 2
    assert statuses["CodeGraph"]["candidate_count"] == 2


def test_agent_context_probe_writes_only_under_agent_context_out(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "agent-context-out" / "probe.json"
    allowed_result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "graph context",
        "--format",
        "json",
        "--output",
        str(allowed),
    )

    assert allowed_result.returncode == 0, allowed_result.stderr
    assert allowed.exists()
    assert json.loads(allowed.read_text(encoding="utf-8"))["schema_version"] == (
        "entroping.agent-context-probe.v1"
    )

    forbidden = tmp_path / "probe.json"
    forbidden_result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "graph context",
        "--output",
        str(forbidden),
    )

    assert forbidden_result.returncode == 2
    assert "output path must be under agent-context-out/" in forbidden_result.stderr
    assert not forbidden.exists()


def test_agent_context_probe_ignores_symlinked_artifacts(tmp_path: Path) -> None:
    outside_artifact = tmp_path / "outside.md"
    outside_artifact.write_text(
        "src/entroping/core/run_workflow.py safe mode report token=secret-value",
        encoding="utf-8",
    )
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    try:
        (graphify_dir / "linked.md").symlink_to(outside_artifact)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "safe mode report",
        "--format",
        "json",
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    statuses = {entry["tool"]: entry for entry in manifest["generated_context"]}

    assert manifest["candidates"] == []
    assert statuses["Graphify"]["status"] == "empty"
    assert statuses["Graphify"]["artifact_count"] == 0


def test_agent_context_probe_text_output_names_guardrails(tmp_path: Path) -> None:
    result = run_probe(
        "--repo-root",
        str(tmp_path),
        "--query",
        "agent graph context",
        "--format",
        "text",
    )

    assert result.returncode == 0, result.stderr
    assert "schema: entroping.agent-context-probe.v1" in result.stdout
    assert "Generated Context Tool Status" in result.stdout
    assert "Graphify: missing" in result.stdout
    assert "CodeGraph: missing" in result.stdout
    assert "Graph output is retrieval evidence, not authority." in result.stdout
    assert "Verify every candidate against source files and tests" in result.stdout
