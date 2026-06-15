#!/usr/bin/env python3
"""Build a deterministic quality-audit trend summary from audit artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "entroping.quality-trend.v1"
GENERATED_BY = "scripts/quality_trend_summary.py"
RANK_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
VULTURE_FINDING_RE = re.compile(r"^[^:\s][^:]*:\d+:\s+.+\(\d+% confidence\)$")


class QualityTrendError(ValueError):
    """User-facing quality trend summary error."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize quality-audit artifacts into stable metrics and optional "
            "numeric deltas for trend comparison."
        )
    )
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--radon-cc", type=Path, required=True)
    parser.add_argument("--radon-mi", type=Path, required=True)
    parser.add_argument("--vulture", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coverage-fail-under", type=float, default=100.0)
    parser.add_argument("--max-complexity-rank", default="D")
    parser.add_argument("--min-mi-rank", default="C")
    parser.add_argument("--vulture-confidence", type=int, default=90)
    args = parser.parse_args()

    try:
        payload = build_summary(args)
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except QualityTrendError as exc:
        print(f"quality_trend_summary: {exc}", file=sys.stderr)
        return 2

    metrics = payload["metrics"]
    print(f"Wrote quality trend summary: {args.output}")
    print(
        "Quality trend: "
        f"coverage={metrics['coverage_percent']:.2f}% "
        f"missing={metrics['coverage_missing_lines']} "
        f"complexity_worst={metrics['complexity_worst_rank']} "
        f"mi_worst={metrics['maintainability_worst_rank']} "
        f"dead_code={metrics['dead_code_findings']} "
        f"tests={metrics['test_static_count']}"
    )
    return 0


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    taxonomy = _load_json(args.taxonomy, "taxonomy")
    coverage = _load_json(args.coverage, "coverage")
    radon_cc = _load_json(args.radon_cc, "radon complexity")
    radon_mi = _load_json(args.radon_mi, "radon maintainability")
    vulture_text = _read_text(args.vulture, "vulture")

    taxonomy_metrics, taxonomy_categories = _taxonomy_metrics(taxonomy)
    metrics = {
        **_coverage_metrics(coverage),
        **_complexity_metrics(radon_cc),
        **_maintainability_metrics(radon_mi),
        "dead_code_findings": _dead_code_findings(vulture_text),
        **taxonomy_metrics,
    }

    deltas: dict[str, int | float] = {}
    if args.previous is not None:
        previous = _load_json(args.previous, "previous quality trend")
        previous_metrics = previous.get("metrics")
        if not isinstance(previous_metrics, dict):
            raise QualityTrendError("previous quality trend missing metrics object")
        deltas = _numeric_deltas(metrics, previous_metrics)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "thresholds": {
            "coverage_fail_under": float(args.coverage_fail_under),
            "max_complexity_rank": str(args.max_complexity_rank).strip().upper(),
            "min_maintainability_rank": str(args.min_mi_rank).strip().upper(),
            "vulture_confidence": int(args.vulture_confidence),
        },
        "metrics": metrics,
        "taxonomy_categories": taxonomy_categories,
        "deltas": deltas,
    }


