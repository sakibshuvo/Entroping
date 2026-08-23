"""Tests for review-only status mutation materialization."""

import ctypes
import errno
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import pytest

import entroping.core.mutation_materializer_hurl_requests as hurl_requests
import entroping.core.mutation_materializer_io as materializer_io
import entroping.core.mutation_materializer_request_shape as request_shape
from entroping.core.mutation_materializer import (
    MutationMaterializerError,
    materialize_mutation_candidate,
)
from entroping.models.secrets import contains_secret_like_value


@pytest.fixture(autouse=True)
def _stub_external_hurlfmt_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep materializer unit tests independent of the optional Hurl binary."""

    monkeypatch.setattr(
        "entroping.core.mutation_materializer.validate_hurl_content",
        lambda _content, _display_path: None,
    )


def _candidate_id(manifest_without_id: dict[str, object]) -> str:
    canonical = json.dumps(
        manifest_without_id,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"mut-{hashlib.sha256(canonical).hexdigest()[:24]}"


def _write_status_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "tests" / "source.hurl"
    source.parent.mkdir(exist_ok=True)
    (tmp_path / "tests" / "generated" / "mutations").mkdir(parents=True, exist_ok=True)
    source_bytes = b"# entroping: safety=read-only\n\nGET {{base_url}}/health\nHTTP 200\n"
    source.write_bytes(source_bytes)
    source_stat = source.stat()
    manifest_core: dict[str, object] = {
        "category": "status-code",
        "project_relative_source_path": "tests/source.hurl",
        "expected_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reviewed_seed": 7,
        "category_selector": {"assertion_ordinal": 0, "replacement_status": 500},
    }
    candidate_id = _candidate_id(manifest_core)
    manifest = {
        "schema_version": "entroping.mutation-materialization.v1",
        **manifest_core,
        "source_size_bytes": len(source_bytes),
        "source_mtime_ns": source_stat.st_mtime_ns,
        "reviewed_seed": 7,
        "review_decision_id": "decision-1",
        "evidence_ids": ["evidence-1"],
        "candidate_id": candidate_id,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return source, manifest_path, candidate_id


def _write_status_xml_fixture(tmp_path: Path, preamble: str) -> tuple[Path, Path]:
    return _write_status_xml_body_fixture(
        tmp_path,
        f"{preamble}<Envelope>\nHTTP 599\n</Envelope>\n",
    )


def _write_status_xml_body_fixture(tmp_path: Path, body: str) -> tuple[Path, Path]:
    source = tmp_path / "tests" / "source.hurl"
    source.parent.mkdir(exist_ok=True)
    (tmp_path / "tests" / "generated" / "mutations").mkdir(parents=True, exist_ok=True)
    source_bytes = (
        "# entroping: safety=read-only\n\n"
        "POST {{base_url}}/xml\n"
        "Content-Type: application/xml\n\n"
        f"{body}"
        "HTTP 200\n"
    ).encode()
    source.write_bytes(source_bytes)
    source_stat = source.stat()
    manifest_core: dict[str, object] = {
        "category": "status-code",
        "project_relative_source_path": "tests/source.hurl",
        "expected_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reviewed_seed": 7,
        "category_selector": {"assertion_ordinal": 0, "replacement_status": 201},
    }
    candidate_id = _candidate_id(manifest_core)
    manifest = {
        "schema_version": "entroping.mutation-materialization.v1",
        **manifest_core,
        "source_size_bytes": len(source_bytes),
        "source_mtime_ns": source_stat.st_mtime_ns,
        "review_decision_id": "decision-1",
        "evidence_ids": ["evidence-1"],
        "candidate_id": candidate_id,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return source, manifest_path


def _write_request_shape_fixture(
    tmp_path: Path,
    body: str,
    *,
    pointer: str = "/value",
    request_ordinal: int = 0,
    reviewed_seed: int = 0,
    fenced: bool = False,
    request_prefix: str = "",
    header_separator: str = "\n\n",
) -> tuple[Path, Path, str]:
    source = tmp_path / "tests" / "source.hurl"
    source.parent.mkdir(exist_ok=True)
    (tmp_path / "tests" / "generated" / "mutations").mkdir(parents=True, exist_ok=True)
    request_body = f"```json\n{body}\n```" if fenced else body
    source_bytes = (
        "# entroping: safety=read-only\n\n"
        f"{request_prefix}"
        "POST {{base_url}}/users\n"
        f"Content-Type: application/json{header_separator}"
        f"{request_body}\n"
        "HTTP 201\n"
    ).encode()
    source.write_bytes(source_bytes)
    source_stat = source.stat()
    manifest_core: dict[str, object] = {
        "category": "request-shape",
        "project_relative_source_path": "tests/source.hurl",
        "expected_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reviewed_seed": reviewed_seed,
        "category_selector": {
            "request_ordinal": request_ordinal,
            "json_pointer": pointer,
            "corpus_id": "request-shape-v1",
        },
    }
    candidate_id = _candidate_id(manifest_core)
    manifest = {
        "schema_version": "entroping.mutation-materialization.v1",
        **manifest_core,
        "source_size_bytes": len(source_bytes),
        "source_mtime_ns": source_stat.st_mtime_ns,
        "review_decision_id": "decision-1",
        "evidence_ids": ["evidence-1"],
        "candidate_id": candidate_id,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return source, manifest_path, candidate_id


def _refresh_manifest(
    manifest_path: Path,
    source: Path,
    *,
    category: str | None = None,
    category_selector: dict[str, object] | None = None,
) -> str:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if category is not None:
        document["category"] = category
    if category_selector is not None:
        document["category_selector"] = category_selector
    source_bytes = source.read_bytes()
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    return candidate_id


def _assert_real_hurlfmt(source: Path) -> None:
    hurlfmt = shutil.which("hurlfmt")
    if hurlfmt is None:
        return
    result = subprocess.run(
        [hurlfmt, "--check", str(source)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr


def test_materialize_request_shape_replaces_one_json_scalar_with_destructive_safety(
    tmp_path: Path,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"name":"alice","active":true}',
        pointer="/name",
        fenced=True,
    )
    source_before = source.read_bytes()

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "# entroping: mutation_category=request-shape\n" in rendered
    assert "# entroping: mutation_seed=0\n" in rendered
    assert "# entroping: safety=destructive\n" in rendered
    assert '{"name":"","active":true}' in rendered
    assert "alice" not in rendered
    assert source.read_bytes() == source_before


@pytest.mark.parametrize(
    ("body", "pointer", "expected"),
    (
        ('{"value":-1}', "/value", '{"value":0}'),
        ('{"value":0}', "/value", '{"value":-1}'),
        ('{"value":true}', "/value", '{"value":false}'),
        ('{"value":null}', "/value", '{"value":""}'),
        ('{"a/b":"original"}', "/a~1b", '{"a/b":""}'),
        ('{"items":["first","second"]}', "/items/1", '{"items":["first",""]}'),
    ),
)
def test_request_shape_uses_type_strict_seeded_corpus(
    tmp_path: Path,
    body: str,
    pointer: str,
    expected: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        body,
        pointer=pointer,
    )

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    assert expected in output.read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8").count(body) == 1


def test_request_shape_seed_changes_only_selected_scalar_and_is_deterministic(
    tmp_path: Path,
) -> None:
    source, first_manifest, first_candidate = _write_request_shape_fixture(
        tmp_path,
        '{"profile":{"name":"alice","active":true},"untouched":7}',
        pointer="/profile/name",
        reviewed_seed=0,
        fenced=True,
    )
    source_before = source.read_bytes()
    first = materialize_mutation_candidate(tmp_path, first_manifest).read_text(encoding="utf-8")

    _source, second_manifest, second_candidate = _write_request_shape_fixture(
        tmp_path,
        '{"profile":{"name":"alice","active":true},"untouched":7}',
        pointer="/profile/name",
        reviewed_seed=1,
        fenced=True,
    )
    second = materialize_mutation_candidate(tmp_path, second_manifest).read_text(encoding="utf-8")

    assert first_candidate != second_candidate
    assert '"name":""' in first
    assert '"name":" "' in second
    assert '"active":true' in first and '"active":true' in second
    assert '"untouched":7' in first and '"untouched":7' in second
    assert source.read_bytes() == source_before


def test_request_shape_handles_exact_1024_byte_pointer_iteratively(
    tmp_path: Path,
) -> None:
    depth = 512
    pointer = "/a" * depth
    body = '{"a":' * depth + '"target"' + "}" * depth
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        body,
        pointer=pointer,
    )
    source_before = source.read_bytes()

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    expected_body = '{"a":' * depth + '""' + "}" * depth
    rendered = output.read_text(encoding="utf-8")
    assert expected_body in rendered
    assert '"target"' not in rendered
    assert source.read_bytes() == source_before


def test_request_shape_bounds_json_decoder_span_work_at_nested_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth = 128
    body = '{"a":' * depth + '"target"' + "}" * depth
    spans: list[int] = []

    class CountingDecoder(json.JSONDecoder):
        def raw_decode(self, s: str, idx: int = 0) -> tuple[object, int]:
            value, end = super().raw_decode(s, idx)
            spans.append(end - idx)
            return value, end

    def counting_decoder() -> json.JSONDecoder:
        return CountingDecoder(
            object_pairs_hook=request_shape._reject_duplicate_pairs,
            parse_constant=request_shape._reject_json_constant,
        )

    monkeypatch.setattr(request_shape, "_new_json_decoder", counting_decoder)

    scalar = request_shape._find_json_scalar_span(body, ("a",) * depth)

    assert scalar.value == "target"
    assert sum(spans) <= 2 * len(body)


def test_request_shape_tracks_escaped_multibyte_lexical_scalar_span() -> None:
    body = ' \n{\n  "prefix": "界",\n  "caf\\u00e9" : "pré\\u00e9post"\n}\n'

    scalar = request_shape._find_json_scalar_span(body, ("café",))

    assert scalar.value == "préépost"
    assert body[scalar.start : scalar.end] == '"pré\\u00e9post"'
    assert body[: scalar.start] == ' \n{\n  "prefix": "界",\n  "caf\\u00e9" : '
    assert body[scalar.end :] == "\n}\n"


@pytest.mark.parametrize(
    ("fenced", "expected_body"),
    (
        (False, '{"value":""\n\n}'),
        (True, '```json\n{"value":""\n\n}\n```'),
    ),
)
def test_request_shape_locates_body_before_internal_blank_line(
    tmp_path: Path,
    fenced: bool,
    expected_body: str,
) -> None:
    body = '{"value":"selected"\n\n}'
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        body,
        fenced=fenced,
        header_separator="\n",
    )
    source_before = source.read_bytes()
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert expected_body in rendered
    assert body not in rendered
    assert source.read_bytes() == source_before
    _assert_real_hurlfmt(output)


@pytest.mark.parametrize(
    "section",
    ("[Options]", "[Asserts]", "[Captures]", "[QueryStringParams]", "[MultipartFormData]"),
)
def test_request_shape_does_not_treat_hurl_section_as_json_array(section: str) -> None:
    with pytest.raises(MutationMaterializerError, match="request JSON body is missing"):
        hurl_requests._locate_json_in_exchange(f"Content-Type: application/json\n{section}\n")


def test_request_shape_rejects_out_of_range_request_ordinal_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
    )
    candidate_id = _refresh_manifest(manifest_path, source)

    with pytest.raises(MutationMaterializerError, match="request ordinal is out of range"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    ("body", "match"),
    (
        ('```json\n{"value":"selected"}', "fence is incomplete"),
        (
            '```json\n{"value":"one"}\n```\n```json\n{"value":"two"}\n```',
            "multiple JSON bodies",
        ),
    ),
)
def test_request_shape_rejects_ambiguous_json_fences_without_output(
    tmp_path: Path,
    body: str,
    match: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(tmp_path, body)
    candidate_id = _refresh_manifest(manifest_path, source)

    with pytest.raises(MutationMaterializerError, match=match):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    ("body", "header_separator"),
    (("", ""), ("\n", "\n\n")),
)
def test_request_shape_rejects_missing_json_body_without_output(
    tmp_path: Path,
    body: str,
    header_separator: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        body,
        header_separator=header_separator,
    )
    candidate_id = _refresh_manifest(manifest_path, source)

    with pytest.raises(MutationMaterializerError, match="request JSON body is missing"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize("header_separator", ("\n", "\n\n"))
def test_request_shape_skips_options_section_before_unfenced_json_body(
    tmp_path: Path,
    header_separator: str,
) -> None:
    body = '[Options]\nretry: 1\n{"value":"selected"\n\n}'
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        body,
        header_separator=header_separator,
    )
    source_before = source.read_bytes()
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert '[Options]\nretry: 1\n{"value":""\n\n}' in rendered
    assert body not in rendered
    assert source.read_bytes() == source_before
    _assert_real_hurlfmt(output)


@pytest.mark.parametrize(
    "request_prefix",
    (
        'GET {{base_url}}/health\nHTTP 200\n"GET https://body.example"\n\n',
        "GET {{base_url}}/health\nHTTP 200\n```text\nGET https://body.example\n```\n\n",
        "GET {{base_url}}/health\nHTTP 200\n<root>\n<child>GET https://body.example</child>\n</root>\n\n",
        "GET {{base_url}}/health\nHTTP 200\n<root><child>\nGET https://body.example\n</child>\n</root>\n\n",
    ),
)
def test_request_shape_uses_declared_request_ordinal_and_ignores_response_body_lines(
    tmp_path: Path,
    request_prefix: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=request_prefix,
    )

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "GET {{base_url}}/health\nHTTP 200" in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


def test_request_shape_accepts_adjacent_hurl_entries_without_blank_line(
    tmp_path: Path,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix="GET {{base_url}}/health\nHTTP 200\n",
    )

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "GET {{base_url}}/health\nHTTP 200\nPOST {{base_url}}/users" in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


@pytest.mark.parametrize("separator", ("", "\n"))
def test_request_shape_scans_xml_preambles_before_json_entry(
    tmp_path: Path,
    separator: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=(
            "POST {{base_url}}/xml\n"
            "Content-Type: application/xml\n\n"
            '<?xml version="1.0"?>\n'
            "<!-- comment -->\n"
            "<?process?>\n"
            "<!DOCTYPE root>\n"
            "<root>value</root>\n"
            f"HTTP 200\n{separator}"
        ),
    )
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert '<?xml version="1.0"?>\n<!-- comment -->\n<?process?>\n<!DOCTYPE root>' in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


@pytest.mark.parametrize(
    "xml_body",
    (
        '<?xml version="1.0"?>\n<!--\nHTTP 599\n-->\n<root>value</root>\n',
        '<?xml version="1.0"?>\n<!DOCTYPE Envelope [\n'
        "<!ELEMENT Envelope ANY>\n]>\n<Envelope>value</Envelope>\n",
    ),
)
@pytest.mark.parametrize("separator", ("", "\n"))
def test_request_shape_scans_multiline_xml_preambles_before_json_entry(
    tmp_path: Path,
    xml_body: str,
    separator: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=(
            "POST {{base_url}}/xml\n"
            "Content-Type: application/xml\n\n"
            f"{xml_body}"
            f"HTTP 200\n{separator}"
        ),
    )
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert xml_body in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


@pytest.mark.parametrize(
    "preamble",
    (
        '<?xml version="1.0"?>',
        "<!--comment-->",
        "<!--\ncomment\n-->",
        "<?process?>",
        "<!DOCTYPE Envelope>",
        "<!DOCTYPE Envelope [\n<!ELEMENT Envelope ANY>\n]>",
    ),
)
def test_request_shape_preserves_xml_body_status_after_inline_preamble_root(
    tmp_path: Path,
    preamble: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=(
            "POST {{base_url}}/xml\n"
            "Content-Type: application/xml\n\n"
            f"{preamble}<Envelope>\n"
            "HTTP 599\n"
            "</Envelope>\n"
            "HTTP 200\n"
        ),
    )
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "HTTP 599\n</Envelope>\nHTTP 200\nPOST" in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


@pytest.mark.parametrize(
    "preamble",
    (
        '<?xml version="1.0"?>',
        "<!--comment-->",
        "<!--\ncomment\n-->",
        "<?process?>",
        "<!DOCTYPE Envelope>",
        "<!DOCTYPE Envelope [\n<!ELEMENT Envelope ANY>\n]>",
    ),
)
def test_status_materialization_ignores_xml_body_status_after_inline_preamble_root(
    tmp_path: Path,
    preamble: str,
) -> None:
    source, manifest_path = _write_status_xml_fixture(tmp_path, preamble)
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "HTTP 599\n</Envelope>\nHTTP 201\n" in rendered
    assert source.read_text(encoding="utf-8").count("HTTP 200") == 1


@pytest.mark.parametrize(
    "xml_body",
    (
        '<?xml version="1.0"?><!--c--><?p x?><!DOCTYPE Envelope>'
        "<Envelope><Body>\nHTTP 599\n</Body></Envelope>\n",
        "<Envelope><Body>\nHTTP 599\n</Body></Envelope>\n",
        '<Envelope note="a > b"><Body>\nHTTP 599\n</Body></Envelope>\n',
        "<Envelope><Body><![CDATA[\nHTTP 599\n]]></Body></Envelope>\n",
        "<Envelope><Body><!--\nHTTP 599\n--></Body></Envelope>\n",
    ),
)
def test_request_shape_scans_lexical_xml_body_before_later_json_entry(
    tmp_path: Path,
    xml_body: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=(
            f"POST {{{{base_url}}}}/xml\nContent-Type: application/xml\n\n{xml_body}HTTP 200\n"
        ),
    )
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "HTTP 599" in rendered
    assert "HTTP 200\nPOST {{base_url}}/users" in rendered
    assert '{"value":""}' in rendered
    assert source.read_text(encoding="utf-8").count('{"value":"selected"}') == 1


@pytest.mark.parametrize(
    "xml_body",
    (
        '<Envelope note="line\nHTTP 599\nvalue"><Body>HTTP 598</Body></Envelope>\n',
        '<?xml version="1.0"?><?process\nHTTP 599\n?>'
        "<!DOCTYPE Envelope [\n"
        '<!ENTITY label "HTTP 598">\n]>'
        "<Envelope><Body>HTTP 597</Body></Envelope>\n",
        "<!DOCTYPE Envelope [<!-- [ HTTP 599 > -->\n"
        "<!ELEMENT Envelope ANY>\n]><Envelope><Body>HTTP 596</Body></Envelope>\n",
        "<!DOCTYPE Envelope [<?process?>]><Envelope><Body>HTTP 595</Body></Envelope>\n",
        "<Envelope><Body><![CDATA[]]]></Body></Envelope>\n",
    ),
)
def test_request_shape_lexes_xml_boundaries_without_parsing_xml(
    tmp_path: Path,
    xml_body: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path,
        '{"value":"selected"}',
        request_ordinal=1,
        request_prefix=(
            f"POST {{{{base_url}}}}/xml\nContent-Type: application/xml\n\n{xml_body}HTTP 200\n"
        ),
    )
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    assert "HTTP 200\nPOST {{base_url}}/users" in rendered
    assert '{"value":"selected"}' not in rendered


@pytest.mark.parametrize(
    "xml_body",
    (
        '<?xml version="1.0"?><!--c--><?p x?><!DOCTYPE Envelope>'
        "<Envelope><Body>\nHTTP 599\n</Body></Envelope>\n",
        "<Envelope><Body>\nHTTP 599\n</Body></Envelope>\n",
        '<Envelope note="a > b"><Body>\nHTTP 599\n</Body></Envelope>\n',
        "<Envelope><Body><![CDATA[\nHTTP 599\n]]></Body></Envelope>\n",
        "<Envelope><Body><![CDATA[]]]></Body></Envelope>\n",
        "<Envelope><Body><!--\nHTTP 599\n--></Body></Envelope>\n",
    ),
)
def test_status_materialization_selects_response_after_lexical_xml_body(
    tmp_path: Path,
    xml_body: str,
) -> None:
    source, manifest_path = _write_status_xml_body_fixture(tmp_path, xml_body)
    _assert_real_hurlfmt(source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    rendered = output.read_text(encoding="utf-8")
    if "HTTP 599" in xml_body:
        assert "HTTP 599" in rendered
    assert "HTTP 201\n" in rendered
    assert xml_body in rendered
    assert source.read_text(encoding="utf-8").count("HTTP 200") == 1


@pytest.mark.parametrize("body", ("</root>\n", "<root/><extra>\n", "<>\n"))
def test_status_materialization_rejects_malformed_xml_request_body_without_output(
    tmp_path: Path,
    body: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        f"# entroping: safety=read-only\n\nPOST {{{{base_url}}}}/health\n{body}HTTP 200\n"
    ).encode()
    source.write_bytes(source_bytes)
    candidate_id = _refresh_manifest(manifest_path, source)

    with pytest.raises(MutationMaterializerError, match="status assertion is missing"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_bytes
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize("category", ("status-code", "request-shape"))
def test_materializer_rejects_mismatched_xml_request_body_without_output(
    tmp_path: Path,
    category: str,
) -> None:
    body = "<root></other>\nHTTP 599\n"
    if category == "status-code":
        source, manifest_path = _write_status_xml_body_fixture(tmp_path, body)
    else:
        source, manifest_path, _candidate_id_value = _write_request_shape_fixture(tmp_path, body)
    candidate_id = json.loads(manifest_path.read_text(encoding="utf-8"))["candidate_id"]
    source_before = source.read_bytes()

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_before
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize("category", ("status-code", "request-shape"))
@pytest.mark.parametrize("depth_delta", (0, 1))
def test_materializer_bounds_xml_nesting_without_partial_output(
    tmp_path: Path,
    category: str,
    depth_delta: int,
) -> None:
    depth = 64 + depth_delta
    body = "<node>" * depth + "\nHTTP 599\n" + "</node>" * depth + "\n"
    if category == "status-code":
        source, manifest_path = _write_status_xml_body_fixture(tmp_path, body)
    else:
        prefix = f"POST {{{{base_url}}}}/xml\nContent-Type: application/xml\n\n{body}HTTP 200\n"
        source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
            tmp_path,
            '{"value":"selected"}',
            request_ordinal=1,
            request_prefix=prefix,
        )
    _assert_real_hurlfmt(source)
    source_before = source.read_bytes()
    candidate_id = json.loads(manifest_path.read_text(encoding="utf-8"))["candidate_id"]
    output_path = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"

    if depth_delta == 0:
        output = materialize_mutation_candidate(tmp_path, manifest_path)
        rendered = output.read_text(encoding="utf-8")
        expected = "HTTP 201" if category == "status-code" else '{"value":""}'
        assert expected in rendered
        assert output == output_path
    else:
        with pytest.raises(MutationMaterializerError):
            materialize_mutation_candidate(tmp_path, manifest_path)
        assert not output_path.exists()
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("category", ("status-code", "request-shape"))
@pytest.mark.parametrize("name_delta", (0, 1))
def test_materializer_bounds_xml_tag_name_without_partial_output(
    tmp_path: Path,
    category: str,
    name_delta: int,
) -> None:
    name = "n" * (64 + name_delta)
    body = f"<{name}>\nHTTP 599\n</{name}>\n"
    if category == "status-code":
        source, manifest_path = _write_status_xml_body_fixture(tmp_path, body)
    else:
        prefix = f"POST {{{{base_url}}}}/xml\nContent-Type: application/xml\n\n{body}HTTP 200\n"
        source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
            tmp_path,
            '{"value":"selected"}',
            request_ordinal=1,
            request_prefix=prefix,
        )
    _assert_real_hurlfmt(source)
    source_before = source.read_bytes()
    candidate_id = json.loads(manifest_path.read_text(encoding="utf-8"))["candidate_id"]
    output_path = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"

    if name_delta == 0:
        output = materialize_mutation_candidate(tmp_path, manifest_path)
        rendered = output.read_text(encoding="utf-8")
        expected = "HTTP 201" if category == "status-code" else '{"value":""}'
        assert expected in rendered
        assert output == output_path
    else:
        with pytest.raises(MutationMaterializerError):
            materialize_mutation_candidate(tmp_path, manifest_path)
        assert not output_path.exists()
    assert source.read_bytes() == source_before


@pytest.mark.parametrize(
    "response_body",
    ("</root>\n", "<root>\n</>\n", "<root/>\nopaque response\n\n"),
)
def test_status_materialization_keeps_status_before_opaque_response_body(
    tmp_path: Path,
    response_body: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        f"# entroping: safety=read-only\n\nGET {{{{base_url}}}}/health\nHTTP 200\n{response_body}"
    ).encode()
    source.write_bytes(source_bytes)
    _refresh_manifest(manifest_path, source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    assert "HTTP 500\n" in output.read_text(encoding="utf-8")


def test_status_materialization_tracks_multiline_json_response_depth(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b'# entroping: safety=read-only\n\nGET {{base_url}}/health\nHTTP 200\n{\n  "value": 1\n}\n'
    )
    source.write_bytes(source_bytes)
    _refresh_manifest(manifest_path, source)

    output = materialize_mutation_candidate(tmp_path, manifest_path)

    assert 'HTTP 500\n{\n  "value": 1\n}\n' in output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("body", "pointer", "match"),
    (
        ('{"value":{}}', "/value", "target must be a JSON scalar"),
        ('{"value":[]}', "/value", "target must be a JSON scalar"),
        ('{"other":1}', "/value", "target is missing"),
        ('{"value":1} {"value":2}', "/value", "multiple JSON values"),
        ("not-json", "/value", "not valid JSON"),
        ('{"value":NaN}', "/value", "not valid JSON"),
        ('{"value":1,"value":2}', "/value", "duplicate keys"),
        ('{"value":1}', "/value/nested", "target is missing"),
        ('{"items":[1]}', "/items/2", "target is missing"),
    ),
)
def test_request_shape_rejects_unsafe_or_ambiguous_targets(
    tmp_path: Path,
    body: str,
    pointer: str,
    match: str,
) -> None:
    source, manifest_path, candidate_id = _write_request_shape_fixture(
        tmp_path,
        body,
        pointer=pointer,
    )
    source_before = source.read_bytes()

    with pytest.raises(MutationMaterializerError, match=match):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_before
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    "pointer",
    (
        "value",
        "/value~2",
        "/" + ("x" * 1_024),
    ),
)
def test_request_shape_rejects_invalid_pointer_before_output(
    tmp_path: Path,
    pointer: str,
) -> None:
    source, manifest_path, candidate_id = _write_request_shape_fixture(
        tmp_path,
        '{"value":1}',
        pointer=pointer,
    )

    with pytest.raises(MutationMaterializerError, match="JSON pointer"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_rejects_unsupported_category_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    candidate_id = _refresh_manifest(manifest_path, source, category="unsupported")
    source_before = source.read_bytes()

    with pytest.raises(MutationMaterializerError, match="manifest field is invalid"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_before
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_rejects_typed_but_malformed_status_selector_without_output(
    tmp_path: Path,
) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    candidate_id = _refresh_manifest(
        manifest_path, source, category_selector={"replacement_status": 500}
    )
    source_before = source.read_bytes()

    with pytest.raises(MutationMaterializerError, match="category selector keys"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_before
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    ("category_selector", "match"),
    (
        (
            {
                "request_ordinal": 0,
                "json_pointer": "/value",
                "corpus_id": "request-shape-v1",
                "extra": "unexpected",
            },
            "category selector keys",
        ),
        (
            {"request_ordinal": 0, "corpus_id": "request-shape-v1"},
            "request-shape selector is invalid",
        ),
    ),
)
def test_materializer_rejects_typed_but_malformed_request_selector_without_output(
    tmp_path: Path,
    category_selector: dict[str, object],
    match: str,
) -> None:
    source, manifest_path, _candidate_id_value = _write_request_shape_fixture(
        tmp_path, '{"value":"selected"}'
    )
    candidate_id = _refresh_manifest(
        manifest_path,
        source,
        category_selector=category_selector,
    )
    source_before = source.read_bytes()

    with pytest.raises(MutationMaterializerError, match=match):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.read_bytes() == source_before
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def _install_linux_link(
    monkeypatch: pytest.MonkeyPatch,
    link: Callable[..., object],
) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("requires the Linux descriptor-link publication path")
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, link})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, link},
    )


@pytest.mark.parametrize("outcome", ("success", "exists", "error"))
def test_descriptor_link_backend_maps_errno_without_platform_mutation(outcome: str) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_link(
        source: str,
        name: str,
        *,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        calls.append((source, name, dst_dir_fd, follow_symlinks))
        if outcome == "exists":
            raise FileExistsError(errno.EEXIST, "injected")
        if outcome == "error":
            raise OSError(errno.EIO, "injected")

    backend = materializer_io.descriptor_link_backend(fake_link)
    expected = {"success": 0, "exists": errno.EEXIST, "error": errno.EIO}[outcome]

    assert backend(7, 9, b"candidate.hurl", ".candidate.materializing") == expected
    assert calls == [
        ("/proc/self/fd/7", "candidate.hurl", 9, True),
    ]


@pytest.mark.parametrize(
    ("clone_result", "clone_errno", "expected"),
    ((0, 0, 0), (-1, errno.EIO, errno.EIO), (-1, 0, errno.ENOTSUP)),
)
def test_darwin_clone_backend_maps_errno_without_platform_mutation(
    clone_result: int,
    clone_errno: int,
    expected: int,
) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_clone(
        descriptor: int,
        destination_fd: int,
        name: bytes,
        flags: int,
    ) -> int:
        calls.append((descriptor, destination_fd, name, flags))
        ctypes.set_errno(clone_errno)
        return clone_result

    backend = materializer_io.darwin_clone_backend(fake_clone)
    try:
        assert backend(7, 9, b"candidate.hurl", ".candidate.materializing") == expected
    finally:
        ctypes.set_errno(0)
    assert calls == [(7, 9, b"candidate.hurl", 0x0018)]


def test_materializer_io_import_skips_darwin_loader_on_windows() -> None:
    script = """
