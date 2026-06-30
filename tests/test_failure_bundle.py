"""Tests for sanitized failure bundle generation."""

import json
from pathlib import Path

import pytest

import entroping.core.failure_bundle as failure_bundle
import entroping.hurl_source as hurl_source
from entroping.core.failure_bundle import FailureBundleError, create_failure_bundle
from entroping.core.report_writer import write_json_report
from entroping.core.safe_write import SafeWriteError
from entroping.models.report import RunReport, RunReportSummary, RunTestReport


def _run_report(*, failed: int = 1, path: str = "tests/health.hurl") -> RunReport:
    status = "failed" if failed else "passed"
    return RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(
            total=1,
            passed=0 if failed else 1,
            failed=failed,
            exit_code=failed,
        ),
        tests=(
            RunTestReport(
                path=path,
                execution_path=".entroping/run-1/health.hurl",
                status=status,
                exit_code=failed,
                duration_ms=123,
                rule_ids=("global_latency",),
                stdout="Authorization: Bearer failure-secret\n",
                stderr="token=failure-secret\nassert failed\n" if failed else "",
            ),
        ),
    )


def _write_latest(project_root: Path, report: RunReport) -> Path:
    latest = project_root / ".entroping" / "latest-run.json"
    write_json_report(report, latest)
    return latest


def test_create_failure_bundle_requires_latest_run(tmp_path: Path) -> None:
    with pytest.raises(FailureBundleError, match="No latest run found"):
        create_failure_bundle(project_root=tmp_path)

    assert not (tmp_path / "reports" / "failure-bundle").exists()


