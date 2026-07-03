"""Tests for external test evidence packets."""

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import entroping.core.evidence.external_test_evidence as external_test_evidence
from entroping.core.evidence.external_test_evidence import (
    EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
    ExternalTestEvidenceError,
    ExternalTestEvidencePacket,
    build_external_test_evidence,
    render_external_test_evidence_markdown,
    run_external_test_evidence_report,
)
from entroping.core.safe_write import SafeWriteError


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_ready_sources(root: Path) -> None:
    external = root / "reports" / "external-tests"
    _write_text(
        external / "unit-junit.xml",
        """<?xml version="1.0"?>
<testsuite name="unit-suite" tests="5" failures="0" errors="0" skipped="1">
  <testcase classname="unit.RawName" name="should_not_render" />
</testsuite>
""",
    )
    _write_text(
        external / "integration-junit.xml",
        """<?xml version="1.0"?>
<testsuites tests="3" failures="1" errors="0" skipped="0">
  <testsuite name="integration-suite" tests="3" failures="1" errors="0" skipped="0">
    <testcase classname="integration.RawName" name="hidden" />
  </testsuite>
</testsuites>
""",
    )
    _write_text(
        external / "component-junit.xml",
        """<?xml version="1.0"?>
<testsuite name="component-suite">
  <testcase classname="component.RawName" name="a" />
  <testcase classname="component.RawName" name="b"><skipped /></testcase>
</testsuite>
""",
    )
    _write_text(
        external / "contract-junit.xml",
        """<?xml version="1.0"?>
<testsuite name="contract-suite" tests="4" failures="0" errors="0" skipped="0" />
""",
    )
    _write_text(
        external / "e2e-junit.xml",
        """<?xml version="1.0"?>
<testsuite name="e2e-suite" tests="1" failures="0" errors="0" skipped="0" />
""",
    )
    _write_text(
        external / "coverage.xml",
        """<?xml version="1.0"?>
<coverage line-rate="0.875" branch-rate="0.5" lines-covered="70" lines-valid="80"
  branches-covered="5" branches-valid="10">
  <packages />
</coverage>
""",
    )
    _write_text(
        external / "lcov.info",
        """TN:
SF:should-not-render.py
DA:1,1
LF:4
LH:3
BRF:2
BRH:1
end_of_record
""",
    )
    _write_text(
        external / "sarif.json",
        json.dumps(
            {
                "version": "2.1.0",
                "runs": [
                    {
                        "tool": {"driver": {"name": "example"}},
                        "results": [
                            {"level": "error", "message": {"text": "do-not-render"}},
                            {"level": "warning", "message": {"text": "do-not-render"}},
                            {"level": "note", "message": {"text": "do-not-render"}},
                            {"level": "none", "message": {"text": "do-not-render"}},
                            {},
                        ],
                    }
                ],
            }
        ),
    )


def test_external_test_evidence_writes_value_free_json_from_ready_sources(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)

    result = run_external_test_evidence_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "external-test-evidence.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION
    assert payload["summary"] == {
        "status": "ready",
        "sources_total": 8,
        "sources_present": 8,
        "sources_missing": 0,
        "sources_invalid": 0,
        "sources_unsafe": 0,
        "layers_total": 5,
        "layers_with_evidence": 5,
        "layers_missing": 0,
        "layers_blocked": 0,
        "total_tests": 15,
        "total_failures": 1,
        "total_errors": 0,
        "total_skipped": 2,
        "line_coverage_percent": 87.5,
        "branch_coverage_percent": 50.0,
        "sarif_results_total": 5,
        "sarif_error_results": 1,
        "next_actions_total": 0,
    }
    sources = {source["id"]: source for source in payload["sources"]}
    assert sources["unit_junit"]["tests"] == 5
    assert sources["component_junit"]["tests"] == 2
    assert sources["coverage_xml"]["line_coverage_percent"] == 87.5
    assert sources["lcov_info"]["line_coverage_percent"] == 75.0
    assert sources["sarif_json"]["sarif_warning_results"] == 2
    assert sources["sarif_json"]["sarif_none_results"] == 1
    layers = {layer["id"]: layer for layer in payload["layers"]}
    assert layers["unit"]["status"] == "covered"
    assert layers["integration"]["failures"] == 1
    assert layers["component"]["skipped"] == 1
    assert layers["contract"]["source_ids"] == ["contract_junit"]
    rendered = json.dumps(payload)
    assert "should_not_render" not in rendered
    assert "should-not-render.py" not in rendered
    assert "do-not-render" not in rendered


