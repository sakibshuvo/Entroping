"""Tests for local design-partner pilot cohort rollups."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entroping.core.evidence.pilot_cohort as pilot_cohort
from entroping.core.evidence.evidence_index import (
    read_local_evidence_json_artifact_bytes,
)
from entroping.core.safe_write import SafeWriteError

PILOT_COHORT_SCHEMA_VERSION = (
    pilot_cohort.PILOT_COHORT_SCHEMA_VERSION
)
PilotCohortError = (
    pilot_cohort.PilotCohortError
)
build_pilot_cohort_packet = (
    pilot_cohort.build_pilot_cohort_packet
)
run_pilot_cohort_report = (
    pilot_cohort.run_pilot_cohort_report
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pilot_outcome(
    *,
    project: str,
    status: str,
    hosted: str = "yes",
    policy: str = "unclear",
    manual_gaps: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "schema_version": "entroping.pilot-outcome.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "project": project,
        "summary": {
            "status": status,
            "sources_total": 5,
            "sources_present": 5,
            "sources_missing": 0,
            "sources_invalid": 0,
            "sources_unsafe": 0,
            "manual_input_gaps": len(manual_gaps),
            "monetization_yes": 1 if hosted == "yes" else 0,
            "monetization_no": 1 if hosted == "no" else 0,
            "monetization_unclear": 1 if hosted == "unclear" else 0,
            "actions_total": 0 if status == "ready" else 1,
            "actions_high": 0,
            "actions_medium": 1 if status == "partial" else 0,
            "actions_low": 0,
        },
        "sources": [],
        "pilot_evidence_readiness": {
            "design_partner_feedback_status": "ready",
            "pilot_metrics_status": "partial" if status == "partial" else "ready",
            "runtime_card_status": "pass",
            "evidence_cloud_status": "ready",
            "work_item_import_status": status,
        },
        "manual_input_gaps": list(manual_gaps),
        "monetization_signals": [
            {
                "id": "hosted_aggregation",
                "answer": hosted,
                "manual_reason_required": bool(manual_gaps),
            },
            {
                "id": "premium_policy_packs",
                "answer": policy,
                "manual_reason_required": bool(manual_gaps),
            },
        ],
        "actions": [],
    }


def _manifest(*paths: str) -> dict[str, object]:
    return {
        "schema_version": "entroping.pilot-cohort-manifest.v1",
        "outcomes": [
            {
                "id": f"pilot-{index}",
                "path": path,
            }
            for index, path in enumerate(paths, start=1)
        ],
    }


def test_pilot_cohort_writes_json_from_explicit_outcomes(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "pilot-a.json",
        _pilot_outcome(project="checkout-api", status="ready", hosted="yes", policy="no"),
    )
    _write_json(
        tmp_path / "reports" / "pilot-b.json",
        _pilot_outcome(
            project="support-api",
            status="partial",
            hosted="no",
            policy="unclear",
            manual_gaps=("feedback.private_note_should_not_render",),
        ),
    )
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot-a.json", "reports/pilot-b.json"))

    result = run_pilot_cohort_report(
        project_root=tmp_path,
        manifest=manifest,
        output="json",
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert result.output_path == tmp_path / "reports" / "pilot-cohort.json"
    assert payload["schema_version"] == PILOT_COHORT_SCHEMA_VERSION
    assert payload["summary"]["status"] == "partial"
    assert payload["summary"]["outcomes_present"] == 2
    assert payload["summary"]["pilots_ready"] == 1
    assert payload["summary"]["pilots_partial"] == 1
    assert payload["summary"]["manual_input_gaps_total"] == 1
    assert payload["monetization_signals"][0]["yes"] == 1
    assert payload["monetization_signals"][0]["no"] == 1
    assert payload["monetization_signals"][1]["unclear"] == 1
    assert [
        (action["priority"], action["category"], action["status"])
        for action in payload["actions"]
    ] == [
        ("medium", "collect", "manual_input_required"),
        ("medium", "review", "partial"),
        ("low", "review", "unclear"),
    ]
    assert "feedback.private_note_should_not_render" not in json.dumps(payload)


def test_pilot_cohort_writes_value_free_markdown(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "pilot-a.json",
        _pilot_outcome(
            project="checkout-api",
            status="partial",
            hosted="unclear",
            manual_gaps=("feedback.private_note_should_not_render",),
        ),
    )
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot-a.json"))

    result = run_pilot_cohort_report(
        project_root=tmp_path,
        manifest=manifest,
        output="md",
    )

    markdown = result.output_path.read_text(encoding="utf-8")
    assert result.output_path == tmp_path / "reports" / "pilot-cohort.md"
    assert "# Entroping Pilot Cohort" in markdown
    assert "hosted_aggregation" in markdown
    assert "feedback.private_note_should_not_render" not in markdown


def test_pilot_cohort_ready_outcomes_have_no_local_actions(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "pilot-a.json",
        _pilot_outcome(project="checkout-api", status="ready", hosted="yes", policy="no"),
    )
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot-a.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)
    markdown = pilot_cohort.render_pilot_cohort_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.summary.actions_total == 0
    assert "No local pilot cohort action required" in markdown


def test_pilot_cohort_unclear_monetization_keeps_cohort_partial(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "pilot-a.json",
        _pilot_outcome(project="checkout-api", status="ready", hosted="yes", policy="unclear"),
    )
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot-a.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.summary.status == "partial"
    assert packet.summary.actions_low == 1


def test_pilot_cohort_ignores_null_readiness_statuses(tmp_path: Path) -> None:
    outcome = _pilot_outcome(
        project="checkout-api",
        status="ready",
        hosted="yes",
        policy="no",
    )
    readiness = outcome["pilot_evidence_readiness"]
    assert isinstance(readiness, dict)
    readiness["evidence_cloud_status"] = None
    _write_json(tmp_path / "reports" / "pilot-a.json", outcome)
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot-a.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    by_id = {signal.id: signal for signal in packet.readiness_signals}
    assert by_id["evidence_cloud"].other == 0


def test_pilot_cohort_missing_outcomes_generate_actions(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing-pilot-outcome.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.summary.status == "insufficient"
    assert packet.summary.outcomes_missing == 1
    assert packet.summary.actions_medium == 1
    assert {action.category for action in packet.actions} == {"generate"}


def test_pilot_cohort_uses_relative_paths_for_local_missing_sources(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing-pilot-outcome.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].path == "reports/missing-pilot-outcome.json"
    assert str(tmp_path) not in json.dumps(packet.model_dump(mode="json"))


def test_pilot_cohort_marks_invalid_and_secret_sources_repairable(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "wrong.json", {"schema_version": "wrong.v1"})
    _write_json(
        tmp_path / "reports" / "secret.json",
        {
            "schema_version": "entroping.pilot-outcome.v1",
            "secret": "sk-proj-" + ("a" * 24),
        },
    )
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/wrong.json", "reports/secret.json"))

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    sources = {source.id: source for source in packet.outcomes}
    assert sources["pilot-1"].state == "invalid"
    assert sources["pilot-2"].state == "unsafe"
    assert packet.summary.status == "insufficient"
    assert packet.summary.actions_high == 1
    repair_actions = [action for action in packet.actions if action.category == "repair"]
    assert len(repair_actions) == 1
    assert repair_actions[0].outcome_ids == ("pilot-1", "pilot-2")


def test_pilot_cohort_marks_invalid_json_validation_and_directory_sources(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "invalid.json").write_text("{not json", encoding="utf-8")
    _write_json(
        reports / "incomplete.json",
        {"schema_version": "entroping.pilot-outcome.v1"},
    )
    (reports / "directory.json").mkdir()
    manifest = reports / "pilot-cohort-manifest.json"
    _write_json(
        manifest,
        _manifest(
            "reports/invalid.json",
            "reports/incomplete.json",
            "reports/directory.json",
        ),
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    sources = {source.id: source for source in packet.outcomes}
    assert sources["pilot-1"].state == "invalid"
    assert sources["pilot-1"].summary == "invalid JSON"
    assert sources["pilot-2"].state == "invalid"
    assert sources["pilot-2"].summary == "schema validation failed"
    assert sources["pilot-3"].state == "unsafe"


def test_pilot_cohort_rejects_manifest_outside_project(tmp_path: Path) -> None:
    with pytest.raises(PilotCohortError, match="manifest path must stay"):
        build_pilot_cohort_packet(
            project_root=tmp_path,
            manifest=tmp_path.parent / "pilot-cohort-manifest.json",
        )


def test_pilot_cohort_rejects_manifest_relative_traversal(tmp_path: Path) -> None:
    with pytest.raises(PilotCohortError, match="manifest path must stay"):
        build_pilot_cohort_packet(
            project_root=tmp_path,
            manifest=Path("reports") / ".." / ".." / "pilot-cohort-manifest.json",
        )


def test_pilot_cohort_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(PilotCohortError, match="Could not read pilot cohort manifest"):
        build_pilot_cohort_packet(
            project_root=tmp_path,
            manifest=tmp_path / "reports" / "pilot-cohort-manifest.json",
        )


def test_pilot_cohort_rejects_forbidden_manifest_directory(tmp_path: Path) -> None:
    with pytest.raises(PilotCohortError, match="manifest must not be read"):
        build_pilot_cohort_packet(
            project_root=tmp_path,
            manifest=Path("reports") / ".Entroping" / "pilot-cohort-manifest.json",
        )


def test_pilot_cohort_rejects_symlinked_manifest_directory(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    manifest = reports / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))
    link = tmp_path / "linked-reports"
    link.symlink_to(reports, target_is_directory=True)

    with pytest.raises(PilotCohortError, match="symlinked component"):
        build_pilot_cohort_packet(
            project_root=tmp_path,
            manifest=link / "pilot-cohort-manifest.json",
        )


def test_pilot_cohort_rejects_invalid_manifest_shape(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, {"schema_version": "wrong.v1", "outcomes": []})

    with pytest.raises(PilotCohortError, match="schema_version"):
        build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ("[]", "must be a JSON object"),
        (
            {
                "schema_version": "entroping.pilot-cohort-manifest.v1",
                "secret": "sk-proj-" + ("a" * 24),
                "outcomes": [{"path": "reports/missing.json"}],
            },
            "secret-like content",
        ),
        (
            {
                "schema_version": "entroping.pilot-cohort-manifest.v1",
                "outcomes": [],
            },
            "non-empty list",
        ),
        (
            {
                "schema_version": "entroping.pilot-cohort-manifest.v1",
                "outcomes": ["reports/missing.json"],
            },
            "entries must be objects",
        ),
        (
            {
                "schema_version": "entroping.pilot-cohort-manifest.v1",
                "outcomes": [{"id": "missing-path"}],
            },
            "entries require path",
        ),
    ],
)
def test_pilot_cohort_rejects_malformed_manifest_payloads(
    tmp_path: Path,
    payload: object,
    match: str,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    manifest.parent.mkdir(parents=True)
    if isinstance(payload, str):
        manifest.write_text(payload, encoding="utf-8")
    else:
        assert isinstance(payload, dict)
        _write_json(manifest, payload)

    with pytest.raises(PilotCohortError, match=match):
        build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)


def test_pilot_cohort_marks_outside_outcome_path_unsafe(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "entroping.pilot-cohort-manifest.v1",
            "outcomes": [{"id": "outside", "path": "../outside.json"}],
        },
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].state == "unsafe"
    assert packet.summary.actions_high == 1


def test_pilot_cohort_marks_absolute_outside_outcome_path_unsafe(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "entroping.pilot-cohort-manifest.v1",
            "outcomes": [
                {"id": "outside", "path": (tmp_path.parent / "outside.json").as_posix()}
            ],
        },
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].state == "unsafe"
    assert packet.outcomes[0].summary == "path outside project"


def test_pilot_cohort_marks_forbidden_outcome_path_unsafe(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "entroping.pilot-cohort-manifest.v1",
            "outcomes": [{"id": "forbidden", "path": "reports/.Entroping/outcome.json"}],
        },
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].state == "unsafe"
    assert packet.outcomes[0].summary == "path in forbidden directory"


def test_pilot_cohort_public_loader_classifies_unexpected_read_error_as_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome_path = tmp_path / "reports" / "pilot.json"
    _write_json(outcome_path, _pilot_outcome(project="checkout-api", status="ready"))
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/pilot.json"))
    original_reader = read_local_evidence_json_artifact_bytes

    def fail_outcome(path: Path, *, root: Path) -> tuple[bytes | None, str]:
        if path == outcome_path:
            return None, "unexpected read error"
        return original_reader(path, root=root)

    monkeypatch.setattr(
        pilot_cohort,
        "read_local_evidence_json_artifact_bytes",
        fail_outcome,
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].state == "invalid"
    assert packet.outcomes[0].summary == "unexpected read error"


def test_pilot_cohort_marks_symlinked_outcome_path_unsafe(tmp_path: Path) -> None:
    real_reports = tmp_path / "real-reports"
    _write_json(
        real_reports / "pilot-a.json",
        _pilot_outcome(project="checkout-api", status="ready", hosted="yes", policy="no"),
    )
    link = tmp_path / "reports" / "linked"
    link.parent.mkdir(parents=True)
    link.symlink_to(real_reports, target_is_directory=True)
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "entroping.pilot-cohort-manifest.v1",
            "outcomes": [{"id": "linked", "path": "reports/linked/pilot-a.json"}],
        },
    )

    packet = build_pilot_cohort_packet(project_root=tmp_path, manifest=manifest)

    assert packet.outcomes[0].state == "unsafe"
    assert packet.outcomes[0].summary == "symlinked path component"


def test_pilot_cohort_rejects_output_outside_project(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))

    with pytest.raises(PilotCohortError, match="output path must stay"):
        run_pilot_cohort_report(
            project_root=tmp_path,
            manifest=manifest,
            output="json",
            output_path=tmp_path.parent / "pilot-cohort.json",
        )


def test_pilot_cohort_rejects_output_relative_traversal(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))

    with pytest.raises(PilotCohortError, match="output path must stay"):
        run_pilot_cohort_report(
            project_root=tmp_path,
            manifest=manifest,
            output="json",
            output_path=Path("reports") / ".." / ".." / "pilot-cohort.json",
        )


def test_pilot_cohort_rejects_symlinked_output_directory(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))
    real_reports = tmp_path / "real-reports"
    real_reports.mkdir()
    link = tmp_path / "linked-reports"
    link.symlink_to(real_reports, target_is_directory=True)

    with pytest.raises(PilotCohortError, match="symlinked component"):
        run_pilot_cohort_report(
            project_root=tmp_path,
            manifest=manifest,
            output="json",
            output_path=link / "pilot-cohort.json",
        )


def test_pilot_cohort_rejects_case_variant_forbidden_output_directory(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))

    with pytest.raises(PilotCohortError, match="must not be written"):
        run_pilot_cohort_report(
            project_root=tmp_path,
            manifest=manifest,
            output="json",
            output_path=Path("reports") / ".Entroping" / "pilot-cohort.json",
        )


def test_pilot_cohort_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))
    packet = build_pilot_cohort_packet(
        project_root=tmp_path,
        manifest=manifest,
    ).model_copy(update={"project": "sk-proj-" + ("a" * 24)})
    monkeypatch.setattr(
        pilot_cohort,
        "build_pilot_cohort_packet",
        lambda **_: packet,
    )

    with pytest.raises(PilotCohortError, match="secret-like content"):
        run_pilot_cohort_report(project_root=tmp_path, manifest=manifest, output="json")


def test_pilot_cohort_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))

    def fail_write(*args: object, **kwargs: object) -> Path:
        raise SafeWriteError("blocked write")

    monkeypatch.setattr(pilot_cohort, "safe_write_text", fail_write)

    with pytest.raises(PilotCohortError, match="blocked write"):
        run_pilot_cohort_report(project_root=tmp_path, manifest=manifest, output="json")


def test_pilot_cohort_rejects_unsupported_output(tmp_path: Path) -> None:
    manifest = tmp_path / "reports" / "pilot-cohort-manifest.json"
    _write_json(manifest, _manifest("reports/missing.json"))

    with pytest.raises(PilotCohortError, match="Unsupported"):
        run_pilot_cohort_report(
            project_root=tmp_path,
            manifest=manifest,
            output="csv",  # type: ignore[arg-type]
        )
