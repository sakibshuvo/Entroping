"""Deterministic run workflow use case."""

import json
import tempfile
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
from entroping.core.hurl_runner import (
    HurlAttemptEvidence,
    HurlFileResult,
    HurlRunOptions,
    HurlSuiteResult,
    run_hurl_files,
)
from entroping.core.hurl_variable_preflight import (
    HurlVariablePreflightError,
    MissingHurlVariable,
    find_missing_hurl_variables,
    preflight_hurl_variables,
)
from entroping.core.known_failures import normalize_known_failure_test
from entroping.core.path_safety import display_path
from entroping.core.report_writer import (
    build_run_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.run_event_log import RunEventLog
from entroping.core.run_safety import RunSafetyEvaluation, evaluate_run_safety
from entroping.core.safe_write import SafeWriteError, safe_write_text
from entroping.core.tag_expression import CompiledTagExpression, compile_tag_expression
from entroping.core.traffic_store import TrafficStoreError, list_project_exchanges_readonly
from entroping.models.drift import DependencyDriftRoute, DriftReport
from entroping.models.hurl import HurlTest
from entroping.models.qanstitution import KnownFailure, Qanstitution
from entroping.models.report import (
    RunAuthEvidence,
    RunReport,
    RunSafetyEvidence,
    build_run_auth_evidence,
)

__all__ = [
    "DependencyDriftObservationError",
    "HurlVariablePreflightError",
    "NoHurlTestsMatchedError",
    "RunWorkflowError",
    "RunExecutionPlan",
    "RunWorkflowResult",
    "execute_run_workflow",
    "plan_run_workflow",
    "run_execution_plan_to_dict",
    "write_run_execution_plan",
]

RUN_PLAN_SCHEMA_VERSION = "entroping.run-plan.v1"


class RunWorkflowError(ValueError):
    """Base error for deterministic run workflow failures."""


class NoHurlTestsMatchedError(RunWorkflowError):
    """Raised when discovery finds no executable Hurl tests."""


class DependencyDriftObservationError(RunWorkflowError):
    """Raised when current dependency routes cannot be observed safely."""


RunPlanStatus = Literal["ready", "blocked", "no_match"]


@dataclass(frozen=True, slots=True)
class RunPlanVariableGap:
    """One unresolved variable and the selected tests that reference it."""

    name: str
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunPlanTest:
    """One selected test in a dry-run execution plan."""

    path: str
    tags: tuple[str, ...]
    operation_id: str | None
    injected_rule_ids: tuple[str, ...]
    missing_variables: tuple[str, ...]
    safety: RunSafetyEvidence | None = None
    auth: RunAuthEvidence | None = None


@dataclass(frozen=True, slots=True)
class RunExecutionPlan:
    """Deterministic run plan that stops before Hurl execution."""

    status: RunPlanStatus
    message: str
    project: str
    environment: str
    tag_filters: tuple[str, ...]
    tag_expression: str | None
    operation_ids: tuple[str, ...]
    changed_from: str | None
    selection_label: str | None
    report_formats: tuple[str, ...]
    would_write_reports: tuple[str, ...]
    parallel: bool
    fail_fast: bool
    drift_check: bool
    worker_count: int
    timeout_ms: int
    retry: int
    discovered_count: int
    selected_count: int
    skipped_count: int
    effective_rule_ids: tuple[str, ...]
    injected_rule_ids: tuple[str, ...]
    provided_variable_count: int
    missing_variables: tuple[RunPlanVariableGap, ...]
    tests: tuple[RunPlanTest, ...]


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


@dataclass(frozen=True, slots=True)
class _PreparedRunSelectionContext:
    law: Qanstitution
    no_match_label: str
    selected_roots: tuple[Path, ...]
    selection: HurlTestSelection
    env_variables: dict[str, str]
    hurl_workers: int


@dataclass(frozen=True, slots=True)
class _PreparedRunExecutionContext:
    execution_copies: tuple[HurlExecutionCopy, ...]
    safety: RunSafetyEvaluation


def _prepare_run_selection_context(
    *,
    root: Path,
    environment: str | None,
    tag_filters: Sequence[str],
    tag_expression: str | None,
    operation_filters: Collection[str],
    changed_from: str | None,
    discovery_roots: Sequence[Path] | None,
    selection_label: str | None,
    compiled_tag_expression: CompiledTagExpression | None = None,
    selected_roots: Sequence[Path] | None = None,
    no_match_label: str | None = None,
    parallel: bool,
) -> _PreparedRunSelectionContext:
    if selected_roots is None or no_match_label is None:
        selected_roots, no_match_label = _selected_run_roots(
            root=root,
            changed_from=changed_from,
            discovery_roots=discovery_roots,
            tag_expression=tag_expression,
            operation_filters=operation_filters,
            selection_label=selection_label,
        )
    if compiled_tag_expression is None and tag_expression is not None:
        compiled_tag_expression = compile_tag_expression(tag_expression)
    law = load_qanstitution(root / "qanstitution.yaml")
    selection = discover_hurl_test_selection(
        selected_roots,
        tag_filters=tuple(tag_filters),
        tag_expression=compiled_tag_expression,
        operation_id_filters=operation_filters,
    )
    env_variables = (
        load_environment_variables(environment, root=root) if environment is not None else {}
    )
    env_variables.update(load_process_hurl_variables())
    hurl_workers = law.settings.parallel_workers if parallel else 1

    return _PreparedRunSelectionContext(
        law=law,
        no_match_label=no_match_label,
        selected_roots=tuple(selected_roots),
        selection=selection,
        env_variables=env_variables,
        hurl_workers=hurl_workers,
    )


def _prepare_run_execution_context(
    *,
    root: Path,
    law: Qanstitution,
    selection: HurlTestSelection,
    environment: str | None,
    protected_run: bool,
    suite_safety: str | None,
    execution_root: Path,
) -> _PreparedRunExecutionContext:
    execution_copies = tuple(
        write_injected_execution_copy(
            hurl_test,
            law.gates,
            execution_root=execution_root,
            known_failures=law.ignore_failures,
            project_root=root,
        )
        for hurl_test in selection.tests
    )
    _reject_unmatched_selected_known_failures(
        known_failures=law.ignore_failures,
        hurl_tests=selection.tests,
        execution_copies=execution_copies,
        project_root=root,
    )
    safety = evaluate_run_safety(
        selection.tests,
        environment=environment,
        protected_run=protected_run,
        suite_safety=suite_safety,
        protected_environments=law.settings.protected_environments,
    )

    return _PreparedRunExecutionContext(
        execution_copies=execution_copies,
        safety=safety,
    )


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
    protected_run: bool = False,
    suite_safety: str | None = None,
) -> RunWorkflowResult:
    """Execute the deterministic Hurl governance loop without CLI concerns."""

    root = project_root.expanduser().resolve()
    operation_filters = normalize_operation_id_filters(operation_ids)
    _validate_run_filters(
        tag_filters=tuple(tag_filters),
        tag_expression=tag_expression,
        operation_filters=operation_filters,
    )
    compiled_tag_expression = (
        compile_tag_expression(tag_expression) if tag_expression is not None else None
    )
    selected_roots, no_match_label = _selected_run_roots(
        root=root,
        changed_from=changed_from,
        discovery_roots=discovery_roots,
        tag_expression=tag_expression,
        operation_filters=operation_filters,
        selection_label=selection_label,
    )
    event_log = RunEventLog.open_project(root)
    started_at = time.perf_counter()
    terminal_event_recorded = False
    state_dir = root / ".entroping"
    state_dir.mkdir(parents=True, exist_ok=True)
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
        selection_context = _prepare_run_selection_context(
            root=root,
            environment=environment,
            tag_filters=tuple(tag_filters),
            tag_expression=tag_expression,
            operation_filters=operation_filters,
            changed_from=changed_from,
            discovery_roots=discovery_roots,
            selection_label=selection_label,
            selected_roots=selected_roots,
            no_match_label=no_match_label,
            compiled_tag_expression=compiled_tag_expression,
            parallel=parallel,
        )
        law = selection_context.law
        selection = selection_context.selection
        hurl_tests = selection.tests
        env_variables = selection_context.env_variables

        if not hurl_tests:
            no_match_message = _no_match_message(
                selection_context.no_match_label,
                selection=selection,
            )
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

        hurl_workers = selection_context.hurl_workers

        with tempfile.TemporaryDirectory(prefix="run-", dir=state_dir) as execution_root:
            execution_context = _prepare_run_execution_context(
                root=root,
                law=selection_context.law,
                selection=selection_context.selection,
                environment=environment,
                protected_run=protected_run,
                suite_safety=suite_safety,
                execution_root=Path(execution_root),
            )
            execution_copies = execution_context.execution_copies
            safety = execution_context.safety
            for hurl_test, execution_copy in zip(hurl_tests, execution_copies, strict=True):
                event_log.record_test_selected(
                    path=execution_copy.source_path,
                    tags=tuple(hurl_test.metadata.tags),
                    operation_id=execution_copy.operation_id,
                    rule_ids=tuple(gate.rule_id for gate in execution_copy.injected_gates),
                )
            if safety.blocks:
                suite = _blocked_suite_result(
                    execution_copies=execution_copies,
                    safety_evidence_by_source_path=safety.evidence_by_path,
                    selected_count=selection.selected_count,
                    timeout_ms=law.settings.timeout,
                )
                run_report = build_run_report(
                    project=law.project,
                    environment=environment or "default",
                    execution_copies=_blocked_execution_copies(
                        execution_copies=execution_copies,
                        safety_evidence_by_source_path=safety.evidence_by_path,
                    ),
                    suite=suite,
                    project_root=root,
                    safety_evidence_by_source_path=safety.evidence_by_path,
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
                blocked_artifacts = _write_requested_run_reports(
                    run_report=run_report,
                    report_formats=report_formats,
                    reports_dir=root / "reports",
                    event_log=event_log,
                )
                result = RunWorkflowResult(
                    suite=suite,
                    latest_state_path=latest_state,
                    event_log_path=event_log.path,
                    artifacts=tuple(blocked_artifacts),
                    drift_report=None,
                    drift_check=drift_check,
                    selection=selection,
                )
                event_log.record_completed(
                    status="blocked",
                    exit_code=result.exit_code,
                    duration_ms=_elapsed_ms(started_at),
                    total=suite.total,
                    passed=suite.passed,
                    failed=suite.failed,
                )
                return result
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
                safety_evidence_by_source_path=safety.evidence_by_path,
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
                dependency_baseline = load_dependency_drift_baseline(dependency_baseline_path)
                drift_report = append_dependency_drift_findings(
                    drift_report,
                    baseline=dependency_baseline,
                    current_routes=_load_current_dependency_routes(root),
                    baseline_path=dependency_baseline_path,
                )

        reports_dir = root / "reports"
        artifacts.extend(
            _write_requested_run_reports(
                run_report=run_report,
                report_formats=report_formats,
                reports_dir=reports_dir,
                event_log=event_log,
            )
        )
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
        return result
    except Exception as exc:
        if not terminal_event_recorded and not isinstance(exc, NoHurlTestsMatchedError):
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
    finally:
        event_log.close()


def _blocked_suite_result(
    *,
    execution_copies: Sequence[HurlExecutionCopy],
    safety_evidence_by_source_path: dict[Path, RunSafetyEvidence],
    selected_count: int,
    timeout_ms: int,
) -> HurlSuiteResult:
    blocked_results: list[HurlFileResult] = []
    for execution_copy in _blocked_execution_copies(
        execution_copies=execution_copies,
        safety_evidence_by_source_path=safety_evidence_by_source_path,
    ):
        evidence = safety_evidence_by_source_path[execution_copy.source_path.resolve()]
        reason = evidence.blocked_reason or "Protected run blocked before Hurl execution"
        blocked_results.append(
            HurlFileResult(
                path=execution_copy.execution_path,
                command=("entroping", "run", "preflight"),
                status="blocked",
                exit_code=1,
                stdout="",
                stderr=f"Protected run blocked before Hurl execution: {reason}",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_ms=0,
                timeout_ms=timeout_ms,
                attempts=(
                    HurlAttemptEvidence(
                        attempt=1,
                        status="blocked",
                        exit_code=1,
                        duration_ms=0,
                        stdout_truncated=False,
                        stderr_truncated=False,
                    ),
                ),
            )
        )
    return HurlSuiteResult(results=tuple(blocked_results), selected_count=selected_count)


def _blocked_execution_copies(
    *,
    execution_copies: Sequence[HurlExecutionCopy],
    safety_evidence_by_source_path: dict[Path, RunSafetyEvidence],
) -> tuple[HurlExecutionCopy, ...]:
    blocked: list[HurlExecutionCopy] = []
    for execution_copy in execution_copies:
        evidence = safety_evidence_by_source_path.get(
            execution_copy.source_path.expanduser().resolve()
        )
        if evidence is not None and evidence.blocked_reason is not None:
            blocked.append(execution_copy)
    return tuple(blocked)


def _write_requested_run_reports(
    *,
    run_report: RunReport,
    report_formats: Sequence[str],
    reports_dir: Path,
    event_log: RunEventLog,
) -> list[Path]:
    artifacts: list[Path] = []
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
    return artifacts


def _validate_run_filters(
    *,
    tag_filters: tuple[str, ...],
    tag_expression: str | None,
    operation_filters: Collection[str],
) -> None:
    """Validate run-surface filters before workflow execution."""

    if tag_filters and tag_expression is not None:
        msg = "tag filters cannot be combined with tag expressions"
        raise RunWorkflowError(msg)
    if operation_filters and tag_filters:
        msg = "operation ID filters cannot be combined with tag filters"
        raise RunWorkflowError(msg)
    if operation_filters and tag_expression is not None:
        msg = "operation ID filters cannot be combined with tag expressions"
        raise RunWorkflowError(msg)


def plan_run_workflow(
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
    protected_run: bool = False,
    suite_safety: str | None = None,
) -> RunExecutionPlan:
    """Build a deterministic run plan without invoking Hurl or writing run state."""

    root = project_root.expanduser().resolve()
    operation_filters = normalize_operation_id_filters(operation_ids)
    _validate_run_filters(
        tag_filters=tuple(tag_filters),
        tag_expression=tag_expression,
        operation_filters=operation_filters,
    )
    selection_context = _prepare_run_selection_context(
        root=root,
        environment=environment,
        tag_filters=tuple(tag_filters),
        tag_expression=tag_expression,
        operation_filters=operation_filters,
        changed_from=changed_from,
        discovery_roots=discovery_roots,
        selection_label=selection_label,
        parallel=parallel,
    )
    law = selection_context.law
    selection = selection_context.selection
    env_variables = selection_context.env_variables
    hurl_workers = selection_context.hurl_workers
    effective_rule_ids = tuple(gate.id for gate in law.gates)
    would_write_reports = _would_write_run_reports(report_formats)

    if not selection.tests:
        no_match_message = _no_match_message(
            selection_context.no_match_label,
            selection=selection,
        )
        return RunExecutionPlan(
            status="no_match",
            message=no_match_message,
            project=law.project,
            environment=environment or "default",
            tag_filters=tuple(tag_filters),
            tag_expression=tag_expression,
            operation_ids=tuple(operation_filters),
            changed_from=changed_from,
            selection_label=selection_label,
            report_formats=tuple(report_formats),
            would_write_reports=would_write_reports,
            parallel=parallel,
            fail_fast=fail_fast,
            drift_check=drift_check,
            worker_count=hurl_workers,
            timeout_ms=law.settings.timeout,
            retry=law.settings.retry,
            discovered_count=selection.discovered_count,
            selected_count=selection.selected_count,
            skipped_count=selection.skipped_count,
            effective_rule_ids=effective_rule_ids,
            injected_rule_ids=(),
            provided_variable_count=len(env_variables),
            missing_variables=(),
            tests=(),
        )

    with tempfile.TemporaryDirectory(prefix="entroping-run-plan-") as execution_root:
        execution_context = _prepare_run_execution_context(
            root=root,
            law=law,
            selection=selection,
            environment=environment,
            protected_run=protected_run,
            suite_safety=suite_safety,
            execution_root=Path(execution_root),
        )
        execution_copies = execution_context.execution_copies
        safety = execution_context.safety
        missing = find_missing_hurl_variables(
            execution_copies,
            variables=env_variables,
            project_root=root,
        )
        missing_by_path: dict[str, tuple[str, ...]] = {}
        for execution_copy in execution_copies:
            display_path = _display_path(execution_copy.source_path, root)
            names = tuple(
                sorted(item.name for item in missing if item.path == execution_copy.source_path)
            )
            missing_by_path[display_path] = names

        tests = tuple(
            RunPlanTest(
                path=_display_path(execution_copy.source_path, root),
                tags=tuple(hurl_test.metadata.tags),
                operation_id=execution_copy.operation_id,
                injected_rule_ids=tuple(gate.rule_id for gate in execution_copy.injected_gates),
                missing_variables=missing_by_path[_display_path(execution_copy.source_path, root)],
                safety=safety.evidence_by_path.get(
                    execution_copy.source_path.expanduser().resolve()
                ),
                auth=build_run_auth_evidence(
                    flow=execution_copy.auth_flow,
                    requires=execution_copy.auth_requires,
                    produces=execution_copy.auth_produces,
                ),
            )
            for hurl_test, execution_copy in zip(selection.tests, execution_copies, strict=True)
        )
        injected_rule_ids = tuple(
            dict.fromkeys(
                rule_id
                for execution_copy in execution_copies
                for rule_id in (gate.rule_id for gate in execution_copy.injected_gates)
            )
        )

    missing_variables = _group_missing_variables(missing, project_root=root)
    if safety.blocks:
        status: RunPlanStatus = "blocked"
        message = "Run plan blocked by protected-environment safety preflight"
    elif missing_variables:
        status = "blocked"
        message = "Run plan blocked by unresolved Hurl variables"
    else:
        status = "ready"
        message = "Run plan ready; Hurl was not executed"
    return RunExecutionPlan(
        status=status,
        message=message,
        project=law.project,
        environment=environment or "default",
        tag_filters=tuple(tag_filters),
        tag_expression=tag_expression,
        operation_ids=tuple(operation_filters),
        changed_from=changed_from,
        selection_label=selection_label,
        report_formats=tuple(report_formats),
        would_write_reports=would_write_reports,
        parallel=parallel,
        fail_fast=fail_fast,
        drift_check=drift_check,
        worker_count=hurl_workers,
        timeout_ms=law.settings.timeout,
        retry=law.settings.retry,
        discovered_count=selection.discovered_count,
        selected_count=selection.selected_count,
        skipped_count=selection.skipped_count,
        effective_rule_ids=effective_rule_ids,
        injected_rule_ids=injected_rule_ids,
        provided_variable_count=len(env_variables),
        missing_variables=missing_variables,
        tests=tests,
    )


def run_execution_plan_to_dict(plan: RunExecutionPlan) -> dict[str, object]:
    """Return a JSON-serializable dry-run plan payload."""

    return {
        "schema_version": RUN_PLAN_SCHEMA_VERSION,
        "status": plan.status,
        "message": plan.message,
        "project": plan.project,
        "environment": plan.environment,
        "filters": {
            "tag_filters": list(plan.tag_filters),
            "tag_expression": plan.tag_expression,
            "operation_ids": list(plan.operation_ids),
            "changed_from": plan.changed_from,
            "selection_label": plan.selection_label,
        },
        "reports": {
            "requested_formats": list(plan.report_formats),
            "would_write": list(plan.would_write_reports),
        },
        "execution": {
            "parallel": plan.parallel,
            "fail_fast": plan.fail_fast,
            "drift_check": plan.drift_check,
            "worker_count": plan.worker_count,
            "timeout_ms": plan.timeout_ms,
            "retry": plan.retry,
        },
        "selection": {
            "discovered_count": plan.discovered_count,
            "selected_count": plan.selected_count,
            "skipped_count": plan.skipped_count,
        },
        "gates": {
            "effective_rule_ids": list(plan.effective_rule_ids),
            "injected_rule_ids": list(plan.injected_rule_ids),
            "injected_count": sum(len(test.injected_rule_ids) for test in plan.tests),
        },
        "variables": {
            "provided_count": plan.provided_variable_count,
            "missing": [
                {"name": item.name, "paths": list(item.paths)} for item in plan.missing_variables
            ],
        },
        "tests": [
            {
                "path": test.path,
                "tags": list(test.tags),
                "operation_id": test.operation_id,
                "injected_rule_ids": list(test.injected_rule_ids),
                "missing_variables": list(test.missing_variables),
                **(
                    {"safety": _safety_evidence_to_dict(test.safety)}
                    if test.safety is not None
                    else {}
                ),
                **({"auth": _auth_evidence_to_dict(test.auth)} if test.auth is not None else {}),
            }
            for test in plan.tests
        ],
    }


def _safety_evidence_to_dict(safety: RunSafetyEvidence) -> dict[str, object]:
    return {
        "protected_environment": safety.protected_environment,
        "safety": safety.safety,
        "safety_source": safety.safety_source,
        "methods": list(safety.methods),
        "blocked_reason": safety.blocked_reason,
    }


def _auth_evidence_to_dict(auth: RunAuthEvidence) -> dict[str, object]:
    return {
        "flow": auth.flow,
        "requires": list(auth.requires),
        "produces": list(auth.produces),
    }


def write_run_execution_plan(
    plan: RunExecutionPlan,
    path: Path,
    *,
    project_root: Path,
) -> Path:
    """Write a dry-run execution plan JSON artifact."""

    try:
        return safe_write_text(
            path,
            json.dumps(run_execution_plan_to_dict(plan), indent=2, sort_keys=True) + "\n",
            artifact="run execution plan",
            root=project_root.expanduser().resolve(),
        )
    except SafeWriteError as exc:
        msg = str(exc)
        raise RunWorkflowError(msg) from exc


def _selected_run_roots(
    *,
    root: Path,
    changed_from: str | None,
    discovery_roots: Sequence[Path] | None,
    tag_expression: str | None,
    operation_filters: Collection[str],
    selection_label: str | None,
) -> tuple[Sequence[Path], str]:
    if changed_from is not None and discovery_roots is not None:
        msg = "changed-from cannot be combined with custom Hurl discovery roots"
        raise RunWorkflowError(msg)
    if changed_from is not None and operation_filters:
        msg = "changed-from cannot be combined with operation ID filters"
        raise RunWorkflowError(msg)
    if changed_from is None:
        selected_roots = discovery_roots if discovery_roots is not None else (root / "tests",)
        no_match_label = (
            _default_no_match_label(
                tag_expression=tag_expression,
                operation_ids=operation_filters,
            )
            if selection_label is None
            else selection_label
        )
        return selected_roots, no_match_label

    changed_paths = select_changed_hurl_tests(project_root=root, base_ref=changed_from)
    if tag_expression is None:
        no_match_label = f"changed Hurl tests matched from base ref {changed_from!r}"
    else:
        no_match_label = (
            f"changed Hurl tests matching tag expression {tag_expression!r} "
            f"from base ref {changed_from!r}"
        )
    return changed_paths, no_match_label


def _would_write_run_reports(report_formats: Sequence[str]) -> tuple[str, ...]:
    paths: list[str] = []
    if "json" in report_formats:
        paths.append("reports/run-latest.json")
    if "junit" in report_formats:
        paths.append("reports/junit.xml")
    if "html" in report_formats:
        paths.append("reports/run-latest.html")
    if "drift" in report_formats:
        paths.append("reports/drift.json")
        paths.append("reports/drift-baseline.candidate.json")
    return tuple(paths)


def _group_missing_variables(
    missing: Sequence[MissingHurlVariable],
    *,
    project_root: Path,
) -> tuple[RunPlanVariableGap, ...]:
    by_name: dict[str, set[str]] = {}
    for item in missing:
        by_name.setdefault(item.name, set()).add(_display_path(item.path, project_root))
    return tuple(
        RunPlanVariableGap(name=name, paths=tuple(sorted(paths)))
        for name, paths in sorted(by_name.items())
    )


def _display_path(path: Path, project_root: Path) -> str:
    return display_path(path, root=project_root)


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
        if normalize_known_failure_test(known_failure.test) in selected_test_keys
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
            normalize_known_failure_test(known_failure.test),
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


def _load_current_dependency_routes(root: Path) -> tuple[DependencyDriftRoute, ...]:
    state_path = root / ".entroping" / "state.db"
    if not state_path.is_file():
        return ()

    try:
        exchanges = list_project_exchanges_readonly(root)
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
