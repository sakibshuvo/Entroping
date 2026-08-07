from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "source_maintainability_ratchet.py"
QUALITY_AUDIT = REPO_ROOT / "scripts" / "audit_quality.sh"
BASELINE = REPO_ROOT / "docs" / "meta" / "source-maintainability-ratchet-baseline.json"
WEIGHTS = {"A": 0, "B": 1, "C": 3, "D": 8, "E": 13, "F": 21}
Rank = Literal["A", "B", "C", "D", "E", "F"]


def _rank_counts(**overrides: int) -> dict[str, int]:
    counts = dict.fromkeys(WEIGHTS, 0)
    counts.update(overrides)
    return counts


def _metric_family(counts: dict[str, int]) -> dict[str, object]:
    worst_rank = next((rank for rank in reversed(WEIGHTS) if counts[rank]), "A")
    return {
        "rank_counts": counts,
        "weighted_score": sum(counts[rank] * WEIGHTS[rank] for rank in WEIGHTS),
        "worst_rank": worst_rank,
    }


def _metrics(
    *,
    cc: dict[str, int],
    mi: dict[str, int],
    hotspots: int = 0,
    hotspot_files: dict[str, int] | None = None,
) -> dict[str, object]:
    if hotspot_files is None:
        hotspot_files = {
            f"src/package/hotspot_{index}.py": 500 for index in range(hotspots)
        }
    return {
        "cyclomatic_complexity": _metric_family(cc),
        "maintainability_index": _metric_family(mi),
        "source_hotspots": {
            "threshold_lines": 500,
            "count": hotspots,
            "files": hotspot_files,
        },
    }


def _baseline_payload(metrics: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "entroping.source-maintainability-ratchet-baseline.v2",
        "revision": 1,
        "owner": "Entroping maintainers",
        "reviewed_on": "2026-07-17",
        "evidence": {
            "issue_url": "https://github.com/sakibshuvo/Entroping/issues/1504",
            "from_commit": "fe86f72f610eb1400109b4a73f03a66373125399",
            "through_commit": "c0ed9ddfe672fc72d5428e79d66e30a34cf760b8",
            "cc_command": "uv run radon cc src tests -s -a --json",
            "mi_command": "uv run radon mi src -s --json",
            "hotspot_definition": ("Python source files with at least 500 physical lines."),
        },
        "weights": WEIGHTS,
        "metrics": metrics,
    }


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _report_payload(
    *,
    baseline: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "entroping.source-maintainability-ratchet-report.v2",
        "baseline_revision": 1,
        "status": "passed",
        "baseline": baseline,
        "current": current,
        "violations": [],
        "contributors": [],
        "rebase_validation": None,
    }