def test_external_test_evidence_markdown_is_escaped_and_value_free(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    packet = build_external_test_evidence(project_root=tmp_path).model_copy(
        update={
            "sources": (
                build_external_test_evidence(project_root=tmp_path)
                .sources[0]
                .model_copy(update={"summary": "unit `ok` | pass"}),
            )
            + build_external_test_evidence(project_root=tmp_path).sources[1:],
        }
    )

    markdown = render_external_test_evidence_markdown(packet)

    assert "# Entroping External Test Evidence" in markdown
    assert "| unit_junit | present | junit | unit |" in markdown
    assert "unit &#96;ok&#96; &#124; pass" in markdown
    assert "should_not_render" not in markdown
    assert "do-not-render" not in markdown


def test_external_test_evidence_handles_missing_sources(tmp_path: Path) -> None:
    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.sources_missing == 8
    assert packet.summary.layers_missing == 5
    assert {source.state for source in packet.sources} == {"missing"}
    assert {layer.status for layer in packet.layers} == {"missing"}
    assert packet.next_actions


def test_external_test_evidence_writes_markdown_with_next_actions_for_missing_sources(
    tmp_path: Path,
) -> None:
    result = run_external_test_evidence_report(project_root=tmp_path, output="md")

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "external-test-evidence.md"
    assert "| Priority | Action | Sources | Layers |" in markdown
    assert "Generate unit JUnit external test evidence." in markdown
    assert "`n/a` lines" in markdown


def test_external_test_evidence_reports_partial_when_some_layers_are_present(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "external-tests" / "unit-junit.xml",
        '<testsuite tests="1" failures="0" errors="0" skipped="0" />',
    )

    packet = build_external_test_evidence(project_root=tmp_path)
    layers = {layer.id: layer for layer in packet.layers}

    assert packet.summary.status == "partial"
    assert layers["unit"].status == "covered"
    assert layers["integration"].status == "missing"


def test_external_test_evidence_reports_partial_for_invalid_auxiliary_artifacts(
    tmp_path: Path,
) -> None:
    _write_ready_sources(tmp_path)
    _write_text(
        tmp_path / "reports" / "external-tests" / "coverage.xml",
        "<coverage />",
    )

    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.layers_with_evidence == 5
    assert packet.summary.sources_invalid == 1


def test_external_test_evidence_parses_child_suite_counts_without_root_counts(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "reports" / "external-tests" / "unit-junit.xml",
        """<?xml version="1.0"?>
<testsuites>
  <testsuite tests="2" failures="1" errors="0" skipped="0" />
  <testsuite tests="3" failures="0" errors="1" skipped="1" />
</testsuites>
""",
    )

    packet = build_external_test_evidence(project_root=tmp_path)
    unit_source = packet.sources[0]

    assert unit_source.suites == 2
    assert unit_source.tests == 5
    assert unit_source.failures == 1
    assert unit_source.errors == 1
    assert unit_source.skipped == 1


def test_external_test_evidence_marks_invalid_and_unsafe_sources(
    tmp_path: Path,
) -> None:
    external = tmp_path / "reports" / "external-tests"
    external.mkdir(parents=True)
    real_unit = _write_text(
        external / "real-unit.xml",
        '<testsuite tests="1" failures="0" errors="0" skipped="0" />',
    )
    os.symlink(real_unit, external / "unit-junit.xml")
    _write_text(external / "integration-junit.xml", "<testsuite tests='x' />")
    (external / "component-junit.xml").mkdir()
    _write_text(
        external / "contract-junit.xml",
        "<not-junit />",
    )
    _write_text(external / "e2e-junit.xml", b"\xff".decode("latin1"))
    _write_text(external / "coverage.xml", "<coverage line-rate='2' />")
    _write_text(external / "lcov.info", "LF:not-int\n")
    _write_text(
        external / "sarif.json",
        json.dumps({"api_key": "sk-proj-" + ("a" * 24)}),
    )

    packet = build_external_test_evidence(project_root=tmp_path)
    sources = {source.id: source for source in packet.sources}

    assert sources["unit_junit"].state == "unsafe"
    assert sources["integration_junit"].state == "invalid"
    assert sources["component_junit"].state == "unsafe"
    assert sources["contract_junit"].state == "invalid"
    assert sources["e2e_junit"].state == "invalid"
    assert sources["coverage_xml"].state == "invalid"
    assert sources["lcov_info"].state == "invalid"
    assert sources["sarif_json"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.layers_blocked == 5
    assert len({action.action for action in packet.next_actions}) == len(
        packet.next_actions
    )
    assert "Repair invalid or unsafe external test evidence." not in {
        action.action for action in packet.next_actions
    }
    assert "sk-proj" not in packet.model_dump_json()


@pytest.mark.parametrize(
    ("relative_path", "raw_text", "expected_summary"),
    [
        ("unit-junit.xml", "<not-junit />", "must be JUnit"),
        ("unit-junit.xml", '<testsuite tests="-1" />', "non-negative integer"),
        ("coverage.xml", "<not-coverage />", "coverage root"),
        ("coverage.xml", "<coverage />", "metrics are missing"),
        ("coverage.xml", '<coverage line-rate="bad" />', "must be a number"),
        (
            "coverage.xml",
            '<coverage lines-covered="1" lines-valid="2" />',
            "line coverage 50%",
        ),
        (
            "coverage.xml",
            '<coverage lines-covered="100" lines-valid="80" />',
            "covered count must not exceed valid count",
        ),
        ("lcov.info", "TN:\nSF:hidden.py\nend_of_record\n", "metrics are missing"),
        ("lcov.info", "LF:-1\n", "non-negative integer"),
        ("lcov.info", "LF:0\nLH:0\n", "line coverage n/a"),
        ("lcov.info", "LF:1\nLH:2\n", "covered count must not exceed valid count"),
        ("sarif.json", "{", "Could not parse SARIF JSON"),
        ("sarif.json", "[]", "must be a JSON object"),
        ("sarif.json", '{"runs": {}}', "runs must be a list"),
        ("sarif.json", '{"runs": [1]}', "run entries must be objects"),
        ("sarif.json", '{"runs": [{"results": {}}]}', "results must be lists"),
        ("sarif.json", '{"runs": [{"results": [1]}]}', "result entries"),
        (
            "sarif.json",
            '{"runs": [{"results": [{"level": "critical"}]}]}',
            "1 results; 0 error; 1 warning",
        ),
    ],
)
def test_external_test_evidence_parser_boundary_cases(
    tmp_path: Path,
    relative_path: str,
    raw_text: str,
    expected_summary: str,
) -> None:
    _write_text(tmp_path / "reports" / "external-tests" / relative_path, raw_text)

    packet = build_external_test_evidence(project_root=tmp_path)
    source_id = {
        "unit-junit.xml": "unit_junit",
        "coverage.xml": "coverage_xml",
        "lcov.info": "lcov_info",
        "sarif.json": "sarif_json",
    }[relative_path]
    source = next(source for source in packet.sources if source.id == source_id)

    assert expected_summary in source.summary


def test_external_test_evidence_rejects_oversized_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.setattr(external_test_evidence, "_MAX_SOURCE_BYTES", 1)

    packet = build_external_test_evidence(project_root=tmp_path)
    first_source = packet.sources[0]

    assert first_source.state == "invalid"
    assert "exceeds" in first_source.summary


def test_external_test_evidence_marks_source_resolution_errors_unsafe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def raise_for_source(*_args: object, **_kwargs: object) -> Path | None:
        raise ValueError("outside root")

    monkeypatch.setattr(
        external_test_evidence,
        "first_symlink_path_component",
        raise_for_source,
    )

    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.sources[0].state == "unsafe"
    assert "must stay under" in packet.sources[0].summary


def test_external_test_evidence_rejects_source_escape_after_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        external_test_evidence,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(ExternalTestEvidenceError, match="must stay under"):
        external_test_evidence._resolve_source_path(Path("..") / "escape.xml", root=tmp_path)


def test_external_test_evidence_rejects_source_replaced_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    target = tmp_path / "reports" / "external-tests" / "unit-junit.xml"
    outside = _write_text(
        tmp_path.parent / "outside-unit.xml",
        '<testsuite tests="1" failures="0" errors="0" skipped="0" />',
    )

    def swap_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o600,
    ) -> int:
        candidate = Path(os.fsdecode(path))
        if candidate == target and not candidate.is_symlink():
            candidate.unlink()
            os.symlink(outside, candidate)
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", swap_before_open)

    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert packet.sources[0].sha256 is None


def test_external_test_evidence_marks_non_utf8_sources_invalid(tmp_path: Path) -> None:
    external = tmp_path / "reports" / "external-tests"
    external.mkdir(parents=True)
    (external / "unit-junit.xml").write_bytes(b"\xff")

    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert "Could not decode unit JUnit as UTF-8" in packet.sources[0].summary


def test_external_test_evidence_bounded_read_handles_open_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_ready_sources(tmp_path)

    def fail_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o600,
    ) -> int:
        if Path(os.fsdecode(path)).name == "unit-junit.xml":
            raise OSError("permission denied")
        return original_open(path, flags, mode)

    original_open = os.open
    monkeypatch.setattr(os, "open", fail_open)

    packet = build_external_test_evidence(project_root=tmp_path)

    assert packet.sources[0].state == "invalid"
    assert "Could not read unit JUnit" in packet.sources[0].summary


