#!/usr/bin/env python3
"""Generate bounded local performance smoke evidence for release review."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from entroping.core.config_loader import load_qanstitution
from entroping.core.gate_injector import write_injected_execution_copy
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.hurl_runner import HurlRunOptions, run_hurl_files
from entroping.core.report_writer import (
    build_run_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.safe_write import safe_write_text
from entroping.core.traffic_store import TrafficStore
from entroping.models.traffic import (
    TrafficBody,
    TrafficExchange,
    TrafficRequest,
    TrafficResponse,
)

SCHEMA_VERSION = "entroping.performance-smoke.v1"
DEFAULT_HURL_FILES = 120
DEFAULT_HURL_WORKERS = 8
DEFAULT_TRAFFIC_EVENTS = 500
DEFAULT_TRAFFIC_RETENTION = 300
DEFAULT_SUITE_MAX_MS = 10_000
DEFAULT_TRAFFIC_MAX_MS = 10_000
DEFAULT_MAX_REPORT_BYTES = 5_000_000
DEFAULT_MAX_DB_BYTES = 10_000_000


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    """One bounded performance smoke check result."""

    name: str
    passed: bool
    duration_ms: int
    threshold_ms: int
    metrics: dict[str, int]
    notes: tuple[str, ...] = ()


def main(argv: list[str] | None = None) -> int:
    """Run the performance smoke and write reviewable JSON evidence."""

    args = _parse_args(argv)
    workspace_parent = Path(".entroping") / "performance-smoke-work"
    workspace_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="run-",
        dir=workspace_parent,
    ) as tmp:
        smoke_root = Path(tmp)
        checks = (
            _run_large_suite_smoke(
                smoke_root / "large-suite",
                hurl_files=args.hurl_files,
                hurl_workers=args.hurl_workers,
                suite_max_ms=args.suite_max_ms,
                max_report_bytes=args.max_report_bytes,
            ),
            _run_traffic_store_smoke(
                smoke_root / "traffic-store",
                traffic_events=args.traffic_events,
                traffic_retention=args.traffic_retention,
                traffic_max_ms=args.traffic_max_ms,
                max_db_bytes=args.max_db_bytes,
            ),
        )

    evidence = _evidence_payload(checks)
    output_path = args.output
    safe_write_text(
        output_path,
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        artifact="performance smoke evidence",
    )

    failed = evidence["summary"]["failed"]
    print(f"Wrote performance smoke evidence: {output_path}")
    if failed:
        print(f"Performance smoke FAILED: {failed} check(s) breached thresholds.")
        return 1
    print("Performance smoke OK")
    return 0


def _run_large_suite_smoke(
    root: Path,
    *,
    hurl_files: int,
    hurl_workers: int,
    suite_max_ms: int,
    max_report_bytes: int,
) -> SmokeCheck:
    _write_large_suite_project(root, hurl_files=hurl_files, hurl_workers=hurl_workers)
    fake_hurl = _write_fake_hurl(root / "bin")
    law = load_qanstitution(root / "qanstitution.yaml")

    started = time.perf_counter()
    hurl_tests = discover_hurl_tests([root / "tests"], tag_filters=("perf",))
    execution_root = root / ".entroping" / "run"
    execution_copies = [
        write_injected_execution_copy(test, law.gates, execution_root=execution_root)
        for test in hurl_tests
    ]
    suite = run_hurl_files(
        [copy.execution_path for copy in execution_copies],
        HurlRunOptions(binary=str(fake_hurl), timeout_ms=law.settings.timeout),
        max_workers=min(hurl_workers, hurl_files),
    )
    report = build_run_report(
        project=law.project,
        environment="performance-smoke",
        execution_copies=execution_copies,
        suite=suite,
        project_root=root,
    )
    reports_dir = root / "reports"
    report_paths = (
        write_json_report(report, reports_dir / "run-latest.json"),
        write_junit_report(report, reports_dir / "junit.xml"),
        write_html_report(report, reports_dir / "run-latest.html"),
    )
    duration_ms = _elapsed_ms(started)
    report_bytes = sum(path.stat().st_size for path in report_paths)
    passed = (
        len(hurl_tests) == hurl_files
        and suite.total == hurl_files
        and suite.failed == 0
        and duration_ms <= suite_max_ms
        and report_bytes <= max_report_bytes
    )
    return SmokeCheck(
        name="large_suite",
        passed=passed,
        duration_ms=duration_ms,
        threshold_ms=suite_max_ms,
        metrics={
            "hurl_files": len(hurl_tests),
            "parallel_workers": min(hurl_workers, hurl_files),
            "suite_total": suite.total,
            "suite_failed": suite.failed,
            "report_bytes": report_bytes,
            "max_report_bytes": max_report_bytes,
        },
        notes=_threshold_notes(
            duration_ms=duration_ms,
            threshold_ms=suite_max_ms,
            measured_bytes=report_bytes,
            max_bytes=max_report_bytes,
        ),
    )


def _run_traffic_store_smoke(
    root: Path,
    *,
    traffic_events: int,
    traffic_retention: int,
    traffic_max_ms: int,
    max_db_bytes: int,
) -> SmokeCheck:
    started = time.perf_counter()
    store = TrafficStore.open_project(root, max_events=traffic_retention)
    for index in range(traffic_events):
        store.record_exchange(_redacted_exchange(index))
    retained = store.list_exchanges()
    duration_ms = _elapsed_ms(started)
    db_bytes = store.db_path.stat().st_size
    expected_retained = min(traffic_events, traffic_retention)
    passed = (
        len(retained) == expected_retained
        and duration_ms <= traffic_max_ms
        and db_bytes <= max_db_bytes
    )
    return SmokeCheck(
        name="traffic_store",
        passed=passed,
        duration_ms=duration_ms,
        threshold_ms=traffic_max_ms,
        metrics={
            "inserted_events": traffic_events,
            "retained_events": len(retained),
            "expected_retained_events": expected_retained,
            "db_bytes": db_bytes,
            "max_db_bytes": max_db_bytes,
        },
        notes=_threshold_notes(
            duration_ms=duration_ms,
            threshold_ms=traffic_max_ms,
            measured_bytes=db_bytes,
            max_bytes=max_db_bytes,
        ),
    )


def _write_large_suite_project(
    root: Path,
    *,
    hurl_files: int,
    hurl_workers: int,
) -> None:
    tests_dir = root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (root / "qanstitution.yaml").write_text(
        "\n".join(
            [
                "project: performance-smoke",
                "settings:",
                "  timeout: 1000",
                f"  parallel_workers: {max(1, min(hurl_workers, hurl_files))}",
                "gates:",
                "  - id: no_server_errors",
                '    condition: "true"',
                "    gate: status < 500",
                "    enforcement: block",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for index in range(hurl_files):
        (tests_dir / f"perf_{index:04d}.hurl").write_text(
            "\n".join(
                [
                    "# entroping: tags=perf,smoke",
                    "",
                    f"GET https://api.example.test/perf/{index}",
                    "HTTP 200",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _write_fake_hurl(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_hurl = bin_dir / "hurl"
    fake_hurl.write_text(
        "#!/bin/sh\n"
        "printf 'HTTP 200\\nContent-Type: application/json\\n\\n{\"ok\":true}\\n'\n",
        encoding="utf-8",
    )
    fake_hurl.chmod(fake_hurl.stat().st_mode | 0o700)
    return fake_hurl


def _redacted_exchange(index: int) -> TrafficExchange:
    captured_at = datetime(2026, 5, 31, 12, 0, tzinfo=UTC) + timedelta(milliseconds=index)
    return TrafficExchange(
        captured_at=captured_at,
        duration_ms=index % 100,
        request=TrafficRequest(
            method="GET",
            url=f"https://api.example.test/items/{index % 20}",
            headers={"Authorization": "[REDACTED]", "Accept": "application/json"},
            body=None,
        ),
        response=TrafficResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=TrafficBody(
                content_type="application/json",
                size_bytes=11,
                text='{"ok":true}',
            ),
        ),
        redacted=True,
    )


def _evidence_payload(checks: tuple[SmokeCheck, ...]) -> dict[str, object]:
    passed = sum(1 for check in checks if check.passed)
    failed = len(checks) - passed
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
        },
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "duration_ms": check.duration_ms,
                "threshold_ms": check.threshold_ms,
                "metrics": check.metrics,
                "notes": list(check.notes),
            }
            for check in checks
        ],
    }


def _threshold_notes(
    *,
    duration_ms: int,
    threshold_ms: int,
    measured_bytes: int,
    max_bytes: int,
) -> tuple[str, ...]:
    notes: list[str] = []
    if duration_ms > threshold_ms:
        notes.append(f"duration {duration_ms}ms exceeded threshold {threshold_ms}ms")
    if measured_bytes > max_bytes:
        notes.append(f"size {measured_bytes} bytes exceeded threshold {max_bytes} bytes")
    return tuple(notes)


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hurl-files", type=_positive_int, default=DEFAULT_HURL_FILES)
    parser.add_argument("--hurl-workers", type=_positive_int, default=DEFAULT_HURL_WORKERS)
    parser.add_argument("--traffic-events", type=_positive_int, default=DEFAULT_TRAFFIC_EVENTS)
    parser.add_argument(
        "--traffic-retention",
        type=_positive_int,
        default=DEFAULT_TRAFFIC_RETENTION,
    )
    parser.add_argument("--suite-max-ms", type=_positive_int, default=DEFAULT_SUITE_MAX_MS)
    parser.add_argument(
        "--traffic-max-ms",
        type=_positive_int,
        default=DEFAULT_TRAFFIC_MAX_MS,
    )
    parser.add_argument(
        "--max-report-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_REPORT_BYTES,
    )
    parser.add_argument("--max-db-bytes", type=_positive_int, default=DEFAULT_MAX_DB_BYTES)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports") / "performance-smoke.json",
    )
    return parser.parse_args(argv)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        msg = f"{value!r} is not an integer"
        raise argparse.ArgumentTypeError(msg) from exc
    if parsed <= 0:
        msg = f"{value!r} must be greater than zero"
        raise argparse.ArgumentTypeError(msg)
    return parsed


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[1])
    raise SystemExit(main(sys.argv[1:]))