def _evidence_artifact(path: Path, *, root: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _rebase_request(
    *,
    before: Path,
    after: Path,
    root: Path,
) -> dict[str, object]:
    return {
        "schema_version": "entroping.source-maintainability-rebase-request.v1",
        "current_revision": 1,
        "proposed_revision": 2,
        "issue_url": "https://github.com/sakibshuvo/Entroping/issues/1600",
        "pull_request_url": "https://github.com/sakibshuvo/Entroping/pull/1601",
        "rationale": "Record reviewed source-only improvements without weakening policy.",
        "before_evidence": _evidence_artifact(before, root=root),
        "after_evidence": _evidence_artifact(after, root=root),
    }


def _cc_entry(
    rank: Rank,
    *,
    name: str = "function",
    lineno: int = 1,
) -> dict[str, object]:
    return {
        "type": "function",
        "rank": rank,
        "name": name,
        "lineno": lineno,
        "complexity": WEIGHTS[rank] + 1,
    }


def _mi_entry(rank: Rank, *, mi: float = 80.0) -> dict[str, object]:
    return {"rank": rank, "mi": mi}


def _prepare_repo(
    root: Path,
    *,
    source_ranks: tuple[Rank, ...] = ("B",),
    mi_ranks: tuple[Rank, ...] = ("A",),
    source_lines: int = 1,
) -> None:
    source = root / "src" / "package" / "module.py"
    source.parent.mkdir(parents=True)
    source_content = "".join(
        f"def source_{index}(): return {index}\n" for index, _ in enumerate(source_ranks, start=1)
    )
    source_content += "# filler\n" * max(0, source_lines - len(source_content.splitlines()))
    source.write_text(source_content, encoding="utf-8")
    test = root / "tests" / "test_module.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_value() -> None:\n    assert True\n", encoding="utf-8")
    _write_json(
        root / "reports" / "radon-cc.json",
        {
            "src/package/module.py": [
                _cc_entry(rank, name=f"source_{index}", lineno=index)
                for index, rank in enumerate(source_ranks, start=1)
            ],
            "tests/test_module.py": [_cc_entry("F", name="excluded_test")],
        },
    )
    mi_payload: dict[str, object] = {}
    for index, rank in enumerate(mi_ranks):
        relative = (
            Path("src/package/module.py") if index == 0 else Path(f"src/package/mi_{index}.py")
        )
        if index > 0:
            extra_source = root / relative
            extra_source.write_text(f"value = {index}\n", encoding="utf-8")
        mi_payload[relative.as_posix()] = _mi_entry(rank)
    _write_json(
        root / "reports" / "radon-mi.json",
        mi_payload,
    )


def _prepare_hotspot_repo(root: Path, line_counts: dict[str, int]) -> None:
    cc_payload: dict[str, object] = {}
    mi_payload: dict[str, object] = {}
    for index, (relative, line_count) in enumerate(sorted(line_counts.items()), start=1):
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            f"def source_{index}(): return {index}\n" + "# filler\n" * (line_count - 1),
            encoding="utf-8",
        )
        cc_payload[relative] = [_cc_entry("A", name=f"source_{index}")]
        mi_payload[relative] = _mi_entry("A")
    test = root / "tests" / "test_module.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_value() -> None:\n    assert True\n", encoding="utf-8")
    cc_payload["tests/test_module.py"] = [_cc_entry("F", name="excluded_test")]
    _write_json(root / "reports" / "radon-cc.json", cc_payload)
    _write_json(root / "reports" / "radon-mi.json", mi_payload)


def _run_ratchet(
    root: Path,
    *,
    baseline: str = "docs/meta/source-maintainability-ratchet-baseline.json",
    output: str = "reports/source-maintainability-ratchet.json",
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO_ROOT)
    )
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            ".",
            "--radon-cc",
            "reports/radon-cc.json",
            "--radon-mi",
            "reports/radon-mi.json",
            "--baseline",
            baseline,
            "--output",
            output,
            *extra_args,
        ],
        check=False,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_source_maintainability_ratchet_help_documents_read_only_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--radon-cc" in result.stdout
    assert "--radon-mi" in result.stdout
    assert "--baseline" in result.stdout
    assert "--output" in result.stdout
    assert "--rebase-request" in result.stdout


