"""Tests for deterministic quality-audit trend summaries."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "quality_trend_summary.py"


def run_quality_trend_summary(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), *args],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _write_quality_inputs(root: Path) -> dict[str, Path]:
    paths = {
        "taxonomy": root / "test-taxonomy.json",
        "coverage": root / "coverage.json",
        "radon_cc": root / "radon-cc.json",
        "radon_mi": root / "radon-mi.json",
        "vulture": root / "vulture.txt",
    }
    paths["taxonomy"].write_text(
        json.dumps(
            {
                "schema_version": "entroping.test-taxonomy.v1",
                "test_file_count": 3,
                "static_test_count": 7,
                "strict_explicit_categories": [
                    "integration",
                    "regression",
                    "security",
                ],
                "categories": {
                    "behavior": {
                        "file_count": 2,
                        "static_test_count": 4,
                        "provenance": {
                            "explicit": {"file_count": 0, "static_test_count": 0},
                            "inferred": {"file_count": 2, "static_test_count": 4},
                            "mixed": {"file_count": 0, "static_test_count": 0},
                        },
                    },
                    "security": {
                        "file_count": 1,
                        "static_test_count": 3,
                        "provenance": {
                            "explicit": {"file_count": 1, "static_test_count": 3},
                            "inferred": {"file_count": 0, "static_test_count": 0},
                            "mixed": {"file_count": 0, "static_test_count": 0},
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    paths["coverage"].write_text(
        json.dumps(
            {
                "totals": {
                    "covered_lines": 197,
                    "missing_lines": 3,
                    "num_statements": 200,
                    "percent_covered": 98.5,
                }
            }
        ),
        encoding="utf-8",
    )
    paths["radon_cc"].write_text(
        json.dumps(
            {
                "src/a.py": [
                    {"complexity": 1, "rank": "A"},
                    {"complexity": 12, "rank": "C"},
                ],
                "tests/test_a.py": [],
            }
        ),
        encoding="utf-8",
    )
    paths["radon_mi"].write_text(
        json.dumps(
            {
                "src/a.py": {"mi": 100, "rank": "A"},
                "src/b.py": [{"mi": 100, "rank": "A"}, {"mi": 42, "rank": "D"}],
            }
        ),
        encoding="utf-8",
    )
    paths["vulture"].write_text(
        "src/a.py:10: unused function 'old_path' (90% confidence)\n",
        encoding="utf-8",
    )
    return paths


def test_quality_trend_summary_writes_stable_json_shape(tmp_path: Path) -> None:
    paths = _write_quality_inputs(tmp_path)
    output = tmp_path / "quality-trend.json"

    result = run_quality_trend_summary(
        "--taxonomy",
        str(paths["taxonomy"]),
        "--coverage",
        str(paths["coverage"]),
        "--radon-cc",
        str(paths["radon_cc"]),
        "--radon-mi",
        str(paths["radon_mi"]),
        "--vulture",
        str(paths["vulture"]),
        "--output",
        str(output),
        "--coverage-fail-under",
        "100",
        "--max-complexity-rank",
        "D",
        "--min-mi-rank",
        "C",
        "--vulture-confidence",
        "90",
    )

    assert result.returncode == 0, result.stderr
    assert "Wrote quality trend summary" in result.stdout
    assert "coverage=98.50%" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": "entroping.quality-trend.v1",
        "generated_by": "scripts/quality_trend_summary.py",
        "thresholds": {
            "coverage_fail_under": 100.0,
            "max_complexity_rank": "D",
            "min_maintainability_rank": "C",
            "vulture_confidence": 90,
        },
        "metrics": {
            "coverage_percent": 98.5,
            "coverage_covered_lines": 197,
            "coverage_missing_lines": 3,
            "coverage_statements": 200,
            "complexity_average": 6.5,
            "complexity_blocks": 2,
            "complexity_worst_rank": "C",
            "complexity_worst_rank_score": 3,
            "dead_code_findings": 1,
            "maintainability_files": 2,
            "maintainability_worst_rank": "D",
            "maintainability_worst_rank_score": 4,
            "test_files": 3,
            "test_static_count": 7,
        },
        "taxonomy_categories": {
            "behavior": {"file_count": 2, "static_test_count": 4},
            "security": {"file_count": 1, "static_test_count": 3},
        },
        "deltas": {},
    }


def test_quality_trend_summary_records_numeric_deltas(tmp_path: Path) -> None:
    paths = _write_quality_inputs(tmp_path)
    previous = tmp_path / "previous-quality-trend.json"
    previous.write_text(
        json.dumps(
            {
                "schema_version": "entroping.quality-trend.v1",
                "metrics": {
                    "coverage_percent": 97.0,
                    "coverage_missing_lines": 5,
                    "complexity_blocks": 1,
                    "dead_code_findings": 2,
                    "test_static_count": 6,
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "quality-trend.json"

    result = run_quality_trend_summary(
        "--taxonomy",
        str(paths["taxonomy"]),
        "--coverage",
        str(paths["coverage"]),
        "--radon-cc",
        str(paths["radon_cc"]),
        "--radon-mi",
        str(paths["radon_mi"]),
        "--vulture",
        str(paths["vulture"]),
        "--previous",
        str(previous),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["deltas"] == {
        "complexity_blocks": 1,
        "coverage_missing_lines": -2,
        "coverage_percent": 1.5,
        "dead_code_findings": -1,
        "test_static_count": 1,
    }


def test_quality_trend_summary_counts_only_vulture_findings(tmp_path: Path) -> None:
    paths = _write_quality_inputs(tmp_path)
    paths["vulture"].write_text(
        "Traceback (most recent call last):\n"
        "RuntimeError: vulture crashed\n"
        "src/a.py:10: unused function 'old_path' (90% confidence)\n",
        encoding="utf-8",
    )
    output = tmp_path / "quality-trend.json"

    result = run_quality_trend_summary(
        "--taxonomy",
        str(paths["taxonomy"]),
        "--coverage",
        str(paths["coverage"]),
        "--radon-cc",
        str(paths["radon_cc"]),
        "--radon-mi",
        str(paths["radon_mi"]),
        "--vulture",
        str(paths["vulture"]),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metrics"]["dead_code_findings"] == 1


def test_quality_trend_summary_rejects_missing_inputs(tmp_path: Path) -> None:
    result = run_quality_trend_summary(
        "--taxonomy",
        str(tmp_path / "missing-taxonomy.json"),
        "--coverage",
        str(tmp_path / "missing-coverage.json"),
        "--radon-cc",
        str(tmp_path / "missing-radon-cc.json"),
        "--radon-mi",
        str(tmp_path / "missing-radon-mi.json"),
        "--vulture",
        str(tmp_path / "missing-vulture.txt"),
        "--output",
        str(tmp_path / "quality-trend.json"),
    )

    assert result.returncode == 2
    assert "missing input file" in result.stderr


def test_quality_trend_summary_rejects_maintainability_without_rank(
    tmp_path: Path,
) -> None:
    paths = _write_quality_inputs(tmp_path)
    paths["radon_mi"].write_text(
        json.dumps({"src/a.py": {}, "src/b.py": []}),
        encoding="utf-8",
    )

    result = run_quality_trend_summary(
        "--taxonomy",
        str(paths["taxonomy"]),
        "--coverage",
        str(paths["coverage"]),
        "--radon-cc",
        str(paths["radon_cc"]),
        "--radon-mi",
        str(paths["radon_mi"]),
        "--vulture",
        str(paths["vulture"]),
        "--output",
        str(tmp_path / "quality-trend.json"),
    )

    assert result.returncode == 2
    assert "radon maintainability missing rank data" in result.stderr
