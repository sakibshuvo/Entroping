import json
import os
from pathlib import Path

import pytest

import entroping.core.readiness.mutation_readiness as mutation_readiness
from entroping.core.readiness.mutation_readiness import (
    MutationReadinessError,
    build_mutation_readiness,
    render_mutation_readiness_markdown,
    run_mutation_readiness_report,
)
from entroping.core.safe_write import SafeWriteError


def test_run_mutation_readiness_writes_json_from_generated_hurl_and_reports(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "security" / "auth.hurl",
        """
# entroping: tags=generated,negative,security
# entroping: source=openapi
# entroping: operation_id=getOrders
# entroping: negative_category=invalid-auth
# entroping: mutation_seed=auth-seed-1
GET http://127.0.0.1:18080/orders
HTTP 401
[Asserts]
header "WWW-Authenticate" exists
jsonpath "$.error" isString
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "generated" / "negative" / "schema.hurl",
        """
# entroping: tags=generated,negative
# entroping: source=openapi
# entroping: operation_id=createOrder
# entroping: negative_category=schema-violations
# entroping: fuzz_seed=schema-seed-1
POST http://127.0.0.1:18080/orders
HTTP 422
[Asserts]
jsonpath "$.code" isString
body contains "validation"
""".strip()
        + "\n",
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "pass", "score": 91},
        },
    )
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {
            "schema_version": "entroping.test-pyramid-report.v1",
            "summary": {"status": "pass"},
        },
    )

    result = run_mutation_readiness_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "mutation-readiness.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "entroping.mutation-readiness.v1"
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 4,
        "sources_present": 4,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "generated_tests": 2,
        "negative_tests": 2,
        "security_tests": 1,
        "assertions_total": 4,
        "seed_metadata_tests": 2,
        "candidate_categories_total": 2,
        "optional_reports_present": 2,
        "optional_reports_invalid": 0,
        "optional_reports_unsafe": 0,
    }
    candidates = {candidate["category"]: candidate for candidate in payload["candidates"]}
    assert candidates["auth"]["tests"] == 1
    assert candidates["schema"]["tests"] == 1
    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[
        ("generated_hurl", "tests/generated/security/auth.hurl")
    ]["candidate_categories"] == ["auth"]
    assert sources[
        ("generated_hurl", "tests/generated/negative/schema.hurl")
    ]["candidate_categories"] == ["schema"]
    serialized = json.dumps(payload)
    assert "127.0.0.1" not in serialized
    assert "POST" not in serialized
    assert "auth-seed-1" not in serialized


def test_mutation_readiness_no_generated_hurl_is_insufficient_markdown(
    tmp_path: Path,
) -> None:
    result = run_mutation_readiness_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "mutation-readiness.md"
    assert result.packet.summary.status == "insufficient"
    markdown = result.output_path.read_text(encoding="utf-8")
    assert "# Entroping Mutation Readiness" in markdown
    assert "No mutation or fuzz readiness candidates were detected." in markdown


def test_mutation_readiness_surfaces_missing_optional_reports(
    tmp_path: Path,
) -> None:
    result = run_mutation_readiness_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["sources_total"] == 2
    assert payload["summary"]["sources_missing"] == 2
    assert payload["summary"]["sources_present"] == 0
    assert payload["summary"]["sources_invalid"] == 0
    assert payload["summary"]["sources_unsafe"] == 0
    assert payload["summary"]["optional_reports_present"] == 0
    assert payload["summary"]["optional_reports_invalid"] == 0
    assert payload["summary"]["optional_reports_unsafe"] == 0

    sources = {(source["kind"], source["path"]): source for source in payload["sources"]}
    assert sources[("test_quality_report", "reports/test-quality.json")] == {
        "kind": "test_quality_report",
        "path": "reports/test-quality.json",
        "state": "missing",
        "schema_version": None,
        "tags": [],
        "candidate_categories": [],
        "assertions": 0,
        "seed_metadata": False,
        "summary": "optional report not found.",
    }
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")]["state"] == (
        "missing"
    )
    serialized = json.dumps(payload)
    assert str(tmp_path) not in serialized
    assert "127.0.0.1" not in serialized
    markdown = render_mutation_readiness_markdown(result.packet)
    assert "reports/test-quality.json" in markdown
    assert "missing" in markdown
    assert str(tmp_path) not in markdown


def test_mutation_readiness_keeps_missing_optional_reports_non_blocking(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "security" / "auth.hurl",
        """
# entroping: tags=generated,negative,security
# entroping: source=openapi
# entroping: negative_category=invalid-auth
# entroping: mutation_seed=auth-seed-1
GET http://127.0.0.1:18080/orders
HTTP 401
[Asserts]
jsonpath "$.error" exists
""".strip()
        + "\n",
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "pass", "score": 91},
        },
    )

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("test_quality_report", "reports/test-quality.json")].state == "present"
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].state == "missing"
    assert packet.summary.status == "ready"
    assert packet.summary.sources_missing == 1
    assert packet.summary.optional_reports_present == 1
    serialized = packet.model_dump_json()
    assert "auth-seed-1" not in serialized
    assert "127.0.0.1" not in serialized


def test_mutation_readiness_markdown_renderer_rejects_secret_like_output(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)
    secret_marker = "sk-proj-" + "secretmarker0123456789"
    poisoned_source = packet.sources[0].model_copy(
        update={"summary": f"unsafe token {secret_marker}"}
    )
    unsafe_packet = packet.model_copy(
        update={"sources": (poisoned_source, *packet.sources[1:])}
    )
    assert len(unsafe_packet.sources) == len(packet.sources)

    with pytest.raises(MutationReadinessError, match="contains secret-like content"):
        render_mutation_readiness_markdown(unsafe_packet)


def test_mutation_readiness_json_renderer_rejects_secret_like_output(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)
    secret_marker = "sk-proj-" + "jsonsecretmarker0123456789"
    poisoned_source = packet.sources[0].model_copy(
        update={"summary": f"unsafe token {secret_marker}"}
    )
    unsafe_packet = packet.model_copy(
        update={"sources": (poisoned_source, *packet.sources[1:])}
    )

    with pytest.raises(MutationReadinessError, match="contains secret-like content"):
        mutation_readiness._render_packet_content(unsafe_packet, output="json")


def test_mutation_readiness_packet_renderer_returns_json_and_markdown(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)

    json_content = mutation_readiness._render_packet_content(packet, output="json")
    markdown_content = mutation_readiness._render_packet_content(packet, output="md")

    assert json.loads(json_content)["schema_version"] == (
        "entroping.mutation-readiness.v1"
    )
    assert "# Entroping Mutation Readiness" in markdown_content


def test_mutation_readiness_packet_json_rejects_secret_like_output(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)
    secret_marker = "sk-proj-" + "packetsecretmarker0123456789"
    poisoned_source = packet.sources[0].model_copy(
        update={"summary": f"unsafe token {secret_marker}"}
    )
    unsafe_packet = packet.model_copy(
        update={"sources": (poisoned_source, *packet.sources[1:])}
    )

    with pytest.raises(MutationReadinessError, match="contains secret-like content"):
        unsafe_packet.model_dump_json()


def test_mutation_readiness_packet_model_dump_rejects_secret_like_output(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)
    secret_marker = "sk-proj-" + "modeldumpsecret0123456789"
    poisoned_source = packet.sources[0].model_copy(
        update={"summary": f"unsafe token {secret_marker}"}
    )
    unsafe_packet = packet.model_copy(
        update={"sources": (poisoned_source, *packet.sources[1:])}
    )

    with pytest.raises(MutationReadinessError, match="contains secret-like content"):
        unsafe_packet.model_dump(mode="json")


def test_mutation_readiness_packet_json_preserves_pydantic_options(
    tmp_path: Path,
) -> None:
    packet = build_mutation_readiness(project_root=tmp_path)

    rendered = packet.model_dump_json(indent=2, exclude_none=True)

    assert "\n  " in rendered
    payload = json.loads(rendered)
    assert payload["schema_version"] == "entroping.mutation-readiness.v1"
    assert "schema_version" not in payload["sources"][0]


def test_mutation_readiness_redacts_secret_like_project_directory_name(
    tmp_path: Path,
) -> None:
    secret_like_project = tmp_path / ("sk-proj-" + "projectsecret0123456789")
    secret_like_project.mkdir()

    result = run_mutation_readiness_report(project_root=secret_like_project, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["project"] == "[REDACTED]"
    assert "projectsecret0123456789" not in result.packet.model_dump_json()


def test_mutation_readiness_marks_invalid_hurl_and_report_states(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "bad.hurl",
        "# entroping: tags=\nGET http://127.0.0.1:18080/health\n",
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "wrong.schema.v1", "summary": {"status": "pass"}},
    )
    real_report = _write_text(tmp_path / "real-test-pyramid.json", "{}\n")
    os.symlink(real_report, tmp_path / "reports" / "test-pyramid.json")
    real_hurl = _write_text(
        tmp_path / "real-generated.hurl",
        "# entroping: source=openapi\nGET http://127.0.0.1:18080/link\n",
    )
    os.symlink(real_hurl, tmp_path / "tests" / "generated" / "link.hurl")

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("generated_hurl", "tests/generated/bad.hurl")].state == "invalid"
    assert "empty tag value" in sources[("generated_hurl", "tests/generated/bad.hurl")].summary
    assert sources[("test_quality_report", "reports/test-quality.json")].state == "invalid"
    assert "unexpected schema" in sources[
        ("test_quality_report", "reports/test-quality.json")
    ].summary
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].state == "unsafe"
    assert "symlinked component" in sources[
        ("test_pyramid_report", "reports/test-pyramid.json")
    ].summary
    linked_source = mutation_readiness._load_hurl_source(
        root=tmp_path,
        raw_path=Path("tests") / "generated" / "link.hurl",
    )
    assert linked_source is not None
    assert linked_source.state == "unsafe"
    assert "symlinked component" in linked_source.summary
    assert packet.summary.status == "partial"


def test_mutation_readiness_ignores_manual_and_ignored_hurl_sources(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / ".pytest_cache" / "ignored.hurl",
        "# entroping: source=openapi\nGET http://127.0.0.1:18080/ignored\n",
    )
    _write_text(
        tmp_path / "tests" / "manual.hurl",
        "GET http://127.0.0.1:18080/manual\nHTTP 200\n",
    )
    _write_text(
        tmp_path / "tests" / "manual-invalid.hurl",
        "# entroping: tags=\nGET http://127.0.0.1:18080/manual\n",
    )
    real_hurl = _write_text(
        tmp_path / "real.hurl",
        "GET http://127.0.0.1:18080/manual-link\n",
    )
    os.symlink(real_hurl, tmp_path / "tests" / "manual-link.hurl")

    packet = build_mutation_readiness(project_root=tmp_path)

    assert all(source.kind != "generated_hurl" for source in packet.sources)
    assert {source.state for source in packet.sources} == {"missing"}
    assert packet.summary.sources_missing == 2
    assert packet.summary.status == "insufficient"
    assert (
        mutation_readiness._load_hurl_source(
            root=tmp_path,
            raw_path=Path("tests") / "manual-link.hurl",
        )
        is None
    )


def test_mutation_readiness_detects_generated_tag_and_path_fallback(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "tagged.hurl",
        """
# entroping: tags=generated,status-code
GET http://127.0.0.1:18080/tagged
HTTP 409
[Asserts]
header "content-type" exists
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "generated" / "path-only.hurl",
        """
GET http://127.0.0.1:18080/path-only
HTTP 200
[Asserts]
jsonpath "$.ok" exists
[Options]
retry: 0
""".strip()
        + "\n",
    )

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("generated_hurl", "tests/tagged.hurl")].candidate_categories == (
        "status_code",
    )
    assert sources[("generated_hurl", "tests/generated/path-only.hurl")].assertions == 1


