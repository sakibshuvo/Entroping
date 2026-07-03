"""Tests for the support API demo fixture."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "examples" / "support-api"


def test_support_demo_server_routes_ticket_list_and_mutations() -> None:
    server = _load_support_server()

    list_response = server.route_request("GET", "/tickets?status=open&limit=2")
    assert list_response.status == 200
    assert json.loads(list_response.body) == {
        "items": [
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
        ],
        "next_cursor": "cursor-002",
    }
    assert list_response.headers["X-Request-Id"] == "support-demo-request"

    create_response = server.route_request(
        "POST",
        "/tickets",
        b'{"subject":"Cannot download invoice","priority":"high"}',
        {"X-Customer-Id": "cust-123"},
    )
    assert create_response.status == 201
    assert create_response.headers["Location"] == "/tickets/tkt_cust-123_001"
    assert create_response.headers["X-Audit-Id"] == "audit-create-ticket"
    assert json.loads(create_response.body)["status"] == "open"

    patch_response = server.route_request(
        "PATCH",
        "/tickets/tkt_cust-123_001/status",
        b'{"status":"triaged"}',
        {"X-Agent-Id": "agent-007"},
    )
    assert patch_response.status == 200
    assert patch_response.headers["X-Audit-Id"] == "audit-update-ticket"
    assert json.loads(patch_response.body) == {
        "id": "tkt_cust-123_001",
        "status": "triaged",
    }


def test_support_demo_server_rejects_missing_boundary_inputs() -> None:
    server = _load_support_server()

    create_response = server.route_request(
        "POST",
        "/tickets",
        b'{"subject":"Cannot download invoice","priority":"high"}',
    )
    assert create_response.status == 400
    assert json.loads(create_response.body)["error"] == "missing_customer_header"

    patch_response = server.route_request(
        "PATCH",
        "/tickets/tkt_001/status",
        b'{"status":"triaged"}',
    )
    assert patch_response.status == 400
    assert json.loads(patch_response.body)["error"] == "missing_agent_header"


def test_support_fixture_files_exercise_distinct_api_shapes() -> None:
    openapi = yaml.safe_load((FIXTURE_ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    qanstitution = yaml.safe_load((FIXTURE_ROOT / "qanstitution.yaml").read_text(encoding="utf-8"))
    hurl = (FIXTURE_ROOT / "tests" / "support_smoke.hurl").read_text(encoding="utf-8")
    readme = (FIXTURE_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/meta/VAULT_INDEX.md").read_text(encoding="utf-8")

    assert sorted(openapi["paths"]) == [
        "/health",
        "/tickets",
        "/tickets/{ticket_id}/events",
        "/tickets/{ticket_id}/status",
    ]
    assert openapi["paths"]["/tickets"]["get"]["parameters"][0]["in"] == "query"
    assert openapi["paths"]["/tickets"]["post"]["parameters"][0]["name"] == "X-Customer-Id"
    status_parameters = openapi["paths"]["/tickets/{ticket_id}/status"]["patch"]["parameters"]
    assert status_parameters[0]["name"] == "ticket_id"

    gate_conditions = {gate["id"]: gate["condition"] for gate in qanstitution["gates"]}
    assert gate_conditions["ticket_request_id"] == "path startswith '/tickets'"
    assert gate_conditions["ticket_creation_location"] == "method == 'POST'"
    assert gate_conditions["ticket_mutation_audit"] == "method == 'PATCH'"
    assert gate_conditions["support_smoke_latency"] == "tags contains 'support'"

    assert "# entroping: tags=smoke,support" in hurl
    assert "# entroping: story_id=SUP-001" in hurl
    assert "GET http://127.0.0.1:18081/tickets?status=open&limit=2" in hurl
    assert "X-Customer-Id: cust-123" in hurl
    assert "PATCH http://127.0.0.1:18081/tickets/tkt_cust-123_001/status" in hurl
    assert 'header "X-Audit-Id" exists' in hurl

    required_commands = [
        "python examples/support-api/demo_server.py --port 18081",
        "uv run --project ../.. entroping architect build --new --tag support",
        "cp envs/local.env.example envs/local.env",
        (
            "uv run --project ../.. entroping run --env local --tag support "
            "--report html --report json --report junit --report drift"
        ),
        "cp reports/run-latest.json reports/run-baseline.json",
        "uv run --project ../.. entroping report promote-drift-baseline",
        (
            "uv run --project ../.. entroping run --env local --tag support "
            "--drift-check --report html --report json --report junit --report drift"
        ),
        (
            "uv run --project ../.. entroping report delta "
            "--base reports/run-baseline.json --current reports/run-latest.json "
            "--output md > reports/run-delta.md"
        ),
    ]
    for command in required_commands:
        assert command in readme

    for artifact in [
        "tests/generated/",
        "reports/run-latest.html",
        "reports/run-latest.json",
        "reports/junit.xml",
        "reports/drift.json",
        "reports/drift-baseline.candidate.json",
        ".entroping/drift-baseline.json",
        "reports/run-delta.md",
    ]:
        assert artifact in readme

    assert "different from the checkout fixture" in readme
    assert "API-first/backend-integrity" in readme
    assert "generic AI QA" not in readme
    assert "entroping run --tag support --report html --report json --report junit" in readme
    assert "API integrity quickstart" in root_readme
    assert "examples/support-api/README.md#api-integrity-quickstart" in root_readme
    assert "[examples/support-api](examples/support-api/README.md)" in root_readme
    assert "[[examples/support-api/README|Support API demo fixture]]" in index


def _load_support_server() -> ModuleType:
    server_path = FIXTURE_ROOT / "demo_server.py"
    spec = importlib.util.spec_from_file_location("support_demo_server", server_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
