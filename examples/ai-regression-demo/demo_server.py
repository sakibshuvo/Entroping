#!/usr/bin/env python3
"""Intentionally broken API fixture for the AI-regression proof demo."""

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BrokenRegressionHandler(BaseHTTPRequestHandler):
    """Serve responses that are body-correct but missing X-Request-Id."""

    server_version = "EntropingBrokenRegressionDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/checkout/demo-cart-001":
            self._json(HTTPStatus.OK, {"id": "demo-cart-001", "status": "accepted"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logs so demo output stays focused."""

        _ = (format, args)

    def _json(self, status: HTTPStatus, payload: dict[str, str]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    """Run the intentionally broken local API."""

    parser = argparse.ArgumentParser(description="Run the broken AI-regression demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18180)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), BrokenRegressionHandler)
    print(f"AI-regression demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AI-regression demo API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
