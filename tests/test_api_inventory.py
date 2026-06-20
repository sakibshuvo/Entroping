import hashlib
import json
import os
from pathlib import Path

import pytest

import entroping.core.api_inventory as api_inventory
from entroping.core.api_inventory import (
    ApiInventoryError,
    build_api_inventory,
    render_api_inventory_markdown,
    run_api_inventory_report,
)
from entroping.core.safe_write import SafeWriteError


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
        "operations_total": 4,
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
    assert sources[("schema_file", "contracts/orders.proto")]["style"] == "grpc_proto"
    styles = {style["style"]: style for style in payload["styles"]}
    assert styles["rest_openapi"]["operations"] == 2
    assert styles["graphql"]["hurl_tests"] == 1
    assert styles["soap_xml"]["hurl_tests"] == 1
    assert styles["grpc_proto"]["sources"] == 1
    serialized = json.dumps(payload)
    assert "127.0.0.1" not in serialized
    assert "127.0.0.1:18082/graphql" not in serialized
    assert "POST" not in serialized


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
        run_api_inventory_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]
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
