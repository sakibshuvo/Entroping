"""Deterministic run workflow use case."""

import tempfile
import time
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
from entroping.core.run_event_log import RunEventLog
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
    event_log_path: Path
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
    fail_fast: bool = False,
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
    state_dir = root / ".entroping"
    state_dir.mkdir(parents=True, exist_ok=True)
    event_log = RunEventLog.open_project(root)
    started_at = time.perf_counter()
    terminal_event_recorded = False
    event_log.record_started(
        environment=environment,
        tag_filters=tuple(tag_filters),
        tag_expression=tag_expression,
        operation_ids=tuple(operation_filters),
        report_formats=tuple(report_formats),
        parallel=parallel,
        fail_fast=fail_fast,
        drift_check=drift_check,
        changed_from=changed_from,
    )

    try:
        law = load_qanstitution(root / "qanstitution.yaml")
        selected_roots: Sequence[Path]
        if changed_from is not None and discovery_roots is not None:
            msg = "changed-from cannot be combined with custom Hurl discovery roots"
            raise RunWorkflowError(msg)
        if changed_from is not None and operation_filters:
            msg = "changed-from cannot be combined with operation ID filters"
            raise RunWorkflowError(msg)
        if changed_from is None:
            selected_roots = (
                discovery_roots if discovery_roots is not None else (root / "tests",)
            )
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
            load_environment_variables(environment, root=root)
            if environment is not None
            else {}
        )
        env_variables.update(load_process_hurl_variables())

        if not hurl_tests:
            no_match_message = _no_match_message(no_match_label, selection=selection)
            event_log.record_no_match(
                message=no_match_message,
                selected_count=selection.selected_count,
                skipped_count=selection.skipped_count,
                discovered_count=selection.discovered_count,
            )
            event_log.record_completed(
                status="no_match",
                exit_code=None,
                duration_ms=_elapsed_ms(started_at),
                total=0,
                passed=0,
                failed=0,
            )
            terminal_event_recorded = True
            raise NoHurlTestsMatchedError(no_match_message)

        hurl_workers = law.settings.parallel_workers if parallel else 1

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
            for hurl_test, execution_copy in zip(hurl_tests, execution_copies, strict=True):
                event_log.record_test_selected(
                    path=execution_copy.source_path,
                    tags=tuple(hurl_test.metadata.tags),
                    operation_id=execution_copy.operation_id,
                    rule_ids=tuple(gate.rule_id for gate in execution_copy.injected_gates),
                )
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
                fail_fast=fail_fast,
            )
            run_report = build_run_report(
                project=law.project,
                environment=environment or "default",
                execution_copies=execution_copies,
                suite=suite,
                project_root=root,
            )
            for test in run_report.tests:
                event_log.record_test_result(
                    path=test.path,
                    status=test.status,
                    exit_code=test.exit_code,
                    duration_ms=test.duration_ms,
                    timeout_ms=test.timeout_ms,
                    rule_ids=test.rule_ids,
                    operation_id=test.operation_id,
                    stdout=test.stdout,
                    stderr=test.stderr,
                    stdout_truncated=test.retry.attempts[-1].stdout_truncated,
                    stderr_truncated=test.retry.attempts[-1].stderr_truncated,
                )

        latest_state = write_json_report(run_report, state_dir / "latest-run.json")
        event_log.record_artifact(artifact_type="latest-run", path=latest_state)
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
                dependency_baseline = load_dependency_drift_baseline(
                    dependency_baseline_path
                )
                drift_report = append_dependency_drift_findings(
                    drift_report,
                    baseline=dependency_baseline,
                    current_routes=_load_current_dependency_routes(root),
                    baseline_path=dependency_baseline_path,
                )

        reports_dir = root / "reports"
        if "json" in report_formats:
            artifact = write_json_report(run_report, reports_dir / "run-latest.json")
            artifacts.append(artifact)
            event_log.record_artifact(artifact_type="json-report", path=artifact)
        if "junit" in report_formats:
            artifact = write_junit_report(run_report, reports_dir / "junit.xml")
            artifacts.append(artifact)
            event_log.record_artifact(artifact_type="junit-report", path=artifact)
        if "html" in report_formats:
            artifact = write_html_report(run_report, reports_dir / "run-latest.html")
            artifacts.append(artifact)
            event_log.record_artifact(artifact_type="html-report", path=artifact)
        if "drift" in report_formats and drift_report is not None:
            artifact = write_drift_report(drift_report, reports_dir / "drift.json")
            artifacts.append(artifact)
            event_log.record_artifact(artifact_type="drift-report", path=artifact)
            if run_report.summary.exit_code == 0:
                artifact = write_reviewed_drift_baseline_candidate(
                    run_report,
                    reports_dir / "drift-baseline.candidate.json",
                )
                artifacts.append(artifact)
                event_log.record_artifact(
                    artifact_type="drift-baseline-candidate",
                    path=artifact,
                )

        result = RunWorkflowResult(
            suite=suite,
            latest_state_path=latest_state,
            event_log_path=event_log.path,
            artifacts=tuple(artifacts),
            drift_report=drift_report,
            drift_check=drift_check,
            selection=selection,
        )
        event_log.record_completed(
            status="passed" if result.exit_code == 0 else "failed",
            exit_code=result.exit_code,
            duration_ms=_elapsed_ms(started_at),
            total=suite.total,
            passed=suite.passed,
            failed=suite.failed,
        )
        terminal_event_recorded = True
        return result
    except Exception as exc:
        if not terminal_event_recorded:
            event_log.record_error(exc)
            event_log.record_completed(
                status="error",
                exit_code=1,
                duration_ms=_elapsed_ms(started_at),
                total=0,
                passed=0,
                failed=0,
            )
        raise


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


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


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
