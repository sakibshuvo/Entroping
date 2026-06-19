"""End-to-end CLI proof with real Hurl when the toolchain is available."""

import contextlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator, Mapping
from http import HTTPStatus
from pathlib import Path
from threading import Thread
from typing import Any, cast
from xml.etree import ElementTree

import pytest

from entroping.core.hurl_runner import discover_hurl
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION


class _GovernedHealthHandler(http.server.BaseHTTPRequestHandler):
    """Tiny local API that satisfies the minimal QAnstitution starter policy."""

    _body = b'{"status":"ok"}'

    def do_GET(self) -> None:
        request_path = self.path.split("?", maxsplit=1)[0]
        if request_path == "/slow":
            time.sleep(1.0)

        if request_path not in {"/health", "/secret", "/slow"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", "entroping-e2e")
        if request_path == "/secret":
            self.send_header("X-Secret", "wrong-value")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        try:
            self.wfile.write(self._body)
        except BrokenPipeError:
            return

    def log_message(self, format: str, *args: object) -> None:
        """Keep pytest output focused on assertion failures."""


@contextlib.contextmanager
def _local_health_api() -> Iterator[int]:
    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _GovernedHealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        server.server_close()


def _entroping_command() -> list[str]:
    executable = shutil.which("entroping")
    if executable is None:
        pytest.fail("entroping console script is not available in the test environment")
    return [executable]


def _run_entroping(
    project_root: Path,
    *args: str,
    env_overrides: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    if env_overrides is not None:
        env.update(env_overrides)
    return subprocess.run(
        [*_entroping_command(), *args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20.0,
    )


def _read_run_events(project_root: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (project_root / ".entroping" / "latest-run-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]


def _set_qanstitution_timeout(project_root: Path, timeout_ms: int) -> None:
    config_path = project_root / "qanstitution.yaml"
    config = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config.replace("timeout: 30000", f"timeout: {timeout_ms}"),
        encoding="utf-8",
    )


def _assert_secret_not_persisted(project_root: Path, secret: str) -> None:
    secret_bytes = secret.encode()
    for path in project_root.rglob("*"):
        if path.is_file():
            assert secret_bytes not in path.read_bytes(), path


def _require_hurl_installed() -> None:
    hurl = discover_hurl()
    if not hurl.available:
        pytest.skip("hurl is not installed")


def _init_minimal_project(project_root: Path) -> None:
    init_result = _run_entroping(project_root, "init", "--minimal")
    assert init_result.returncode == 0, init_result.stderr or init_result.stdout


def _assert_source_unchanged_and_temp_clean(
    project_root: Path,
    source: Path,
    source_content: str,
) -> None:
    assert source.read_text(encoding="utf-8") == source_content
    assert not list((project_root / ".entroping").glob("run-*"))


def _load_json_file(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _latest_report(project_root: Path) -> dict[str, object]:
    return _load_json_file(project_root / "reports" / "run-latest.json")


def _latest_state(project_root: Path) -> dict[str, object]:
    return _load_json_file(project_root / ".entroping" / "latest-run.json")


def _first_report_test(report: dict[str, object]) -> dict[str, Any]:
    tests = report["tests"]
    assert isinstance(tests, list)
    test = tests[0]
    assert isinstance(test, dict)
    return cast(dict[str, Any], test)


def _events_named(
    events: list[dict[str, object]],
    event_name: str,
) -> list[dict[str, object]]:
    return [event for event in events if event["event"] == event_name]


def _assert_failed_cli_result(run_result: subprocess.CompletedProcess[str]) -> None:
    assert run_result.returncode == 1
    assert "Hurl run: 0 passed, 1 failed" in run_result.stdout


def _assert_failed_completion(events: list[dict[str, object]], *, exit_code: int = 1) -> None:
    completed_events = _events_named(events, "run_completed")
    assert completed_events[-1]["status"] == "failed"
    assert completed_events[-1]["exit_code"] == exit_code
    assert completed_events[-1]["total"] == 1
    assert completed_events[-1]["failed"] == 1


def _assert_redacted_failure_report(
    project_root: Path,
    *,
    secret: str,
) -> None:
    report = _latest_report(project_root)
    assert report == _latest_state(project_root)
    assert report["summary"] == {"total": 1, "passed": 0, "failed": 1, "exit_code": 1}
    test = _first_report_test(report)
    assert test["path"] == "tests/secret-header.hurl"
    assert test["status"] == "failed"
    assert test["exit_code"] != 0
    assert test["stdout"] == ""
    assert "expected: string <[REDACTED]>" in test["stderr"]
    assert secret not in json.dumps(report)


def _assert_redacted_failure_events(
    events: list[dict[str, object]],
    *,
    secret: str,
) -> None:
    result_events = _events_named(events, "test_result")
    artifact_events = _events_named(events, "artifact_written")
    assert len(result_events) == 1
    assert result_events[0]["path"] == "tests/secret-header.hurl"
    assert result_events[0]["status"] == "failed"
    event_stderr = result_events[0].get("stderr")
    assert isinstance(event_stderr, str)
    assert "expected: string <[REDACTED]>" in event_stderr
    assert {event["artifact_type"] for event in artifact_events} >= {
        "latest-run",
        "json-report",
    }
    assert secret not in json.dumps(events)


def _assert_timeout_report(project_root: Path) -> None:
    report = _latest_report(project_root)
    test = _first_report_test(report)
    assert test["path"] == "tests/slow.hurl"
    assert test["status"] == "timeout"
    assert test["exit_code"] == 124
    assert test["timeout_ms"] == 100
    assert "Hurl subprocess timed out after 100 ms" in test["stderr"]
    attempts = test["retry"]["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["attempt"] == 1
    assert attempts[0]["status"] == "timeout"
    assert attempts[0]["exit_code"] == 124
    assert attempts[0]["duration_ms"] >= 0
    assert attempts[0]["stdout_truncated"] is False
    assert attempts[0]["stderr_truncated"] is False


def _assert_timeout_events(events: list[dict[str, object]]) -> None:
    result_events = _events_named(events, "test_result")
    assert len(result_events) == 1
    assert result_events[0]["path"] == "tests/slow.hurl"
    assert result_events[0]["status"] == "timeout"
    assert result_events[0]["exit_code"] == 124
    assert result_events[0]["timeout_ms"] == 100


@pytest.mark.integration
def test_installed_cli_init_to_run_reports_with_real_hurl(tmp_path: Path) -> None:
    _require_hurl_installed()
    _init_minimal_project(tmp_path)

    with _local_health_api() as port:
        source = tmp_path / "tests" / "health.hurl"
        source_content = (
            "# entroping: tags=e2e\n\n"
            f"GET http://127.0.0.1:{port}/health\n"
            "HTTP 200\n"
        )
        source.write_text(source_content, encoding="utf-8")

        run_result = _run_entroping(
            tmp_path,
            "run",
            "--ci",
            "--report",
            "json",
            "--report",
            "junit",
        )

    assert run_result.returncode == 0, run_result.stderr or run_result.stdout
    assert "Hurl run: 1 passed, 0 failed" in run_result.stdout
    assert source.read_text(encoding="utf-8") == source_content

    report = json.loads((tmp_path / "reports" / "run-latest.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == RUN_REPORT_SCHEMA_VERSION
    assert report["summary"]["total"] == 1
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 0
    assert report["summary"]["exit_code"] == 0
    assert report["tests"][0]["path"] == "tests/health.hurl"
    assert report["tests"][0]["status"] == "passed"
    assert set(report["tests"][0]["rule_ids"]) == {
        "global_latency",
        "no_server_errors",
        "request_id_header",
    }

    junit_root = ElementTree.parse(tmp_path / "reports" / "junit.xml").getroot()
    assert junit_root.tag == "testsuite"
    assert junit_root.attrib["tests"] == "1"
    assert junit_root.attrib["failures"] == "0"
    testcase = junit_root.find("testcase")
    assert testcase is not None
    assert testcase.attrib["classname"] == "tests"
    assert testcase.attrib["name"] == "health.hurl"
    assert testcase.find("failure") is None


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.security
def test_real_hurl_failure_reports_redacted_output_and_consistent_events(
    tmp_path: Path,
) -> None:
    _require_hurl_installed()
    _init_minimal_project(tmp_path)

    secret = "issue-958-secret-token"
    with _local_health_api() as port:
        source = tmp_path / "tests" / "secret-header.hurl"
        source_content = (
            "# entroping: tags=e2e,failure-boundary\n\n"
            f"GET http://127.0.0.1:{port}/secret\n"
            "HTTP 200\n"
            "[Asserts]\n"
            'header "X-Secret" == "{{api_token}}"\n'
        )
        source.write_text(source_content, encoding="utf-8")

        run_result = _run_entroping(
            tmp_path,
            "run",
            "--tag",
            "failure-boundary",
            "--report",
            "json",
            env_overrides={"HURL_VARIABLE_api_token": secret},
        )

    _assert_failed_cli_result(run_result)
    _assert_source_unchanged_and_temp_clean(tmp_path, source, source_content)
    _assert_redacted_failure_report(tmp_path, secret=secret)
    events = _read_run_events(tmp_path)
    _assert_redacted_failure_events(events, secret=secret)
    _assert_failed_completion(events)
    _assert_secret_not_persisted(tmp_path, secret)


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.security
def test_real_hurl_timeout_preserves_source_and_records_timeout_evidence(
    tmp_path: Path,
) -> None:
    _require_hurl_installed()
    _init_minimal_project(tmp_path)
    _set_qanstitution_timeout(tmp_path, 100)

    with _local_health_api() as port:
        source = tmp_path / "tests" / "slow.hurl"
        source_content = (
            "# entroping: tags=e2e,timeout-boundary\n\n"
            f"GET http://127.0.0.1:{port}/slow\n"
            "HTTP 200\n"
        )
        source.write_text(source_content, encoding="utf-8")

        run_result = _run_entroping(
            tmp_path,
            "run",
            "--tag",
            "timeout-boundary",
            "--report",
            "json",
        )

    _assert_failed_cli_result(run_result)
    _assert_source_unchanged_and_temp_clean(tmp_path, source, source_content)
    _assert_timeout_report(tmp_path)
    events = _read_run_events(tmp_path)
    _assert_timeout_events(events)
    _assert_failed_completion(events)