def _load_json(path: Path, label: str) -> dict[str, Any]:
    text = _read_text(path, label)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QualityTrendError(f"{label} ({path}) is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise QualityTrendError(f"{label} must be a JSON object")
    return payload


def _read_text(path: Path, label: str) -> str:
    expanded = path.expanduser()
    if not expanded.is_file():
        raise QualityTrendError(f"missing input file: {path}")
    try:
        return expanded.read_text(encoding="utf-8")
    except OSError as exc:
        raise QualityTrendError(f"could not read {label}: {path}") from exc


def _coverage_metrics(payload: dict[str, Any]) -> dict[str, int | float]:
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        raise QualityTrendError("coverage missing totals object")
    return {
        "coverage_percent": _number(totals.get("percent_covered"), "coverage percent"),
        "coverage_covered_lines": _integer(
            totals.get("covered_lines"), "coverage covered lines"
        ),
        "coverage_missing_lines": _integer(
            totals.get("missing_lines"), "coverage missing lines"
        ),
        "coverage_statements": _integer(
            totals.get("num_statements"), "coverage statements"
        ),
    }


def _complexity_metrics(payload: dict[str, Any]) -> dict[str, int | float | str]:
    blocks: list[dict[str, Any]] = []
    for entries in payload.values():
        if isinstance(entries, list):
            blocks.extend(entry for entry in entries if isinstance(entry, dict))
    complexities = [
        _number(entry.get("complexity"), "complexity")
        for entry in blocks
        if entry.get("complexity") is not None
    ]
    worst_rank = _worst_rank(entry.get("rank") for entry in blocks)
    average = sum(complexities) / len(complexities) if complexities else 0.0
    return {
        "complexity_average": _rounded(average),
        "complexity_blocks": len(blocks),
        "complexity_worst_rank": worst_rank,
        "complexity_worst_rank_score": RANK_ORDER[worst_rank],
    }


def _maintainability_metrics(payload: dict[str, Any]) -> dict[str, int | str]:
    ranks: list[Any] = []
    file_count = 0
    for entry in payload.values():
        if isinstance(entry, dict):
            entry_ranks = [entry.get("rank")]
        elif isinstance(entry, list):
            entry_ranks = [item.get("rank") for item in entry if isinstance(item, dict)]
        else:
            entry_ranks = []
        valid_ranks = [
            str(rank).strip().upper()
            for rank in entry_ranks
            if str(rank or "").strip().upper() in RANK_ORDER
        ]
        if valid_ranks:
            file_count += 1
            ranks.extend(valid_ranks)
    if not ranks:
        raise QualityTrendError("radon maintainability missing rank data")
    worst_rank = _worst_rank(ranks)
    return {
        "maintainability_files": file_count,
        "maintainability_worst_rank": worst_rank,
        "maintainability_worst_rank_score": RANK_ORDER[worst_rank],
    }


def _taxonomy_metrics(
    payload: dict[str, Any],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        raise QualityTrendError("taxonomy missing categories object")

    category_metrics: dict[str, dict[str, int]] = {}
    for name, value in sorted(categories.items()):
        if not isinstance(value, dict):
            raise QualityTrendError(f"taxonomy category {name} must be an object")
        category_metrics[str(name)] = {
            "file_count": _integer(value.get("file_count"), f"{name} file_count"),
            "static_test_count": _integer(
                value.get("static_test_count"), f"{name} static_test_count"
            ),
        }

    return (
        {
            "test_files": _integer(payload.get("test_file_count"), "test file count"),
            "test_static_count": _integer(
                payload.get("static_test_count"), "static test count"
            ),
        },
        category_metrics,
    )


def _dead_code_findings(text: str) -> int:
    return sum(1 for line in text.splitlines() if VULTURE_FINDING_RE.match(line.strip()))


def _worst_rank(raw_ranks: Any) -> str:
    worst = "A"
    for raw_rank in raw_ranks:
        rank = str(raw_rank or "").strip().upper()
        if rank in RANK_ORDER and RANK_ORDER[rank] > RANK_ORDER[worst]:
            worst = rank
    return worst


def _numeric_deltas(
    metrics: dict[str, int | float | str], previous_metrics: dict[str, Any]
) -> dict[str, int | float]:
    deltas: dict[str, int | float] = {}
    for key in sorted(metrics):
        current = metrics[key]
        previous = previous_metrics.get(key)
        if isinstance(current, bool) or isinstance(previous, bool):
            continue
        if isinstance(current, int) and isinstance(previous, int):
            deltas[key] = current - previous
        elif isinstance(current, (int, float)) and isinstance(previous, (int, float)):
            deltas[key] = _rounded(float(current) - float(previous))
    return deltas


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualityTrendError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QualityTrendError(f"{label} must be a number")
    return _rounded(float(value))


def _rounded(value: float) -> float:
    return round(value, 4)


if __name__ == "__main__":
    raise SystemExit(main())
