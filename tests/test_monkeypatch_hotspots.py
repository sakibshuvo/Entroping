import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "monkeypatch_hotspots.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False, cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_json_schema_and_counts() -> None:
    result = _run("--format", "json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "entroping.monkeypatch-hotspot-report.v1"
    assert isinstance(payload["total_monkeypatch_uses"], int)
    assert payload["total_monkeypatch_uses"] > 0
    assert isinstance(payload["files_with_monkeypatch"], int)
    assert payload["files_with_monkeypatch"] > 0


def test_hotspots_sorted_by_count() -> None:
    result = _run("--format", "json")
    payload = json.loads(result.stdout)
    hotspots = payload["hotspots"]
    counts = [h["count"] for h in hotspots]
    assert counts == sorted(counts, reverse=True), f"not descending: {counts}"


def test_top_limit_respected() -> None:
    result = _run("--format", "json", "--top", "3")
    payload = json.loads(result.stdout)
    assert len(payload["hotspots"]) == 3


def test_excludes_virtualenvs() -> None:
    result = _run("--format", "json")
    payload = json.loads(result.stdout)
    for h in payload["hotspots"]:
        assert ".venv" not in h["file"]
        assert "__pycache__" not in h["file"]


def test_ignores_strings_and_comments(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    tests = root / "tests"
    tests.mkdir(parents=True)
    (tests / "test_text_only.py").write_text(
        "# monkeypatch in a comment\n"
        "def test_text_only():\n"
        "    value = 'monkeypatch in a string'\n"
        "    assert value\n",
        encoding="utf-8",
    )

    result = _run("--root", str(root), "--format", "json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["total_monkeypatch_uses"] == 0
    assert payload["hotspots"] == []


def test_markdown_output() -> None:
    result = _run("--format", "md")
    assert result.returncode == 0
    assert "# Monkeypatch Hotspot Report" in result.stdout
    assert "Total monkeypatch uses" in result.stdout


def test_strict_fails_when_no_monkeypatch(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "tests").mkdir()
    (empty / "tests" / "no_patch.py").write_text("def test(): pass\n", encoding="utf-8")
    result = subprocess.run(
        ["python", str(SCRIPT), "--root", str(empty), "--strict"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "no monkeypatch usage found" in result.stderr