def test_mutation_readiness_marks_unsafe_and_oversized_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "secret.hurl",
        "sk-proj-" + ("a" * 24),
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "pass"},
        },
    )
    monkeypatch.setattr(mutation_readiness, "_MAX_MUTATION_READINESS_ARTIFACT_BYTES", 1)

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("generated_hurl", "tests/generated/secret.hurl")].state == "unsafe"
    assert "secret-like content" in sources[
        ("generated_hurl", "tests/generated/secret.hurl")
    ].summary
    assert sources[("test_quality_report", "reports/test-quality.json")].state == "invalid"
    assert "exceeds 1 bytes" in sources[
        ("test_quality_report", "reports/test-quality.json")
    ].summary


def test_mutation_readiness_marks_optional_report_shape_and_decode_errors(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "reports" / "test-quality.json", "{not-json}\n")
    _write_json(tmp_path / "reports" / "test-pyramid.json", ["not", "an", "object"])

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("test_quality_report", "reports/test-quality.json")].state == "invalid"
    assert "invalid JSON" in sources[
        ("test_quality_report", "reports/test-quality.json")
    ].summary
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].state == "invalid"
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].summary == (
        "invalid JSON"
    )

    _write_bytes(tmp_path / "reports" / "test-quality.json", b"\xff\xfe")
    (tmp_path / "reports" / "test-pyramid.json").unlink()

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    quality_source = sources[("test_quality_report", "reports/test-quality.json")]
    assert quality_source.state == "invalid"
    assert "Could not decode" in quality_source.summary
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].state == (
        "missing"
    )


