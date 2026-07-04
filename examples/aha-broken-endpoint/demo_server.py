#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

type JsonValue = str | int | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class RouteResponse:
    status: int
    headers: dict[str, str]
    body: str


def route_request(method: str, path: str) -> RouteResponse:

    target = urlsplit(path)
    request_path = target.path

    if method != "GET":
        return _json_response(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "method_not_allowed"},
        )

    if request_path == "/health":
        return _json_response(
            HTTPStatus.OK,
            {"service": "aha-broken-endpoint", "status": "ok"},
        )

    if request_path == "/products":
        return _json_response(
            HTTPStatus.OK,
            {
                "items": [
                    {"id": "prd_001", "name": "widget"},
                    {"id": "prd_002", "name": "gizmo"},
                ]
            },
        )

    return _json_response(
        HTTPStatus.NOT_FOUND,
        {"error": "not_found", "path": unquote(request_path)},
    )


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "EntropingAhaBrokenEndpointDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send(route_request("GET", self.path))

    def log_message(self, format: str, *args: object) -> None:
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

    parser = argparse.ArgumentParser(
        description="Run the Entroping Aha broken-endpoint demo API.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18110)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), DemoHandler)
    print(f"Aha broken-endpoint demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Aha broken-endpoint demo API")
    finally:
        server.server_close()


def _json_response(status: HTTPStatus, payload: JsonObject) -> RouteResponse:
    headers = {
        "Content-Type": "application/json",
    }
    if status != HTTPStatus.NOT_FOUND:
        headers["X-Request-Id"] = "aha-demo-request"

    return RouteResponse(
        status=int(status),
        headers=headers,
        body=json.dumps(payload, sort_keys=True),
    )


if __name__ == "__main__":
    main()
