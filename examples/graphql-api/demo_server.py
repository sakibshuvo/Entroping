#!/usr/bin/env python3
"""Local GraphQL-over-HTTP API used as an Entroping protocol fixture."""

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

type JsonValue = str | int | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class RouteResponse:
    """HTTP response returned by the demo router."""

    status: int
    headers: dict[str, str]
    body: str


def route_request(
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> RouteResponse:
    """Return a deterministic response for a GraphQL-over-HTTP request."""

    _ = headers
    request_path = urlsplit(path).path
    if method == "GET" and request_path == "/health":
        return _json_response(
            HTTPStatus.OK,
            {"service": "graphql-api", "status": "ok"},
        )

    if method != "POST" or request_path != "/graphql":
        return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    try:
        payload = _json_object(body)
    except ValueError:
        return _graphql_error("invalid_graphql_payload")

    query = payload.get("query")
    if not isinstance(query, str) or query.strip() == "":
        return _graphql_error("missing_graphql_query")

    if "UserProfile" in query and "user" in query and "usr_001" in query:
        return _json_response(
            HTTPStatus.OK,
            {
                "data": {
                    "user": {
                        "id": "usr_001",
                        "name": "Ada Lovelace",
                        "plan": "pro",
                    }
                }
            },
        )

    if "UpdatePlan" in query and "updatePlan" in query and "enterprise" in query:
        return _json_response(
            HTTPStatus.OK,
            {
                "data": {
                    "updatePlan": {
                        "id": "usr_001",
                        "plan": "enterprise",
                        "updated": True,
                    }
                }
            },
        )

    return _graphql_error("unsupported_graphql_operation")


class DemoHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local GraphQL fixture."""

    server_version = "EntropingGraphQLDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send(route_request("GET", self.path, headers=dict(self.headers)))

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name.
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._send(route_request("POST", self.path, body, dict(self.headers)))

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logs so fixture output stays focused."""

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
    """Run the local GraphQL demo server."""

    parser = argparse.ArgumentParser(description="Run the Entroping GraphQL demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18082)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), DemoHandler)
    print(f"GraphQL demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GraphQL demo API")
    finally:
        server.server_close()


def _json_object(body: bytes) -> JsonObject:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _graphql_error(message: str) -> RouteResponse:
    return _json_response(
        HTTPStatus.OK,
        {"errors": [{"message": message}]},
    )


def _json_response(
    status: HTTPStatus,
    payload: JsonObject,
) -> RouteResponse:
    return RouteResponse(
        status=int(status),
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "graphql-demo-request",
        },
        body=json.dumps(payload, sort_keys=True),
    )


if __name__ == "__main__":
    main()