def test_mutation_readiness_marks_optional_report_directory_and_fallback_summary(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {"schema_version": "entroping.test-pyramid-report.v1"},
    )
    (tmp_path / "reports" / "test-quality.json").mkdir(parents=True)

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    assert sources[("test_quality_report", "reports/test-quality.json")].state == "unsafe"
    assert "not a file" in sources[
        ("test_quality_report", "reports/test-quality.json")
    ].summary
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].state == "present"
    assert sources[("test_pyramid_report", "reports/test-pyramid.json")].summary == (
        "test_pyramid_report schema present"
    )


def test_mutation_readiness_candidate_categories_cover_safe_lanes(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "request-shape.hurl",
        """
# entroping: tags=generated,request-shape,latency
# entroping: mutation_category=status-code
# entroping: fuzz_category=request-shape
# entroping: negative_category=boundary-values
GET http://127.0.0.1:18080/request
HTTP 400
[Asserts]
jsonpath "$.error" exists
""".strip()
        + "\n",
    )

    packet = build_mutation_readiness(project_root=tmp_path)

    sources = {(source.kind, source.path): source for source in packet.sources}
    categories = sources[
        ("generated_hurl", "tests/generated/request-shape.hurl")
    ].candidate_categories
    assert categories == ("latency", "request_shape", "status_code")
    assert {candidate.category for candidate in packet.candidates} == {
        "latency",
        "request_shape",
        "status_code",
    }