def test_create_failure_bundle_rejects_malformed_latest_run(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(FailureBundleError, match="Could not load latest run report"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_unsupported_latest_run_schema(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v999",
                "project": "checkout-api",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FailureBundleError, match="Could not load latest run report") as exc_info:
        create_failure_bundle(project_root=tmp_path)
    assert "must use schema_version entroping.run-report.v1" in str(exc_info.value)
    assert "entroping.run-report.v999" not in str(exc_info.value)


def test_create_failure_bundle_rejects_versioned_latest_run_missing_required_field(
    tmp_path: Path,
) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.parent.mkdir()
    latest.write_text(
        json.dumps(
            {
                "schema_version": "entroping.run-report.v1",
                "project": "private-runtime-value",
                "environment": "default",
                "generated_at": "2026-05-30T00:00:00+00:00",
                "summary": {"passed": 0, "failed": 1, "exit_code": 1},
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FailureBundleError, match="Could not load latest run report") as exc_info:
        create_failure_bundle(project_root=tmp_path)
    assert "required field summary.total" in str(exc_info.value)
    assert "private-runtime-value" not in str(exc_info.value)


def test_create_failure_bundle_requires_failed_run(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report(failed=0))

    with pytest.raises(FailureBundleError, match="no failures"):
        create_failure_bundle(project_root=tmp_path)

    assert not (tmp_path / "reports" / "failure-bundle").exists()


def test_create_failure_bundle_writes_manifest_and_sanitized_artifacts(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke,checkout",
                "# entroping: story_id=CHK-001",
                "",
                "GET {{base_url}}/health?token=failure-secret",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_text("<testsuite>token=failure-secret</testsuite>\n")
    (reports_dir / "run-latest.html").write_text("<html>Bearer failure-secret</html>\n")
    (reports_dir / "effective-policy.md").write_text("# Policy\n\nNo secrets here.\n")
    (reports_dir / "redaction-review.md").write_text("# Redaction\n\nCounts only.\n")

    result = create_failure_bundle(project_root=tmp_path)

    assert result.output_dir == tmp_path / "reports" / "failure-bundle"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "entroping.failure-bundle.v1"
    assert manifest["project"] == "checkout-api"
    assert manifest["summary"] == {"total": 1, "passed": 0, "failed": 1, "exit_code": 1}
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert artifact_paths == {
        "bug.md",
        "effective-policy.md",
        "hurl-metadata.json",
        "junit.xml",
        "redaction-review.md",
        "run-latest.html",
        "run-latest.json",
    }
    assert all(artifact["sha256"] for artifact in manifest["artifacts"])
    assert manifest["failed_tests"] == [
        {
            "path": "tests/health.hurl",
            "status": "failed",
            "rule_ids": ["global_latency"],
            "tags": ["checkout", "smoke"],
            "metadata": {"story_id": "CHK-001"},
            "exchanges": [{"method": "GET", "path": "/health"}],
        }
    ]
    bundle_text = "\n".join(
        path.read_text(encoding="utf-8") for path in result.output_dir.iterdir()
    )
    assert "failure-secret" not in bundle_text
    assert "Authorization: [REDACTED]" in (result.output_dir / "run-latest.json").read_text(
        encoding="utf-8"
    )
    assert "token=[REDACTED]" in (result.output_dir / "junit.xml").read_text(encoding="utf-8")


def test_create_failure_bundle_redacts_secret_like_hurl_metadata_values(
    tmp_path: Path,
) -> None:
    _write_latest(tmp_path, _run_report(path="tests/secret-metadata.hurl"))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    token = "sk-proj-" + ("a" * 24)
    (tests_dir / "secret-metadata.hurl").write_text(
        "\n".join(
            [
                "# entroping: tags=smoke",
                f"# entroping: owner={token}",
                "# entroping: story_id=CHK-001",
                "",
                "GET {{base_url}}/health",
                "HTTP 200",
            ],
        ),
        encoding="utf-8",
    )

    result = create_failure_bundle(project_root=tmp_path)

    metadata_path = result.output_dir / "hurl-metadata.json"
    raw_metadata = metadata_path.read_text(encoding="utf-8")
    payload = json.loads(raw_metadata)
    assert token not in raw_metadata
    assert payload["tests"][0]["metadata"] == {
        "owner": "[REDACTED]",
        "story_id": "CHK-001",
    }


def test_create_failure_bundle_rejects_oversized_failed_hurl_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hurl_source, "HURL_SOURCE_MAX_BYTES", 32)
    _write_latest(tmp_path, _run_report(path="tests/oversized.hurl"))
    source = tmp_path / "tests" / "oversized.hurl"
    source.parent.mkdir()
    source.write_bytes(b"# entroping: tags=smoke\n" + (b"x" * 32))

    with pytest.raises(FailureBundleError, match=r"Hurl source .* exceeds 32 bytes"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_oversized_optional_text_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(failure_bundle, "_MAX_FAILURE_BUNDLE_ARTIFACT_BYTES", 32, raising=False)
    _write_latest(tmp_path, _run_report())
    source = tmp_path / "tests" / "health.hurl"
    source.parent.mkdir()
    source.write_text("GET {{base_url}}/health\nHTTP 200\n", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "junit.xml").write_bytes(b"x" * 33)

    with pytest.raises(FailureBundleError, match=r"junit artifact .* exceeds 32 bytes"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_writes_fence_safe_bug_report(tmp_path: Path) -> None:
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/fence.hurl",
                execution_path=".entroping/run-1/fence.hurl",
                status="failed",
                exit_code=1,
                duration_ms=123,
                rule_ids=("global_latency",),
                stdout="",
                stderr="before\n````\ninjected\n````\nafter\n",
            ),
        ),
    )
    _write_latest(tmp_path, report)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "fence.hurl").write_text("GET {{base_url}}/fence\nHTTP 200\n")

    result = create_failure_bundle(project_root=tmp_path)

    bug = (result.output_dir / "bug.md").read_text(encoding="utf-8")
    output_section = bug.split("## Output\n\n", maxsplit=1)[1]
    assert output_section.startswith("`````text\n")
    assert output_section.endswith("\n`````\n")
    assert "before\n````\ninjected\n````\nafter" in output_section


def test_create_failure_bundle_omits_passing_tests_and_allows_missing_hurl_source(
    tmp_path: Path,
) -> None:
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=2, passed=1, failed=1, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/passing.hurl",
                execution_path=".entroping/run-1/passing.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="",
                stderr="",
            ),
            RunTestReport(
                path="tests/missing.hurl",
                execution_path=".entroping/run-1/missing.hurl",
                status="failed",
                exit_code=1,
                duration_ms=11,
                rule_ids=("global_latency",),
                stdout="",
                stderr="assert failed",
            ),
        ),
    )
    _write_latest(tmp_path, report)

    result = create_failure_bundle(project_root=tmp_path)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["failed_tests"] == [
        {
            "path": "tests/missing.hurl",
            "status": "failed",
            "rule_ids": ["global_latency"],
            "tags": [],
            "metadata": {},
            "exchanges": [],
        }
    ]


