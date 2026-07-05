import json
from pathlib import Path

import pytest

from entroping.core.plan.qa_brain_corpus_manifest import (
    QA_BRAIN_CORPUS_MANIFEST_SCHEMA_VERSION,
    QaBrainCorpusManifestError,
    build_qa_brain_corpus_manifest,
    build_qa_brain_corpus_manifest_from_retrieval_plan,
    render_qa_brain_corpus_manifest_markdown,
    run_qa_brain_corpus_manifest_report,
)
from entroping.core.plan.qa_brain_retrieval_plan import (
    QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION,
    QaBrainRetrievalPlanError,
    QaBrainRetrievalPlanNextAction,
    QaBrainRetrievalPlanPacket,
    QaBrainRetrievalPlanRow,
    QaBrainRetrievalPlanSummary,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _retrieval_packet(*, project: str = "corpus-project") -> QaBrainRetrievalPlanPacket:
    return QaBrainRetrievalPlanPacket(
        generated_at="2026-07-05T00:00:00+00:00",
        project=project,
        eval_plan_schema_version="entroping.qa-brain-eval-plan.v1",
        summary=QaBrainRetrievalPlanSummary(
            status="partial",
            plans_total=3,
            plans_ready=1,
            plans_missing=1,
            plans_attention=1,
            next_actions_total=1,
        ),
        retrieval_plans=(
            QaBrainRetrievalPlanRow(
                case_id="weak_test_detection",
                label="Weak-test detection",
                readiness="ready",
                source_ids=("test-quality-json", "missing-json"),
                source_paths=("reports/test-quality.json", "reports/missing.json"),
                retrieval_category="test_quality",
                retrieval_intent="Find weak-test evidence.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body", "tokens"),
                query_hints=("Use schema IDs.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Use evidence for retrieval design.",
            ),
            QaBrainRetrievalPlanRow(
                case_id="bogus_evidence",
                label="Bogus evidence",
                readiness="attention",
                source_ids=("artifact-manifest-json",),
                source_paths=("reports/artifact-manifest.json",),
                retrieval_category="evidence_integrity",
                retrieval_intent="Find artifact integrity evidence.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body", "tokens"),
                query_hints=("Use artifact IDs.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Repair evidence before retrieval indexing.",
            ),
            QaBrainRetrievalPlanRow(
                case_id="redaction_mistakes",
                label="Redaction mistakes",
                readiness="missing",
                source_ids=("redaction-json",),
                source_paths=("reports/redaction-review.json",),
                retrieval_category="redaction_safety",
                retrieval_intent="Find redaction evidence.",
                allowed_fields=("schema_version", "artifact_id"),
                forbidden_fields=("request_body", "response_body", "tokens"),
                query_hints=("Use confidence counts.",),
                safety_notes=("Use value-free local metadata only.",),
                next_action="Add evidence before retrieval indexing.",
            ),
        ),
        next_actions=(
            QaBrainRetrievalPlanNextAction(
                priority="high",
                action="Repair evidence before retrieval indexing.",
                case_ids=("bogus_evidence",),
            ),
        ),
    )


def _packet_with_sources(
    *,
    source_ids: tuple[str, ...],
    source_paths: tuple[str, ...],
    project: str = "corpus-project",
) -> QaBrainRetrievalPlanPacket:
    packet = _retrieval_packet(project=project)
    return packet.model_copy(
        update={
            "retrieval_plans": (
                packet.retrieval_plans[0].model_copy(
                    update={"source_ids": source_ids, "source_paths": source_paths}
                ),
            )
        }
    )


def test_qa_brain_corpus_manifest_includes_eligible_and_excluded_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80},
        },
    )
    _write_json(
        tmp_path / "reports" / "artifact-manifest.json",
        {
            "schema_version": "entroping.report-artifact-manifest.v1",
            "summary": {"status": "incomplete"},
        },
    )
    _write_json(
        tmp_path / "reports" / "redaction-review.json",
        {
            "schema_version": "entroping.redaction-review.v1",
            "sample": "sk-proj-secret1234567890",
        },
    )
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: _retrieval_packet(project=project_root.name),
    )

    packet = build_qa_brain_corpus_manifest(project_root=tmp_path)
    candidates = {candidate.source_id: candidate for candidate in packet.candidates}
    rendered = packet.model_dump_json()

    assert packet.schema_version == QA_BRAIN_CORPUS_MANIFEST_SCHEMA_VERSION
    assert packet.retrieval_plan_schema_version == QA_BRAIN_RETRIEVAL_PLAN_SCHEMA_VERSION
    assert packet.summary.status == "partial"
    assert packet.summary.candidates_total == 4
    assert packet.summary.eligible_total == 2
    assert packet.summary.excluded_total == 2
    assert candidates["test-quality-json"].state == "eligible"
    assert candidates["test-quality-json"].schema_id == "entroping.test-quality-report.v1"
    assert candidates["test-quality-json"].source_category == "test_quality"
    assert candidates["artifact-manifest-json"].state == "eligible"
    assert candidates["artifact-manifest-json"].source_category == "evidence_integrity"
    assert candidates["missing-json"].state == "excluded"
    assert candidates["missing-json"].exclusion_reason == "missing"
    assert candidates["redaction-json"].state == "excluded"
    assert candidates["redaction-json"].exclusion_reason == "secret_like_content"
    assert "sk-proj" not in rendered
    assert "score" not in rendered