def test_mutation_readiness_flags_unseeded_candidate_categories(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "seeded-status.hurl",
        """
# entroping: tags=generated,status-code
# entroping: mutation_seed=do-not-render
GET http://127.0.0.1:18080/seeded
HTTP 409
[Asserts]
jsonpath "$.error" exists
""".strip()
        + "\n",
    )
    _write_text(
        tmp_path / "tests" / "generated" / "unseeded-status.hurl",
        """
# entroping: tags=generated,status-code
GET http://127.0.0.1:18080/unseeded
HTTP 409
[Asserts]
jsonpath "$.error" exists
""".strip()
        + "\n",
    )

    result = run_mutation_readiness_report(project_root=tmp_path, output="json")

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    candidates = {candidate["category"]: candidate for candidate in payload["candidates"]}
    assert candidates["status_code"]["tests"] == 2
    assert candidates["status_code"]["next_action"] == (
        "Add deterministic seed metadata to 1 status-code mutation candidate "
        "before future mutation/fuzz execution."
    )
    serialized = json.dumps(payload)
    assert "do-not-render" not in serialized
    assert "127.0.0.1" not in serialized


def test_mutation_readiness_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(MutationReadinessError, match="Unsupported mutation-readiness output"):
        run_mutation_readiness_report(project_root=tmp_path, output="html")  # type: ignore[arg-type]

    with pytest.raises(MutationReadinessError, match="mutation readiness path is unsafe"):
        run_mutation_readiness_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "mutation-readiness.json",
        )

    def fail_write(*args: object, **kwargs: object) -> object:
        raise SafeWriteError("cannot write mutation readiness")

    monkeypatch.setattr(mutation_readiness, "safe_write_text", fail_write)

    with pytest.raises(MutationReadinessError, match="cannot write mutation readiness"):
        run_mutation_readiness_report(project_root=tmp_path, output="md")


