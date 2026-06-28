"""Tests for long-file hotspot reporting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "quality_hotspot_report.py"


def run_quality_hotspot_report(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line-{index}" for index in range(count)) + "\n", encoding="utf-8")


def test_quality_hotspot_report_detects_sorted_long_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    _write_lines(tmp_path / "src" / "small.py", 10)
    _write_lines(tmp_path / "src" / "medium.py", 450)
    _write_lines(tmp_path / "src" / "large.py", 550)
    _write_lines(tmp_path / "tests" / "suite.py", 520)

    output = tmp_path / "reports" / "hotspots.json"
    result = run_quality_hotspot_report(
        "--root",
        str(tmp_path),
        "--output",
        str(output),
        "--max-lines",
        "400",
        "--limit",
        "2",
    )

    assert result.returncode == 0, result.stderr
    assert "wrote quality hotspot report" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "entroping.quality-hotspot-report.v1"
    assert payload["max_lines_threshold"] == 400
    assert payload["limit"] == 2
    assert payload["hotspot_count"] == 3
    assert len(payload["hotspots"]) == 2
    assert payload["hotspots"][0]["path"].endswith("large.py")
    assert payload["hotspots"][0]["lines"] == 550
    assert payload["hotspots"][1]["path"].endswith("suite.py")
    assert payload["hotspots"][1]["lines"] == 520


def test_quality_hotspot_report_rejects_unbounded_thresholds() -> None:
    result = run_quality_hotspot_report("--max-lines", "0")

    assert result.returncode != 0
    assert "max-lines must be positive" in result.stdout


def test_quality_hotspot_report_respects_path_prefix_filter(tmp_path: Path) -> None:
    _write_lines(tmp_path / "src" / "root.py", 700)
    _write_lines(tmp_path / "docs" / "notes.py", 900)
    output = tmp_path / "reports" / "hotspots.json"

    result = run_quality_hotspot_report(
        "--root",
        str(tmp_path),
        "--output",
        str(output),
        "--max-lines",
        "500",
        "--path-prefix",
        "src",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["hotspots"]) == 1
    assert payload["hotspots"][0]["path"].endswith("src/root.py")