def test_quality_audit_dry_run_declares_source_maintainability_ratchet() -> None:
    env = os.environ.copy()
    env["ENTROPING_SOURCE_MAINTAINABILITY_BASELINE"] = "reports/untrusted-baseline.json"
    result = subprocess.run(
        ["bash", str(QUALITY_AUDIT), "--dry-run"],
        check=False,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (
        "source maintainability baseline: docs/meta/source-maintainability-ratchet-baseline.json"
    ) in result.stdout
    assert "reports/untrusted-baseline.json" not in result.stdout
    assert "Would run source maintainability ratchet" in result.stdout


def test_tracked_baseline_records_the_accepted_source_only_anchor() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert payload["schema_version"] == ("entroping.source-maintainability-ratchet-baseline.v2")
    assert payload["revision"] == 2
    assert payload["owner"] == "Entroping maintainers"
    assert payload["reviewed_on"] == "2026-08-07"
    assert payload["weights"] == WEIGHTS
    assert payload["evidence"]["issue_url"].endswith("/issues/1546")
    assert payload["evidence"]["through_commit"] == ("f7515cc918d99ee9c288877456e33a38a69d73ca")
    assert payload["metrics"]["cyclomatic_complexity"] == _metric_family(
        _rank_counts(A=2959, B=485, C=139, D=10)
    )
    assert payload["metrics"]["maintainability_index"] == _metric_family(
        _rank_counts(A=196, B=27, C=24)
    )
    hotspots = payload["metrics"]["source_hotspots"]
    assert hotspots["threshold_lines"] == 500
    assert hotspots["count"] == len(hotspots["files"]) == 60
    assert hotspots["files"]["src/entroping/bridge/openapi_to_hurl/compiler.py"] == 1557
    assert hotspots["files"]["src/entroping/core/demo_runner.py"] == 505


def test_source_maintainability_ratchet_passes_unchanged_source_only_metrics(
    tmp_path: Path,
) -> None:
    _prepare_repo(tmp_path)
    baseline_path = _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    result = _run_ratchet(tmp_path)

    assert result.returncode == 0, result.stderr
    output_path = tmp_path / "reports" / "source-maintainability-ratchet.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["current"] == payload["baseline"]
    assert payload["current"]["cyclomatic_complexity"]["rank_counts"] == (_rank_counts(B=1))
    assert payload["violations"] == []
    assert payload["contributors"] == []
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash

    first = output_path.read_bytes()
    second = _run_ratchet(
        tmp_path,
        output="reports/source-maintainability-ratchet-second.json",
    )

    assert second.returncode == 0, second.stderr
    assert (
        tmp_path / "reports" / "source-maintainability-ratchet-second.json"
    ).read_bytes() == first


def test_source_maintainability_ratchet_passes_independent_improvements(
    tmp_path: Path,
) -> None:
    _prepare_repo(
        tmp_path,
        source_ranks=("B",),
        mi_ranks=("B",),
        source_lines=499,
    )
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(C=1),
                mi=_rank_counts(C=1),
                hotspots=1,
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(
        (tmp_path / "reports" / "source-maintainability-ratchet.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "passed"
    assert payload["current"]["cyclomatic_complexity"]["weighted_score"] == 1
    assert payload["current"]["maintainability_index"]["weighted_score"] == 1
    assert payload["current"]["source_hotspots"]["count"] == 0


def test_source_hotspot_growth_fails_when_count_is_unchanged(tmp_path: Path) -> None:
    relative = "src/package/module.py"
    _prepare_hotspot_repo(tmp_path, {relative: 501})
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(A=1),
                mi=_rank_counts(A=1),
                hotspots=1,
                hotspot_files={relative: 500},
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    assert "source_hotspots count increased" not in result.stderr
    assert f"source_hotspots file grew: {relative} 500 -> 501 lines" in result.stderr


def test_source_hotspot_shrink_does_not_mask_growth_in_another_file(tmp_path: Path) -> None:
    shrinking = "src/package/shrinking.py"
    growing = "src/package/growing.py"
    _prepare_hotspot_repo(tmp_path, {shrinking: 500, growing: 501})
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(A=2),
                mi=_rank_counts(A=2),
                hotspots=2,
                hotspot_files={shrinking: 501, growing: 500},
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    assert "source_hotspots count increased" not in result.stderr
    assert f"source_hotspots file grew: {growing} 500 -> 501 lines" in result.stderr
    assert f"source_hotspots file grew: {shrinking}" not in result.stderr


def test_source_hotspot_shrink_and_removal_pass(tmp_path: Path) -> None:
    retained = "src/package/retained.py"
    removed = "src/package/removed.py"
    _prepare_hotspot_repo(tmp_path, {retained: 500})
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(A=1),
                mi=_rank_counts(A=1),
                hotspots=2,
                hotspot_files={retained: 501, removed: 500},
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(
        (tmp_path / "reports" / "source-maintainability-ratchet.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["current"]["source_hotspots"]["files"] == {retained: 500}


@pytest.mark.parametrize(
    ("hotspots", "hotspot_files", "expected_message"),
    [
        (0, {"src/package/module.py": 500}, "count must match recorded files"),
        (1, {"tests/test_module.py": 500}, "outside the allowed scope"),
        (1, {"src/package/../module.py": 500}, "forbidden path alias"),
        (1, {"src/package/module.py": 499}, "line count is below 500"),
    ],
)
def test_source_hotspot_baseline_rejects_inconsistent_file_evidence(
    tmp_path: Path,
    hotspots: int,
    hotspot_files: dict[str, int],
    expected_message: str,
) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
                hotspots=hotspots,
                hotspot_files=hotspot_files,
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    (
        "baseline_metrics",
        "source_ranks",
        "mi_ranks",
        "source_lines",
        "expected_violation",
        "expected_contributor",
    ),
    [
        (
            _metrics(cc=_rank_counts(C=1), mi=_rank_counts(A=1)),
            ("D",),
            ("A",),
            1,
            "cyclomatic_complexity rank D count increased",
            "contributor: cc:",
        ),
        (
            _metrics(cc=_rank_counts(B=1, C=1), mi=_rank_counts(A=1)),
            ("C", "C"),
            ("A",),
            1,
            "cyclomatic_complexity weighted score increased",
            "contributor: cc:",
        ),
        (
            _metrics(cc=_rank_counts(A=1), mi=_rank_counts(C=1)),
            ("A",),
            ("D",),
            1,
            "maintainability_index rank D count increased",
            "contributor: mi:",
        ),
        (
            _metrics(cc=_rank_counts(A=1), mi=_rank_counts(B=1, C=1)),
            ("A",),
            ("C", "C"),
            1,
            "maintainability_index weighted score increased",
            "contributor: mi:",
        ),
        (
            _metrics(cc=_rank_counts(A=1), mi=_rank_counts(A=1)),
            ("A",),
            ("A",),
            500,
            "source_hotspots count increased",
            "contributor: hotspot:",
        ),
        (
            _metrics(cc=_rank_counts(D=1), mi=_rank_counts(B=1)),
            ("A",),
            ("C",),
            1,
            "maintainability_index weighted score increased",
            "contributor: mi:",
        ),
    ],
)
def test_source_maintainability_ratchet_fails_each_protected_worsening(
    tmp_path: Path,
    baseline_metrics: dict[str, object],
    source_ranks: tuple[Rank, ...],
    mi_ranks: tuple[Rank, ...],
    source_lines: int,
    expected_violation: str,
    expected_contributor: str,
) -> None:
    _prepare_repo(
        tmp_path,
        source_ranks=source_ranks,
        mi_ranks=mi_ranks,
        source_lines=source_lines,
    )
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(baseline_metrics),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    assert expected_violation in result.stderr
    assert expected_contributor in result.stderr
    payload = json.loads(
        (tmp_path / "reports" / "source-maintainability-ratchet.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "regressed"


def test_normal_audit_cannot_overwrite_the_tracked_baseline(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    baseline_path = _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    result = _run_ratchet(
        tmp_path,
        output="docs/meta/source-maintainability-ratchet-baseline.json",
    )

    assert result.returncode == 2
    assert "tracked baseline" in result.stderr
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash


def test_alternate_baseline_cannot_overwrite_the_tracked_baseline(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    metrics = _metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))
    tracked = _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(metrics),
    )
    alternate = _write_json(
        tmp_path / "reviews" / "alternate-baseline.json",
        _baseline_payload(metrics),
    )
    tracked_hash = hashlib.sha256(tracked.read_bytes()).hexdigest()

    result = _run_ratchet(
        tmp_path,
        baseline=alternate.relative_to(tmp_path).as_posix(),
        output=tracked.relative_to(tmp_path).as_posix(),
    )

    assert result.returncode == 2
    assert "tracked baseline" in result.stderr
    assert hashlib.sha256(tracked.read_bytes()).hexdigest() == tracked_hash


def test_normal_audit_rejects_an_alternate_baseline(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    metrics = _metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(metrics),
    )
    alternate = _write_json(
        tmp_path / "reviews" / "alternate-baseline.json",
        _baseline_payload(metrics),
    )

    result = _run_ratchet(
        tmp_path,
        baseline=alternate.relative_to(tmp_path).as_posix(),
    )

    assert result.returncode == 2
    assert "tracked baseline" in result.stderr
    assert not (tmp_path / "reports" / "source-maintainability-ratchet.json").exists()


@pytest.mark.parametrize(
    "output",
    (
        "reports/radon-cc.json",
        "reports/radon-mi.json",
        "src/package/module.py",
    ),
)
def test_output_cannot_overwrite_measurement_inputs_or_source(
    tmp_path: Path,
    output: str,
) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(_metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))),
    )
    protected = tmp_path / output
    protected_hash = hashlib.sha256(protected.read_bytes()).hexdigest()

    result = _run_ratchet(tmp_path, output=output)

    assert result.returncode == 2
    assert "output" in result.stderr
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == protected_hash


@pytest.mark.parametrize(
    "protected",
    (
        "reports/radon-cc.json",
        "src/package/module.py",
    ),
)
def test_output_hardlink_cannot_alias_measurement_inputs_or_source(
    tmp_path: Path,
    protected: str,
) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(_metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))),
    )
    protected_path = tmp_path / protected
    protected_hash = hashlib.sha256(protected_path.read_bytes()).hexdigest()
    output = tmp_path / "reports" / "source-maintainability-alias.json"
    os.link(protected_path, output)

    result = _run_ratchet(
        tmp_path,
        output=output.relative_to(tmp_path).as_posix(),
    )

    assert result.returncode == 2
    assert "output" in result.stderr
    assert hashlib.sha256(protected_path.read_bytes()).hexdigest() == protected_hash