def test_mutation_readiness_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_build = mutation_readiness.build_mutation_readiness

    def build_secret_packet(*, project_root: Path) -> object:
        packet = real_build(project_root=project_root)
        return packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)})

    monkeypatch.setattr(mutation_readiness, "build_mutation_readiness", build_secret_packet)

    with pytest.raises(MutationReadinessError, match="secret-like content"):
        run_mutation_readiness_report(project_root=tmp_path, output="json")


def test_mutation_readiness_writer_rejects_secret_like_renderer_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_rendered_content(packet: mutation_readiness.MutationReadinessPacket) -> str:
        _ = packet
        secret_marker = "sk-proj-" + "writersecret0123456789"
        return f"unsafe token {secret_marker}\n"

    monkeypatch.setattr(
        mutation_readiness,
        "render_mutation_readiness_markdown",
        fake_rendered_content,
    )

    with pytest.raises(MutationReadinessError, match="contains secret-like content"):
        run_mutation_readiness_report(project_root=tmp_path, output="md")


def test_mutation_readiness_rejects_symlink_and_escaped_output_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_output_dir = tmp_path / "real-output"
    real_output_dir.mkdir()
    os.symlink(real_output_dir, tmp_path / "reports-link")

    with pytest.raises(MutationReadinessError, match="symlinked component"):
        run_mutation_readiness_report(
            project_root=tmp_path,
            output="md",
            output_path=Path("reports-link") / "mutation-readiness.md",
        )

    with pytest.raises(MutationReadinessError, match="must stay under the project root"):
        run_mutation_readiness_report(
            project_root=tmp_path,
            output="md",
            output_path=tmp_path.parent / "outside-mutation-readiness.md",
        )

    monkeypatch.setattr(
        mutation_readiness,
        "_unsafe_path_summary",
        lambda path, *, root: None,
    )

    with pytest.raises(MutationReadinessError, match="output must stay under project root"):
        run_mutation_readiness_report(
            project_root=tmp_path,
            output="md",
            output_path=tmp_path.parent / "outside-mutation-readiness.md",
        )


def test_mutation_readiness_private_read_and_path_error_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read_bytes(self: Path) -> bytes:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    source = mutation_readiness._read_text_artifact(
        tmp_path / "reports" / "test-quality.json",
        artifact="reports/test-quality.json",
        root=tmp_path,
        kind="test_quality_report",
    )

    assert not isinstance(source, str)
    assert source.state == "invalid"
    assert "permission denied" in source.summary
    assert mutation_readiness._unsafe_path_summary(
        tmp_path.parent / "outside.hurl",
        root=tmp_path,
    ) == "mutation readiness source path must stay under the project root"
    assert mutation_readiness._ignored(tmp_path.parent / "outside.hurl", root=tmp_path)
    assert mutation_readiness._relative_path(
        tmp_path.parent / "outside.hurl",
        root=tmp_path,
    ).startswith("<outside-project>/")


def test_render_mutation_readiness_markdown_escapes_values(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "tests" / "generated" / "pipe.hurl",
        """
# entroping: tags=generated,response-shape
# entroping: source=openapi
# entroping: mutation_seed=pipe-seed-1
GET http://127.0.0.1:18080/health
HTTP 200
[Asserts]
jsonpath "$.name" isString
""".strip()
        + "\n",
    )

    packet = build_mutation_readiness(project_root=tmp_path)

    markdown = render_mutation_readiness_markdown(packet)
    assert "response_shape" in markdown
    assert "127.0.0.1" not in markdown
    assert "pipe-seed-1" not in markdown
    assert "\\|" not in markdown


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_json(path: Path, payload: object) -> Path:
    return _write_text(path, json.dumps(payload) + "\n")
