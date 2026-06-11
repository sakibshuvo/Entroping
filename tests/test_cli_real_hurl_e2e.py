"""End-to-end CLI proof with real Hurl when the toolchain is available."""

import contextlib
import http.server
import json
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from threading import Thread
from xml.etree import ElementTree

import pytest

from entroping.core.hurl_runner import discover_hurl
from entroping.core.report_serialization import RUN_REPORT_SCHEMA_VERSION


class _GovernedHealthHandler(http.server.BaseHTTPRequestHandler):
    """Tiny local API that satisfies the minimal QAnstitution starter policy."""

    _body = b'{"status":"ok"}'

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", "entroping-e2e")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

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


def _run_entroping(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    return subprocess.run(
        [*_entroping_command(), *args],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20.0,
    )


@pytest.mark.integration
def test_installed_cli_init_to_run_reports_with_real_hurl(tmp_path: Path) -> None:
    hurl = discover_hurl()
    if not hurl.available:
        pytest.skip("hurl is not installed")

    init_result = _run_entroping(tmp_path, "init", "--minimal")
    assert init_result.returncode == 0, init_result.stderr or init_result.stdout

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