def test_qa_brain_corpus_manifest_excludes_invalid_json_and_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "test-quality.json").write_text("{not-json\n", encoding="utf-8")
    outside = tmp_path.parent / "outside-artifact.json"
    outside.write_text('{"schema_version":"entroping.outside.v1"}\n', encoding="utf-8")
    (reports / "artifact-manifest.json").symlink_to(outside)
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: _retrieval_packet(project=project_root.name),
    )

    packet = build_qa_brain_corpus_manifest(project_root=tmp_path)
    candidates = {candidate.source_id: candidate for candidate in packet.candidates}

    assert packet.summary.status == "insufficient"
    assert candidates["test-quality-json"].exclusion_reason == "invalid_json"
    assert candidates["artifact-manifest-json"].exclusion_reason == "unsafe_path"
    assert candidates["redaction-json"].exclusion_reason == "missing"


def test_qa_brain_corpus_manifest_excludes_symlinked_path_components(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    real_reports = tmp_path / "real-reports"
    real_reports.mkdir()
    (real_reports / "test-quality.json").write_text(
        '{"schema_version":"entroping.test-quality-report.v1"}\n',
        encoding="utf-8",
    )
    reports.symlink_to(real_reports)

    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=_packet_with_sources(
            source_ids=("test-quality-json",),
            source_paths=("reports/test-quality.json",),
            project=tmp_path.name,
        ),
    )

    assert manifest.candidates[0].exclusion_reason == "unsafe_path"


def test_qa_brain_corpus_manifest_markdown_is_value_free(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {
            "schema_version": "entroping.test-quality-report.v1",
            "summary": {"status": "warn", "score": 80},
        },
    )
    packet = _retrieval_packet(project=tmp_path.name)
    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=packet,
    )

    markdown = render_qa_brain_corpus_manifest_markdown(manifest)

    assert "# Entroping QA Brain Corpus Manifest" in markdown
    assert "| test-quality-json | eligible | test_quality |" in markdown
    assert "score" not in markdown
    assert "Find weak-test evidence" not in markdown


def test_qa_brain_corpus_manifest_marks_all_eligible_sources_ready(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=_packet_with_sources(
            source_ids=("test-quality-json",),
            source_paths=("reports/test-quality.json",),
            project=tmp_path.name,
        ),
    )

    markdown = render_qa_brain_corpus_manifest_markdown(manifest)

    assert manifest.summary.status == "ready"
    assert manifest.next_actions == ()
    assert "No QA brain corpus-manifest actions are currently needed." in markdown


def test_qa_brain_corpus_manifest_writes_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: _retrieval_packet(project=project_root.name),
    )

    result = run_qa_brain_corpus_manifest_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "qa-brain-corpus-manifest.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == QA_BRAIN_CORPUS_MANIFEST_SCHEMA_VERSION


