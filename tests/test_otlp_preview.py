import json
import os
from pathlib import Path

import pytest

import entroping.core.evidence.otlp_preview as otlp_preview
from entroping.core.safe_write import SafeWriteError


def _write_run_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-checkout-service",
                "environment": "local",
                "generated_at": "2026-07-04T00:00:00+00:00",
                "summary": {
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "exit_code": 1,
                },
                "tests": [
                    {
                        "path": "tests/private-checkout-flow.hurl",
                        "execution_path": ".entroping/run/private-checkout-flow.hurl",
                        "status": "failed",
                        "exit_code": 1,
                        "duration_ms": 42,
                        "rule_ids": ["status"],
                        "stdout": "raw-output-should-not-render",
                        "stderr": "stderr-should-not-render",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_passing_run_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "summary": {
                    "total": 3,
                    "passed": 3,
                    "failed": 0,
                    "exit_code": 0,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_runtime_card(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.runtime-card.v1",
                "summary": {
                    "status": "ready",
                    "findings": 0,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_otel_mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "schema_version": "entroping.otel-mapping.v1",
                "summary": {
                    "status": "ready",
                    "mappings_total": 4,
                },
            }
        ),
        encoding="utf-8",
    )


def test_otlp_preview_reports_missing_sources_explicitly(tmp_path: Path) -> None:
    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.schema_version == otlp_preview.OTLP_PREVIEW_SCHEMA_VERSION
    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "missing"
    assert by_id["otel_mapping"].state == "missing"
    assert packet.fixture.log_records == ()
    assert packet.fixture.metrics == ()
    assert packet.fixture.spans == ()
    assert packet.next_actions[0].source_ids == ("run_report",)


def test_otlp_preview_uses_counts_without_raw_run_values(tmp_path: Path) -> None:
    _write_run_report(tmp_path / "reports" / "run-latest.json")

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    payload = json.dumps(packet.model_dump(mode="json"), sort_keys=True)
    markdown = otlp_preview.render_otlp_preview_markdown(packet)

    assert packet.summary.status == "partial"
    assert packet.summary.sources_present == 1
    assert packet.summary.metrics_total == 3
    assert packet.fixture.log_records[0].name == "entroping.run.summary"
    assert packet.fixture.metrics[0].name == "entroping.tests.total"
    assert packet.fixture.metrics[0].value == 2
    assert packet.fixture.spans[0].status_code == "ERROR"
    assert "private-checkout-service" not in payload
    assert "private-checkout-flow" not in payload
    assert "raw-output-should-not-render" not in payload
    assert "stderr-should-not-render" not in markdown


def test_otlp_preview_marks_wrong_schema_invalid(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _ = (reports / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v999"}\n',
        encoding="utf-8",
    )

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "invalid"
    assert by_id["run_report"].summary == ("schema mismatch: expected entroping.run-report.v1")


def test_otlp_preview_marks_symlinked_source_unsafe(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    target = tmp_path / "run-latest.json"
    _ = target.write_text('{"schema_version":"entroping.run-report.v1"}\n', encoding="utf-8")
    os.symlink(target, reports / "run-latest.json")

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "unsafe"
    assert by_id["run_report"].summary == "symlinked path component"


def test_otlp_preview_marks_secret_like_source_unsafe(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _ = (reports / "run-latest.json").write_text(
        '{"schema_version":"entroping.run-report.v1","token":"sk-proj-secret123"}\n',
        encoding="utf-8",
    )

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert by_id["run_report"].state == "unsafe"
    assert by_id["run_report"].summary == "secret-like content"


def test_otlp_preview_reports_ready_when_all_sources_are_present(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_passing_run_report(reports / "run-latest.json")
    _write_runtime_card(reports / "runtime-card.json")
    _write_otel_mapping(reports / "otel-mapping.json")

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "ready"
    assert packet.summary.severity == "info"
    assert packet.next_actions == ()
    assert by_id["runtime_card"].summary == "ready runtime card, 0 findings"
    assert by_id["otel_mapping"].summary == "ready OTEL mapping, 4 mappings"
    assert packet.fixture.spans[0].status_code == "OK"


def test_otlp_preview_marks_directory_source_unsafe(tmp_path: Path) -> None:
    run_report = tmp_path / "reports" / "run-latest.json"
    run_report.mkdir(parents=True)

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert packet.summary.status == "insufficient"
    assert by_id["run_report"].state == "unsafe"
    assert by_id["run_report"].summary == "not a file"


def test_otlp_preview_marks_invalid_source_bytes_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    _ = (reports / "run-latest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        otlp_preview,
        "read_local_evidence_json_artifact_bytes",
        lambda path, *, root: (None, "artifact too large"),
    )

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    by_id = {source.id: source for source in packet.sources}

    assert by_id["run_report"].state == "invalid"
    assert by_id["run_report"].summary == "artifact too large"


def test_otlp_preview_marks_invalid_utf8_json_and_non_object_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "run-latest.json").write_bytes(b"\xff")

    utf8_packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    utf8_by_id = {source.id: source for source in utf8_packet.sources}
    assert utf8_by_id["run_report"].state == "invalid"
    assert utf8_by_id["run_report"].summary.startswith("invalid UTF-8:")

    _ = (reports / "run-latest.json").write_text("not-json", encoding="utf-8")
    json_packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    json_by_id = {source.id: source for source in json_packet.sources}
    assert json_by_id["run_report"].state == "invalid"
    assert json_by_id["run_report"].summary == "invalid JSON: Expecting value"

    _ = (reports / "run-latest.json").write_text("[]", encoding="utf-8")
    object_packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)
    object_by_id = {source.id: source for source in object_packet.sources}
    assert object_by_id["run_report"].state == "invalid"
    assert object_by_id["run_report"].summary == "JSON artifact must be an object"


def test_otlp_preview_adds_repair_action_for_invalid_optional_source(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_passing_run_report(reports / "run-latest.json")
    _ = (reports / "runtime-card.json").write_text("not-json", encoding="utf-8")

    packet = otlp_preview.build_otlp_preview_packet(project_root=tmp_path)

    assert any(action.source_ids == ("runtime_card",) for action in packet.next_actions)


def test_run_otlp_preview_report_writes_json_and_rejects_unsupported_output(
    tmp_path: Path,
) -> None:
    _write_passing_run_report(tmp_path / "reports" / "run-latest.json")

    result = otlp_preview.run_otlp_preview_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "otlp-preview.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == otlp_preview.OTLP_PREVIEW_SCHEMA_VERSION

    with pytest.raises(otlp_preview.OtlpPreviewError, match="Unsupported otlp-preview output"):
        otlp_preview.run_otlp_preview_report(project_root=tmp_path, output="yaml")


def test_run_otlp_preview_report_rejects_unsafe_output_paths(tmp_path: Path) -> None:
    with pytest.raises(otlp_preview.OtlpPreviewError, match="must stay under the project root"):
        otlp_preview.run_otlp_preview_report(
            project_root=tmp_path,
            output="md",
            output_path=tmp_path.parent / "otlp-preview.md",
        )
    with pytest.raises(otlp_preview.OtlpPreviewError, match="must not be written into"):
        otlp_preview.run_otlp_preview_report(
            project_root=tmp_path,
            output="md",
            output_path=Path(".entroping") / "otlp-preview.md",
        )

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    os.symlink(real_dir, tmp_path / "linked")
    with pytest.raises(otlp_preview.OtlpPreviewError, match="symlinked component:"):
        otlp_preview.run_otlp_preview_report(
            project_root=tmp_path,
            output="md",
            output_path=Path("linked") / "otlp-preview.md",
        )


def test_run_otlp_preview_report_wraps_secret_and_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(otlp_preview, "contains_unredacted_evidence_secret", lambda content: True)
    with pytest.raises(otlp_preview.OtlpPreviewError, match="contains secret-like content"):
        otlp_preview.run_otlp_preview_report(project_root=tmp_path, output="md")

    monkeypatch.setattr(otlp_preview, "contains_unredacted_evidence_secret", lambda content: False)

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("write blocked")

    monkeypatch.setattr(otlp_preview, "safe_write_text", fail_write)
    with pytest.raises(otlp_preview.OtlpPreviewError, match="write blocked"):
        otlp_preview.run_otlp_preview_report(project_root=tmp_path, output="md")


def test_otlp_preview_internal_safety_helpers_cover_absent_and_escaped_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    escaped = otlp_preview._markdown_cell("\\|*_`\n")

    assert "&#92;" in escaped
    assert "\\|" in escaped
    assert "&#42;" in escaped
    assert "&#95;" in escaped
    assert "&#96;" in escaped
    assert "\n" not in escaped
    assert otlp_preview._document_by_id((), "run_report") is None
    assert otlp_preview._relative_display(tmp_path.parent / "outside", root=tmp_path) == "outside"

    def raise_path_error(path: Path, *, root: Path) -> Path | None:
        _ = (path, root)
        raise ValueError("outside")

    monkeypatch.setattr(otlp_preview, "first_symlink_path_component", raise_path_error)
    assert (
        otlp_preview._source_path_error(tmp_path / "reports" / "run-latest.json", root=tmp_path)
        == "path outside project"
    )

    monkeypatch.setattr(
        otlp_preview,
        "first_symlink_path_component",
        lambda path, *, root: None,
    )
    assert (
        otlp_preview._source_path_error(tmp_path.parent / "outside.json", root=tmp_path)
        == "path outside project"
    )
