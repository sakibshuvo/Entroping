import json
from pathlib import Path

import pytest

from entroping.core.plan import mutation_candidate_coverage as coverage


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mutation_readiness_payload() -> dict[str, object]:
    return {
        "schema_version": "entroping.mutation-readiness.v1",
        "summary": {
            "status": "partial",
            "candidate_categories_total": 2,
            "seeded_fuzz_candidates_total": 1,
            "category_coverage": [
                {
                    "category": "auth",
                    "label": "Auth/security mutation",
                    "candidate_tests": 2,
                    "seeded_tests": 1,
                    "missing_seed_tests": 1,
                },
                {
                    "category": "schema",
                    "label": "Schema mutation",
                    "candidate_tests": 1,
                    "seeded_tests": 1,
                    "missing_seed_tests": 0,
                },
            ],
        },
        "sources": [
            {
                "kind": "generated_hurl",
                "path": "tests/generated/auth.hurl",
                "state": "present",
                "summary": "value-free source summary",
            },
            {
                "kind": "test_quality_report",
                "path": "reports/test-quality.json",
                "state": "missing",
                "summary": "optional report missing",
            },
        ],
        "candidates": [
            {
                "category": "auth",
                "label": "Auth/security mutation",
                "tests": 2,
                "source_paths": ["tests/generated/auth.hurl"],
                "next_action": "Review auth candidate",
            },
            {
                "category": "schema",
                "label": "Schema mutation",
                "tests": 1,
                "source_paths": ["tests/generated/schema.hurl"],
                "next_action": "Review schema candidate",
            },
        ],
        "seeded_fuzz_candidates": [
            {
                "id": "seeded-fuzz:schema:tests/generated/schema.hurl",
                "category": "schema",
                "source_path": "tests/generated/schema.hurl",
                "assertions": 2,
                "seed_metadata": True,
                "next_action": "Review seeded candidate",
            },
        ],
    }


def _ready_mutation_readiness_payload() -> dict[str, object]:
    return {
        **_mutation_readiness_payload(),
        "summary": {
            "status": "ready",
            "candidate_categories_total": 1,
            "seeded_fuzz_candidates_total": 1,
            "category_coverage": [
                {
                    "category": "auth",
                    "label": "Auth/security mutation",
                    "candidate_tests": 1,
                    "seeded_tests": 1,
                    "missing_seed_tests": 0,
                }
            ],
        },
        "sources": [
            {
                "kind": "generated_hurl",
                "path": "tests/generated/auth.hurl",
                "state": "present",
                "summary": "value-free source summary",
            }
        ],
        "candidates": [
            {
                "category": "auth",
                "label": "Auth/security mutation",
                "tests": 1,
                "source_paths": ["tests/generated/auth.hurl"],
                "next_action": "Review auth candidate",
            }
        ],
        "seeded_fuzz_candidates": [
            {
                "id": "seeded-fuzz:auth:tests/generated/auth.hurl",
                "category": "auth",
                "source_path": "tests/generated/auth.hurl",
                "assertions": 2,
                "seed_metadata": True,
                "next_action": "Review seeded candidate",
            }
        ],
    }


def test_mutation_candidate_coverage_summarizes_existing_manifests(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "reports" / "mutation-readiness.json", _mutation_readiness_payload())
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1", "summary": {"score": 90}},
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)
    payload = packet.model_dump(mode="json")
    rendered = json.dumps(payload, sort_keys=True)

    assert packet.schema_version == coverage.MUTATION_CANDIDATE_COVERAGE_SCHEMA_VERSION
    assert packet.summary.status == "partial"
    assert packet.summary.manifests_total == 3
    assert packet.summary.manifests_present == 2
    assert packet.summary.manifests_missing == 1
    assert packet.summary.candidate_tests_total == 3
    assert packet.summary.seeded_tests_total == 2
    assert packet.summary.missing_seed_tests_total == 1
    assert packet.summary.source_kinds_total == 2
    assert packet.summary.source_kinds_present == 1
    assert packet.summary.source_kinds_missing == 1
    assert packet.categories[0].category == "auth"
    assert packet.categories[0].state == "partial"
    assert packet.categories[0].missing_seed_tests == 1
    assert packet.categories[0].source_paths == ("tests/generated/auth.hurl",)
    assert packet.categories[1].category == "schema"
    assert packet.categories[1].state == "seeded"
    assert packet.manifests[2].id == "test-pyramid-json"
    assert packet.manifests[2].state == "missing"
    assert "tests/generated/auth.hurl" in rendered
    assert "127.0.0.1" not in rendered
    assert "Review auth candidate" not in rendered
    assert "score" not in rendered


