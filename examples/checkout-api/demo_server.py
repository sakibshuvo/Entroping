#!/usr/bin/env python3
"""Tiny local checkout API used by the Entroping alpha quickstart."""

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


@dataclass(frozen=True)
class RouteResponse:
    """HTTP response returned by the demo router."""

    status: int
    headers: dict[str, str]
    body: str


def route_request(method: str, path: str, body: bytes) -> RouteResponse:
    """Return the deterministic response for a demo API request."""

    target = urlsplit(path)
    request_path = target.path
    query = parse_qs(target.query, keep_blank_values=True)

    if method == "GET" and request_path == "/health":
        return _json_response(HTTPStatus.OK, {"status": "ok"})

    if method == "GET" and request_path.startswith("/checkout/"):
        checkout_id = unquote(request_path.removeprefix("/checkout/"))
        if not checkout_id or "/" in checkout_id:
            return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        payload: dict[str, str | list[str]] = {
            "id": checkout_id,
            "status": "accepted",
        }
        if "events" in query.get("include", []):
            payload["events"] = ["created", "accepted"]
        return _json_response(HTTPStatus.OK, payload)

    if method == "POST" and request_path == "/checkout":
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_checkout_payload"},
            )

        cart_id = payload.get("cart_id")
        if not isinstance(cart_id, str) or cart_id.strip() == "":
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_checkout_payload"},
            )
        return _json_response(
            HTTPStatus.CREATED,
            {"id": f"chk_{cart_id}", "status": "accepted"},
        )

    return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})


class DemoHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local checkout demo."""

    server_version = "EntropingCheckoutDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send(route_request("GET", self.path, b""))

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name.
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._send(route_request("POST", self.path, body))

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logs so quickstart output stays focused."""

        _ = (format, args)

    def _send(self, response: RouteResponse) -> None:
        encoded = response.body.encode("utf-8")
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    """Run the local demo server."""

    parser = argparse.ArgumentParser(description="Run the Entroping checkout demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), DemoHandler)
    print(f"Checkout demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping checkout demo API")
    finally:
        server.server_close()


def _json_response(status: HTTPStatus, payload: dict[str, str | list[str]]) -> RouteResponse:
    return RouteResponse(
        status=int(status),
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload, sort_keys=True),
    )


if __name__ == "__main__":
    main()
