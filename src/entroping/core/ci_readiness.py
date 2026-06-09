"""CI-readiness checks for deterministic Entroping runs."""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from entroping.core.env_loader import (
    EnvironmentLoadError,
    load_environment_variables,
    load_process_hurl_variables,
)
from entroping.core.gate_injector import HurlExecutionCopy
from entroping.core.hurl_discovery import discover_hurl_test_selection
from entroping.core.hurl_variable_preflight import find_missing_hurl_variables
from entroping.core.path_safety import first_symlink_path_component
from entroping.core.run_suite_manifest import RunSuiteManifestError, load_run_suite_manifest
from entroping.models.doctor import (
    DoctorCiReadiness,
    DoctorCiReadinessCheck,
    DoctorHealthStatus,
    DoctorHurlCompatibility,
)
from entroping.models.hurl import HurlMetadataSyntaxError, HurlTest
from entroping.models.qanstitution import Qanstitution

_CI_REPORT_PATHS = (
    Path(".entroping") / "latest-run.json",
    Path("reports") / "run-latest.json",
    Path("reports") / "junit.xml",
    Path("reports") / "run-latest.html",
    Path("reports") / "drift.json",
    Path("reports") / "drift-baseline.candidate.json",
)


def collect_ci_readiness(
    *,
    project_root: Path,
    hurl_available: bool,
    law: Qanstitution | None,
    hurl_compatibility: DoctorHurlCompatibility | None = None,
    environ: Mapping[str, str] | None = None,
) -> DoctorCiReadiness:
    """Collect CI-focused readiness without provider calls or workflow mutation."""

    root = project_root.expanduser().resolve()
    process_environ = os.environ if environ is None else environ
    checks = [
        _qanstitution_check(law),
        _hurl_available_check(hurl_available, hurl_compatibility),
        _report_paths_check(root),
        *_suite_and_env_checks(root, process_environ),
        _provider_free_run_check(law),
    ]
    status = _overall_status([check.status for check in checks])
    return DoctorCiReadiness(
        status=status,
        provider_free_run=True,
        message="CI readiness valid" if status != "error" else "CI readiness invalid",
        checks=checks,
    )


def _qanstitution_check(law: Qanstitution | None) -> DoctorCiReadinessCheck:
    if law is None:
        return DoctorCiReadinessCheck(
            id="qanstitution_loaded",
            status="error",
            message="qanstitution.yaml must be valid before CI can run deterministically",
            path="qanstitution.yaml",
        )
    return DoctorCiReadinessCheck(
        id="qanstitution_loaded",
        status="ok",
        message="qanstitution.yaml is available for CI runs",
        path="qanstitution.yaml",
    )


def _hurl_available_check(
    hurl_available: bool,
    hurl_compatibility: DoctorHurlCompatibility | None,
) -> DoctorCiReadinessCheck:
    if not hurl_available:
        return DoctorCiReadinessCheck(
            id="hurl_available",
            status="error",
            message="hurl must be installed before entroping run --ci can execute tests",
        )
    if hurl_compatibility is not None and hurl_compatibility.status != "ok":
        return DoctorCiReadinessCheck(
            id="hurl_available",
            status="error",
            message=hurl_compatibility.message,
            path=hurl_compatibility.path,
        )
    return DoctorCiReadinessCheck(
        id="hurl_available",
        status="ok",
        message=(
            hurl_compatibility.message
            if hurl_compatibility is not None
            else "hurl is available for CI execution"
        ),
    )


def _report_paths_check(root: Path) -> DoctorCiReadinessCheck:
    problems: list[str] = []
    for relative_path in _CI_REPORT_PATHS:
        problem = _report_path_problem(root / relative_path, root=root)
        if problem is not None:
            problems.append(problem)

    if problems:
        return DoctorCiReadinessCheck(
            id="report_paths",
            status="error",
            message="; ".join(problems),
            path="reports",
        )

    return DoctorCiReadinessCheck(
        id="report_paths",
        status="ok",
        message=".entroping and reports output paths are safe for local CI artifacts",
        path="reports",
    )


def _report_path_problem(path: Path, *, root: Path) -> str | None:
    try:
        path.relative_to(root)
    except ValueError:
        return f"Report path must stay inside project root: {_display_path(path, root)}"

    symlink_component = first_symlink_path_component(path, root=root)
    if symlink_component is not None:
        return f"Report paths must not use symlinks: {_display_path(symlink_component, root)}"

    parent = path.parent
    if parent.exists() and not parent.is_dir():
        return f"Report path parent must be a directory: {_display_path(parent, root)}"
    if path.exists() and path.is_dir():
        return f"Report path target must not be a directory: {_display_path(path, root)}"
    return None


