#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from entroping.core.bounded_read import BoundedReadError, read_text_bounded
from entroping.core.safe_write import safe_write_text

SCHEMA_VERSION = "entroping.script-quality-report.v1"
GENERATED_BY = "scripts/script_quality_report.py"
SCRIPT_TEST_PATTERNS = (
    "test_*script*.py",
    "test_doc_governance_script.py",
    "test_factory_inbox.py",
    "test_factory_review_packet.py",
    "test_package_index_readiness.py",
    "test_pytest_collection_manifest.py",
    "test_release_evidence.py",
    "test_source_maintainability_ratchet.py",
)
SCRIPT_SOURCE_MAX_BYTES = 1_000_000
JSON_MAX_BYTES = 10_000_000
SCRIPT_COVERAGE_TIMEOUT_SECONDS = 600
SCRIPT_COVERAGE_CONFIG = Path("docs/meta/script-coverage.ini")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a script quality visibility report without touching coverage config."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/script-quality-report.json"),
        help="JSON output path for the script quality report.",
    )
    parser.add_argument(
        "--coverage-output",
        type=Path,
        default=Path("reports/script-coverage.json"),
        help="JSON coverage output path for temporary pytest-cov artifacts.",
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        help="Use existing coverage JSON and skip running pytest.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help=(
            "Optional baseline report path for ratchet comparison."
            " Omit to run no-baseline behavior."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without running coverage or writing output.",
    )
    return parser.parse_args(argv)


def _collect_script_files(script_root: Path) -> tuple[Path, ...]:
    if not script_root.is_dir():
        return ()
    files: list[Path] = []
    for path in sorted(script_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(script_root).parts):
            continue
        if path.suffix != ".py":
            continue
        files.append(path)
    return tuple(files)


def _collect_script_inventory(root: Path) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for path in sorted(_collect_script_files(root / "scripts")):
        relative = path.relative_to(root).as_posix()
        try:
            source = read_text_bounded(
                path,
                max_bytes=SCRIPT_SOURCE_MAX_BYTES,
                label="script source",
            )
            ast.parse(source, filename=relative)
            inventory.append({"path": relative, "kind": "importable"})
        except (BoundedReadError, SyntaxError):
            inventory.append(
                {
                    "path": relative,
                    "kind": "non_importable",
                    "reason": "unparseable script",
                }
            )
    return inventory


def _discover_script_tests(tests_root: Path) -> tuple[Path, ...]:
    if not tests_root.is_dir():
        return ()
    discovered: set[Path] = set()
    for pattern in SCRIPT_TEST_PATTERNS:
        discovered.update(tests_root.glob(pattern))
    return tuple(sorted(discovered))


def _run_script_coverage(
    root: Path,
    coverage_output: Path,
    script_tests: tuple[Path, ...],
) -> Path:
    if not script_tests:
        raise RuntimeError("No script-focused tests found; run with --coverage-json or add tests.")

    if not coverage_output.is_absolute():
        coverage_output = root / coverage_output
    coverage_output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "pytest",
        "--cov=scripts",
        f"--cov-config={(root / SCRIPT_COVERAGE_CONFIG).as_posix()}",
        f"--cov-report=json:{coverage_output.as_posix()}",
        "--cov-report=term-missing",
        *(str(path) for path in script_tests),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root / 'src'}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        command,
        cwd=str(root),
        env=env,
        text=True,
        capture_output=True,
        timeout=SCRIPT_COVERAGE_TIMEOUT_SECONDS,
        # nosec B603: fixed argv, shell disabled, bounded by timeout.
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"pytest script coverage failed with exit code {result.returncode}")
    if not coverage_output.exists():
        raise RuntimeError(f"coverage output not produced: {coverage_output}")
    return coverage_output


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            read_text_bounded(path, max_bytes=JSON_MAX_BYTES, label="script quality JSON")
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON file: {path}") from exc
    except BoundedReadError as exc:
        raise RuntimeError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected JSON structure in {path}")
    return payload


