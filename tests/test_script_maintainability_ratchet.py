from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "script_maintainability_ratchet.py"
QUALITY_AUDIT = REPO_ROOT / "scripts" / "audit_quality.sh"
BASELINE = REPO_ROOT / "docs/meta/script-maintainability-ratchet-baseline.json"
WEIGHTS = {"A": 0, "B": 1, "C": 3, "D": 8, "E": 13, "F": 21}


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _rank_counts(**overrides: int) -> dict[str, int]:
    counts = dict.fromkeys(WEIGHTS, 0)
    counts.update(overrides)
    return counts


def _family(counts: dict[str, int]) -> dict[str, object]:
    worst = next((rank for rank in reversed(WEIGHTS) if counts[rank]), "A")
    return {
        "rank_counts": counts,
        "weighted_score": sum(counts[rank] * WEIGHTS[rank] for rank in WEIGHTS),
        "worst_rank": worst,
    }


def _metrics(
    *,
    counts: dict[str, int],
    hotspots: dict[str, int] | None = None,
) -> dict[str, object]:
    files = hotspots or {}
    return {
        "cyclomatic_complexity": _family(counts),
        "script_hotspots": {
            "threshold_lines": 500,
            "count": len(files),
            "files": files,
        },
    }


def _baseline_payload(metrics: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "entroping.script-maintainability-ratchet-baseline.v1",
        "revision": 1,
        "owner": "Entroping maintainers",
        "reviewed_on": "2026-08-09",
        "evidence": {
            "issue_url": "https://github.com/sakibshuvo/Entroping/issues/1533",
            "cc_command": "uv run radon cc scripts -s -a --json",
            "hotspot_definition": "Python scripts with at least 500 physical lines.",
        },
        "weights": WEIGHTS,
        "metrics": metrics,
    }


def _prepare_repo(
    root: Path,
    *,
    ranks: tuple[str, ...] = ("B",),
    line_count: int = 1,
) -> None:
    script = root / "scripts" / "example.py"
    script.parent.mkdir(parents=True)
    functions = "".join(
        f"def function_{index}():\n    return {index}\n"
        for index, _rank in enumerate(ranks, start=1)
    )
    filler = "# filler\n" * max(0, line_count - len(functions.splitlines()))
    script.write_text(functions + filler, encoding="utf-8")
    _write_json(
        root / "reports" / "radon-scripts-cc.json",
        {
            "scripts/example.py": [
                {
                    "type": "function",
                    "rank": rank,
                    "name": f"function_{index}",
                    "lineno": (index * 2) - 1,
                    "complexity": WEIGHTS[rank] + 1,
                }
                for index, rank in enumerate(ranks, start=1)
            ]
        },
    )


def _run_ratchet(
    root: Path,
    *,
    output: str = "reports/script-maintainability-ratchet.json",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(REPO_ROOT)
    )
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            ".",
            "--radon-cc",
            "reports/radon-scripts-cc.json",
            "--baseline",
            "docs/meta/script-maintainability-ratchet-baseline.json",
            "--output",
            output,
        ],
        check=False,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_help_documents_read_only_baseline_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--radon-cc" in result.stdout
    assert "--baseline" in result.stdout
    assert "--output" in result.stdout
    assert "immutable" in result.stdout


def test_quality_audit_dry_run_declares_script_maintainability_ratchet() -> None:
    result = subprocess.run(
        ["bash", str(QUALITY_AUDIT), "--dry-run"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (
        "script maintainability baseline: "
        "docs/meta/script-maintainability-ratchet-baseline.json"
    ) in result.stdout
    assert "Would run script maintainability ratchet" in result.stdout


def test_unchanged_and_independently_improved_metrics_pass_deterministically(
    tmp_path: Path,
) -> None:
    _prepare_repo(tmp_path, ranks=("B",), line_count=499)
    baseline_path = _write_json(
        tmp_path / "docs/meta/script-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                counts=_rank_counts(C=1),
                hotspots={"scripts/example.py": 500},
            )
        ),
    )
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    result = _run_ratchet(tmp_path)

    assert result.returncode == 0, result.stderr
    report = tmp_path / "reports/script-maintainability-ratchet.json"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["current"]["cyclomatic_complexity"]["weighted_score"] == 1
    assert payload["current"]["script_hotspots"]["count"] == 0
    assert payload["violations"] == []
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash

    first = report.read_bytes()
    second = _run_ratchet(
        tmp_path,
        output="reports/script-maintainability-ratchet-second.json",
    )
    assert second.returncode == 0, second.stderr
    assert (
        tmp_path / "reports/script-maintainability-ratchet-second.json"
    ).read_bytes() == first


