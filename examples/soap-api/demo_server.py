#!/usr/bin/env python3
"""Local SOAP-over-HTTP API used as an Entroping protocol fixture."""

import argparse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


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
    """Return a deterministic response for a SOAP-over-HTTP request."""

    request_headers = headers or {}
    request_path = urlsplit(path).path
    if method == "GET" and request_path == "/health":
        return _xml_response(
            HTTPStatus.OK,
            "<health><service>soap-api</service><status>ok</status></health>",
        )

    if method != "POST" or request_path != "/soap/orders":
        return _soap_fault(HTTPStatus.NOT_FOUND, "not_found")

    if _header(request_headers, "SOAPAction") != "GetOrder":
        return _soap_fault(HTTPStatus.BAD_REQUEST, "missing_or_invalid_soap_action")

    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError:
        return _soap_fault(HTTPStatus.BAD_REQUEST, "invalid_xml_encoding")

    if "ord_1001" not in body_text or "GetOrderRequest" not in body_text:
        return _soap_fault(HTTPStatus.BAD_REQUEST, "unsupported_order_request")

    return _xml_response(
        HTTPStatus.OK,
        (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:ord="https://entroping.dev/examples/orders">'
            "<soapenv:Body>"
            "<ord:GetOrderResponse>"
            "<ord:id>ord_1001</ord:id>"
            "<ord:status>paid</ord:status>"
            "<ord:total>42.50</ord:total>"
            "</ord:GetOrderResponse>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        ),
    )


class DemoHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local SOAP fixture."""

    server_version = "EntropingSOAPDemo/0.1"

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
    """Run the local SOAP demo server."""

    parser = argparse.ArgumentParser(description="Run the Entroping SOAP demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18083)
    namespace = parser.parse_args()

    server = ThreadingHTTPServer((namespace.host, namespace.port), DemoHandler)
    print(f"SOAP demo API listening on http://{namespace.host}:{namespace.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SOAP demo API")
    finally:
        server.server_close()


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if key.lower() == expected:
            return value
    return None


def _soap_fault(status: HTTPStatus, code: str) -> RouteResponse:
    return _xml_response(
        status,
        (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soapenv:Body>"
            "<soapenv:Fault>"
            f"<faultcode>{code}</faultcode>"
            f"<faultstring>{code}</faultstring>"
            "</soapenv:Fault>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        ),
    )


def _xml_response(status: HTTPStatus, body: str) -> RouteResponse:
    return RouteResponse(
        status=int(status),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "X-Request-Id": "soap-demo-request",
        },
        body=body,
    )


if __name__ == "__main__":
    main()
