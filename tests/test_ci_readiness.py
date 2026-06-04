"""CI-readiness collector tests."""

from pathlib import Path

from entroping.core import ci_readiness
from entroping.core.ci_readiness import collect_ci_readiness
from entroping.models.qanstitution import AgentConfig, Qanstitution


def _law_with_agents() -> Qanstitution:
    return Qanstitution(
        project="checkout-api",
        gates=[],
        agents={
            "builder": AgentConfig(
                source="agents/builder.md",
                model="openai/builder-model",
                api_key_env="ENTROPING_BUILDER_KEY",
            )
        },
    )


def _minimal_law() -> Qanstitution:
    return Qanstitution(project="checkout-api", gates=[])


def test_collect_ci_readiness_requires_valid_qanstitution_and_default_tests(
    tmp_path: Path,
) -> None:
    report = collect_ci_readiness(
        project_root=tmp_path,
        hurl_available=False,
        law=None,
        environ={},
    )

    checks = {check.id: check for check in report.checks}
    assert report.status == "error"
    assert report.message == "CI readiness invalid"
    assert checks["qanstitution_loaded"].status == "error"
    assert checks["hurl_available"].status == "error"
    assert checks["env_variables"].status == "error"
    assert "Hurl discovery root does not exist" in checks["env_variables"].message
    assert checks["provider_free_run"].message.endswith("agent API keys")


def test_collect_ci_readiness_reports_warning_when_suite_manifests_are_absent(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "health.hurl").write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )

    report = collect_ci_readiness(
        project_root=tmp_path,
        hurl_available=True,
        law=_law_with_agents(),
        environ={},
    )

    checks = {check.id: check for check in report.checks}
    assert report.status == "warn"
    assert report.message == "CI readiness valid"
    assert checks["suite_manifests"].status == "warn"
    assert "No suite manifests found" in checks["suite_manifests"].message
    assert "1 configured agent roles ignored" in checks["provider_free_run"].message


def test_collect_ci_readiness_reports_suite_and_env_misconfigurations(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "checkout.hurl").write_text(
        "GET {{base_url}}/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tests_dir / "empty").mkdir()
    suites_dir = tmp_path / "suites"
    suites_dir.mkdir()
    (suites_dir / "bad.yaml").write_text("- not a mapping\n", encoding="utf-8")
    (suites_dir / "empty.yaml").write_text(
        "version: entroping.suite.v1\nname: empty\npaths:\n  - tests/empty\n",
        encoding="utf-8",
    )
    (suites_dir / "missing-env.yaml").write_text(
        """
version: entroping.suite.v1
name: missing-env
env: ci
paths:
  - tests/*.hurl
""".lstrip(),
        encoding="utf-8",
    )

    report = collect_ci_readiness(
        project_root=tmp_path,
        hurl_available=True,
        law=_minimal_law(),
        environ={"HURL_VARIABLE_": "bad"},
    )

    checks = {check.id: check for check in report.checks}
    assert report.status == "error"
    assert checks["suite_manifests"].status == "error"
    assert checks["suite_manifests"].suites == ["bad", "empty", "missing-env"]
    assert "Run suite manifest must contain a YAML mapping" in checks["suite_manifests"].message
    assert "No Hurl tests matched suite 'empty'" in checks["suite_manifests"].message
    assert checks["env_variables"].status == "error"
    assert "Environment file not found" in checks["env_variables"].message
    assert "Invalid Hurl environment variable name" in checks["env_variables"].message
    assert checks["env_variables"].required_env_names == ["base_url"]


def test_collect_ci_readiness_reports_non_directory_suites_path(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "health.hurl").write_text(
        "GET http://localhost:18080/health\nHTTP 200\n",
        encoding="utf-8",
    )
    (tmp_path / "suites").write_text("not a directory\n", encoding="utf-8")

    report = collect_ci_readiness(
        project_root=tmp_path,
        hurl_available=True,
        law=_minimal_law(),
        environ={},
    )

    checks = {check.id: check for check in report.checks}
    assert report.status == "warn"
    assert checks["suite_manifests"].status == "warn"
    assert checks["suite_manifests"].message == "suites path exists but is not a directory"


def test_report_path_problem_covers_non_symlink_path_errors(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-report.json"
    outside_problem = ci_readiness._report_path_problem(outside, root=tmp_path)
    assert outside_problem is not None
    assert "inside project root" in outside_problem

    reports_file = tmp_path / "reports"
    reports_file.write_text("not a directory\n", encoding="utf-8")
    parent_problem = ci_readiness._report_path_problem(
        tmp_path / "reports" / "run-latest.json",
        root=tmp_path,
    )
    assert parent_problem is not None
    assert "parent must be a directory" in parent_problem

    state_dir = tmp_path / ".entroping"
    state_dir.mkdir()
    latest_run = state_dir / "latest-run.json"
    latest_run.mkdir()
    target_problem = ci_readiness._report_path_problem(
        latest_run,
        root=tmp_path,
    )
    assert target_problem is not None
    assert "target must not be a directory" in target_problem