def test_create_failure_bundle_includes_non_passed_zero_exit_metadata(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for name in ("passing", "blocked", "timeout", "error"):
        (tests_dir / f"{name}.hurl").write_text(
            "\n".join(
                [
                    f"# entroping: story_id={name.upper()}-001",
                    "# entroping: owner=sk-proj-" + ("a" * 24),
                    "",
                    f"GET {{{{base_url}}}}/{name}",
                    "HTTP 200",
                ]
            ),
            encoding="utf-8",
        )
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=4, passed=1, failed=3, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/passing.hurl",
                execution_path=".entroping/run-1/passing.hurl",
                status="passed",
                exit_code=0,
                duration_ms=10,
                rule_ids=(),
                stdout="",
                stderr="",
            ),
            RunTestReport(
                path="tests/blocked.hurl",
                execution_path=".entroping/run-1/blocked.hurl",
                status="blocked",
                exit_code=0,
                duration_ms=11,
                rule_ids=("protected_environment",),
                stdout="Authorization: Bearer failure-secret\n",
                stderr="",
            ),
            RunTestReport(
                path="tests/timeout.hurl",
                execution_path=".entroping/run-1/timeout.hurl",
                status="timeout",
                exit_code=0,
                duration_ms=12,
                rule_ids=("runtime_timeout",),
                stdout="",
                stderr="token=failure-secret\n",
            ),
            RunTestReport(
                path="tests/error.hurl",
                execution_path=".entroping/run-1/error.hurl",
                status="error",
                exit_code=0,
                duration_ms=13,
                rule_ids=("report_error",),
                stdout="",
                stderr="",
            ),
        ),
    )
    _write_latest(tmp_path, report)

    result = create_failure_bundle(project_root=tmp_path)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    failed_tests = manifest["failed_tests"]
    assert [test["path"] for test in failed_tests] == [
        "tests/blocked.hurl",
        "tests/timeout.hurl",
        "tests/error.hurl",
    ]
    assert [test["status"] for test in failed_tests] == ["blocked", "timeout", "error"]
    assert [test["rule_ids"] for test in failed_tests] == [
        ["protected_environment"],
        ["runtime_timeout"],
        ["report_error"],
    ]
    assert all(test["metadata"]["owner"] == "[REDACTED]" for test in failed_tests)
    bundle_text = "\n".join(
        path.read_text(encoding="utf-8") for path in result.output_dir.iterdir()
    )
    assert "failure-secret" not in bundle_text
    assert "sk-proj-" not in bundle_text


def test_create_failure_bundle_allows_non_passed_tests_when_summary_failed_is_zero(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "blocked.hurl").write_text(
        "GET {{base_url}}/blocked\nHTTP 200\n",
        encoding="utf-8",
    )
    report = RunReport(
        project="checkout-api",
        environment="local",
        generated_at="2026-06-04T00:00:00+00:00",
        summary=RunReportSummary(total=1, passed=0, failed=0, exit_code=1),
        tests=(
            RunTestReport(
                path="tests/blocked.hurl",
                execution_path=".entroping/run-1/blocked.hurl",
                status="blocked",
                exit_code=0,
                duration_ms=11,
                rule_ids=("protected_environment",),
                stdout="",
                stderr="",
            ),
        ),
    )
    _write_latest(tmp_path, report)

    result = create_failure_bundle(project_root=tmp_path)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["failed_tests"] == [
        {
            "path": "tests/blocked.hurl",
            "status": "blocked",
            "rule_ids": ["protected_environment"],
            "tags": [],
            "metadata": {},
            "exchanges": [{"method": "GET", "path": "/blocked"}],
        }
    ]