import ctypes
import sys

import entroping.core

def fail_darwin_load(*_args, **_kwargs):
    raise AssertionError("Darwin libc must not load on Windows")

ctypes.CDLL = fail_darwin_load
sys.platform = "win32"
import entroping.core.mutation_materializer_io
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("result", "message"),
    (
        (errno.EEXIST, "candidate output already exists"),
        (errno.ENOTSUP, "candidate output publication unsupported"),
        (errno.EIO, "candidate output could not be published"),
    ),
)
def test_publication_result_check_maps_fixed_errors(result: int, message: str) -> None:
    with pytest.raises(MutationMaterializerError, match=message) as caught:
        materializer_io.publication_result_check(result)
    assert str(caught.value) == message
    materializer_io.publication_result_check(0)


def _verification_fixture(
    tmp_path: Path,
    *,
    final_bytes: bytes | None,
) -> tuple[int, int, Path, tuple[int, int]]:
    destination = tmp_path / "destination"
    destination.mkdir()
    held_path = tmp_path / "held.hurl"
    content = b"GET /health\nHTTP 200\n"
    held_path.write_bytes(content)
    held_fd = os.open(held_path, os.O_RDONLY)
    held = os.fstat(held_fd)
    output = destination / "candidate.hurl"
    if final_bytes is not None:
        output.write_bytes(final_bytes)
    destination_fd = os.open(
        destination,
        os.O_RDONLY | materializer_io.DIRECTORY_FLAG | materializer_io.NOFOLLOW,
    )
    return held_fd, destination_fd, output, (held.st_dev, held.st_ino)