def test_mutation_candidate_coverage_missing_required_manifest_is_insufficient(
    tmp_path: Path,
) -> None:
    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.summary.manifests_missing == 3
    assert packet.summary.candidate_tests_total == 0
    assert packet.categories == ()
    assert packet.next_actions[0].manifest_ids == ("mutation-readiness-json",)
    markdown = coverage.render_mutation_candidate_coverage_markdown(packet)
    assert "# Entroping Mutation Candidate Coverage" in markdown
    assert "mutation-readiness-json" in markdown
    assert str(tmp_path) not in markdown


def test_mutation_candidate_coverage_ready_when_manifests_and_seeds_present(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "mutation-readiness.json",
        _ready_mutation_readiness_payload(),
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )
    _write_json(
        tmp_path / "reports" / "test-pyramid.json",
        {"schema_version": "entroping.test-pyramid-report.v1"},
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)
    markdown = coverage.render_mutation_candidate_coverage_markdown(packet)

    assert packet.summary.status == "ready"
    assert packet.next_actions == ()
    assert "No mutation candidate coverage actions are currently needed." in markdown


def test_mutation_candidate_coverage_partial_for_missing_optional_manifest_only(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "mutation-readiness.json",
        _ready_mutation_readiness_payload(),
    )
    _write_json(
        tmp_path / "reports" / "test-quality.json",
        {"schema_version": "entroping.test-quality-report.v1"},
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.summary.status == "partial"
    assert packet.summary.missing_seed_tests_total == 0
    assert packet.summary.source_kinds_missing == 0


def test_mutation_candidate_coverage_excludes_unsafe_and_invalid_manifests(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    outside = tmp_path.parent / "mutation-readiness.json"
    _write_json(outside, _mutation_readiness_payload())
    (reports / "mutation-readiness.json").symlink_to(outside)
    (reports / "test-quality.json").write_text("{not-json\n", encoding="utf-8")
    _write_json(
        reports / "test-pyramid.json",
        {
            "schema_version": "entroping.test-pyramid-report.v1",
            "sample": "sk-proj-secret1234567890",
        },
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)
    manifests = {manifest.id: manifest for manifest in packet.manifests}

    assert packet.summary.status == "insufficient"
    assert manifests["mutation-readiness-json"].state == "unsafe"
    assert manifests["test-quality-json"].state == "invalid"
    assert manifests["test-pyramid-json"].state == "unsafe"


def test_mutation_candidate_coverage_excludes_symlinked_manifest_directory(
    tmp_path: Path,
) -> None:
    real_reports = tmp_path / "real-reports"
    real_reports.mkdir()
    _write_json(real_reports / "mutation-readiness.json", _ready_mutation_readiness_payload())
    (tmp_path / "reports").symlink_to(real_reports)

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.manifests[0].state == "unsafe"


@pytest.mark.parametrize(
    ("payload", "state"),
    (
        (b"\xff", "invalid"),
        (b"[]", "invalid"),
        (b"{}", "invalid"),
        (b'{"schema_version":"wrong.v1"}', "invalid"),
        (
            b'{"schema_version":"entroping.mutation-readiness.v1","summary":[]}',
            "invalid",
        ),
    ),
)
def test_mutation_candidate_coverage_rejects_bad_required_manifest_shapes(
    tmp_path: Path,
    payload: bytes,
    state: str,
) -> None:
    path = tmp_path / "reports" / "mutation-readiness.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.manifests[0].state == state
    assert packet.summary.status == "insufficient"


@pytest.mark.parametrize(
    ("read_error", "state"),
    (
        ("symlinked path component", "unsafe"),
        ("unreadable", "invalid"),
    ),
)
def test_mutation_candidate_coverage_maps_local_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_error: str,
    state: str,
) -> None:

    _write_json(
        tmp_path / "reports" / "mutation-readiness.json",
        _ready_mutation_readiness_payload(),
    )
    monkeypatch.setattr(
        coverage,
        "read_local_evidence_artifact_bytes",
        lambda path: (None, read_error),
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.manifests[0].state == state


def test_mutation_candidate_coverage_excludes_absolute_manifest_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    outside = tmp_path.parent / "mutation-readiness.json"
    _write_json(outside, _ready_mutation_readiness_payload())
    monkeypatch.setattr(
        coverage,
        "_MANIFEST_DEFINITIONS",
        (
            (
                "mutation-readiness-json",
                outside,
                "entroping.mutation-readiness.v1",
                True,
            ),
        ),
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.manifests[0].state == "unsafe"


def test_mutation_candidate_coverage_tracks_zero_candidate_and_unsafe_source_state(
    tmp_path: Path,
) -> None:
    payload = {
        **_ready_mutation_readiness_payload(),
        "summary": {
            "category_coverage": [
                {
                    "category": "latency",
                    "label": "Latency boundary mutation",
                    "candidate_tests": 0,
                    "seeded_tests": 1,
                    "missing_seed_tests": 0,
                }
            ],
        },
        "sources": [
            {
                "kind": "generated_hurl",
                "path": "tests/generated/latency.hurl",
                "state": "unsafe",
                "summary": "unsafe source summary",
            },
            {
                "kind": "test_quality_report",
                "path": "reports/test-quality.json",
                "state": "invalid",
                "summary": "invalid source summary",
            }
        ],
    }
    _write_json(tmp_path / "reports" / "mutation-readiness.json", payload)

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.categories[0].state == "missing"
    assert packet.source_kinds[0].unsafe == 1
    assert packet.source_kinds[1].invalid == 1


def test_mutation_candidate_coverage_writes_json_report(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "mutation-readiness.json", _mutation_readiness_payload())

    result = coverage.run_mutation_candidate_coverage_report(project_root=tmp_path, output="json")

    assert result.output_path == tmp_path / "reports" / "mutation-candidate-coverage.json"
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == coverage.MUTATION_CANDIDATE_COVERAGE_SCHEMA_VERSION


def test_mutation_candidate_coverage_writes_markdown_report(tmp_path: Path) -> None:
    _write_json(tmp_path / "reports" / "mutation-readiness.json", _mutation_readiness_payload())

    result = coverage.run_mutation_candidate_coverage_report(project_root=tmp_path, output="md")

    assert result.output_path == tmp_path / "reports" / "mutation-candidate-coverage.md"
    assert "# Entroping Mutation Candidate Coverage" in result.output_path.read_text(
        encoding="utf-8"
    )


def test_mutation_candidate_coverage_rejects_unsupported_output(tmp_path: Path) -> None:
    output = json.loads('"html"')

    with pytest.raises(
        coverage.MutationCandidateCoverageError,
        match="Unsupported mutation-candidate-coverage output",
    ):
        coverage.run_mutation_candidate_coverage_report(project_root=tmp_path, output=output)


def test_mutation_candidate_coverage_wraps_safe_write_errors(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reports" / "mutation-readiness.json",
        _ready_mutation_readiness_payload(),
    )

    with pytest.raises(coverage.MutationCandidateCoverageError, match="path must stay under"):
        coverage.run_mutation_candidate_coverage_report(
            project_root=tmp_path,
            output="json",
            output_path=tmp_path.parent / "mutation-candidate-coverage.json",
        )


def test_mutation_candidate_coverage_rejects_secret_like_rendered_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    monkeypatch.setattr(
        coverage,
        "contains_unredacted_evidence_secret",
        lambda value: True,
    )

    with pytest.raises(
        coverage.MutationCandidateCoverageError,
        match="contains secret-like content",
    ):
        coverage.run_mutation_candidate_coverage_report(project_root=tmp_path, output="json")


def test_mutation_candidate_coverage_excludes_secret_like_manifest_content(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "reports" / "mutation-readiness.json",
        {
            **_mutation_readiness_payload(),
            "summary": {
                "category_coverage": [
                    {
                        "category": "sk-proj-" + ("a" * 32),
                        "label": "Secret category",
                        "candidate_tests": 1,
                        "seeded_tests": 0,
                        "missing_seed_tests": 1,
                    }
                ]
            },
        },
    )

    packet = coverage.build_mutation_candidate_coverage(project_root=tmp_path)

    assert packet.summary.status == "insufficient"
    assert packet.manifests[0].state == "unsafe"
    assert packet.categories == ()