@pytest.mark.parametrize(
    "protected",
    (
        "reviews/rebase.json",
        "reviews/before.json",
        "reviews/after.json",
    ),
)
def test_output_hardlink_cannot_alias_rebase_inputs(
    tmp_path: Path,
    protected: str,
) -> None:
    metrics = _metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(metrics),
    )
    before = _write_json(
        tmp_path / "reviews" / "before.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    after = _write_json(
        tmp_path / "reviews" / "after.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    _write_json(
        tmp_path / "reviews" / "rebase.json",
        _rebase_request(before=before, after=after, root=tmp_path),
    )
    protected_path = tmp_path / protected
    protected_hash = hashlib.sha256(protected_path.read_bytes()).hexdigest()
    output = tmp_path / "reports" / "source-maintainability-alias.json"
    os.link(protected_path, output)

    result = _run_ratchet(
        tmp_path,
        output=output.relative_to(tmp_path).as_posix(),
        extra_args=("--rebase-request", "reviews/rebase.json"),
    )

    assert result.returncode == 2
    assert "output" in result.stderr
    assert hashlib.sha256(protected_path.read_bytes()).hexdigest() == protected_hash


def test_regression_report_names_each_violated_metric_family(tmp_path: Path) -> None:
    _prepare_repo(
        tmp_path,
        source_ranks=("D",) * 25,
        mi_ranks=("D",),
        source_lines=500,
    )
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(A=1),
                mi=_rank_counts(A=1),
            )
        ),
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 1
    report = json.loads(
        (tmp_path / "reports" / "source-maintainability-ratchet.json").read_text(encoding="utf-8")
    )
    contributors = report["contributors"]
    assert len(contributors) <= 20
    assert any(item.startswith("cc:") for item in contributors)
    assert any(item.startswith("mi:") for item in contributors)
    assert any(item.startswith("hotspot:") for item in contributors)


