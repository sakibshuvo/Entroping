"""Tests for selecting failed Hurl files from the latest run report."""

import json
from pathlib import Path

import pytest

import entroping.core.rerun_failures as rerun_failures


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_report(*, environment: object = "local", tests: list[dict[str, object]]) -> str:
    failed = sum(1 for test in tests if test["status"] != "passed")
    return json.dumps(
        {
            "schema_version": "entroping.run-report.v1",
            "project": "checkout-api",
            "environment": environment,
            "generated_at": "2026-06-05T00:00:00+00:00",
            "summary": {
                "total": len(tests),
                "passed": len(tests) - failed,
                "failed": failed,
                "exit_code": 1 if failed else 0,
            },
            "tests": tests,
        },
    )


def _test_row(path: str, *, status: str) -> dict[str, object]:
    return {
        "path": path,
        "execution_path": f".entroping/run-1/{Path(path).name}",
        "status": status,
        "exit_code": 0 if status == "passed" else 1,
        "duration_ms": 12,
        "timeout_ms": 2500,
        "rule_ids": ["latency"],
        "stdout": "ok\n" if status == "passed" else "",
        "stderr": "" if status == "passed" else "assert failed\n",
        "retry": {
            "retry_count": 0,
            "unstable": False,
            "attempts": [
                {
                    "attempt": 1,
                    "status": status,
                    "exit_code": 0 if status == "passed" else 1,
                    "duration_ms": 12,
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                }
            ],
        },
    }


def test_select_latest_failed_hurl_tests_prefers_reports_run_latest(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(tmp_path / "tests" / "refund.hurl", "GET http://api.test/refund\n")
    _write_text(
        tmp_path / ".entroping" / "latest-run.json",
        _run_report(tests=[_test_row("tests/refund.hurl", status="failed")]),
    )
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(
            environment="local",
            tests=[
                _test_row("tests/health.hurl", status="failed"),
                _test_row("tests/refund.hurl", status="passed"),
            ],
        ),
    )

    selection = rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)

    assert selection.report_path == (tmp_path / "reports" / "run-latest.json").resolve()
    assert selection.environment == "local"
    assert selection.failed_paths == ((tmp_path / "tests" / "health.hurl").resolve(),)


def test_select_latest_failed_hurl_tests_falls_back_to_entroping_state(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(
        tmp_path / ".entroping" / "latest-run.json",
        _run_report(environment="default", tests=[_test_row("tests/health.hurl", status="failed")]),
    )

    selection = rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)

    assert selection.report_path == (tmp_path / ".entroping" / "latest-run.json").resolve()
    assert selection.environment is None
    assert selection.failed_paths == ((tmp_path / "tests" / "health.hurl").resolve(),)


def test_select_latest_failed_hurl_tests_rejects_missing_latest_report(
    tmp_path: Path,
) -> None:
    with pytest.raises(rerun_failures.RerunFailuresError, match="No latest run report found"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_malformed_report(tmp_path: Path) -> None:
    _write_text(tmp_path / "reports" / "run-latest.json", "{")

    with pytest.raises(rerun_failures.RerunFailuresError, match="Could not read latest run report"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_report_directory(tmp_path: Path) -> None:
    (tmp_path / "reports" / "run-latest.json").mkdir(parents=True)

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Latest run report path is not a file"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_zero_failures(tmp_path: Path) -> None:
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row("tests/health.hurl", status="passed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Latest run report has no failed tests"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_deleted_failed_paths(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row("tests/missing.hurl", status="failed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl test no longer exists"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_unsafe_failed_paths(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row("../outside.hurl", status="failed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl path must stay inside project"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_absolute_path_escape(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.hurl"
    _write_text(outside, "GET http://api.test/outside\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row(outside.as_posix(), status="failed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl path must stay inside project"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rechecks_resolved_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-resolved-outside.hurl"
    _write_text(outside, "GET http://api.test/outside\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row(outside.as_posix(), status="failed")]),
    )

    def allow_path(path: Path, *, root: Path | None = None) -> Path | None:
        return None

    monkeypatch.setattr(rerun_failures, "first_symlink_path_component", allow_path)

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl path must stay inside project"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_symlink_components(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "real.hurl", "GET http://api.test/health\n")
    (tmp_path / "tests" / "link.hurl").symlink_to(tmp_path / "tests" / "real.hurl")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row("tests/link.hurl", status="failed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl path must not use symlinks"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_non_hurl_failed_paths(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "health.txt", "not hurl\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row("tests/health.txt", status="failed")]),
    )

    with pytest.raises(
        rerun_failures.RerunFailuresError, match="Failed Hurl path must be a .hurl file"
    ):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_non_string_failed_path(
    tmp_path: Path,
) -> None:
    row = _test_row("tests/health.hurl", status="failed")
    row["path"] = 123
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(tmp_path / "reports" / "run-latest.json", _run_report(tests=[row]))

    with pytest.raises(rerun_failures.RerunFailuresError, match="must be a string"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


@pytest.mark.parametrize("path", ["", "tests/bad\npath.hurl"])
def test_select_latest_failed_hurl_tests_rejects_invalid_failed_path(
    tmp_path: Path,
    path: str,
) -> None:
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(tests=[_test_row(path, status="failed")]),
    )

    with pytest.raises(rerun_failures.RerunFailuresError, match="Failed Hurl path .* is invalid"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_non_string_environment(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(environment=123, tests=[_test_row("tests/health.hurl", status="failed")]),
    )

    with pytest.raises(rerun_failures.RerunFailuresError, match="environment must be a string"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_select_latest_failed_hurl_tests_rejects_control_character_environment(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "tests" / "health.hurl", "GET http://api.test/health\n")
    _write_text(
        tmp_path / "reports" / "run-latest.json",
        _run_report(
            environment="local\nci",
            tests=[_test_row("tests/health.hurl", status="failed")],
        ),
    )

    with pytest.raises(rerun_failures.RerunFailuresError, match="environment must not contain"):
        rerun_failures.select_latest_failed_hurl_tests(project_root=tmp_path)


def test_display_path_returns_absolute_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-display.txt"

    assert rerun_failures._display_path(outside, root=tmp_path) == outside.resolve().as_posix()