def _suite_and_env_checks(
    root: Path,
    environ: Mapping[str, str],
) -> tuple[DoctorCiReadinessCheck, DoctorCiReadinessCheck]:
    suite_names: list[str] = []
    suite_errors: list[str] = []
    env_errors: list[str] = []
    missing_env_names: set[str] = set()

    suite_paths = _suite_manifest_paths(root)
    if suite_paths is None:
        suite_errors.append("suites path exists but is not a directory")
    elif suite_paths:
        for manifest_path in suite_paths:
            suite_name = manifest_path.stem
            suite_names.append(suite_name)
            try:
                suite = load_run_suite_manifest(project_root=root, suite_name=suite_name)
                if not suite.discovery_roots:
                    suite_errors.append(f"No Hurl tests matched suite {suite_name!r}")
                    continue
                selection = discover_hurl_test_selection(
                    suite.discovery_roots,
                    tag_filters=suite.tag_filters,
                )
            except (
                FileNotFoundError,
                HurlMetadataSyntaxError,
                RunSuiteManifestError,
                ValueError,
            ) as exc:
                suite_errors.append(str(exc))
                continue

            if not selection.tests:
                suite_errors.append(f"No Hurl tests matched suite {suite_name!r}")
                continue

            variables: dict[str, str] = {}
            if suite.environment is not None:
                try:
                    variables.update(
                        load_environment_variables(
                            suite.environment,
                            root=root,
                            environ=environ,
                        )
                    )
                except EnvironmentLoadError as exc:
                    env_errors.append(str(exc))
            _load_process_variables(variables, environ=environ, errors=env_errors)
            missing_env_names.update(
                _missing_variables(selection.tests, variables=variables, root=root)
            )
    else:
        suite_errors.append(
            "No suite manifests found under suites/*.yaml; default all-tests CI runs are possible"
        )
        _check_default_tests(
            root,
            environ=environ,
            env_errors=env_errors,
            missing_env_names=missing_env_names,
        )

    suite_status: DoctorHealthStatus
    if any("No Hurl tests matched" in item for item in suite_errors):
        suite_status = "error"
    elif suite_errors:
        suite_status = "warn"
    else:
        suite_status = "ok"
    env_status: DoctorHealthStatus = "error" if env_errors or missing_env_names else "ok"
    return (
        DoctorCiReadinessCheck(
            id="suite_manifests",
            status=suite_status,
            message="; ".join(suite_errors) if suite_errors else "suite manifests valid",
            path="suites",
            suites=sorted(suite_names),
        ),
        DoctorCiReadinessCheck(
            id="env_variables",
            status=env_status,
            message=(
                "; ".join(env_errors)
                if env_errors
                else _env_variable_message(missing_env_names)
            ),
            required_env_names=sorted(missing_env_names),
            suites=sorted(suite_names),
        ),
    )


def _suite_manifest_paths(root: Path) -> tuple[Path, ...] | None:
    suites_dir = root / "suites"
    if not suites_dir.exists():
        return ()
    if not suites_dir.is_dir():
        return None
    return tuple(sorted(suites_dir.glob("*.yaml"), key=lambda path: path.name))


def _check_default_tests(
    root: Path,
    *,
    environ: Mapping[str, str],
    env_errors: list[str],
    missing_env_names: set[str],
) -> None:
    try:
        selection = discover_hurl_test_selection((root / "tests",))
    except (FileNotFoundError, HurlMetadataSyntaxError, ValueError) as exc:
        env_errors.append(str(exc))
        return
    variables: dict[str, str] = {}
    _load_process_variables(variables, environ=environ, errors=env_errors)
    missing_env_names.update(_missing_variables(selection.tests, variables=variables, root=root))


def _load_process_variables(
    variables: dict[str, str],
    *,
    environ: Mapping[str, str],
    errors: list[str],
) -> None:
    try:
        variables.update(load_process_hurl_variables(environ=environ))
    except EnvironmentLoadError as exc:
        errors.append(str(exc))


def _missing_variables(
    tests: Sequence[HurlTest],
    *,
    variables: Mapping[str, str],
    root: Path,
) -> set[str]:
    execution_copies = tuple(
        HurlExecutionCopy(source_path=test.path, execution_path=test.path, injected_gates=())
        for test in tests
    )
    return {
        missing.name
        for missing in find_missing_hurl_variables(
            execution_copies,
            variables=variables,
            project_root=root,
        )
    }


def _env_variable_message(missing_env_names: set[str]) -> str:
    if not missing_env_names:
        return "required Hurl variables are available for selected CI tests"
    return (
        "Missing required Hurl variables for selected CI tests: "
        f"{', '.join(sorted(missing_env_names))}"
    )


def _provider_free_run_check(law: Qanstitution | None) -> DoctorCiReadinessCheck:
    agent_count = 0 if law is None else len(law.agents)
    suffix = f"; {agent_count} configured agent roles ignored by run --ci" if agent_count else ""
    return DoctorCiReadinessCheck(
        id="provider_free_run",
        status="ok",
        message=(
            "entroping run --ci does not call model providers "
            f"or require agent API keys{suffix}"
        ),
    )


def _display_path(path: Path, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _overall_status(statuses: Sequence[DoctorHealthStatus]) -> DoctorHealthStatus:
    if "error" in statuses:
        return "error"
    if "warn" in statuses:
        return "warn"
    return "ok"
