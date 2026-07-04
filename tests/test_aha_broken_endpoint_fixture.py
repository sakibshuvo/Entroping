import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "examples" / "aha-broken-endpoint"
DEMO_SERVER_PATH = FIXTURE_ROOT / "demo_server.py"


def _load_demo_server() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "aha_broken_endpoint_demo_server",
        DEMO_SERVER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load aha demo server module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aha_demo_server_health_and_products_routes() -> None:
    server = _load_demo_server()

    response = server.route_request("GET", "/health")
    assert response.status == 200
    assert json.loads(response.body) == {
        "service": "aha-broken-endpoint",
        "status": "ok",
    }
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["X-Request-Id"] == "aha-demo-request"

    response = server.route_request("GET", "/products")
    assert response.status == 200
    payload = json.loads(response.body)
    assert len(payload["items"]) == 2


def test_aha_demo_server_reports_missing_route_as_404() -> None:
    server = _load_demo_server()

    response = server.route_request("GET", "/products/ghost")

    assert response.status == 404
    assert json.loads(response.body)["error"] == "not_found"


def test_aha_fixture_files_define_missing_endpoint_proof() -> None:
    hurl = (FIXTURE_ROOT / "tests" / "broken_endpoint.hurl").read_text(encoding="utf-8")
    readme = (FIXTURE_ROOT / "README.md").read_text(encoding="utf-8")
    policy = (FIXTURE_ROOT / "qanstitution.yaml").read_text(encoding="utf-8")
    envs = (FIXTURE_ROOT / "envs" / "local.env.example").read_text(encoding="utf-8")

    assert "# entroping: tags=smoke,aha-endpoint" in hurl
    assert "GET {{base_url}}/products/ghost" in hurl
    assert "base_url=http://localhost:18110" in envs

    assert "missing-endpoint" in readme
    assert "entroping run --env local --tag aha-endpoint" in readme

    assert "id: \"no_missing_product_endpoint\"" in policy
    assert 'gate: \'status != 404\'' in policy
