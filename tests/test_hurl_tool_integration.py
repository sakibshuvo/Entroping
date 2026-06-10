"""Integration checks for real Hurl tooling when available."""

import contextlib
import http.server
import socket
import subprocess
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from threading import Thread

import pytest

from entroping.core.hurl_runner import HurlRunOptions, discover_hurl, run_hurl_file
from entroping.core.hurl_validator import validate_hurl_content


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Tiny deterministic server used by real-hurl integration checks."""

    _success_body = b'{"status":"ok"}'

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._success_body)))
        self.end_headers()
        self.wfile.write(self._success_body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress noisy HTTP server logs during tests."""


@contextlib.contextmanager
def _hurl_local_server() -> Iterator[tuple[int, Thread]]:
    """Yield host/port from an ephemeral local HTTP fixture server."""

    with contextlib.closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, thread
    finally:
        server.shutdown()
        thread.join(timeout=2.0)
        server.server_close()


@pytest.mark.integration
def test_real_hurl_binary_executes_version_probe() -> None:
    """Validate the discovered Hurl binary can execute a version check."""

    hurl = discover_hurl()
    if not hurl.available:
        pytest.skip("hurl is not installed")

    assert hurl.path is not None
    result = subprocess.run(
        [hurl.path, "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5.0,
    )

    assert result.returncode == 0
    assert (result.stdout or result.stderr).strip()


@pytest.mark.integration
def test_real_hurlfmt_validates_hurl_content() -> None:
    """Validate real hurlfmt accepts parser-valid Hurl content."""

    hurlfmt = discover_hurl("hurlfmt")
    if not hurlfmt.available:
        pytest.skip("hurlfmt is not installed")

    validate_hurl_content(
        "GET http://localhost:18080/health\nHTTP 200\n",
        display_path="tests/generated/health.hurl",
    )


@pytest.mark.integration
def test_real_hurl_executes_smoke_request(tmp_path: Path) -> None:
    """Run a real minimal Hurl request against a local deterministic server."""

    hurl = discover_hurl()
    if not hurl.available:
        pytest.skip("hurl is not installed")
    assert hurl.path is not None

    with _hurl_local_server() as (port, _thread):
        hurl_path = tmp_path / "health_smoke.hurl"
        hurl_path.write_text(
            f"GET http://127.0.0.1:{port}/health\nHTTP 200\n",
            encoding="utf-8",
        )

        result = run_hurl_file(hurl_path, HurlRunOptions(binary=hurl.path, timeout_ms=2_000))

        assert result.passed
        assert result.exit_code == 0
        assert result.status == "passed"