def test_external_test_evidence_bounded_read_works_without_no_follow_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_text(tmp_path / "source.xml", "<testsuite />")
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)

    assert external_test_evidence._read_bounded_bytes(source, artifact="source") == (
        b"<testsuite />"
    )


def test_external_test_evidence_bounded_read_rejects_directories(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()

    with pytest.raises(ExternalTestEvidenceError, match="not a regular file"):
        external_test_evidence._read_bounded_bytes(directory, artifact="directory")


def test_external_test_evidence_rejects_unsupported_and_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ExternalTestEvidenceError, match="Unsupported"):
        run_external_test_evidence_report(project_root=tmp_path, output=cast(Any, "html"))
    with pytest.raises(ExternalTestEvidenceError, match="must stay under"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "external-test-evidence.json",
        )
    with pytest.raises(ExternalTestEvidenceError, match="must not be written into"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=Path(".entroping") / "external-test-evidence.json",
        )
    with pytest.raises(ExternalTestEvidenceError, match="must not be written into"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / ".entroping" / "external-test-evidence.json",
        )
    with pytest.raises(ExternalTestEvidenceError, match="must not be written into"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("reports") / "envs" / "external-test-evidence.json",
        )

    monkeypatch.setattr(
        external_test_evidence,
        "first_symlink_path_component",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(ExternalTestEvidenceError, match="must stay under"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "escaped-external-test-evidence.json",
        )


def test_external_test_evidence_rejects_symlinked_output_path(tmp_path: Path) -> None:
    (tmp_path / "real-reports").mkdir()
    os.symlink(tmp_path / "real-reports", tmp_path / "linked-reports")

    with pytest.raises(ExternalTestEvidenceError, match="symlinked component"):
        run_external_test_evidence_report(
            project_root=tmp_path,
            output="json",
            output_path=Path("linked-reports") / "external-test-evidence.json",
        )


def test_external_test_evidence_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_safe_write(*_args: object, **_kwargs: object) -> Path:
        raise SafeWriteError("disk full")

    monkeypatch.setattr(external_test_evidence, "safe_write_text", fail_safe_write)

    with pytest.raises(ExternalTestEvidenceError, match="disk full"):
        run_external_test_evidence_report(project_root=tmp_path, output="json")


def test_external_test_evidence_rejects_secret_like_rendered_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = build_external_test_evidence(project_root=tmp_path)
    monkeypatch.setattr(
        external_test_evidence,
        "build_external_test_evidence",
        lambda **_: packet.model_copy(update={"project": "sk-proj-" + ("a" * 24)}),
    )

    with pytest.raises(ExternalTestEvidenceError, match="contains secret-like content"):
        run_external_test_evidence_report(project_root=tmp_path, output="json")


def test_external_test_evidence_wraps_packet_serialization_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = ExternalTestEvidencePacket.model_construct(
        schema_version=EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
        generated_at="2026-06-21T00:00:00+00:00",
        project="sk-proj-" + ("a" * 24),
        summary=object(),
        sources=(),
        layers=(),
        next_actions=(),
    )
    monkeypatch.setattr(external_test_evidence, "_build_packet", lambda **_: packet)

    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(ExternalTestEvidenceError, match="contains secret-like"),
    ):
        build_external_test_evidence(project_root=tmp_path)


def test_external_test_evidence_packet_json_fallback_and_errors() -> None:
    class FallbackPacket:
        def model_dump(self, **kwargs: object) -> dict[str, str]:
            if "fallback" in kwargs:
                raise TypeError("old pydantic")
            return {"schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION}

    class BrokenPacket:
        def model_dump(self, **_kwargs: object) -> object:
            raise RuntimeError("broken")

    assert json.loads(external_test_evidence._packet_json(cast(Any, FallbackPacket()))) == {
        "schema_version": EXTERNAL_TEST_EVIDENCE_SCHEMA_VERSION,
    }
    with pytest.raises(ExternalTestEvidenceError, match="could not be serialized"):
        external_test_evidence._packet_json(cast(Any, BrokenPacket()))


def test_external_test_evidence_deduplicates_next_actions() -> None:
    action = external_test_evidence.ExternalTestEvidenceNextAction(
        priority="medium",
        action="Generate unit evidence.",
        source_ids=("unit_junit",),
    )

    assert external_test_evidence._dedupe_actions((action, action)) == (action,)
