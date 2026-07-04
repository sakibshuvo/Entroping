from pathlib import Path

from entroping.core.first_run_checklist import run_first_run_checklist


def test_run_first_run_checklist_reports_missing_and_optional_delta(tmp_path: Path) -> None:
    result = run_first_run_checklist(project_root=tmp_path)

    states = {item.key: item.state for item in result.items}
    assert states["hurl-tests"] == "missing"
    assert states["run-latest-json"] == "missing"
    assert states["run-latest-html"] == "missing"
    assert states["run-junit"] == "missing"
    assert states["drift-baseline-candidate"] == "missing"
    assert states["delta-output"] == "optional-missing"
    assert not result.has_errors


def test_run_first_run_checklist_reports_all_artifacts_present(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "GET https://example.internal/health\nHTTP 200\n",
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "run-latest.json").write_text("{}", encoding="utf-8")
    (reports_dir / "run-latest.html").write_text("{}", encoding="utf-8")
    (reports_dir / "junit.xml").write_text("<testsuite></testsuite>", encoding="utf-8")
    (reports_dir / "drift-baseline.candidate.json").write_text("{}", encoding="utf-8")
    (reports_dir / "delta.json").write_text("{}", encoding="utf-8")

    result = run_first_run_checklist(project_root=tmp_path)

    assert not result.has_errors
    states = {item.key: item.state for item in result.items}
    assert states["hurl-tests"] == "present"
    assert states["run-latest-json"] == "present"
    assert states["run-latest-html"] == "present"
    assert states["run-junit"] == "present"
    assert states["drift-baseline-candidate"] == "present"
    assert states["delta-output"] == "present"


def test_run_first_run_checklist_detects_named_delta_artifact(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "custom-delta-report.json").write_text("{}", encoding="utf-8")

    result = run_first_run_checklist(project_root=tmp_path)

    delta_item = next(item for item in result.items if item.key == "delta-output")
    assert delta_item.state == "present"
    assert delta_item.paths == (reports_dir / "custom-delta-report.json",)


def test_run_first_run_checklist_marks_hurl_discovery_error_state(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "bad.hurl").write_text(
        "# entroping: tags=\nGET https://example.internal/health\nHTTP 200\n",
        encoding="utf-8",
    )

    result = run_first_run_checklist(project_root=tmp_path)

    assert result.has_errors
    error_item = next(item for item in result.items if item.key == "hurl-tests")
    assert error_item.state == "error"
    assert "Could not discover Hurl tests" in error_item.hints[0]