def test_verify_published_output_rejects_missing_final(tmp_path: Path) -> None:
    held_fd, destination_fd, _output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=None,
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                "candidate.hurl",
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_empty_final(tmp_path: Path) -> None:
    held_fd, destination_fd, _output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=b"",
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                "candidate.hurl",
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_distinct_inode(tmp_path: Path) -> None:
    content = b"GET /health\nHTTP 200\n"
    held_fd, destination_fd, output, expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=content,
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                output.name,
                expected_identity,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_verify_published_output_rejects_same_size_wrong_content(tmp_path: Path) -> None:
    held_fd, destination_fd, output, _expected_identity = _verification_fixture(
        tmp_path,
        final_bytes=b"GET /health\nHTTP 201\n",
    )
    try:
        with pytest.raises(MutationMaterializerError, match="verification failed"):
            materializer_io.verify_published_output(
                held_fd,
                destination_fd,
                output.name,
                None,
            )
    finally:
        os.close(held_fd)
        os.close(destination_fd)


def test_materializer_rejects_relative_and_symlink_roots(tmp_path: Path) -> None:
    with pytest.raises(MutationMaterializerError, match="root is unsafe"):
        materialize_mutation_candidate(Path("relative"), Path("relative/manifest.json"))

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(MutationMaterializerError, match="root is unsafe"):
        materialize_mutation_candidate(link, link / "manifest.json")