def _build_script_coverage(
    root: Path,
    payload: dict[str, Any],
    script_files: tuple[Path, ...],
) -> dict[str, object]:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("coverage JSON missing files map")

    per_file: list[dict[str, object]] = []
    total_statements = 0
    total_covered = 0
    total_missing = 0

    for path in sorted(script_files):
        key = path.relative_to(root).as_posix()
        file_payload = files.get(key)
        if file_payload is None:
            file_payload = files.get(str(path.resolve()))
        if not isinstance(file_payload, dict):
            summary = {
                "path": key,
                "statements": 0,
                "covered_lines": 0,
                "missing_lines": 0,
                "percent_covered": 0.0,
            }
        else:
            raw_summary = file_payload.get("summary", {})
            if not isinstance(raw_summary, dict):
                raw_summary = {}
            statements = int(raw_summary.get("num_statements", 0) or 0)
            covered = int(raw_summary.get("covered_lines", 0) or 0)
            missing = int(raw_summary.get("missing_lines", 0) or 0)
            percent = float(raw_summary.get("percent_covered", 0.0) or 0.0)
            summary = {
                "path": key,
                "statements": statements,
                "covered_lines": covered,
                "missing_lines": missing,
                "percent_covered": round(percent, 2),
            }
            total_statements += statements
            total_covered += covered
            total_missing += missing

        per_file.append(summary)

    percent_covered = 0.0
    if total_statements:
        percent_covered = (total_covered / float(total_statements)) * 100.0

    return {
        "percent_covered": round(percent_covered, 2),
        "covered_lines": total_covered,
        "missing_lines": total_missing,
        "statements": total_statements,
        "files": per_file,
    }


def _function_has_annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = node.args
    signature_args = [
        *args.posonlyargs,
        *args.args,
        *args.kwonlyargs,
    ]
    if args.vararg is not None:
        signature_args.append(args.vararg)
    if args.kwarg is not None:
        signature_args.append(args.kwarg)
    if any(argument.annotation is None for argument in signature_args):
        return False
    return node.returns is not None


def _build_typing_metrics(script_files: tuple[Path, ...], root: Path) -> dict[str, object]:
    file_metrics: list[dict[str, object]] = []
    typed_functions = 0
    total_functions = 0

    for path in sorted(script_files):
        source = read_text_bounded(
            path,
            max_bytes=SCRIPT_SOURCE_MAX_BYTES,
            label="script source",
        )
        tree = ast.parse(source, filename=path.as_posix())
        local_typed = 0
        local_total = 0
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            local_total += 1
            if _function_has_annotations(node):
                local_typed += 1
                typed_functions += 1
            total_functions += 1

        file_metrics.append(
            {
                "path": path.relative_to(root).as_posix(),
                "typed_functions": local_typed,
                "total_functions": local_total,
            }
        )

    percent = 0.0 if total_functions == 0 else (typed_functions / float(total_functions)) * 100.0
    return {
        "typed_functions": typed_functions,
        "total_functions": total_functions,
        "function_annotation_coverage_percent": round(percent, 2),
        "files": file_metrics,
    }


def _baseline_value(payload: dict[str, object], *keys: str) -> float | None:
    value: object = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _baseline_script_paths(payload: dict[str, object]) -> tuple[str, ...] | None:
    raw_paths = payload.get("script_paths")
    if raw_paths is None:
        ratchet = payload.get("ratchet")
        if isinstance(ratchet, dict):
            raw_paths = ratchet.get("script_paths")
    if raw_paths is None:
        return None
    if not isinstance(raw_paths, list) or not raw_paths:
        raise RuntimeError("baseline report has invalid script_paths")
    paths: list[str] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or raw_path.strip() == "":
            raise RuntimeError("baseline report has invalid script_paths")
        paths.append(raw_path)
    return tuple(dict.fromkeys(paths))


def _baseline_deferred_script_paths(payload: dict[str, object]) -> tuple[str, ...]:
    raw_paths = payload.get("deferred_subprocess_covered_scripts", [])
    if not isinstance(raw_paths, list):
        raise RuntimeError("baseline report has invalid deferred_subprocess_covered_scripts")
    paths: list[str] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or raw_path.strip() == "":
            raise RuntimeError("baseline report has invalid deferred_subprocess_covered_scripts")
        paths.append(raw_path)
    return tuple(dict.fromkeys(paths))