def test_qa_brain_corpus_manifest_writes_markdown_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: _packet_with_sources(
            source_ids=("test-quality-json",),
            source_paths=("reports/test-quality.json",),
            project=project_root.name,
        ),
    )

    result = run_qa_brain_corpus_manifest_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "qa-brain-corpus-manifest.md"
    assert "# Entroping QA Brain Corpus Manifest" in result.output_path.read_text(
        encoding="utf-8"
    )


def test_qa_brain_corpus_manifest_rejects_unsupported_output(tmp_path: Path) -> None:
    output = json.loads('"html"')

    with pytest.raises(
        QaBrainCorpusManifestError,
        match="Unsupported qa-brain-corpus-manifest output",
    ):
        run_qa_brain_corpus_manifest_report(project_root=tmp_path, output=output)


def test_qa_brain_corpus_manifest_wraps_retrieval_plan_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    def raise_retrieval_error(*, project_root: Path) -> QaBrainRetrievalPlanPacket:
        raise QaBrainRetrievalPlanError("retrieval failed")

    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        raise_retrieval_error,
    )

    with pytest.raises(QaBrainCorpusManifestError, match="retrieval failed"):
        build_qa_brain_corpus_manifest(project_root=tmp_path)


def test_qa_brain_corpus_manifest_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: _packet_with_sources(
            source_ids=("test-quality-json",),
            source_paths=("reports/test-quality.json",),
            project=project_root.name,
        ),
    )

    with pytest.raises(QaBrainCorpusManifestError, match="path must stay under"):
        run_qa_brain_corpus_manifest_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "manifest.json",
        )


@pytest.mark.parametrize(
    ("filename", "payload", "reason"),
    (
        ("invalid-utf8.json", b"\xff", "invalid_utf8"),
        ("list.json", b"[]", "non_object_json"),
        ("missing-schema.json", b"{}", "missing_schema_version"),
    ),
)
def test_qa_brain_corpus_manifest_excludes_invalid_artifact_shapes(
    tmp_path: Path,
    filename: str,
    payload: bytes,
    reason: str,
) -> None:
    path = tmp_path / "reports" / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)

    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=_packet_with_sources(
            source_ids=("candidate",),
            source_paths=(f"reports/{filename}",),
            project=tmp_path.name,
        ),
    )

    assert manifest.candidates[0].exclusion_reason == reason


@pytest.mark.parametrize(
    ("read_error", "reason"),
    (
        ("artifact exceeds 104857600 bytes", "too_large"),
        ("symlinked path component", "unsafe_path"),
        ("unreadable", "unreadable"),
    ),
)
def test_qa_brain_corpus_manifest_maps_local_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_error: str,
    reason: str,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    monkeypatch.setattr(
        corpus_manifest,
        "read_local_evidence_artifact_bytes",
        lambda path: (None, read_error),
    )

    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=_packet_with_sources(
            source_ids=("candidate",),
            source_paths=("reports/test-quality.json",),
            project=tmp_path.name,
        ),
    )

    assert manifest.candidates[0].exclusion_reason == reason


def test_qa_brain_corpus_manifest_excludes_absolute_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.json"
    _write_json(outside, {"schema_version": "entroping.outside.v1"})

    manifest = build_qa_brain_corpus_manifest_from_retrieval_plan(
        project_root=tmp_path,
        retrieval_plan=_packet_with_sources(
            source_ids=("outside",),
            source_paths=(outside.as_posix(),),
            project=tmp_path.name,
        ),
    )

    assert manifest.candidates[0].exclusion_reason == "unsafe_path"


def test_qa_brain_corpus_manifest_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import entroping.core.plan.qa_brain_corpus_manifest as corpus_manifest

    secret_id = "sk-" + "proj-" + "secretmarker0123456789"
    packet = _retrieval_packet(project=tmp_path.name).model_copy(
        update={
            "retrieval_plans": (
                _retrieval_packet(project=tmp_path.name).retrieval_plans[0].model_copy(
                    update={"source_ids": (secret_id,), "source_paths": ("reports/x.json",)}
                ),
            )
        }
    )
    monkeypatch.setattr(
        corpus_manifest,
        "build_qa_brain_retrieval_plan",
        lambda *, project_root: packet,
    )

    with pytest.raises(QaBrainCorpusManifestError, match="contains secret-like content"):
        run_qa_brain_corpus_manifest_report(project_root=tmp_path, output="json")
