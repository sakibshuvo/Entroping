import hashlib
import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence.api_inventory as api_inventory
from entroping.core.evidence.api_inventory import (
    ApiInventoryError,
    build_api_inventory,
    render_api_inventory_markdown,
    run_api_inventory_report,
)
from entroping.core.safe_write import SafeWriteError

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBHOOK_FIXTURE_ROOT = REPO_ROOT / "examples" / "webhook-api"


def test_run_api_inventory_writes_json_from_local_api_signals(tmp_path: Path) -> None:
    openapi_path = _write_text(
        tmp_path / "openapi.yaml",
        """
openapi: 3.0.0
paths:
  /health:
    get:
      operationId: getHealth
  /orders:
    post:
      operationId: createOrder
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: checkout-api
sources:
  spec: openapi.yaml
gates: []
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "graphql.hurl",
        """
# entroping: tags=smoke,graphql
POST http://127.0.0.1:18082/graphql
HTTP 200
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "soap.hurl",
        """
# entroping: tags=soap
POST http://127.0.0.1:18083/soap/orders
HTTP 200
""".strip()
        + "\n",
    )
    _write_text(tmp_path / "schema.graphql", "type Query { health: String }\n")
    _write_text(tmp_path / "contracts" / "orders.proto", "service Orders {}\n")

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "api-inventory.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.api-inventory.v1"
    assert payload["project"] == "checkout-api"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 5,
        "sources_present": 5,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "styles_total": 4,
        "hurl_tests_total": 2,
        "operations_total": 5,
    }
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("configured_openapi", "openapi.yaml")] == {
        "kind": "configured_openapi",
        "style": "rest_openapi",
        "path": "openapi.yaml",
        "state": "present",
        "sha256": hashlib.sha256(openapi_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 2,
        "summary": "2 OpenAPI operations.",
    }
    assert sources[("hurl_test", "tests/graphql.hurl")]["style"] == "graphql"
    assert sources[("hurl_test", "tests/soap.hurl")]["style"] == "soap_xml"
    assert sources[("schema_file", "schema.graphql")]["style"] == "graphql"
    assert sources[("schema_file", "schema.graphql")]["operations"] == 1
    assert sources[("schema_file", "schema.graphql")]["signals"] == [
        {"name": "query", "count": 1},
        {"name": "mutation", "count": 0},
        {"name": "subscription", "count": 0},
    ]
    assert sources[("schema_file", "schema.graphql")]["summary"] == (
        "1 GraphQL root operation (query: 1, mutation: 0, subscription: 0)."
    )
    assert sources[("schema_file", "contracts/orders.proto")]["style"] == "grpc_proto"
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["rest_openapi"]["operations"] == 2
    assert styles["graphql"]["operations"] == 2
    assert styles["graphql"]["hurl_tests"] == 1
    assert styles["soap_xml"]["hurl_tests"] == 1
    assert styles["grpc_proto"]["sources"] == 1
    serialized = json.dumps(payload)
    assert "127.0.0.1" not in serialized
    assert "127.0.0.1:18082/graphql" not in serialized
    assert "POST" not in serialized


def test_api_inventory_detects_webhook_example_event_contract_fixture() -> None:
    packet = build_api_inventory(project_root=WEBHOOK_FIXTURE_ROOT)
    sources = {(source.kind, source.path): source for source in packet.sources}

    assert packet.summary.status == "ready"
    contract = sources[("schema_file", "contracts/order-events.event-contract.yaml")]
    assert contract.style == "webhook_event"
    assert contract.state == "present"
    assert contract.operations == 2
    assert contract.summary == "2 webhook/event contract entries."


def test_api_inventory_no_sources_is_insufficient_markdown(tmp_path: Path) -> None:
    result = run_api_inventory_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "api-inventory.md"
    assert result.packet.summary.status == "insufficient"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping API Inventory" in markdown
    assert "No API styles were detected." in markdown


def test_api_inventory_detects_unknown_http_hurl_without_protocol_tags(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "tests" / "health.hurl",
        """
# entroping: tags=smoke
GET http://127.0.0.1:18080/health
HTTP 200
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.summary.status == "ready"
    assert packet.summary.hurl_tests_total == 1
    assert packet.styles[0].style == "unknown_http"
    assert packet.sources[0].operations == 1


def test_api_inventory_detects_asyncapi_and_webhook_event_contract_sources(
    tmp_path: Path,
) -> None:
    asyncapi_path = _write_text(
        tmp_path / "contracts" / "orders.asyncapi.yaml",
        """
asyncapi: 2.6.0
channels:
  orders.created:
    publish:
      message:
        name: OrderCreated
  orders.cancelled:
    subscribe:
      message:
        name: OrderCancelled
""".strip()
        + "\n",
    )
    webhook_contract_path = _write_text(
        tmp_path / "contracts" / "order-events.event-contract.yaml",
        """
schema_version: example.webhook-events.v1
webhooks:
  order.created:
    method: post
    url: https://hooks.example.test/orders/created
    body:
      example: should-not-appear-in-report
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "webhook.hurl",
        """
# entroping: tags=webhook,event-contract
POST http://127.0.0.1:18080/hooks/order-created
HTTP 202
""".strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "contracts/orders.asyncapi.yaml")] == {
        "kind": "schema_file",
        "style": "asyncapi",
        "path": "contracts/orders.asyncapi.yaml",
        "state": "present",
        "sha256": hashlib.sha256(asyncapi_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 2,
        "summary": "2 AsyncAPI operations/channels.",
    }
    assert sources[("schema_file", "contracts/order-events.event-contract.yaml")] == {
        "kind": "schema_file",
        "style": "webhook_event",
        "path": "contracts/order-events.event-contract.yaml",
        "state": "present",
        "sha256": hashlib.sha256(webhook_contract_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 1,
        "summary": "1 webhook/event contract entry.",
    }
    assert sources[("hurl_test", "tests/webhook.hurl")]["style"] == "webhook_event"
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["asyncapi"]["operations"] == 2
    assert styles["webhook_event"]["operations"] == 2
    assert styles["webhook_event"]["hurl_tests"] == 1
    serialized = json.dumps(payload)
    assert "https://hooks.example.test/orders/created" not in serialized
    assert "should-not-appear-in-report" not in serialized
    assert "127.0.0.1" not in serialized

    markdown = render_api_inventory_markdown(result.packet)
    assert "AsyncAPI" in markdown
    assert "Webhook/Event" in markdown


def test_api_inventory_event_contract_sources_reuse_safety_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contracts_root = tmp_path / "contracts"
    real_contract = _write_text(
        tmp_path / "real.event-contract.yaml",
        "webhooks:\n  order.created: {}\n",
    )
    contracts_root.mkdir()
    os.symlink(real_contract, contracts_root / "linked.event-contract.yaml")
    (contracts_root / "binary.event-contract.yaml").write_bytes(b"\xff")
    _write_text(contracts_root / "secret.event-contract.yaml", "sk-proj-" + ("a" * 24))
    _write_text(contracts_root / "bad.event-contract.yaml", "webhooks: []\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("schema_file", "contracts/linked.event-contract.yaml")].state == "unsafe"
    assert "symlinked component" in (
        sources[("schema_file", "contracts/linked.event-contract.yaml")].summary
    )
    assert sources[("schema_file", "contracts/binary.event-contract.yaml")].state == "invalid"
    assert "UTF-8" in sources[("schema_file", "contracts/binary.event-contract.yaml")].summary
    assert sources[("schema_file", "contracts/secret.event-contract.yaml")].state == "unsafe"
    assert "secret-like content" in (
        sources[("schema_file", "contracts/secret.event-contract.yaml")].summary
    )
    assert sources[("schema_file", "contracts/bad.event-contract.yaml")].state == "invalid"
    assert "webhooks or events mapping" in (
        sources[("schema_file", "contracts/bad.event-contract.yaml")].summary
    )

    oversized_root = tmp_path / "oversized"
    _write_text(
        oversized_root / "contracts" / "oversized.event-contract.yaml",
        "webhooks:\n  order.created: {}\n",
    )
    monkeypatch.setattr(api_inventory, "_MAX_API_INVENTORY_ARTIFACT_BYTES", 1)

    oversized_packet = build_api_inventory(project_root=oversized_root)

    assert oversized_packet.sources[0].state == "invalid"
    assert "exceeds 1 bytes" in oversized_packet.sources[0].summary


def test_api_inventory_marks_bad_asyncapi_sources_invalid(tmp_path: Path) -> None:
    _write_text(tmp_path / "contracts" / "invalid.asyncapi.yaml", "{not yaml: [}\n")
    _write_text(tmp_path / "contracts" / "list.asyncapi.yaml", "[]\n")
    _write_text(tmp_path / "contracts" / "no-channels.asyncapi.yaml", "asyncapi: 2.6.0\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    invalid_yaml = sources[("schema_file", "contracts/invalid.asyncapi.yaml")]
    assert invalid_yaml.state == "invalid"
    assert "Invalid AsyncAPI YAML" in invalid_yaml.summary
    list_document = sources[("schema_file", "contracts/list.asyncapi.yaml")]
    assert list_document.state == "invalid"
    assert "operations or channels" in list_document.summary
    no_channels = sources[("schema_file", "contracts/no-channels.asyncapi.yaml")]
    assert no_channels.state == "invalid"
    assert "operations or channels" in no_channels.summary


def test_api_inventory_counts_asyncapi_operations_and_sparse_channels(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "contracts" / "ops.asyncapi.yaml",
        """
asyncapi: 3.0.0
operations:
  publishOrderCreated:
    action: send
  consumeOrderCancelled:
    action: receive
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "contracts" / "sparse.asyncapi.yaml",
        """
asyncapi: 2.6.0
channels:
  orders.created: not-a-mapping
  orders.cancelled:
    bindings: {}
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("schema_file", "contracts/ops.asyncapi.yaml")].operations == 2
    assert sources[("schema_file", "contracts/sparse.asyncapi.yaml")].operations == 2


def test_api_inventory_marks_bad_webhook_event_sources_invalid(tmp_path: Path) -> None:
    _write_text(tmp_path / "contracts" / "invalid.event-contract.yaml", "{not yaml: [}\n")
    _write_text(tmp_path / "contracts" / "list.event-contract.yaml", "[]\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    invalid_yaml = sources[("schema_file", "contracts/invalid.event-contract.yaml")]
    assert invalid_yaml.state == "invalid"
    assert "Invalid webhook/event contract YAML" in invalid_yaml.summary
    list_document = sources[("schema_file", "contracts/list.event-contract.yaml")]
    assert list_document.state == "invalid"
    assert "webhooks or events mapping" in list_document.summary


def test_api_inventory_counts_webhook_event_plurals_and_asyncapi_tags(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "contracts" / "orders.event-contract.yaml",
        """
event_contracts:
  order.created: {}
  order.cancelled: {}
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "asyncapi.hurl",
        "# entroping: tags=asyncapi\nPOST http://127.0.0.1:18080/events\nHTTP 202\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    contract = sources[("schema_file", "contracts/orders.event-contract.yaml")]
    assert contract.operations == 2
    assert contract.summary == "2 webhook/event contract entries."
    assert sources[("hurl_test", "tests/asyncapi.hurl")].style == "asyncapi"


def test_api_inventory_detects_conventional_asyncapi_and_webhook_filenames(
    tmp_path: Path,
) -> None:
    _ = _write_text(
        tmp_path / "contracts" / "asyncapi.yaml",
        """
asyncapi: 3.0.0
channels:
  orders.created: {}
""".strip()
        + "\n",
    )
    _ = _write_text(
        tmp_path / "contracts" / "webhooks.yaml",
        """
webhooks:
  order.created: {}
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("schema_file", "contracts/asyncapi.yaml")].style == "asyncapi"
    assert sources[("schema_file", "contracts/webhooks.yaml")].style == "webhook_event"


def test_api_inventory_detects_bruno_collection_files_without_leaking_values(
    tmp_path: Path,
) -> None:
    manifest_path = _write_text(
        tmp_path / "collections" / "checkout" / "bruno.json",
        """
{
  "version": "1",
  "name": "checkout-internal",
  "type": "collection"
}
""".strip()
        + "\n",
    )
    request_path = _write_text(
        tmp_path / "collections" / "checkout" / "orders" / "create-order.bru",
        """
meta {
  name: Create order
  type: http
}

post {
  url: https://internal.example.test/orders
  body: json
  auth: bearer
}

headers {
  x-request-id: trace-value-should-not-appear
}
""".strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "collections/checkout/bruno.json")] == {
        "kind": "schema_file",
        "style": "bruno_collection",
        "path": "collections/checkout/bruno.json",
        "state": "present",
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 0,
        "summary": "Bruno collection manifest.",
    }
    assert sources[
        ("schema_file", "collections/checkout/orders/create-order.bru")
    ] == {
        "kind": "schema_file",
        "style": "bruno_collection",
        "path": "collections/checkout/orders/create-order.bru",
        "state": "present",
        "sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 1,
        "summary": "1 Bruno request file.",
    }
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["bruno_collection"]["sources"] == 2
    assert styles["bruno_collection"]["operations"] == 1
    serialized = json.dumps(payload)
    assert "checkout-internal" not in serialized
    assert "Create order" not in serialized
    assert "https://internal.example.test/orders" not in serialized
    assert "trace-value-should-not-appear" not in serialized

    markdown = render_api_inventory_markdown(result.packet)
    assert "Bruno collection" in markdown


def test_api_inventory_marks_bad_bruno_collection_sources_invalid_or_unsafe(
    tmp_path: Path,
) -> None:
    contracts_root = tmp_path / "collections" / "checkout"
    _write_text(contracts_root / "invalid.bruno.json", "{not yaml: [}\n")
    _write_text(contracts_root / "list.bruno.json", "[]\n")
    _write_text(contracts_root / "secret.bru", "sk-proj-" + ("a" * 24))
    (contracts_root / "binary.bru").parent.mkdir(parents=True, exist_ok=True)
    (contracts_root / "binary.bru").write_bytes(b"\xff")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    invalid_yaml = sources[("schema_file", "collections/checkout/invalid.bruno.json")]
    assert invalid_yaml.state == "invalid"
    assert "Invalid Bruno collection YAML" in invalid_yaml.summary
    list_document = sources[("schema_file", "collections/checkout/list.bruno.json")]
    assert list_document.state == "invalid"
    assert "Bruno collection document must be an object" in list_document.summary
    secret_source = sources[("schema_file", "collections/checkout/secret.bru")]
    assert secret_source.state == "unsafe"
    assert "secret-like content" in secret_source.summary
    binary_source = sources[("schema_file", "collections/checkout/binary.bru")]
    assert binary_source.state == "invalid"
    assert "UTF-8" in binary_source.summary


def test_api_inventory_counts_graphql_root_operations_without_leaking_names(
    tmp_path: Path,
) -> None:
    schema_path = _write_text(
        tmp_path / "schema.graphql",
        '''
"""customer: internal context should not appear"""
type Query {
  # comment-only lines should not count
  health: String
  order(id: ID!): Order
}

extend type Query {
  orders(
    status: OrderStatus = OPEN
  ): [Order!]!
}

type Mutation {
  createOrder(input: OrderInput!): Order!
}

type Subscription {
  orderCreated: Order!
}

type Order {
  id: ID!
}
'''.strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "schema.graphql")] == {
        "kind": "schema_file",
        "style": "graphql",
        "path": "schema.graphql",
        "state": "present",
        "sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 5,
        "signals": [
            {"name": "query", "count": 3},
            {"name": "mutation", "count": 1},
            {"name": "subscription", "count": 1},
        ],
        "summary": "5 GraphQL root operations (query: 3, mutation: 1, subscription: 1).",
    }
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["graphql"]["operations"] == 5
    assert styles["graphql"]["signals"] == [
        {"name": "query", "count": 3},
        {"name": "mutation", "count": 1},
        {"name": "subscription", "count": 1},
    ]
    serialized = json.dumps(payload)
    assert "health" not in serialized
    assert "orderCreated" not in serialized
    assert "customer: internal context" not in serialized
    assert "OrderStatus" not in serialized


def test_api_inventory_keeps_non_operation_graphql_sdl_present(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "types.graphqls",
        """
type Order {
  id: ID!
}

input OrderInput {
  id: ID!
}
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "types.graphqls")]
    assert source.state == "present"
    assert source.operations == 0
    assert [signal.model_dump(mode="json") for signal in source.signals] == [
        {"name": "query", "count": 0},
        {"name": "mutation", "count": 0},
        {"name": "subscription", "count": 0},
    ]
    assert source.summary == "0 GraphQL root operations (query: 0, mutation: 0, subscription: 0)."


def test_api_inventory_counts_grpc_proto_rpc_operations_without_leaking_names(
    tmp_path: Path,
) -> None:
    proto_path = _write_text(
        tmp_path / "contracts" / "orders.proto",
        """
syntax = "proto3";
package internal.orders;

// rpc CommentedOut(CommentedRequest) returns (CommentedResponse);
/*
rpc BlockCommented(BlockRequest) returns (BlockResponse);
*/
service Orders {
  option deprecated = false;
  rpc CreateOrder (CreateOrderRequest) returns (Order);
  rpc GetOrder (GetOrderRequest) returns (Order) {}
  rpc StreamOrders (StreamOrdersRequest) returns (stream Order);
}

message Order {
  string internal_url = 1;
  string note = 2 [json_name = "rpc NotADeclaration"];
}
""".strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "contracts/orders.proto")] == {
        "kind": "schema_file",
        "style": "grpc_proto",
        "path": "contracts/orders.proto",
        "state": "present",
        "sha256": hashlib.sha256(proto_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 3,
        "summary": "3 proto RPC operations.",
    }
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["grpc_proto"]["operations"] == 3
    serialized = json.dumps(payload)
    assert "CreateOrder" not in serialized
    assert "StreamOrders" not in serialized
    assert "internal.orders" not in serialized
    assert "NotADeclaration" not in serialized


def test_api_inventory_keeps_non_rpc_proto_present(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "contracts" / "messages.proto",
        """
syntax = "proto3";

message Order {
  string id = 1;
}
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "contracts/messages.proto")]
    assert source.state == "present"
    assert source.operations == 0
    assert source.summary == "0 proto RPC operations."


def test_api_inventory_keeps_wsdl_schema_as_present_style_evidence(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "contracts" / "orders.wsdl", "<definitions />\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "contracts/orders.wsdl")]
    assert source.state == "present"
    assert source.style == "soap_xml"
    assert source.operations == 0
    assert source.summary == "0 WSDL operations."


def test_api_inventory_marks_bad_wsdl_sources_invalid_or_unsafe(tmp_path: Path) -> None:
    _write_text(tmp_path / "contracts" / "malformed.wsdl", "<definitions><portType>\n")
    _write_text(
        tmp_path / "contracts" / "entity.wsdl",
        """
<!DOCTYPE definitions [
  <!ENTITY secret "should-not-appear">
]>
<definitions>&secret;</definitions>
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    malformed = sources[("schema_file", "contracts/malformed.wsdl")]
    assert malformed.state == "invalid"
    assert malformed.operations == 0
    assert "Invalid WSDL XML" in malformed.summary
    entity = sources[("schema_file", "contracts/entity.wsdl")]
    assert entity.state == "unsafe"
    assert entity.operations == 0
    assert "Unsafe WSDL XML construct" in entity.summary
    assert "should-not-appear" not in packet.model_dump_json()


def test_api_inventory_keeps_generic_schema_styles_as_present_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(api_inventory._SCHEMA_EXTENSIONS, ".http-schema", "unknown_http")
    _write_text(tmp_path / "contracts" / "legacy.http-schema", "legacy schema\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "contracts/legacy.http-schema")]
    assert source.state == "present"
    assert source.style == "unknown_http"
    assert source.operations == 0
    assert source.summary == "Unknown HTTP schema file."


def test_api_inventory_counts_wsdl_operations_without_leaking_names(
    tmp_path: Path,
) -> None:
    wsdl_path = _write_text(
        tmp_path / "contracts" / "orders.wsdl",
        """
<?xml version="1.0" encoding="UTF-8"?>
<definitions
  xmlns="http://schemas.xmlsoap.org/wsdl/"
  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
  targetNamespace="https://internal.example.test/orders"
>
  <portType name="OrdersPortType">
    <operation name="CreateOrder">
      <input message="tns:CreateOrderRequest" />
      <output message="tns:CreateOrderResponse" />
    </operation>
    <operation name="GetOrder">
      <input message="tns:GetOrderRequest" />
      <output message="tns:GetOrderResponse" />
    </operation>
  </portType>
  <portType name="PaymentsPortType">
    <operation name="CreatePayment">
      <input message="tns:CreatePaymentRequest" />
      <output message="tns:CreatePaymentResponse" />
    </operation>
  </portType>
  <binding name="OrdersBinding" type="tns:OrdersPortType">
    <soap:binding transport="http://schemas.xmlsoap.org/soap/http" />
    <operation name="CreateOrder">
      <soap:operation soapAction="https://internal.example.test/create-order" />
    </operation>
  </binding>
  <service name="OrdersService">
    <port name="OrdersPort" binding="tns:OrdersBinding">
      <soap:address location="https://internal.example.test/soap/orders" />
    </port>
  </service>
</definitions>
""".strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "contracts/orders.wsdl")] == {
        "kind": "schema_file",
        "style": "soap_xml",
        "path": "contracts/orders.wsdl",
        "state": "present",
        "sha256": hashlib.sha256(wsdl_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 3,
        "summary": "3 WSDL operations.",
    }
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["soap_xml"]["operations"] == 3
    serialized = json.dumps(payload)
    assert "CreateOrder" not in serialized
    assert "CreatePayment" not in serialized
    assert "OrdersService" not in serialized
    assert "internal.example.test" not in serialized


def test_api_inventory_counts_only_top_level_wsdl_port_type_operations(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "contracts" / "nested.wsdl",
        """
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/">
  <types>
    <schema>
      <portType name="NestedNoise">
        <operation name="DoNotCount" />
      </portType>
    </schema>
  </types>
  <portType name="OrdersPortType">
    <operation name="CreateOrder" />
  </portType>
</definitions>
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "contracts/nested.wsdl")]
    assert source.state == "present"
    assert source.operations == 1
    assert source.summary == "1 WSDL operation."


def test_api_inventory_keeps_non_definitions_wsdl_as_zero_operation_evidence(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "contracts" / "not-definitions.wsdl",
        """
<schema>
  <portType name="NotWsdl">
    <operation name="DoNotCount" />
  </portType>
</schema>
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    source = sources[("schema_file", "contracts/not-definitions.wsdl")]
    assert source.state == "present"
    assert source.operations == 0
    assert source.summary == "0 WSDL operations."


def test_api_inventory_detects_websocket_realtime_contract_and_hurl_tags(
    tmp_path: Path,
) -> None:
    websocket_contract_path = _write_text(
        tmp_path / "contracts" / "chat.websocket-contract.yaml",
        """
websockets:
  chat.message:
    url: wss://socket.example.test/chat
    example: should-not-appear-in-report
  chat.typing:
    url: wss://socket.example.test/typing
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "websocket-handshake.hurl",
        """
# entroping: tags=websocket,realtime
GET http://127.0.0.1:18080/socket
HTTP 101
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "socketio-poll.hurl",
        """
# entroping: tags=socketio
GET http://127.0.0.1:18080/socket.io/
HTTP 200
""".strip()
        + "\n",
    )

    result = run_api_inventory_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("schema_file", "contracts/chat.websocket-contract.yaml")] == {
        "kind": "schema_file",
        "style": "websocket_realtime",
        "path": "contracts/chat.websocket-contract.yaml",
        "state": "present",
        "sha256": hashlib.sha256(websocket_contract_path.read_bytes()).hexdigest(),
        "tags": [],
        "operations": 2,
        "summary": "2 WebSocket/realtime entries.",
    }
    assert sources[("hurl_test", "tests/websocket-handshake.hurl")]["style"] == (
        "websocket_realtime"
    )
    assert sources[("hurl_test", "tests/socketio-poll.hurl")]["style"] == (
        "websocket_realtime"
    )
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["websocket_realtime"]["operations"] == 4
    assert styles["websocket_realtime"]["hurl_tests"] == 2
    assert styles["websocket_realtime"]["tags"] == [
        "realtime",
        "socketio",
        "websocket",
    ]
    serialized = json.dumps(payload)
    assert "wss://socket.example.test" not in serialized
    assert "should-not-appear-in-report" not in serialized
    assert "127.0.0.1" not in serialized

    markdown = render_api_inventory_markdown(result.packet)
    assert "WebSocket/realtime" in markdown


def test_api_inventory_websocket_realtime_sources_reuse_safety_boundaries(
    tmp_path: Path,
) -> None:
    contracts_root = tmp_path / "contracts"
    real_contract = _write_text(
        tmp_path / "real.websocket.yaml",
        "channels:\n  chat.message: {}\n",
    )
    contracts_root.mkdir()
    os.symlink(real_contract, contracts_root / "linked.websocket.yaml")
    (contracts_root / "binary.websocket.yaml").write_bytes(b"\xff")
    _write_text(contracts_root / "secret.websocket.yaml", "sk-proj-" + ("a" * 24))
    _write_text(contracts_root / "bad.websocket.yaml", "[]\n")
    _write_text(contracts_root / "invalid.websocket.yaml", "{not yaml: [}\n")
    _write_text(contracts_root / "missing-map.websocket.yaml", "name: chat\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("schema_file", "contracts/linked.websocket.yaml")].state == "unsafe"
    assert "symlinked component" in (
        sources[("schema_file", "contracts/linked.websocket.yaml")].summary
    )
    assert sources[("schema_file", "contracts/binary.websocket.yaml")].state == "invalid"
    assert "UTF-8" in sources[("schema_file", "contracts/binary.websocket.yaml")].summary
    assert sources[("schema_file", "contracts/secret.websocket.yaml")].state == "unsafe"
    assert "secret-like content" in (
        sources[("schema_file", "contracts/secret.websocket.yaml")].summary
    )
    assert sources[("schema_file", "contracts/bad.websocket.yaml")].state == "invalid"
    assert "realtime mapping" in sources[
        ("schema_file", "contracts/bad.websocket.yaml")
    ].summary
    assert sources[("schema_file", "contracts/invalid.websocket.yaml")].state == "invalid"
    assert "Invalid WebSocket/realtime contract YAML" in (
        sources[("schema_file", "contracts/invalid.websocket.yaml")].summary
    )
    assert sources[("schema_file", "contracts/missing-map.websocket.yaml")].state == (
        "invalid"
    )
    assert "realtime mapping" in sources[
        ("schema_file", "contracts/missing-map.websocket.yaml")
    ].summary


def test_api_inventory_keeps_empty_and_ambiguous_hurl_sources_unknown(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "empty.hurl",
        "# entroping: tags=smoke\n",
    )
    _write_text(
        tmp_path / "tests" / "xml-parser.hurl",
        """
# entroping: tags=xml-parser
GET http://127.0.0.1:18080/health
HTTP 200
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "conflict.hurl",
        """
# entroping: tags=rest,graphql
POST http://127.0.0.1:18080/graphql
HTTP 200
""".strip()
        + "\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("hurl_test", "tests/empty.hurl")].style == "unknown_http"
    assert sources[("hurl_test", "tests/empty.hurl")].operations == 0
    assert sources[("hurl_test", "tests/xml-parser.hurl")].style == "unknown_http"
    assert sources[("hurl_test", "tests/xml-parser.hurl")].operations == 1
    assert sources[("hurl_test", "tests/conflict.hurl")].style == "graphql"


def test_api_inventory_marks_missing_invalid_and_unsafe_sources(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        """
project: unsafe-api
sources:
  spec: missing-openapi.yaml
gates: []
""".strip()
        + "\n",
    )
    _write_text(tmp_path / "api" / "openapi.yaml", "{not yaml: [}\n")
    _write_text(tmp_path / "schema.graphql", "sk-proj-" + ("a" * 24))
    real_proto = tmp_path / "real.proto"
    real_proto.write_text("service Unsafe {}\n", encoding="utf-8")
    os.symlink(real_proto, tmp_path / "unsafe.proto")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("configured_openapi", "missing-openapi.yaml")].state == "missing"
    assert sources[("conventional_openapi", "api/openapi.yaml")].state == "invalid"
    assert "Invalid OpenAPI YAML" in sources[("conventional_openapi", "api/openapi.yaml")].summary
    assert sources[("schema_file", "schema.graphql")].state == "unsafe"
    assert "secret-like content" in sources[("schema_file", "schema.graphql")].summary
    assert sources[("schema_file", "unsafe.proto")].state == "unsafe"
    assert "symlinked component" in sources[("schema_file", "unsafe.proto")].summary
    assert packet.summary.status == "partial"
    assert packet.summary.sources_missing == 1
    assert packet.summary.sources_invalid == 1
    assert packet.summary.sources_unsafe == 2
    assert "sk-proj" not in packet.model_dump_json()


def test_api_inventory_marks_bad_qanstitution_and_hurl_metadata_invalid(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "qanstitution.yaml", "project: [bad\n")
    _write_text(
        tmp_path / "tests" / "bad.hurl",
        "# entroping: tags=\nGET http://127.0.0.1:18080/health\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("configured_openapi", "qanstitution.yaml")].state == "invalid"
    assert "Invalid YAML" in sources[("configured_openapi", "qanstitution.yaml")].summary
    assert sources[("hurl_test", "tests/bad.hurl")].state == "invalid"
    assert "empty tag value" in sources[("hurl_test", "tests/bad.hurl")].summary
    assert packet.summary.status == "partial"


def test_api_inventory_handles_empty_and_unsafe_configured_specs(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "qanstitution.yaml", "project: no-sources\ngates: []\n")

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources == ()
    assert packet.summary.status == "insufficient"

    unsafe_refs = (
        ("bad\u0001.yaml", "control characters"),
        ("https://example.test/openapi.yaml", "Remote API source references"),
        ("file://openapi.yaml", "Unsupported API source reference scheme"),
        (str(tmp_path / "openapi.yaml"), "project-relative"),
        ("../openapi.yaml", "project root"),
        ("foo/../../openapi.yaml", "project root"),
    )
    for spec_ref, expected_summary in unsafe_refs:
        _write_text(
            tmp_path / "qanstitution.yaml",
            f"project: unsafe-ref\nsources:\n  spec: {json.dumps(spec_ref)}\ngates: []\n",
        )

        packet = build_api_inventory(project_root=tmp_path)

        assert len(packet.sources) == 1
        assert packet.sources[0].state == "unsafe"
        assert expected_summary in packet.sources[0].summary


def test_api_inventory_marks_configured_openapi_source_safety_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_openapi = _write_text(
        tmp_path / "real-openapi.yaml",
        "openapi: 3.0.0\npaths: {}\n",
    )
    os.symlink(real_openapi, tmp_path / "openapi.yaml")
    _write_text(
        tmp_path / "qanstitution.yaml",
        "project: configured\nsources:\n  spec: openapi.yaml\ngates: []\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources[0].kind == "configured_openapi"
    assert packet.sources[0].state == "unsafe"
    assert "symlinked component" in packet.sources[0].summary

    (tmp_path / "openapi.yaml").unlink()
    (tmp_path / "openapi.yaml").mkdir()

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources[0].state == "unsafe"
    assert "not a file" in packet.sources[0].summary

    (tmp_path / "openapi.yaml").rmdir()
    _write_text(tmp_path / "openapi.yaml", "sk-proj-" + ("a" * 24))

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources[0].state == "unsafe"
    assert "secret-like content" in packet.sources[0].summary

    _write_text(tmp_path / "openapi.yaml", "openapi: 3.0.0\npaths: {}\n")
    monkeypatch.setattr(api_inventory, "_MAX_API_INVENTORY_ARTIFACT_BYTES", 1)

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert "exceeds 1 bytes" in packet.sources[0].summary


def test_api_inventory_marks_bad_openapi_shapes_invalid(tmp_path: Path) -> None:
    _write_text(tmp_path / "openapi.yaml", "[]\n")
    _write_text(tmp_path / "swagger.yaml", "openapi: 3.0.0\npaths: []\n")
    _write_text(
        tmp_path / "api" / "openapi.yaml",
        "openapi: 3.0.0\npaths:\n  /health: []\n",
    )

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("conventional_openapi", "openapi.yaml")].state == "invalid"
    assert sources[("conventional_openapi", "swagger.yaml")].state == "invalid"
    assert sources[("conventional_openapi", "api/openapi.yaml")].state == "present"
    assert sources[("conventional_openapi", "api/openapi.yaml")].operations == 0


def test_api_inventory_does_not_duplicate_invalid_configured_openapi(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "qanstitution.yaml",
        "project: duplicate-invalid\nsources:\n  spec: openapi.yaml\ngates: []\n",
    )
    _write_text(tmp_path / "openapi.yaml", "{not yaml: [}\n")

    packet = build_api_inventory(project_root=tmp_path)

    assert [(source.kind, source.path) for source in packet.sources] == [
        ("configured_openapi", "openapi.yaml")
    ]
    assert packet.sources[0].state == "invalid"


def test_api_inventory_invalid_only_sources_are_partial(tmp_path: Path) -> None:
    _write_text(tmp_path / "openapi.yaml", "{not yaml: [}\n")

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 0
    assert packet.summary.sources_invalid == 1


def test_api_inventory_detects_rest_and_grpc_hurl_tags_and_ignored_paths(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "rest.hurl",
        "# entroping: tags=rest\nGET http://127.0.0.1:18080/health\n",
    )
    _write_text(
        tmp_path / "tests" / "grpc.hurl",
        "# entroping: tags=grpc\nPOST http://127.0.0.1:18080/grpc\n",
    )
    _write_text(
        tmp_path / "tests" / ".ignored" / "ignored.hurl",
        "# entroping: tags=graphql\nPOST http://127.0.0.1:18080/graphql\n",
    )
    _write_text(tmp_path / "reports" / "schema.graphql", "type Query { health: String }\n")
    _write_text(tmp_path / ".hidden" / "schema.graphql", "type Query { hidden: String }\n")

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("hurl_test", "tests/rest.hurl")].style == "rest_openapi"
    assert sources[("hurl_test", "tests/grpc.hurl")].style == "grpc_proto"
    assert ("hurl_test", "tests/.ignored/ignored.hurl") not in sources
    assert ("schema_file", "reports/schema.graphql") not in sources
    assert ("schema_file", ".hidden/schema.graphql") not in sources


def test_api_inventory_marks_hurl_source_safety_states(tmp_path: Path) -> None:
    real_hurl = _write_text(
        tmp_path / "real.hurl",
        "# entroping: tags=graphql\nPOST http://127.0.0.1:18080/graphql\n",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    os.symlink(real_hurl, tests_dir / "linked.hurl")
    _write_text(tests_dir / "secret.hurl", "sk-proj-" + ("a" * 24))

    packet = build_api_inventory(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("hurl_test", "tests/linked.hurl")].state == "unsafe"
    assert sources[("hurl_test", "tests/secret.hurl")].state == "unsafe"


def test_api_inventory_marks_binary_schema_invalid(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.graphql"
    schema_path.write_bytes(b"\xff")

    packet = build_api_inventory(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert "UTF-8" in packet.sources[0].summary


def test_api_inventory_marks_resolution_and_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(tmp_path / "schema.graphql", "type Query { health: String }\n")

    def reject_path(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside")

    monkeypatch.setattr(api_inventory, "first_symlink_path_component", reject_path)

    packet = build_api_inventory(project_root=tmp_path)
    assert packet.sources[0].state == "unsafe"
    assert "must stay under" in packet.sources[0].summary

    monkeypatch.setattr(api_inventory, "first_symlink_path_component", lambda *_a, **_k: None)

    def unreadable(self: Path) -> bytes:
        if self.name == "schema.graphql":
            raise OSError("permission denied")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", unreadable)

    packet = build_api_inventory(project_root=tmp_path)
    assert packet.sources[0].state == "invalid"
    assert "Could not read" in packet.sources[0].summary


def test_api_inventory_defensive_path_helpers(tmp_path: Path) -> None:
    assert api_inventory._ignored(tmp_path.parent / "outside.graphql", root=tmp_path) is True
    assert api_inventory._relative_path(tmp_path.parent / "outside.graphql", root=tmp_path)
    assert api_inventory._safe_optional_text(None) is None


def test_api_inventory_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ApiInventoryError, match="Unsupported API inventory output"):
        run_api_inventory_report(project_root=tmp_path, output="html")
    with pytest.raises(ApiInventoryError, match="must stay under"):
        run_api_inventory_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "api-inventory.json",
        )
    with pytest.raises(ApiInventoryError, match="must not be written into"):
        run_api_inventory_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "api-inventory.json",
        )
    monkeypatch.setattr(api_inventory, "first_symlink_path_component", lambda *_a, **_k: None)
    with pytest.raises(ApiInventoryError, match="must stay under"):
        run_api_inventory_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-api-inventory.json",
        )


def test_api_inventory_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(ApiInventoryError, match="symlinked component"):
        run_api_inventory_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "api-inventory.json",
        )


def test_api_inventory_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_api_inventory(project_root=tmp_path)
    monkeypatch.setattr(
        api_inventory,
        "build_api_inventory",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(ApiInventoryError, match="contains secret-like content"):
        run_api_inventory_report(project_root=tmp_path, output="json")


def test_api_inventory_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(api_inventory, "safe_write_text", fail_safe_write)

    with pytest.raises(ApiInventoryError, match="disk full"):
        run_api_inventory_report(project_root=tmp_path, output="json")


def test_api_inventory_markdown_escapes_table_cells(tmp_path: Path) -> None:
    _write_text(tmp_path / "schema.graphql", "type Query { health: String }\n")
    packet = build_api_inventory(project_root=tmp_path)
    escaped = packet.model_copy(
        update={
            "sources": (
                packet.sources[0].model_copy(update={"summary": r"schema\|detected"}),
            )
        }
    )

    markdown = render_api_inventory_markdown(escaped)

    assert "schema&#92;\\|detected" in markdown


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