def test_create_failure_bundle_rejects_unsafe_report_artifact_symlink(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "health.hurl").write_text("GET {{base_url}}/health\nHTTP 200\n")
    outside = tmp_path / "outside.xml"
    outside.write_text("<testsuite />\n", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "junit.xml").symlink_to(outside)

    with pytest.raises(FailureBundleError, match="unsafe artifact"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_unsafe_hurl_test_path(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report(path="../escape.hurl"))

    with pytest.raises(FailureBundleError, match="must stay inside the project"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_non_file_hurl_test_path(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())
    (tmp_path / "tests" / "health.hurl").mkdir(parents=True)

    with pytest.raises(FailureBundleError, match="is not a file"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_non_hurl_failed_test_path(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report(path="tests/not-hurl.txt"))
    source = tmp_path / "tests" / "not-hurl.txt"
    source.parent.mkdir()
    source.write_text("# entroping: tags=smoke\nGET /health\nHTTP 200\n", encoding="utf-8")

    with pytest.raises(FailureBundleError, match=r"Expected a \.hurl file"):
        create_failure_bundle(project_root=tmp_path)


@pytest.mark.parametrize(
    ("output_dir", "message"),
    [
        (Path("../bundle"), "must stay inside the project"),
        (Path(".entroping/failure-bundle"), "must not be written into"),
        (Path("envs/failure-bundle"), "must not be written into"),
    ],
)
def test_create_failure_bundle_rejects_unsafe_output_directory(
    tmp_path: Path,
    output_dir: Path,
    message: str,
) -> None:
    _write_latest(tmp_path, _run_report())

    with pytest.raises(FailureBundleError, match=message):
        create_failure_bundle(project_root=tmp_path, output_dir=output_dir)


def test_create_failure_bundle_rejects_absolute_output_outside_root(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())

    with pytest.raises(FailureBundleError, match="must stay inside the project"):
        create_failure_bundle(project_root=tmp_path, output_dir=tmp_path.parent / "outside-bundle")


def test_create_failure_bundle_rejects_parent_traversal_latest_path(tmp_path: Path) -> None:
    with pytest.raises(FailureBundleError, match="unsafe artifact path must stay inside"):
        create_failure_bundle(project_root=tmp_path, latest_run_path=Path("../latest-run.json"))


def test_create_failure_bundle_rejects_output_path_that_is_file(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())
    output = tmp_path / "reports" / "failure-bundle"
    output.parent.mkdir()
    output.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(FailureBundleError, match="is not a directory"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_wraps_output_directory_creation_errors(tmp_path: Path) -> None:
    _write_latest(tmp_path, _run_report())
    (tmp_path / "reports").write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(FailureBundleError, match="Could not create failure bundle directory"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_latest_run_that_is_directory(tmp_path: Path) -> None:
    latest = tmp_path / ".entroping" / "latest-run.json"
    latest.mkdir(parents=True)

    with pytest.raises(FailureBundleError, match="latest run artifact is not a file"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_optional_artifact_that_is_directory(
    tmp_path: Path,
) -> None:
    _write_latest(tmp_path, _run_report())
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "health.hurl").write_text("GET {{base_url}}/health\nHTTP 200\n")
    (tmp_path / "reports" / "junit.xml").mkdir(parents=True)

    with pytest.raises(FailureBundleError, match="unsafe artifact is not a file"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_rejects_local_env_latest_path(tmp_path: Path) -> None:
    env_file = tmp_path / "envs" / "local.env"
    env_file.parent.mkdir()
    env_file.write_text("token=env-secret\n", encoding="utf-8")

    with pytest.raises(FailureBundleError, match="refuses local env files"):
        create_failure_bundle(project_root=tmp_path, latest_run_path=Path("envs/local.env"))


def test_create_failure_bundle_rejects_optional_local_state_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_latest(tmp_path, _run_report())
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "health.hurl").write_text("GET {{base_url}}/health\nHTTP 200\n")
    (tmp_path / ".entroping" / "state.db").write_text("raw local state\n", encoding="utf-8")
    monkeypatch.setattr(
        failure_bundle,
        "_OPTIONAL_TEXT_ARTIFACTS",
        ((Path(".entroping") / "state.db", "traffic_state", "state.db"),),
    )

    with pytest.raises(FailureBundleError, match="refuses local state files"):
        create_failure_bundle(project_root=tmp_path)


def test_create_failure_bundle_wraps_safe_write_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_latest(tmp_path, _run_report())

    def fail_safe_write(
        path: Path,
        content: str,
        *,
        artifact: str,
        root: Path | None = None,
    ) -> Path:
        _ = path, content, artifact, root
        raise SafeWriteError("disk full")

    monkeypatch.setattr(failure_bundle, "safe_write_text", fail_safe_write)

    with pytest.raises(FailureBundleError, match="disk full"):
        create_failure_bundle(project_root=tmp_path)


def test_write_bundle_text_rejects_non_local_artifact_path(tmp_path: Path) -> None:
    with pytest.raises(FailureBundleError, match="must be relative and local"):
        failure_bundle._write_bundle_text(
            root=tmp_path,
            bundle_dir=tmp_path / "reports" / "failure-bundle",
            relative_path=Path("../escape.txt"),
            content="x\n",
            kind="test",
            source_path="generated",
            schema_version="test.v1",
        )


def test_schema_version_and_display_path_fallbacks(tmp_path: Path) -> None:
    assert failure_bundle._schema_version_for_optional_artifact("unknown.txt") == "text"
    assert failure_bundle._display_path(tmp_path.parent / "outside.txt", tmp_path).endswith(
        "outside.txt"
    )