@pytest.mark.parametrize(
    ("baseline_counts", "current_ranks", "expected"),
    [
        (_rank_counts(A=1), ("B",), "weighted score increased"),
        (_rank_counts(C=1), ("D",), "worst rank worsened"),
        (_rank_counts(F=1), ("F", "F"), "rank F count increased"),
    ],
)
def test_complexity_regressions_fail_with_ranked_path_evidence(
    tmp_path: Path,
    baseline_counts: dict[str, int],
    current_ranks: tuple[str, ...],
    expected: str,
) -> None:
    _prepare_repo(tmp_path, ranks=current_ranks)
    _write_json(
        tmp_path / "docs/meta/script-maintainability-ratchet-baseline.json",
        _baseline_payload(_metrics(counts=baseline_counts)),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    assert expected in result.stderr
    assert "scripts/example.py:" in result.stderr
    assert "rank" in result.stderr


def test_hotspot_growth_cannot_be_offset_by_another_script_shrinking(tmp_path: Path) -> None:
    _prepare_repo(tmp_path, ranks=("A",), line_count=501)
    _write_json(
        tmp_path / "docs/meta/script-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                counts=_rank_counts(A=1),
                hotspots={
                    "scripts/example.py": 500,
                    "scripts/removed.py": 700,
                },
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    assert "script_hotspots count increased" not in result.stderr
    assert "script_hotspots file grew: scripts/example.py 500 -> 501 lines" in result.stderr


def test_missing_radon_script_evidence_fails_closed(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    _write_json(tmp_path / "reports/radon-scripts-cc.json", {})
    _write_json(
        tmp_path / "docs/meta/script-maintainability-ratchet-baseline.json",
        _baseline_payload(_metrics(counts=_rank_counts(B=1))),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "must exactly match script code blocks" in result.stderr


def test_normal_audit_cannot_overwrite_the_tracked_baseline(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    baseline_path = _write_json(
        tmp_path / "docs/meta/script-maintainability-ratchet-baseline.json",
        _baseline_payload(_metrics(counts=_rank_counts(B=1))),
    )
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    result = _run_ratchet(
        tmp_path,
        output="docs/meta/script-maintainability-ratchet-baseline.json",
    )

    assert result.returncode == 2
    assert "tracked baseline" in result.stderr
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash


def test_tracked_baseline_records_current_accepted_scripts_anchor() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert payload["schema_version"] == (
        "entroping.script-maintainability-ratchet-baseline.v1"
    )
    assert payload["revision"] == 1
    assert payload["owner"] == "Entroping maintainers"
    assert payload["reviewed_on"] == "2026-08-09"
    assert payload["evidence"]["issue_url"].endswith("/issues/1533")
    assert payload["weights"] == WEIGHTS
    metrics = payload["metrics"]
    assert metrics["cyclomatic_complexity"]["rank_counts"] == _rank_counts(
        A=1987,
        B=491,
        C=209,
        D=28,
        E=3,
        F=6,
    )
    assert metrics["cyclomatic_complexity"]["worst_rank"] == "F"
    assert metrics["cyclomatic_complexity"]["weighted_score"] == 1507
    hotspots = metrics["script_hotspots"]
    assert hotspots["threshold_lines"] == 500
    assert hotspots["count"] == len(hotspots["files"]) == 14
    assert hotspots["files"]["scripts/pytest_collection_manifest.py"] >= 500