def test_materializer_rejects_unavailable_project_root_without_output(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-project"

    with pytest.raises(MutationMaterializerError, match="root is unavailable") as caught:
        materialize_mutation_candidate(missing_root, missing_root / "manifest.json")

    assert str(caught.value) == "project root is unavailable"


@pytest.mark.parametrize(
    "source_path",
    ("", "tests//source.hurl", "tests/../source.hurl", "tests/token=abc.hurl"),
)
def test_materializer_rejects_unsafe_source_paths_without_output(
    tmp_path: Path,
    source_path: str,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["project_relative_source_path"] = source_path
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError) as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) in {
        "source path is unsafe",
        "source path must be project-relative",
        "manifest contains unsafe text",
    }
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


@pytest.mark.parametrize("source_path", ("source.hurl", "tests/source.hurl/"))
def test_materializer_rejects_unsafe_source_shape_without_output(
    tmp_path: Path,
    source_path: str,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["project_relative_source_path"] = source_path
    identity: dict[str, object] = {
        "category": document["category"],
        "project_relative_source_path": source_path,
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) in {
        "source path is unsafe",
        "source path must be project-relative",
    }
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_busy_temporary_without_overwrite(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    temporary = output.with_name(f".{output.name}.materializing")
    temporary.write_text("busy", encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="already being materialized") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output is already being materialized"
    assert temporary.read_text(encoding="utf-8") == "busy"
    assert not output.exists()


def test_materializer_wraps_output_sync_error_and_cleans_temporary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)

    def fail_fsync(_fd: int) -> None:
        raise OSError("injected sync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(MutationMaterializerError, match="could not be written") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output could not be written"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()


def test_materialize_status_candidate_writes_deterministic_review_only_hurl(
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    source_stat_before = os.stat(source)

    output_path = materialize_mutation_candidate(tmp_path, manifest_path)

    assert output_path == tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output_path.read_text(encoding="utf-8") == (
        "# entroping: materializer_schema=entroping.mutation-materialization.v1\n"
        "# entroping: review_only=true\n"
        f"# entroping: candidate_id={candidate_id}\n"
        "# entroping: mutation_category=status-code\n"
        "# entroping: mutation_seed=7\n"
        f"# entroping: source_sha256={hashlib.sha256(source_before).hexdigest()}\n"
        f"# entroping: source_size_bytes={len(source_before)}\n"
        f"# entroping: source_mtime_ns={source_stat_before.st_mtime_ns}\n"
        "# entroping: safety=read-only\n"
        "# entroping: review_decision_id=decision-1\n"
        "# entroping: evidence_ids=evidence-1\n\n"
        "GET {{base_url}}/health\n"
        "HTTP 500\n"
    )
    assert source.read_bytes() == source_before
    assert os.stat(source).st_mtime_ns == source_stat_before.st_mtime_ns


def test_materializer_rejects_non_utf8_source(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: safety=read-only\n\nGET /health\nHTTP 200\n\xff"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source is not UTF-8"):
        materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_rejects_malformed_source_metadata_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: tags=\n\nGET /health\nHTTP 200\n"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="source metadata is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source metadata is invalid"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_wraps_public_hurl_validation_error_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import entroping.core.hurl_validator as hurl_validator

    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)

    def reject(_content: str, _display_path: str) -> None:
        raise hurl_validator.HurlValidationError("invalid")

    monkeypatch.setattr("entroping.core.mutation_materializer.validate_hurl_content", reject)
    with pytest.raises(
        MutationMaterializerError, match="generated Hurl failed validation"
    ) as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "generated Hurl failed validation"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_manifest_outside_root_and_duplicate_keys(tmp_path: Path) -> None:
    _write_status_fixture(tmp_path)
    outside = tmp_path.parent / "outside-manifest.json"
    with pytest.raises(MutationMaterializerError, match="project-relative"):
        materialize_mutation_candidate(tmp_path, outside)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version": "one", "schema_version": "two"}', encoding="utf-8")
    with pytest.raises(MutationMaterializerError, match="duplicate keys"):
        materialize_mutation_candidate(tmp_path, duplicate)


def test_materializer_rejects_destination_identity_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    real_open_relative = materializer_io.open_relative_directory
    destination_calls = 0

    def changed_destination(
        root_fd: int, parts: tuple[str, ...]
    ) -> tuple[int, tuple[tuple[int, int], ...]]:
        nonlocal destination_calls
        result = real_open_relative(root_fd, parts)
        if parts == ("tests", "generated", "mutations"):
            destination_calls += 1
            if destination_calls == 2:
                return result[0], ((-1, -1),)
        return result

    monkeypatch.setattr(materializer_io, "open_relative_directory", changed_destination)
    with pytest.raises(MutationMaterializerError, match="destination changed"):
        materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_wraps_bounded_source_read_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_read = materializer_io.read_bounded_fd
    reads = 0

    def fail_source_read(descriptor: int, limit: int) -> bytes:
        nonlocal reads
        reads += 1
        if reads == 2:
            raise MutationMaterializerError("bounded input is oversized")
        return real_read(descriptor, limit)

    monkeypatch.setattr(materializer_io, "read_bounded_fd", fail_source_read)
    with pytest.raises(MutationMaterializerError, match="source size is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source size is invalid"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_rejects_source_inode_change_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    replaced = False

    real_stat = os.stat

    def replace_before_recheck(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal replaced
        if path == "source.hurl" and dir_fd is not None and not replaced:
            replaced = True
            source.unlink()
            source.write_bytes(source_before)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", replace_before_recheck)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, replace_before_recheck})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, replace_before_recheck},
    )
    with pytest.raises(MutationMaterializerError, match="source changed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "source changed before publication"
    assert source.read_bytes() == source_before
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_reports_output_close_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_close = os.close
    output_descriptor: int | None = None

    def fail_write(descriptor: int, _raw: bytes) -> int:
        nonlocal output_descriptor
        output_descriptor = descriptor
        return 0

    def fail_output_close(descriptor: int) -> None:
        if descriptor == output_descriptor:
            raise OSError("injected close failure")
        real_close(descriptor)

    monkeypatch.setattr(os, "write", fail_write)
    monkeypatch.setattr(os, "close", fail_output_close)
    try:
        with pytest.raises(MutationMaterializerError, match="cleanup failed") as caught:
            materialize_mutation_candidate(tmp_path, manifest_path)
    finally:
        monkeypatch.undo()
        if output_descriptor is not None:
            with suppress(OSError):
                real_close(output_descriptor)

    assert str(caught.value) == "candidate output cleanup failed"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


@pytest.mark.parametrize("capability", ("_NOFOLLOW", "_DIRECTORY_FLAG", "_NONBLOCK"))
def test_materializer_rejects_unsupported_platform_before_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capability: str,
) -> None:
    touched: list[str] = []
    monkeypatch.setattr("entroping.core.mutation_materializer." + capability, 0)

    def fake_open_root(_root: Path) -> int:
        touched.append("root")
        return -1

    monkeypatch.setattr(materializer_io, "open_root", fake_open_root)
    monkeypatch.setattr(
        materializer_io,
        "open_relative_directory",
        lambda _root: touched.append("destination"),
    )
    monkeypatch.setattr(
        "entroping.core.mutation_materializer._load_manifest",
        lambda _root, _fd, _manifest: touched.append("manifest"),
    )
    monkeypatch.setattr(
        materializer_io,
        "open_source",
        lambda _root, _parts: touched.append("source"),
    )

    with pytest.raises(MutationMaterializerError, match="platform capability"):
        materialize_mutation_candidate(tmp_path, tmp_path / "manifest.json")

    assert touched == []


@pytest.mark.parametrize(
    ("capability_set", "required_function"),
    (("supports_dir_fd", os.open), ("supports_follow_symlinks", os.stat)),
)
def test_materializer_rejects_missing_capability_set_before_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capability_set: str,
    required_function: object,
) -> None:
    supported = set(getattr(os, capability_set))
    supported.discard(required_function)
    monkeypatch.setattr(os, capability_set, supported)
    touched: list[str] = []
    monkeypatch.setattr(materializer_io, "open_root", lambda _root: touched.append("root"))

    with pytest.raises(MutationMaterializerError, match="platform capability"):
        materialize_mutation_candidate(tmp_path, tmp_path / "manifest.json")

    assert touched == []


def test_materializer_reconstructs_short_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_read = os.read

    def short_read(fd: int, size: int) -> bytes:
        return real_read(fd, min(size, 2))

    monkeypatch.setattr(os, "read", short_read)

    output_path = materialize_mutation_candidate(tmp_path, manifest_path)

    assert output_path.name == f"{candidate_id}.hurl"
    assert source.exists()


def test_materializer_rejects_nonregular_manifest_before_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    manifest_path.unlink()
    manifest_path.mkdir()

    def read_must_not_run(_fd: int, _size: int) -> bytes:
        raise AssertionError("manifest read must not run for non-regular file")

    monkeypatch.setattr(os, "read", read_must_not_run)

    with pytest.raises(MutationMaterializerError, match="manifest"):
        materialize_mutation_candidate(tmp_path, manifest_path)


def test_materializer_rejects_fifo_source_without_blocking(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO support is unavailable")
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source.unlink()
    os.mkfifo(source)
    script = """
import sys
from pathlib import Path
from entroping.core.mutation_materializer import (
    MutationMaterializerError,
    materialize_mutation_candidate,
)
try:
    materialize_mutation_candidate(Path(sys.argv[1]), Path(sys.argv[2]))
except MutationMaterializerError:
    raise SystemExit(0)
raise SystemExit(3)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(manifest_path)],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=2,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_bounded_read_rejects_limit_plus_one(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"123456789")
    descriptor = os.open(oversized, os.O_RDONLY)
    try:
        with pytest.raises(MutationMaterializerError, match="oversized"):
            materializer_io.read_bounded_fd(descriptor, 8)
    finally:
        os.close(descriptor)


def test_materializer_rejects_zero_progress_write_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    monkeypatch.setattr(os, "write", lambda _fd, _raw: 0)

    with pytest.raises(MutationMaterializerError, match="no progress"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("category", []),
        ("project_relative_source_path", 17),
        ("source_size_bytes", []),
        ("source_mtime_ns", {}),
        ("reviewed_seed", "7"),
        ("review_decision_id", []),
        ("evidence_ids", {}),
        ("candidate_id", []),
        ("category_selector", []),
    ),
)
def test_materializer_rejects_malformed_manifest_types_without_raw_errors(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document[field] = value
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="manifest field is invalid") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "manifest field is invalid"
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_surfaces_output_cleanup_failure_without_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    monkeypatch.setattr(os, "write", lambda _fd, _raw: 0)

    real_unlink = os.unlink
    destination = tmp_path / "tests" / "generated" / "mutations"
    destination_identity = (destination.stat().st_dev, destination.stat().st_ino)

    def fail_unlink(_name: str, *, dir_fd: int | None = None) -> None:
        if _name.endswith(".materializing") and dir_fd is not None:
            identity = os.fstat(dir_fd)
            if (identity.st_dev, identity.st_ino) == destination_identity:
                raise OSError("injected cleanup failure")
        real_unlink(_name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_unlink)
    supported_dir_fd = set(os.supports_dir_fd)
    supported_dir_fd.add(fail_unlink)
    monkeypatch.setattr(os, "supports_dir_fd", supported_dir_fd)

    with pytest.raises(MutationMaterializerError, match="output cleanup failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output cleanup failed"
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materializer_commits_after_link_when_temp_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_unlink = os.unlink

    def fail_temp_unlink(name: str, *, dir_fd: int | None = None) -> None:
        if name.endswith(".materializing") and dir_fd is not None:
            raise OSError("injected post-link cleanup failure")
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_temp_unlink)
    supported_dir_fd = set(os.supports_dir_fd)
    supported_dir_fd.add(fail_temp_unlink)
    monkeypatch.setattr(os, "supports_dir_fd", supported_dir_fd)

    output = materialize_mutation_candidate(tmp_path, manifest_path)
    assert output == tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output.exists()
    assert output.with_name(f".{output.name}.materializing").exists()


def test_materializer_rejects_replaced_temp_before_linux_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    attacker_target = destination / "attacker-controlled.hurl"
    attacker_target.write_text("attacker controlled", encoding="utf-8")
    real_unlink = os.unlink
    real_symlink = os.symlink
    real_link = os.link

    def replace_temp_then_link(
        source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        real_unlink(f".{name}.materializing", dir_fd=dst_dir_fd)
        real_symlink(attacker_target.name, f".{name}.materializing", dir_fd=dst_dir_fd)
        real_link(
            source,
            name,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    _install_linux_link(monkeypatch, replace_temp_then_link)
    output = destination / f"{candidate_id}.hurl"
    with pytest.raises(MutationMaterializerError, match="could not be published") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)
    assert str(caught.value) == "candidate output could not be published"
    assert not output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()
    assert source.read_bytes() == source_before
    assert attacker_target.exists()


def test_materializer_rejects_filesystem_publication_refusal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def refuse_link(
        _source: str,
        _name: str,
        *,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del dst_dir_fd, follow_symlinks
        raise OSError(errno.ENOTSUP, "injected refusal")

    _install_linux_link(monkeypatch, refuse_link)
    with pytest.raises(MutationMaterializerError, match="publication unsupported") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output publication unsupported"
    assert not output.exists()
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_generic_publication_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()

    def fail_link(
        _source: str,
        _name: str,
        *,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del dst_dir_fd, follow_symlinks
        raise OSError(errno.EIO, "injected publication error")

    _install_linux_link(monkeypatch, fail_link)

    with pytest.raises(MutationMaterializerError, match="could not be published") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output could not be published"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_noop_publication_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def noop_backend(
        _source: str,
        _name: str,
        *,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del dst_dir_fd, follow_symlinks
        return None

    _install_linux_link(monkeypatch, noop_backend)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert not output.exists()
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_forged_final_without_trusting_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source_before = source.read_bytes()
    destination = tmp_path / "tests" / "generated" / "mutations"
    attacker_target = destination / "attacker-controlled.hurl"
    attacker_target.write_bytes(b"attacker-controlled")
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_final(
        _source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert follow_symlinks
        os.symlink(attacker_target.name, name, dir_fd=dst_dir_fd)

    _install_linux_link(monkeypatch, forge_final)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert output.is_symlink()
    assert output.resolve() == attacker_target
    assert not temporary.exists()
    assert source.read_bytes() == source_before


def test_materializer_rejects_forged_empty_final(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_empty_final(
        _source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert follow_symlinks
        final_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        os.close(final_fd)

    _install_linux_link(monkeypatch, forge_empty_final)
    with pytest.raises(MutationMaterializerError, match="verification failed"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.exists()
    assert output.stat().st_size == 0
    assert not temporary.exists()


def test_materializer_rejects_same_size_forged_final(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"

    def forge_same_size_final(
        source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert follow_symlinks
        expected = Path(source).read_bytes()
        replacement = bytes((expected[0] ^ 1,)) + expected[1:]
        final_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(final_fd, replacement)
        finally:
            os.close(final_fd)

    _install_linux_link(monkeypatch, forge_same_size_final)
    with pytest.raises(MutationMaterializerError, match="verification failed"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.exists()
    assert output.read_bytes() != source.read_bytes()
    assert not temporary.exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="requires the Linux descriptor-link publication path",
)
def test_linux_public_materializer_rejects_distinct_inode_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    destination = tmp_path / "tests" / "generated" / "mutations"
    output = destination / f"{candidate_id}.hurl"
    temporary = destination / f".{output.name}.materializing"
    copied: list[bytes] = []

    def copy_as_distinct_inode(
        source: str,
        name: str,
        *,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert source.startswith("/proc/self/fd/")
        assert follow_symlinks
        content = Path(source).read_bytes()
        copied.append(content)
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(descriptor, content)
        finally:
            os.close(descriptor)

    monkeypatch.setattr(os, "link", copy_as_distinct_inode)
    monkeypatch.setattr(os, "supports_dir_fd", {*os.supports_dir_fd, copy_as_distinct_inode})
    monkeypatch.setattr(
        os,
        "supports_follow_symlinks",
        {*os.supports_follow_symlinks, copy_as_distinct_inode},
    )

    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    assert copied
    assert output.exists()
    assert output.read_bytes() == copied[0]
    assert not temporary.exists()


def test_materializer_wraps_verification_read_oserror(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    real_bounded_read = materializer_io.read_bounded_fd
    reads = 0

    def fail_final_read(descriptor: int, size: int) -> bytes:
        nonlocal reads
        reads += 1
        if reads == 4:
            raise OSError("injected verification read failure")
        return real_bounded_read(descriptor, size)

    monkeypatch.setattr(materializer_io, "read_bounded_fd", fail_final_read)
    with pytest.raises(MutationMaterializerError, match="verification failed") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "candidate output verification failed"
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert output.exists()
    assert not output.with_name(f".{output.name}.materializing").exists()


@pytest.mark.parametrize("first_write", (0, 1))
def test_materializer_failed_partial_write_cannot_claim_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    first_write: int,
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    writes = 0

    def partial_write(_fd: int, raw: bytes) -> int:
        nonlocal writes
        writes += 1
        return first_write if writes == 1 else 0

    monkeypatch.setattr(os, "write", partial_write)

    with pytest.raises(MutationMaterializerError, match="no progress"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()


def test_materializer_imports_secret_checks_from_models() -> None:
    assert contains_secret_like_value.__module__ == "entroping.models.secrets"
    source = inspect.getsource(sys.modules[materialize_mutation_candidate.__module__])
    assert "from entroping.models.secrets import" in source


@pytest.mark.parametrize(
    "manifest_change",
    (
        {"expected_sha256": "0" * 64},
        {"project_relative_source_path": "../outside.hurl"},
        {"project_relative_source_path": "tests//source.hurl"},
        {"project_relative_source_path": "tests/./source.hurl"},
        {"project_relative_source_path": "tests/source.hurl/"},
        {"candidate_id": "mut-invalid"},
        {"category": "request-shape"},
    ),
)
def test_materialize_rejects_invalid_manifest_before_output(
    tmp_path: Path,
    manifest_change: dict[str, object],
) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document.update(manifest_change)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_duplicate_output_without_overwrite(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    output.write_bytes(b"sentinel")

    with pytest.raises(MutationMaterializerError, match="already exists"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert output.read_bytes() == b"sentinel"


def test_materialize_rejects_source_symlink_without_writing(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    target = tmp_path / "outside.hurl"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_symlinked_destination_ancestry(tmp_path: Path) -> None:
    _source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "tests" / "generated").rename(tmp_path / "tests" / "generated-real")
    (tmp_path / "tests" / "generated").symlink_to(outside, target_is_directory=True)

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (outside / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_missing_safety_and_reserved_metadata(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    source.write_text("# entroping: candidate_id=old\n\nGET /health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(MutationMaterializerError):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_materialize_rejects_status_no_op_before_output(tmp_path: Path) -> None:
    source, manifest_path, candidate_id = _write_status_fixture(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["category_selector"]["replacement_status"] = 200
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="no-op"):
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert source.exists()
    assert not (tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl").exists()


def test_status_ordinal_ignores_http_line_after_response(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = b"# entroping: safety=read-only\n\nGET /health\nHTTP 200\nHTTP 599\n"
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 1, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="assertion is missing"):
        materialize_mutation_candidate(tmp_path, manifest_path)


def test_status_ordinal_never_mutates_triple_backtick_body_status(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n```\nHTTP 201\n```\nHTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 0, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    output = materialize_mutation_candidate(tmp_path, manifest_path).read_text(encoding="utf-8")

    assert "```\nHTTP 201\n```" in output
    assert "```\nHTTP 500\n```" not in output
    assert output.endswith("HTTP 500\n")


@pytest.mark.parametrize(
    ("body", "body_status"),
    (
        (b"```json\nHTTP 201\n```\n", b"```json\nHTTP 201\n```"),
        (b"<request>\nHTTP 201\n</request>\n", b"<request>\nHTTP 201\n</request>"),
        (
            b"<request>\n<inner>\nHTTP 201\n</inner>\n</request>\n",
            b"<request>\n<inner>\nHTTP 201\n</inner>\n</request>",
        ),
        (
            b"<request><x>HTTP 201</x></request>\n",
            b"<request><x>HTTP 201</x></request>",
        ),
    ),
)
def test_status_ordinal_never_mutates_typed_or_xml_body_status(
    tmp_path: Path,
    body: bytes,
    body_status: bytes,
) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n" + body + b"HTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 0, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    output = materialize_mutation_candidate(tmp_path, manifest_path).read_bytes()

    assert body_status in output
    assert body_status.replace(b"201", b"500") not in output
    assert output.endswith(b"HTTP 500\n")


def test_status_ordinal_handles_self_closing_xml_body(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n<request/>\nHTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    document["category_selector"] = {"assertion_ordinal": 0, "replacement_status": 500}
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    document["candidate_id"] = _candidate_id(identity)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    output = materialize_mutation_candidate(tmp_path, manifest_path).read_bytes()

    assert b"<request/>\nHTTP 500\n" in output
    assert b"<request/>\nHTTP 200\n" not in output


def test_status_ordinal_rejects_ambiguous_body_status_without_output(tmp_path: Path) -> None:
    source, manifest_path, _candidate_id_value = _write_status_fixture(tmp_path)
    source_bytes = (
        b"# entroping: safety=read-only\n\nPOST {{base_url}}/health\n"
        b"<request\nHTTP 201\n</request>\nHTTP 200\n"
    )
    source.write_bytes(source_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["expected_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_size_bytes"] = len(source_bytes)
    document["source_mtime_ns"] = source.stat().st_mtime_ns
    identity = {
        "category": document["category"],
        "project_relative_source_path": document["project_relative_source_path"],
        "expected_sha256": document["expected_sha256"],
        "reviewed_seed": document["reviewed_seed"],
        "category_selector": document["category_selector"],
    }
    candidate_id = _candidate_id(identity)
    document["candidate_id"] = candidate_id
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MutationMaterializerError, match="assertion is missing") as caught:
        materialize_mutation_candidate(tmp_path, manifest_path)

    assert str(caught.value) == "status assertion is missing"
    assert source.read_bytes() == source_bytes
    output = tmp_path / "tests" / "generated" / "mutations" / f"{candidate_id}.hurl"
    assert not output.exists()
