"""Tests for GraphQL and SOAP example fixtures."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHQL_ROOT = REPO_ROOT / "examples" / "graphql-api"
SOAP_ROOT = REPO_ROOT / "examples" / "soap-api"
ASYNCAPI_ROOT = REPO_ROOT / "examples" / "asyncapi-events"


def test_graphql_demo_server_returns_data_without_top_level_errors() -> None:
    server = _load_demo_server(GRAPHQL_ROOT, "graphql_demo_server")
    payload = {
        "query": "query UserProfile { user(id: \"usr_001\") { id name plan } }",
    }

    response = server.route_request(
        "POST",
        "/graphql",
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )

    assert response.status == 200
    body = json.loads(response.body)
    assert "errors" not in body
    assert body["data"]["user"] == {
        "id": "usr_001",
        "name": "Ada Lovelace",
        "plan": "pro",
    }
    assert response.headers["X-Request-Id"] == "graphql-demo-request"


def test_graphql_demo_server_exposes_errors_for_bad_queries() -> None:
    server = _load_demo_server(GRAPHQL_ROOT, "graphql_demo_server")

    response = server.route_request(
        "POST",
        "/graphql",
        json.dumps({"query": "query Unknown { account { id } }"}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )

    assert response.status == 200
    body = json.loads(response.body)
    assert body["errors"][0]["message"] == "unsupported_graphql_operation"
    assert "data" not in body


def test_soap_demo_server_returns_order_xml_envelope() -> None:
    server = _load_demo_server(SOAP_ROOT, "soap_demo_server")
    soap_body = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
        "xmlns:ord=\"https://entroping.dev/examples/orders\">"
        "<soapenv:Body><ord:GetOrderRequest><ord:id>ord_1001</ord:id>"
        "</ord:GetOrderRequest></soapenv:Body></soapenv:Envelope>"
    )

    response = server.route_request(
        "POST",
        "/soap/orders",
        soap_body.encode("utf-8"),
        {"Content-Type": "text/xml", "SOAPAction": "GetOrder"},
    )

    assert response.status == 200
    assert response.headers["X-Request-Id"] == "soap-demo-request"
    assert response.headers["Content-Type"] == "text/xml; charset=utf-8"
    assert "<ord:status>paid</ord:status>" in response.body
    assert "<ord:total>42.50</ord:total>" in response.body


def test_protocol_fixture_files_are_discoverable_and_hurl_over_http() -> None:
    graphql_qanstitution = yaml.safe_load(
        (GRAPHQL_ROOT / "qanstitution.yaml").read_text(encoding="utf-8")
    )
    soap_qanstitution = yaml.safe_load(
        (SOAP_ROOT / "qanstitution.yaml").read_text(encoding="utf-8")
    )
    graphql_hurl = (GRAPHQL_ROOT / "tests" / "graphql_smoke.hurl").read_text(
        encoding="utf-8"
    )
    soap_hurl = (SOAP_ROOT / "tests" / "soap_smoke.hurl").read_text(encoding="utf-8")
    graphql_readme = (GRAPHQL_ROOT / "README.md").read_text(encoding="utf-8")
    soap_readme = (SOAP_ROOT / "README.md").read_text(encoding="utf-8")
    asyncapi_readme = (ASYNCAPI_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    use_cases = (REPO_ROOT / "docs" / "user" / "USE_CASES.md").read_text(
        encoding="utf-8"
    )
    vault_index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    graphql_gates = {gate["id"]: gate for gate in graphql_qanstitution["gates"]}
    assert graphql_gates["graphql_no_top_level_errors"]["gate"] == (
        'jsonpath "$.errors" not exists'
    )
    assert graphql_gates["graphql_request_id"]["condition"] == "path startswith '/graphql'"

    soap_gates = {gate["id"]: gate for gate in soap_qanstitution["gates"]}
    assert soap_gates["soap_request_id"]["gate"] == 'header "X-Request-Id" exists'
    assert soap_gates["soap_envelope_success"]["gate"] == (
        'xpath "string(//*[local-name()=\'status\'])" == "paid"'
    )

    assert "# entroping: tags=smoke,graphql" in graphql_hurl
    assert 'jsonpath "$.errors" not exists' in graphql_hurl
    assert "POST http://127.0.0.1:18082/graphql" in graphql_hurl
    assert "query UserProfile" in graphql_hurl

    assert "# entroping: tags=smoke,soap" in soap_hurl
    assert "SOAPAction: GetOrder" in soap_hurl
    assert "POST http://127.0.0.1:18083/soap/orders" in soap_hurl
    assert 'xpath "string(//*[local-name()=\'status\'])" == "paid"' in soap_hurl

    assert "Hurl-over-HTTP" in graphql_readme
    assert "top-level GraphQL `errors`" in graphql_readme
    assert "Hurl-over-HTTP" in soap_readme
    assert "SOAPAction" in soap_readme
    assert "deterministic webhook acknowledgement scaffold compiler" in asyncapi_readme
    assert "compile_asyncapi_webhook_to_hurl" in asyncapi_readme
    assert "advanced examples remain documented" in root_readme
    assert "## 8. GraphQL API Governance" in use_cases
    assert "[[examples/graphql-api/README|GraphQL API demo fixture]]" in vault_index
    assert "[[examples/soap-api/README|SOAP API demo fixture]]" in vault_index


def _load_demo_server(fixture_root: Path, module_name: str) -> ModuleType:
    server_path = fixture_root / "demo_server.py"
    spec = importlib.util.spec_from_file_location(module_name, server_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
