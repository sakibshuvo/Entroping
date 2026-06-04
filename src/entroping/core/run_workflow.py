"""Deterministic run workflow use case."""

import tempfile
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from entroping.bridge.traffic_sessions import (
    TrafficSessionError,
    build_traffic_session_candidate,
)
from entroping.bridge.traffic_to_graph import (
    TrafficGraphCompilationError,
    compile_traffic_dependency_graph,
)
from entroping.core.config_loader import load_qanstitution
from entroping.core.drift_report import (
    DriftBaselineNotFoundError,
    append_dependency_drift_findings,
    build_drift_report,
    build_missing_baseline_report,
    load_dependency_drift_baseline,
    load_drift_baseline,
    write_drift_report,
    write_reviewed_drift_baseline_candidate,
)
from entroping.core.env_loader import load_environment_variables, load_process_hurl_variables
from entroping.core.gate_injector import HurlExecutionCopy, write_injected_execution_copy
from entroping.core.git_changed_hurl import select_changed_hurl_tests
from entroping.core.hurl_discovery import (
    HurlTestSelection,
    discover_hurl_test_selection,
    normalize_operation_id_filters,
)
from entroping.core.hurl_runner import HurlRunOptions, HurlSuiteResult, run_hurl_files
from entroping.core.hurl_variable_preflight import (
    HurlVariablePreflightError,
    preflight_hurl_variables,
)
from entroping.core.report_writer import (
    build_run_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.tag_expression import compile_tag_expression
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.drift import DependencyDriftRoute, DriftReport
from entroping.models.hurl import HurlTest
from entroping.models.qanstitution import KnownFailure

__all__ = [
    "DependencyDriftObservationError",
    "HurlVariablePreflightError",
    "NoHurlTestsMatchedError",
    "RunWorkflowError",
    "RunWorkflowResult",
    "execute_run_workflow",
]


class RunWorkflowError(ValueError):
    """Base error for deterministic run workflow failures."""


class NoHurlTestsMatchedError(RunWorkflowError):
    """Raised when discovery finds no executable Hurl tests."""


class DependencyDriftObservationError(RunWorkflowError):
    """Raised when current dependency routes cannot be observed safely."""


@dataclass(frozen=True, slots=True)
class RunWorkflowResult:
    """Completed deterministic run workflow result."""

    suite: HurlSuiteResult
    latest_state_path: Path
    artifacts: tuple[Path, ...]
    drift_report: DriftReport | None
    drift_check: bool
    selection: HurlTestSelection

    @property
    def exit_code(self) -> int:
        """Return the process exit code implied by Hurl and drift results."""

        if self.suite.exit_code != 0:
            return self.suite.exit_code
        if (
            self.drift_check
            and self.drift_report is not None
            and self.drift_report.summary.drifted > 0
        ):
            return 1
        return 0


def execute_run_workflow(
    *,
    project_root: Path,
    environment: str | None,
    tag_filters: Sequence[str],
    tag_expression: str | None = None,
    operation_ids: Collection[str] | None = None,
    report_formats: Sequence[str],
    parallel: bool,
    drift_check: bool,
    changed_from: str | None = None,
    discovery_roots: Sequence[Path] | None = None,
    selection_label: str | None = None,
) -> RunWorkflowResult:
    """Execute the deterministic Hurl governance loop without CLI concerns."""

    root = project_root.expanduser().resolve()
    if tag_filters and tag_expression is not None:
        msg = "tag filters cannot be combined with tag expressions"
        raise RunWorkflowError(msg)
    operation_filters = normalize_operation_id_filters(operation_ids)
    if operation_filters and tag_filters:
        msg = "operation ID filters cannot be combined with tag filters"
        raise RunWorkflowError(msg)
    if operation_filters and tag_expression is not None:
        msg = "operation ID filters cannot be combined with tag expressions"
        raise RunWorkflowError(msg)
    compiled_tag_expression = (
        compile_tag_expression(tag_expression) if tag_expression is not None else None
    )
    law = load_qanstitution(root / "qanstitution.yaml")
    selected_roots: Sequence[Path]
    if changed_from is not None and discovery_roots is not None:
        msg = "changed-from cannot be combined with custom Hurl discovery roots"
        raise RunWorkflowError(msg)
    if changed_from is not None and operation_filters:
        msg = "changed-from cannot be combined with operation ID filters"
        raise RunWorkflowError(msg)
    if changed_from is None:
        selected_roots = discovery_roots if discovery_roots is not None else (root / "tests",)
        if selection_label is None:
            no_match_label = _default_no_match_label(
                tag_expression=tag_expression,
                operation_ids=operation_filters,
            )
        else:
            no_match_label = selection_label
    else:
        changed_paths = select_changed_hurl_tests(project_root=root, base_ref=changed_from)
        selected_roots = changed_paths
        if tag_expression is None:
            no_match_label = f"changed Hurl tests matched from base ref {changed_from!r}"
        else:
            no_match_label = (
                f"changed Hurl tests matching tag expression {tag_expression!r} "
                f"from base ref {changed_from!r}"
            )

    selection = discover_hurl_test_selection(
        selected_roots,
        tag_filters=tuple(tag_filters),
        tag_expression=compiled_tag_expression,
        operation_id_filters=operation_filters,
    )
    hurl_tests = selection.tests
    env_variables = (
        load_environment_variables(environment, root=root) if environment is not None else {}
    )
    env_variables.update(load_process_hurl_variables())

    if not hurl_tests:
        raise NoHurlTestsMatchedError(_no_match_message(no_match_label, selection=selection))

    hurl_workers = law.settings.parallel_workers if parallel else 1
    state_dir = root / ".entroping"
    state_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="run-", dir=state_dir) as execution_root:
        execution_copies = [
            write_injected_execution_copy(
                hurl_test,
                law.gates,
                execution_root=Path(execution_root),
                known_failures=law.ignore_failures,
                project_root=root,
            )
            for hurl_test in hurl_tests
        ]
        _reject_unmatched_selected_known_failures(
            known_failures=law.ignore_failures,
            hurl_tests=hurl_tests,
            execution_copies=execution_copies,
            project_root=root,
        )
        preflight_hurl_variables(
            execution_copies,
            variables=env_variables,
            project_root=root,
        )
        suite = run_hurl_files(
            [execution.execution_path for execution in execution_copies],
            HurlRunOptions(
                timeout_ms=law.settings.timeout,
                retry=law.settings.retry,
                variables=env_variables,
            ),
            max_workers=hurl_workers,
        )
        run_report = build_run_report(
            project=law.project,
            environment=environment or "default",
            execution_copies=execution_copies,
            suite=suite,
            project_root=root,
        )

    latest_state = write_json_report(run_report, state_dir / "latest-run.json")
    artifacts: list[Path] = []
    drift_report = None
    if drift_check or "drift" in report_formats:
        baseline_path = state_dir / "drift-baseline.json"
        try:
            baseline = load_drift_baseline(baseline_path)
        except DriftBaselineNotFoundError:
            drift_report = build_missing_baseline_report(
                current=run_report,
                baseline_path=baseline_path,
            )
        else:
            drift_report = build_drift_report(
                current=run_report,
                baseline=baseline,
                baseline_path=baseline_path,
            )
        dependency_baseline_path = state_dir / "dependency-baseline.json"
        if dependency_baseline_path.exists() and drift_report is not None:
            dependency_baseline = load_dependency_drift_baseline(dependency_baseline_path)
            drift_report = append_dependency_drift_findings(
                drift_report,
                baseline=dependency_baseline,
                current_routes=_load_current_dependency_routes(root),
                baseline_path=dependency_baseline_path,
            )

    reports_dir = root / "reports"
    if "json" in report_formats:
        artifacts.append(write_json_report(run_report, reports_dir / "run-latest.json"))
    if "junit" in report_formats:
        artifacts.append(write_junit_report(run_report, reports_dir / "junit.xml"))
    if "html" in report_formats:
        artifacts.append(write_html_report(run_report, reports_dir / "run-latest.html"))
    if "drift" in report_formats and drift_report is not None:
        artifacts.append(write_drift_report(drift_report, reports_dir / "drift.json"))
        if run_report.summary.exit_code == 0:
            artifacts.append(
                write_reviewed_drift_baseline_candidate(
                    run_report,
                    reports_dir / "drift-baseline.candidate.json",
                )
            )

    return RunWorkflowResult(
        suite=suite,
        latest_state_path=latest_state,
        artifacts=tuple(artifacts),
        drift_report=drift_report,
        drift_check=drift_check,
        selection=selection,
    )


