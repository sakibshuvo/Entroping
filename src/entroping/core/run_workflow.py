"""Deterministic run workflow use case."""

import tempfile
from collections.abc import Sequence
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
from entroping.core.env_loader import load_environment_variables
from entroping.core.gate_injector import write_injected_execution_copy
from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.core.hurl_runner import HurlRunOptions, HurlSuiteResult, run_hurl_files
from entroping.core.report_writer import (
    build_run_report,
    write_html_report,
    write_json_report,
    write_junit_report,
)
from entroping.core.traffic_store import TrafficStore, TrafficStoreError
from entroping.models.drift import DependencyDriftRoute, DriftReport


class NoHurlTestsMatchedError(ValueError):
    """Raised when discovery finds no executable Hurl tests."""


@dataclass(frozen=True, slots=True)
class RunWorkflowResult:
    """Completed deterministic run workflow result."""

    suite: HurlSuiteResult
    latest_state_path: Path
    artifacts: tuple[Path, ...]
    drift_report: DriftReport | None
    drift_check: bool

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
    report_formats: Sequence[str],
    parallel: bool,
    drift_check: bool,
) -> RunWorkflowResult:
    """Execute the deterministic Hurl governance loop without CLI concerns."""

    root = project_root.expanduser().resolve()
    law = load_qanstitution(root / "qanstitution.yaml")
    hurl_tests = discover_hurl_tests([root / "tests"], tag_filters=tuple(tag_filters))
    env_variables = (
        load_environment_variables(environment, root=root) if environment is not None else {}
    )

    if not hurl_tests:
        raise NoHurlTestsMatchedError("No Hurl tests matched the requested filters.")

    hurl_workers = law.settings.parallel_workers if parallel else 1
    state_dir = root / ".entroping"
    state_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="run-", dir=state_dir) as execution_root:
        execution_copies = [
            write_injected_execution_copy(
                hurl_test,
                law.gates,
                execution_root=Path(execution_root),
            )
            for hurl_test in hurl_tests
        ]
        suite = run_hurl_files(
            [execution.execution_path for execution in execution_copies],
            HurlRunOptions(timeout_ms=law.settings.timeout, variables=env_variables),
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
    )


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
        raise ValueError(msg) from exc

    return tuple(
        DependencyDriftRoute(
            destination_host=route.destination_host,
            method=route.method,
            path_template=route.path_template,
        )
        for route in graph.routes
    )
