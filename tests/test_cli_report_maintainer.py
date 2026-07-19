"""Maintainer and baseline CLI report command tests."""

from cli_report_test_helpers import (
    _write_complete_artifact_manifest_inputs,
    _write_text,
)
from cli_test_support import (
    CliRunner,
    Path,
    app,
    json,
    pytest,
)


def test_report_badges_writes_shields_endpoint_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "tests": [{"path": "tests/health.hurl", "rule_ids": ["latency"]}],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.effective-policy-report.v1",
                "gates": [{"id": "latency"}, {"id": "auth_required"}],
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 2, "covered_operations": 2},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [{"story_id": "CHK-001", "test_paths": ["tests/health.hurl"]}],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "badges"])

    assert result.exit_code == 0
    assert "reports/badges/policy-gates.json" in result.output
    policy_badge = json.loads((reports_dir / "badges" / "policy-gates.json").read_text())
    assert policy_badge == {
        "schemaVersion": 1,
        "label": "policy gates",
        "message": "1/2 (50%)",
        "color": "yellow",
    }


def test_report_badges_reports_missing_source_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["report", "badges"])

    assert result.exit_code == 1
    assert "Missing run report" in result.output
    assert not (tmp_path / "reports" / "badges").exists()


@pytest.mark.security
@pytest.mark.regression
def test_report_badges_rejects_outside_project_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True)
    monkeypatch.chdir(project_root)
    (reports_dir / "run-latest.json").write_text(
        json.dumps({"schema_version": "entroping.run-report.v1", "tests": []}),
        encoding="utf-8",
    )
    (reports_dir / "effective-policy.json").write_text(
        json.dumps({"schema_version": "entroping.effective-policy-report.v1", "gates": []}),
        encoding="utf-8",
    )
    (reports_dir / "openapi-audit.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.openapi-audit.v1",
                "summary": {"total_operations": 0, "covered_operations": 0},
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "traceability.json").write_text(
        json.dumps(
            {
                "schema_version": "entroping.traceability-report.v1",
                "stories": [],
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "outside-badges"

    result = CliRunner().invoke(
        app,
        ["report", "badges", "--output", str(output_dir)],
    )

    assert result.exit_code == 1
    assert "coverage badge path must stay under" in result.output
    assert not output_dir.exists()
def test_report_artifact_manifest_preserves_default_success_with_missing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        '{"schema_version":"password=manifest-secret"}\n',
    )

    result = CliRunner().invoke(app, ["report", "artifact-manifest"])

    assert result.exit_code == 0
    assert "9 missing" in result.output
    assert "manifest-secret" not in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 9
    assert "manifest-secret" not in json.dumps(payload)


def test_report_artifact_manifest_fail_on_incomplete_passes_when_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_complete_artifact_manifest_inputs(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 0
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 0
    assert payload["audit"]["verification"]["status"] == "verified"


def test_report_artifact_manifest_fail_on_incomplete_fails_after_writing_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_text(
        Path("reports") / "run-latest.json",
        '{"schema_version":"password=manifest-secret"}\n',
    )

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 1
    assert "Artifact manifest incomplete: missing=9, audit=verified." in result.output
    assert "manifest-secret" not in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 9
    assert "manifest-secret" not in json.dumps(payload)


def test_report_artifact_manifest_fail_on_incomplete_writes_custom_output_before_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = Path("reports") / "custom-artifact-manifest.json"

    result = CliRunner().invoke(
        app,
        [
            "report",
            "artifact-manifest",
            "--output",
            str(output_path),
            "--fail-on-incomplete",
        ],
    )

    assert result.exit_code == 1
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 10


def test_report_artifact_manifest_fail_on_incomplete_fails_on_broken_audit_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_complete_artifact_manifest_inputs(tmp_path)
    first = CliRunner().invoke(app, ["report", "artifact-manifest"])
    assert first.exit_code == 0
    chain_path = Path(".entroping") / "report-audit-chain.jsonl"
    chain_path.write_text(
        chain_path.read_text(encoding="utf-8").replace(
            "entroping.run-report.v1",
            "entroping.run-report.v9",
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["report", "artifact-manifest", "--fail-on-incomplete"],
    )

    assert result.exit_code == 1
    assert "Artifact manifest incomplete: missing=0, audit=broken." in result.output
    payload = json.loads(Path("reports/artifact-manifest.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_missing"] == 0
    assert payload["audit"]["verification"]["status"] == "broken"
def test_report_promote_drift_baseline_writes_active_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    candidate = reports_dir / "drift-baseline.candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema_version": "entroping.drift-baseline.v1",
                "project": "checkout-api",
                "environment": "staging",
                "tests": [
                    {
                        "path": "tests/health.hurl",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 25,
                        "rule_ids": ["global_latency"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["report", "promote-drift-baseline"])

    assert result.exit_code == 0
    assert "Promoted drift baseline: .entroping/drift-baseline.json" in result.output
    assert "1 test" in result.output
    active = json.loads((Path(".entroping") / "drift-baseline.json").read_text(encoding="utf-8"))
    assert active == json.loads(candidate.read_text(encoding="utf-8"))


def test_report_promote_drift_baseline_wraps_candidate_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    reports_dir = Path("reports")
    reports_dir.mkdir()
    (reports_dir / "drift-baseline.candidate.json").write_text("{", encoding="utf-8")

    result = CliRunner().invoke(app, ["report", "promote-drift-baseline"])

    assert result.exit_code == 1
    assert "Could not parse drift baseline candidate" in result.output
    assert not (Path(".entroping") / "drift-baseline.json").exists()
