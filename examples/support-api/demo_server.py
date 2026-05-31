#!/usr/bin/env python3
"""Local support-ticket API used as Entroping's second demo fixture."""

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

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
    """Return a deterministic response for a support API request."""

    request_headers = headers or {}
    target = urlsplit(path)
    request_path = target.path
    query = parse_qs(target.query, keep_blank_values=True)

    if method == "GET" and request_path == "/health":
        return _json_response(
            HTTPStatus.OK,
            {"service": "support-api", "status": "ok"},
        )

    if method == "GET" and request_path == "/tickets":
        return _json_response(
            HTTPStatus.OK,
            {
                "items": _ticket_rows(query.get("status", ["open"])[0]),
                "next_cursor": "cursor-002",
            },
        )

    if method == "POST" and request_path == "/tickets":
        customer_id = _header(request_headers, "X-Customer-Id")
        if customer_id is None or customer_id.strip() == "":
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "missing_customer_header"},
            )

        try:
            payload = _json_object(body)
        except ValueError:
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ticket_payload"},
            )

        subject = payload.get("subject")
        priority = payload.get("priority")
        if not isinstance(subject, str) or subject.strip() == "":
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ticket_payload"},
            )
        if priority not in {"low", "normal", "high"}:
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ticket_payload"},
            )

        ticket_id = f"tkt_{customer_id}_001"
        return _json_response(
            HTTPStatus.CREATED,
            {
                "id": ticket_id,
                "priority": priority,
                "status": "open",
                "subject": subject,
            },
            headers={
                "Location": f"/tickets/{ticket_id}",
                "X-Audit-Id": "audit-create-ticket",
            },
        )

    if method == "GET" and request_path.endswith("/events") and request_path.startswith(
        "/tickets/"
    ):
        ticket_id = unquote(request_path.removeprefix("/tickets/").removesuffix("/events"))
        if not ticket_id or "/" in ticket_id:
            return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        return _json_response(
            HTTPStatus.OK,
            {
                "events": [
                    {"type": "created", "actor": "customer"},
                    {"type": "assigned", "actor": "system"},
                ],
                "id": ticket_id,
            },
        )

    if method == "PATCH" and request_path.endswith("/status") and request_path.startswith(
        "/tickets/"
    ):
        agent_id = _header(request_headers, "X-Agent-Id")
        if agent_id is None or agent_id.strip() == "":
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "missing_agent_header"},
            )

        ticket_id = unquote(request_path.removeprefix("/tickets/").removesuffix("/status"))
        if not ticket_id or "/" in ticket_id:
            return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        try:
            payload = _json_object(body)
        except ValueError:
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_status_payload"},
            )

        status = payload.get("status")
        if status not in {"open", "triaged", "resolved"}:
            return _json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_status_payload"},
            )
        return _json_response(
            HTTPStatus.OK,
            {"id": ticket_id, "status": status},
            headers={"X-Audit-Id": "audit-update-ticket"},
        )

    return _json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})


class DemoHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local support demo."""

    server_version = "EntropingSupportDemo/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send(route_request("GET", self.path, headers=dict(self.headers)))

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send_with_body("POST")

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._send_with_body("PATCH")

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logs so fixture output stays focused."""

        _ = (format, args)

    def _send_with_body(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._send(route_request(method, self.path, body, dict(self.headers)))

    def _send(self, response: RouteResponse) -> None:
        encoded = response.body.encode("utf-8")
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    """Run the local support demo server."""

    parser = argparse.ArgumentParser(description="Run the Entroping support demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), DemoHandler)
    print(f"Support demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping support demo API")
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


def _ticket_rows(status: str) -> list[JsonObject]:
    rows: list[JsonObject] = [
        {
            "id": "tkt_001",
            "priority": "high",
            "status": "open",
            "subject": "Invoice download fails",
        },
        {
            "id": "tkt_002",
            "priority": "normal",
            "status": "open",
            "subject": "Webhook retry question",
        },
    ]
    if status == "open":
        return rows
    return []


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def _json_response(
    status: HTTPStatus,
    payload: JsonObject,
    *,
    headers: dict[str, str] | None = None,
) -> RouteResponse:
    response_headers = {
        "Content-Type": "application/json",
        "X-Request-Id": "support-demo-request",
    }
    response_headers.update(headers or {})
    return RouteResponse(
        status=int(status),
        headers=response_headers,
        body=json.dumps(payload, sort_keys=True),
    )


if __name__ == "__main__":
    main()
