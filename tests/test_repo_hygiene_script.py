"""Smoke tests for deterministic repo-hygiene tooling."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_hygiene_help_documents_forbidden_tracked_paths() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh"), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert ".DS_Store" in result.stdout
    assert ".obsidian/" in result.stdout
    assert ".entroping/" in result.stdout
    assert "llm-wiki-out/" in result.stdout
    assert "understand-anything-out/" in result.stdout
    assert "codegraph-out/" in result.stdout
    assert "headroom-out/" in result.stdout
    assert "agent-context-out/" in result.stdout
    assert ".entroping/factory-metrics/" in result.stdout


def test_gitignore_excludes_coverage_artifacts() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ".coverage", "coverage.xml", "htmlcov/index.html"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    ignored = set(result.stdout.splitlines())
    assert ignored == {".coverage", "coverage.xml", "htmlcov/index.html"}


def test_gitignore_excludes_generated_context_tool_outputs() -> None:
    generated_paths = {
        "graphify-out/index.json",
        "llm-wiki-out/index.md",
        "understand-anything-out/session.json",
        "codegraph-out/src-tests.json",
        "headroom-out/context-pack.json",
        "agent-context-out/probe.json",
        ".entroping/factory-metrics/events.jsonl",
        ".obsidian/workspace.json",
    }

    result = subprocess.run(
        ["git", "check-ignore", *sorted(generated_paths)],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == generated_paths


def test_repo_hygiene_rejects_forbidden_tracked_paths(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True
    )
    forbidden = tmp_path / ".DS_Store"
    forbidden.write_text("machine state\n", encoding="utf-8")
    subprocess.run(["git", "add", ".DS_Store"], check=True, cwd=tmp_path)

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Forbidden tracked local/generated files" in result.stderr
    assert ".DS_Store" in result.stderr


def test_repo_hygiene_rejects_tracked_context_tool_output(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True
    )
    generated = tmp_path / "agent-context-out" / "probe.json"
    generated.parent.mkdir()
    generated.write_text('{"generated": true}\n', encoding="utf-8")
    subprocess.run(["git", "add", str(generated.relative_to(tmp_path))], check=True, cwd=tmp_path)

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Forbidden tracked local/generated files" in result.stderr
    assert "agent-context-out/probe.json" in result.stderr


def test_repo_hygiene_rejects_tracked_factory_metrics(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"], check=True, cwd=tmp_path, capture_output=True, text=True
    )
    generated = tmp_path / ".entroping" / "factory-metrics" / "events.jsonl"
    generated.parent.mkdir(parents=True)
    generated.write_text(
        '{"schema_version":"entroping.factory-metrics.v1"}\n', encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "-f", str(generated.relative_to(tmp_path))],
        check=True,
        cwd=tmp_path,
    )

    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Forbidden tracked local/generated files" in result.stderr
    assert ".entroping/factory-metrics/events.jsonl" in result.stderr


def test_repo_hygiene_passes_current_repo() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "repo_hygiene.sh")],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Repo hygiene OK" in result.stdout
