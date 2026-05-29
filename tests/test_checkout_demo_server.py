"""Tests for the checkout API demo server used by the README quickstart."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_demo_server() -> ModuleType:
    server_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "checkout-api"
        / "demo_server.py"
    )
    spec = importlib.util.spec_from_file_location("checkout_demo_server", server_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_server_routes_health_response() -> None:
    demo_server = _load_demo_server()

    response = demo_server.route_request("GET", "/health", b"")

    assert response.status == 200
    assert json.loads(response.body) == {"status": "ok"}
    assert response.headers["Content-Type"] == "application/json"


def test_demo_server_routes_checkout_response() -> None:
    demo_server = _load_demo_server()

    response = demo_server.route_request("POST", "/checkout", b'{"cart_id":"demo-cart-001"}')

    assert response.status == 201
    assert json.loads(response.body) == {
        "id": "chk_demo-cart-001",
        "status": "accepted",
    }


def test_demo_server_routes_checkout_lookup_with_query() -> None:
    demo_server = _load_demo_server()

    response = demo_server.route_request("GET", "/checkout/chk_demo-cart-001?include=events", b"")

    assert response.status == 200
    assert json.loads(response.body) == {
        "events": ["created", "accepted"],
        "id": "chk_demo-cart-001",
        "status": "accepted",
    }


def test_demo_server_rejects_bad_checkout_json() -> None:
    demo_server = _load_demo_server()

    response = demo_server.route_request("POST", "/checkout", b"not json")

    assert response.status == 400
    assert json.loads(response.body)["error"] == "invalid_checkout_payload"
