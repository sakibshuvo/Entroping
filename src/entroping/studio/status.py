"""Read-only local Studio status shell."""

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from entroping.core.config_loader import QanstitutionLoadError, load_qanstitution
from entroping.core.report_writer import load_run_report

_KNOWN_REPORT_PATHS = (
    Path("reports") / "run-latest.json",
    Path("reports") / "junit.xml",
    Path("reports") / "run-latest.html",
    Path("reports") / "drift.json",
    Path("reports") / "bug.md",
)


class StudioDependencyError(RuntimeError):
    """Raised when optional Studio dependencies are unavailable."""


@dataclass(frozen=True)
class LatestRunStatus:
    """Small read-only latest-run summary for Studio."""

    generated_at: str
    passed: int
    failed: int
    total: int
    exit_code: int


@dataclass(frozen=True)
class StudioStatus:
    """Read-only local state snapshot for Studio."""

    environment: str
    project: str
    qanstitution_status: str
    latest_run: LatestRunStatus | None
    latest_run_status: str
    report_paths: tuple[str, ...]
    traffic_state_available: bool


def ensure_studio_available() -> None:
    """Fail with actionable setup guidance when the optional Studio extra is missing."""

    if importlib.util.find_spec("textual") is None:
        msg = (
            "Studio requires the optional Textual dependency. "
            "Install Studio dependencies with: uv sync --extra studio"
        )
        raise StudioDependencyError(msg)


def collect_studio_status(*, project_root: Path, environment: str | None) -> StudioStatus:
    """Collect a read-only snapshot of local Entroping state."""

    root = project_root.expanduser().resolve()
    project, qanstitution_status = _load_project_status(root)
    latest_run, latest_run_status = _load_latest_run_status(root)
    return StudioStatus(
        environment=environment or "default",
        project=project,
        qanstitution_status=qanstitution_status,
        latest_run=latest_run,
        latest_run_status=latest_run_status,
        report_paths=_existing_report_paths(root),
        traffic_state_available=(root / ".entroping" / "state.db").is_file(),
    )


def render_studio_status(status: StudioStatus) -> str:
    """Render the read-only status shell as terminal-friendly text."""

    lines = [
        "Entroping Studio (read-only)",
        f"Environment: {status.environment}",
        f"Project: {status.project}",
        f"QAnstitution: {status.qanstitution_status}",
        _latest_run_line(status),
        f"Reports: {_reports_line(status.report_paths)}",
        f"Traffic state: {'available' if status.traffic_state_available else 'missing'}",
    ]
    return "\n".join(lines) + "\n"


def _load_project_status(root: Path) -> tuple[str, str]:
    config_path = root / "qanstitution.yaml"
    if not config_path.exists():
        return "not configured", "missing"
    try:
        law = load_qanstitution(config_path)
    except (QanstitutionLoadError, ValueError) as exc:
        return "unavailable", f"error: {exc}"
    return law.project, "ok"


def _load_latest_run_status(root: Path) -> tuple[LatestRunStatus | None, str]:
    latest_path = root / ".entroping" / "latest-run.json"
    if not latest_path.exists():
        return None, "none"
    try:
        report = load_run_report(latest_path)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return None, f"error: {exc}"
    return (
        LatestRunStatus(
            generated_at=report.generated_at,
            passed=report.summary.passed,
            failed=report.summary.failed,
            total=report.summary.total,
            exit_code=report.summary.exit_code,
        ),
        "ok",
    )


def _existing_report_paths(root: Path) -> tuple[str, ...]:
    paths = [
        str(path)
        for path in _KNOWN_REPORT_PATHS
        if (root / path).is_file()
    ]
    return tuple(sorted(paths))


def _latest_run_line(status: StudioStatus) -> str:
    if status.latest_run is None:
        return f"Latest run: {status.latest_run_status}"
    latest = status.latest_run
    return (
        f"Latest run: {latest.passed} passed, {latest.failed} failed, "
        f"{latest.total} total"
    )


def _reports_line(report_paths: tuple[str, ...]) -> str:
    if not report_paths:
        return "none"
    return ", ".join(report_paths)