def _int_metric(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _float_metric(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _file_metrics_by_path(report: dict[str, object], section: str) -> dict[str, dict[str, object]]:
    raw_section = report.get(section)
    if not isinstance(raw_section, dict):
        raise RuntimeError(f"script quality report missing {section} section")
    raw_files = raw_section.get("files")
    if not isinstance(raw_files, list):
        raise RuntimeError(f"script quality report missing {section} files")
    files: dict[str, dict[str, object]] = {}
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        path = raw_file.get("path")
        if isinstance(path, str):
            files[path] = raw_file
    return files


def _has_file_metrics(report: dict[str, object], section: str) -> bool:
    raw_section = report.get(section)
    if not isinstance(raw_section, dict):
        return False
    return isinstance(raw_section.get("files"), list)


def _coverage_for_script_paths(
    report: dict[str, object],
    script_paths: tuple[str, ...],
) -> dict[str, object]:
    files = _file_metrics_by_path(report, "coverage")
    missing_paths = [path for path in script_paths if path not in files]
    if missing_paths:
        raise RuntimeError(
            "script quality ratchet path missing from coverage report: "
            + ", ".join(missing_paths)
        )

    selected = [files[path] for path in script_paths]
    statements = sum(_int_metric(file, "statements") for file in selected)
    covered = sum(_int_metric(file, "covered_lines") for file in selected)
    missing = sum(_int_metric(file, "missing_lines") for file in selected)
    percent = 0.0 if statements == 0 else (covered / float(statements)) * 100.0
    return {
        "percent_covered": round(percent, 2),
        "covered_lines": covered,
        "missing_lines": missing,
        "statements": statements,
    }


def _typing_for_script_paths(
    report: dict[str, object],
    script_paths: tuple[str, ...],
) -> dict[str, object]:
    files = _file_metrics_by_path(report, "typing")
    missing_paths = [path for path in script_paths if path not in files]
    if missing_paths:
        raise RuntimeError(
            "script quality ratchet path missing from typing report: "
            + ", ".join(missing_paths)
        )

    selected = [files[path] for path in script_paths]
    typed_functions = sum(_int_metric(file, "typed_functions") for file in selected)
    total_functions = sum(_int_metric(file, "total_functions") for file in selected)
    percent = (
        0.0
        if total_functions == 0
        else (typed_functions / float(total_functions)) * 100.0
    )
    return {
        "typed_functions": typed_functions,
        "total_functions": total_functions,
        "function_annotation_coverage_percent": round(percent, 2),
    }


def _coverage_file_deltas(
    report: dict[str, object],
    baseline: dict[str, object],
    script_paths: tuple[str, ...],
) -> tuple[list[dict[str, object]], list[str]]:
    if not _has_file_metrics(baseline, "coverage"):
        return [], []

    current_files = _file_metrics_by_path(report, "coverage")
    baseline_files = _file_metrics_by_path(baseline, "coverage")
    missing_paths = [
        path for path in script_paths if path not in current_files or path not in baseline_files
    ]
    if missing_paths:
        raise RuntimeError(
            "script quality ratchet path missing from per-file coverage: "
            + ", ".join(missing_paths)
        )

    deltas: list[dict[str, object]] = []
    regressed_paths: list[str] = []
    for path in script_paths:
        current_percent = _float_metric(current_files[path], "percent_covered")
        baseline_percent = _float_metric(baseline_files[path], "percent_covered")
        delta = round(current_percent - baseline_percent, 2)
        status = "regressed" if delta < 0 else "passed"
        if status == "regressed":
            regressed_paths.append(path)
        deltas.append(
            {
                "path": path,
                "baseline_percent_covered": round(baseline_percent, 2),
                "current_percent_covered": round(current_percent, 2),
                "coverage_delta": delta,
                "status": status,
            }
        )
    return deltas, regressed_paths


def _run_ratchet(
    report: dict[str, object],
    baseline_path: Path | None,
) -> dict[str, object]:
    if baseline_path is None:
        return {
            "enabled": False,
            "status": "not_configured",
            "baseline_path": None,
            "coverage_delta": None,
            "typing_delta": None,
        }

    baseline_payload = _read_json(baseline_path)
    script_paths = _baseline_script_paths(baseline_payload)
    deferred_script_paths = _baseline_deferred_script_paths(baseline_payload)
    if script_paths is not None:
        overlap = sorted(set(script_paths) & set(deferred_script_paths))
        if overlap:
            raise RuntimeError(
                "baseline report classifies scripts as both selected and deferred: "
                + ", ".join(overlap)
            )
    scope = "all_scripts"
    current_coverage_summary: dict[str, object] | None = None
    current_typing_summary: dict[str, object] | None = None
    baseline_coverage_summary: dict[str, object] | None = None
    baseline_typing_summary: dict[str, object] | None = None
    coverage_files: list[dict[str, object]] = []
    regressed_script_paths: list[str] = []
    if script_paths is None:
        current_coverage = _baseline_value(report, "coverage", "percent_covered")
        current_typing = _baseline_value(
            report,
            "typing",
            "function_annotation_coverage_percent",
        )
    else:
        scope = "selected_scripts"
        current_coverage_summary = _coverage_for_script_paths(report, script_paths)
        current_typing_summary = _typing_for_script_paths(report, script_paths)
        if _has_file_metrics(baseline_payload, "coverage"):
            baseline_coverage_summary = _coverage_for_script_paths(baseline_payload, script_paths)
        if _has_file_metrics(baseline_payload, "typing"):
            baseline_typing_summary = _typing_for_script_paths(baseline_payload, script_paths)
        coverage_files, regressed_script_paths = _coverage_file_deltas(
            report,
            baseline_payload,
            script_paths,
        )
        current_coverage = _baseline_value(current_coverage_summary, "percent_covered")
        current_typing = _baseline_value(
            current_typing_summary,
            "function_annotation_coverage_percent",
        )
    if baseline_coverage_summary is None:
        baseline_coverage = _baseline_value(
            baseline_payload,
            "coverage",
            "percent_covered",
        )
    else:
        baseline_coverage = _baseline_value(
            baseline_coverage_summary,
            "percent_covered",
        )
    if baseline_typing_summary is None:
        baseline_typing = _baseline_value(
            baseline_payload,
            "typing",
            "function_annotation_coverage_percent",
        )
    else:
        baseline_typing = _baseline_value(
            baseline_typing_summary,
            "function_annotation_coverage_percent",
        )

    if current_coverage is None or baseline_coverage is None:
        raise RuntimeError("baseline report is missing coverage percent")

    coverage_delta = round(current_coverage - baseline_coverage, 2)
    typing_delta = (
        round(current_typing - baseline_typing, 2)
        if current_typing is not None and baseline_typing is not None
        else None
    )

    status = "passed"
    if (
        coverage_delta < 0
        or regressed_script_paths
        or (typing_delta is not None and typing_delta < 0)
    ):
        status = "regressed"

    return {
        "enabled": True,
        "status": status,
        "baseline_path": str(baseline_path),
        "scope": scope,
        "script_paths": list(script_paths) if script_paths is not None else None,
        "deferred_script_paths": list(deferred_script_paths),
        "coverage": current_coverage_summary,
        "coverage_files": coverage_files,
        "regressed_script_paths": regressed_script_paths,
        "typing": current_typing_summary,
        "coverage_delta": coverage_delta,
        "typing_delta": typing_delta,
    }


def _build_governance_populations(report: dict[str, object]) -> dict[str, object]:
    ratchet = report.get("ratchet")
    if not isinstance(ratchet, dict):
        raise RuntimeError("script quality report missing ratchet section")
    raw_selected = ratchet.get("script_paths")
    raw_deferred = ratchet.get("deferred_script_paths")
    selected_paths = [path for path in raw_selected or [] if isinstance(path, str)]
    deferred_paths = [path for path in raw_deferred or [] if isinstance(path, str)]

    coverage_files = _file_metrics_by_path(report, "coverage")
    aggregate_paths = list(coverage_files)
    classified_paths = [*selected_paths, *deferred_paths]
    missing_paths = [path for path in classified_paths if path not in coverage_files]
    if missing_paths:
        raise RuntimeError(
            "script quality governance path missing from aggregate inventory: "
            + ", ".join(missing_paths)
        )
    covered_paths = [
        path
        for path, metrics in coverage_files.items()
        if _int_metric(metrics, "covered_lines") > 0
    ]

    def population(paths: list[str]) -> dict[str, object]:
        return {"count": len(paths), "script_paths": paths}

    return {
        "selected": population(selected_paths),
        "deferred": population(deferred_paths),
        "covered": population(covered_paths),
        "aggregate": population(aggregate_paths),
    }


def _build_report(
    root: Path,
    coverage_payload: dict[str, Any],
    script_tests: tuple[Path, ...],
    baseline_path: Path | None,
) -> dict[str, object]:
    inventory = _collect_script_inventory(root)
    script_file_list: list[Path] = []
    for item in inventory:
        path = item.get("path")
        if item.get("kind") == "importable" and isinstance(path, str):
            script_file_list.append(root / path)
    script_files = tuple(script_file_list)
    importable = [item for item in inventory if item.get("kind") == "importable"]
    non_importable = [item for item in inventory if item.get("kind") != "importable"]

    coverage = _build_script_coverage(root, coverage_payload, script_files)
    typing = _build_typing_metrics(script_files, root)
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "script_file_count": len(importable) + len(non_importable),
        "script_python_file_count": len(importable),
        "script_non_python_file_count": len(non_importable),
        "script_tests": {
            "file_count": len(script_tests),
            "files": [path.relative_to(root).as_posix() for path in script_tests],
        },
        "coverage": coverage,
        "typing": typing,
        "non_importable_scripts": non_importable,
    }
    report["ratchet"] = _run_ratchet(report=report, baseline_path=baseline_path)
    report["governance"] = _build_governance_populations(report)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.repo_root.expanduser().resolve()
    output = args.output
    if not output.is_absolute():
        output = root / output
    coverage_output = args.coverage_output
    if not coverage_output.is_absolute():
        coverage_output = root / coverage_output
    baseline_path = (
        args.baseline.expanduser().resolve()
        if args.baseline is not None
        else None
    )
    script_tests = _discover_script_tests(root / "tests")
    if args.dry_run:
        print("Script quality report dry run:")
        print(f"  repository root: {root}")
        print(f"  output: {output}")
        print(f"  script coverage output: {coverage_output}")
        print(f"  subprocess coverage config: {root / SCRIPT_COVERAGE_CONFIG}")
        print(f"  baseline: {baseline_path if baseline_path is not None else 'not configured'}")
        print(f"  discovered script tests: {len(script_tests)}")
        if script_tests:
            for test in script_tests:
                print(f"  - {test.relative_to(root).as_posix()}")
        print("  Would run pytest --cov=scripts for script-focused test files.")
        print("  Would write machine-readable JSON report under reports/.")
        print("  Would fail only when baseline configured and metrics regressed.")
        return 0

    if args.coverage_json is not None:
        coverage_payload = _read_json(args.coverage_json.expanduser())
    else:
        coverage_path = _run_script_coverage(
            root=root,
            coverage_output=coverage_output,
            script_tests=tuple(script_tests),
        )
        coverage_payload = _read_json(coverage_path)

    report = _build_report(
        root=root,
        coverage_payload=coverage_payload,
        script_tests=tuple(script_tests),
        baseline_path=baseline_path,
    )
    safe_write_text(
        output,
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        artifact="script quality report",
        root=root,
    )

    coverage = report["coverage"]
    typing = report["typing"]
    ratchet = report["ratchet"]
    if (
        not isinstance(coverage, dict)
        or not isinstance(typing, dict)
        or not isinstance(ratchet, dict)
    ):
        raise RuntimeError("invalid report composition")

    print(f"Wrote script quality report: {output}")
    print(
        "Aggregate script coverage:",
        f"{coverage['percent_covered']}%",
        f"({coverage['covered_lines']}/{coverage['statements']} statements)",
    )
    selected_coverage = ratchet.get("coverage")
    if isinstance(selected_coverage, dict):
        print(
            "Selected ratchet coverage:",
            f"{selected_coverage['percent_covered']}%",
            (
                f"({selected_coverage['covered_lines']}/"
                f"{selected_coverage['statements']} statements)"
            ),
        )
    governance = report.get("governance")
    if not isinstance(governance, dict):
        raise RuntimeError("script quality report missing governance section")
    population_counts: dict[str, int] = {}
    for name in ("selected", "deferred", "covered", "aggregate"):
        value = governance.get(name)
        if not isinstance(value, dict):
            raise RuntimeError(f"script quality report missing {name} population")
        population_counts[name] = _int_metric(value, "count")
    print(
        "Script governance populations:",
        f"selected={population_counts['selected']}",
        f"deferred={population_counts['deferred']}",
        f"covered={population_counts['covered']}",
        f"aggregate={population_counts['aggregate']}",
    )
    print(
        "Function typing visibility:",
        f"{typing['function_annotation_coverage_percent']}%",
        f"({typing['typed_functions']}/{typing['total_functions']})",
    )
    print(f"Ratchet status: {ratchet['status']}")

    if ratchet["status"] == "regressed":
        print(
            "Script quality ratchet failed: coverage or typing visibility regressed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
