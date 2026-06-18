"""Select failed Hurl tests from the latest local run report."""

import json
from dataclasses import dataclass
from pathlib import Path

from entroping.core.path_safety import first_symlink_path_component
from entroping.core.report_serialization import load_run_report
from entroping.models.report import RunReport, RunTestReport

_LATEST_REPORT_CANDIDATES = (
    Path("reports") / "run-latest.json",
    Path(".entroping") / "latest-run.json",
)


class RerunFailuresError(ValueError):
    """Raised when failed tests cannot be selected from the latest run report."""


@dataclass(frozen=True, slots=True)
class RerunFailureSelection:
    """Failed source Hurl files selected from a latest run report."""

    report_path: Path
    environment: str | None
    failed_paths: tuple[Path, ...]


def select_latest_failed_hurl_tests(*, project_root: Path) -> RerunFailureSelection:
    """Return failed source Hurl paths from the newest local run report."""

    root = project_root.expanduser().resolve()
    report_path = _latest_report_path(root)
    report = _load_latest_report(report_path, root=root)
    failed_tests = tuple(test for test in report.tests if not test.passed)
    if not failed_tests:
        msg = f"Latest run report has no failed tests: {_display_path(report_path, root=root)}"
        raise RerunFailuresError(msg)

    failed_paths = tuple(
        dict.fromkeys(
            _resolve_failed_hurl_path(test, root=root, report_path=report_path)
            for test in failed_tests
        )
    )
    return RerunFailureSelection(
        report_path=report_path,
        environment=_report_environment(report),
        failed_paths=failed_paths,
    )


def _latest_report_path(root: Path) -> Path:
    for candidate in _LATEST_REPORT_CANDIDATES:
        report_path = root / candidate
        if report_path.exists():
            if not report_path.is_file():
                display_path = _display_path(report_path, root=root)
                msg = f"Latest run report path is not a file: {display_path}"
                raise RerunFailuresError(msg)
            return report_path.resolve()
    msg = (
        "No latest run report found. Run `entroping run` or "
        "`entroping run --report json` before `entroping run --rerun-failures`."
    )
    raise RerunFailuresError(msg)


def _load_latest_report(report_path: Path, *, root: Path) -> RunReport:
    try:
        return load_run_report(report_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        msg = f"Could not read latest run report {_display_path(report_path, root=root)}: {exc}"
        raise RerunFailuresError(msg) from exc


def _resolve_failed_hurl_path(
    test: RunTestReport,
    *,
    root: Path,
    report_path: Path,
) -> Path:
    path_text = test.path.strip()
    if not path_text or _has_control_character(path_text):
        msg = f"Failed Hurl path in {_display_path(report_path, root=root)} is invalid"
        raise RerunFailuresError(msg)

    raw_candidate = Path(path_text)
    if ".." in raw_candidate.parts:
        msg = f"Failed Hurl path must stay inside project: {path_text}"
        raise RerunFailuresError(msg)
    candidate = raw_candidate if raw_candidate.is_absolute() else root / raw_candidate
    try:
        symlink_component = first_symlink_path_component(candidate, root=root)
    except ValueError as exc:
        msg = f"Failed Hurl path must stay inside project: {path_text}"
        raise RerunFailuresError(msg) from exc
    if symlink_component is not None:
        msg = f"Failed Hurl path must not use symlinks: {symlink_component}"
        raise RerunFailuresError(msg)

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        msg = f"Failed Hurl path must stay inside project: {path_text}"
        raise RerunFailuresError(msg)
    if resolved.suffix != ".hurl":
        msg = f"Failed Hurl path must be a .hurl file: {path_text}"
        raise RerunFailuresError(msg)
    if not resolved.is_file():
        msg = f"Failed Hurl test no longer exists: {_display_path(resolved, root=root)}"
        raise RerunFailuresError(msg)
    return resolved


def _report_environment(report: RunReport) -> str | None:
    environment = report.environment.strip()
    if environment in {"", "default"}:
        return None
    if _has_control_character(environment):
        msg = "Latest run report environment must not contain control characters"
        raise RerunFailuresError(msg)
    return environment


def _display_path(path: Path, *, root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