def test_reviewed_rebase_validates_improvement_evidence_without_writing_baseline(
    tmp_path: Path,
) -> None:
    baseline_metrics = _metrics(
        cc=_rank_counts(C=1),
        mi=_rank_counts(C=1),
    )
    current_metrics = _metrics(
        cc=_rank_counts(B=1),
        mi=_rank_counts(B=1),
    )
    _prepare_repo(tmp_path, source_ranks=("B",), mi_ranks=("B",))
    baseline_path = _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(baseline_metrics),
    )
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    before = _write_json(
        tmp_path / "reviews" / "before.json",
        _report_payload(baseline=baseline_metrics, current=baseline_metrics),
    )
    after = _write_json(
        tmp_path / "reviews" / "after.json",
        _report_payload(baseline=baseline_metrics, current=current_metrics),
    )
    _write_json(
        tmp_path / "reviews" / "rebase.json",
        _rebase_request(before=before, after=after, root=tmp_path),
    )

    result = _run_ratchet(
        tmp_path,
        extra_args=("--rebase-request", "reviews/rebase.json"),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(
        (tmp_path / "reports" / "source-maintainability-ratchet.json").read_text(encoding="utf-8")
    )
    assert payload["rebase_validation"] == {
        "after_evidence": "reviews/after.json",
        "before_evidence": "reviews/before.json",
        "current_revision": 1,
        "issue_url": "https://github.com/sakibshuvo/Entroping/issues/1600",
        "proposed_revision": 2,
        "pull_request_url": "https://github.com/sakibshuvo/Entroping/pull/1601",
        "status": "passed",
    }
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == baseline_hash


def test_rebase_rejects_protected_worsening_even_with_complete_review_metadata(
    tmp_path: Path,
) -> None:
    baseline_metrics = _metrics(
        cc=_rank_counts(C=1),
        mi=_rank_counts(A=1),
    )
    current_metrics = _metrics(
        cc=_rank_counts(D=1),
        mi=_rank_counts(A=1),
    )
    _prepare_repo(tmp_path, source_ranks=("D",), mi_ranks=("A",))
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(baseline_metrics),
    )
    before = _write_json(
        tmp_path / "reviews" / "before.json",
        _report_payload(baseline=baseline_metrics, current=baseline_metrics),
    )
    after = _write_json(
        tmp_path / "reviews" / "after.json",
        _report_payload(baseline=baseline_metrics, current=current_metrics),
    )
    _write_json(
        tmp_path / "reviews" / "rebase.json",
        _rebase_request(before=before, after=after, root=tmp_path),
    )

    result = _run_ratchet(
        tmp_path,
        extra_args=("--rebase-request", "reviews/rebase.json"),
    )

    assert result.returncode == 2
    assert "rebase evidence contains protected worsening" in result.stderr
    assert not (tmp_path / "reports" / "source-maintainability-ratchet.json").exists()


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        (
            "issue_url",
            "https://github.com/sakibshuvo/Entroping/issues/1504",
            "dedicated issue",
        ),
        ("pull_request_url", "not-a-pull-request", "pull_request_url"),
        ("rationale", "too short", "at least 20 characters"),
        ("proposed_revision", 3, "increment current_revision"),
    ],
)
def test_rebase_requires_dedicated_complete_review_metadata(
    tmp_path: Path,
    field: str,
    value: str | int,
    expected_message: str,
) -> None:
    metrics = _metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(metrics),
    )
    before = _write_json(
        tmp_path / "reviews" / "before.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    after = _write_json(
        tmp_path / "reviews" / "after.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    request = _rebase_request(before=before, after=after, root=tmp_path)
    request[field] = value
    _write_json(tmp_path / "reviews" / "rebase.json", request)

    result = _run_ratchet(
        tmp_path,
        extra_args=("--rebase-request", "reviews/rebase.json"),
    )

    assert result.returncode == 2
    assert expected_message in result.stderr


def test_validation_error_does_not_echo_rebase_input_values(tmp_path: Path) -> None:
    marker = "PRIVATE-MARKER"
    metrics = _metrics(cc=_rank_counts(B=1), mi=_rank_counts(A=1))
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(metrics),
    )
    before = _write_json(
        tmp_path / "reviews" / "before.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    after = _write_json(
        tmp_path / "reviews" / "after.json",
        _report_payload(baseline=metrics, current=metrics),
    )
    request = _rebase_request(before=before, after=after, root=tmp_path)
    request["current_revision"] = marker
    _write_json(tmp_path / "reviews" / "rebase.json", request)

    result = _run_ratchet(
        tmp_path,
        extra_args=("--rebase-request", "reviews/rebase.json"),
    )

    assert result.returncode == 2
    assert marker not in result.stderr
    assert "Traceback" not in result.stderr