def _default_no_match_label(
    *,
    tag_expression: str | None,
    operation_ids: Collection[str],
) -> str:
    if operation_ids:
        return "OpenAPI operation IDs " + ", ".join(repr(item) for item in sorted(operation_ids))
    if tag_expression is None:
        return "the requested filters"
    return f"tag expression {tag_expression!r}"


def _no_match_message(label: str, *, selection: HurlTestSelection) -> str:
    if label.startswith("changed Hurl tests"):
        prefix = f"No {label}"
    else:
        prefix = f"No Hurl tests matched {label}"
    return (
        f"{prefix} "
        f"({selection.selected_count} selected, {selection.skipped_count} skipped "
        f"from {selection.discovered_count} discovered)."
    )


def _reject_unmatched_selected_known_failures(
    *,
    known_failures: Sequence[KnownFailure],
    hurl_tests: Sequence[HurlTest],
    execution_copies: Sequence[HurlExecutionCopy],
    project_root: Path,
) -> None:
    selected_test_keys = {
        _known_failure_source_key(hurl_test.path, project_root=project_root)
        for hurl_test in hurl_tests
    }
    expected = [
        known_failure
        for known_failure in known_failures
        if _normalize_known_failure_test(known_failure.test) in selected_test_keys
    ]
    if not expected:
        return

    applied_keys = {
        (known_failure.test, known_failure.rule_id)
        for execution_copy in execution_copies
        for known_failure in execution_copy.known_failures
    }
    unmatched = [
        known_failure
        for known_failure in expected
        if (
            _normalize_known_failure_test(known_failure.test),
            known_failure.rule_id,
        )
        not in applied_keys
    ]
    if not unmatched:
        return

    details = "; ".join(
        f"{known_failure.issue_id} {known_failure.test} rule {known_failure.rule_id}"
        for known_failure in unmatched
    )
    msg = f"Known failure exception did not match any selected injected gate: {details}"
    raise RunWorkflowError(msg)


def _known_failure_source_key(path: Path, *, project_root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _normalize_known_failure_test(test: str) -> str:
    return test.strip().replace("\\", "/")


def _load_current_dependency_routes(root: Path) -> tuple[DependencyDriftRoute, ...]:
    state_path = root / ".entroping" / "state.db"
    if not state_path.exists():
        return ()

    try:
        store = TrafficStore.open_project(root)
        exchanges = store.list_exchanges()
        if not exchanges:
            return ()
        session = build_traffic_session_candidate(
            exchanges,
            name="dependency_drift",
            target_url=None,
        )
        graph = compile_traffic_dependency_graph(session)
    except (TrafficGraphCompilationError, TrafficSessionError, TrafficStoreError) as exc:
        msg = f"Could not build dependency drift observations: {exc}"
        raise DependencyDriftObservationError(msg) from exc

    return tuple(
        DependencyDriftRoute(
            destination_host=route.destination_host,
            method=route.method,
            path_template=route.path_template,
        )
        for route in graph.routes
    )