def test_baseline_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    marker = "PRIVATE-MARKER"
    _prepare_repo(tmp_path)
    baseline_path = _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    content = baseline_path.read_text(encoding="utf-8")
    baseline_path.write_text(
        content.replace(
            '"revision": 1',
            f'"revision": 1, "{marker}": 1, "{marker}": 2',
            1,
        ),
        encoding="utf-8",
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "duplicate JSON key is forbidden" in result.stderr
    assert marker not in result.stderr


def test_boundary_rejects_excessive_json_nesting_without_a_traceback(
    tmp_path: Path,
) -> None:
    _prepare_repo(tmp_path)
    baseline_path = tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "invalid json" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_boundary_rejects_non_finite_radon_numbers(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    (tmp_path / "reports" / "radon-mi.json").write_text(
        '{"src/package/module.py":{"rank":"A","mi":NaN}}\n',
        encoding="utf-8",
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "non-finite JSON number is forbidden" in result.stderr


def test_boundary_rejects_overflowing_radon_numbers(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    (tmp_path / "reports" / "radon-mi.json").write_text(
        '{"src/package/module.py":{"rank":"A","mi":1e309}}\n',
        encoding="utf-8",
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "non-finite Radon MI value" in result.stderr


@pytest.mark.parametrize("digits", (400, 5_000))
def test_boundary_rejects_oversized_integer_without_a_traceback(
    tmp_path: Path,
    digits: int,
) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    (tmp_path / "reports" / "radon-mi.json").write_text(
        '{"src/package/module.py":{"rank":"A","mi":' + "9" * digits + "}}\n",
        encoding="utf-8",
    )

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "JSON integer exceeds safe digit limit" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("report_name", ["radon-cc.json", "radon-mi.json"])
def test_boundary_rejects_missing_radon_source_evidence(
    tmp_path: Path,
    report_name: str,
) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    _write_json(tmp_path / "reports" / report_name, {})

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "must include source evidence" in result.stderr


def test_boundary_rejects_incomplete_radon_cc_block_evidence(tmp_path: Path) -> None:
    _prepare_repo(tmp_path, source_ranks=("A", "D"))
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(A=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    cc_path = tmp_path / "reports" / "radon-cc.json"
    payload = json.loads(cc_path.read_text(encoding="utf-8"))
    payload["src/package/module.py"] = payload["src/package/module.py"][:1]
    _write_json(cc_path, payload)

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "must exactly match source code blocks" in result.stderr


def test_boundary_rejects_duplicate_radon_cc_block_evidence(tmp_path: Path) -> None:
    _prepare_repo(tmp_path)
    _write_json(
        tmp_path / "docs" / "meta" / "source-maintainability-ratchet-baseline.json",
        _baseline_payload(
            _metrics(
                cc=_rank_counts(B=1),
                mi=_rank_counts(A=1),
            )
        ),
    )
    cc_path = tmp_path / "reports" / "radon-cc.json"
    payload = json.loads(cc_path.read_text(encoding="utf-8"))
    payload["src/package/module.py"].append(payload["src/package/module.py"][0])
    _write_json(cc_path, payload)

    result = _run_ratchet(tmp_path)

    assert result.returncode == 2
    assert "duplicate Radon CC block evidence" in result.stderr
