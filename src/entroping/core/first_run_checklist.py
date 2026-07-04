from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from entroping.core.hurl_discovery import discover_hurl_tests
from entroping.models.hurl import HurlMetadataSyntaxError

FirstRunChecklistState = Literal["present", "missing", "error", "optional-missing"]

_DEFAULT_REPORT_DIR: Final[Path] = Path("reports")
_DEFAULT_TEST_DIR: Final[Path] = Path("tests")
_DEFAULT_DELTA_PATHS: Final[tuple[Path, ...]] = (
    _DEFAULT_REPORT_DIR / "delta.json",
    _DEFAULT_REPORT_DIR / "run-delta.json",
)


@dataclass(frozen=True, slots=True)
class FirstRunChecklistItem:
    key: str
    label: str
    state: FirstRunChecklistState
    paths: tuple[Path, ...]
    hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FirstRunChecklist:
    items: tuple[FirstRunChecklistItem, ...]

    @property
    def has_errors(self) -> bool:
        return any(item.state == "error" for item in self.items)


def run_first_run_checklist(*, project_root: Path) -> FirstRunChecklist:
    root = project_root.expanduser().resolve()
    checks = (
        _check_hurl_tests(root),
        _check_report_artifact(
            root=root,
            key="run-latest-json",
            label="Latest run JSON",
            path=_DEFAULT_REPORT_DIR / "run-latest.json",
            missing_hint="Run entroping run with --report json to create this artifact.",
        ),
        _check_report_artifact(
            root=root,
            key="run-latest-html",
            label="Latest run HTML",
            path=_DEFAULT_REPORT_DIR / "run-latest.html",
            missing_hint="Run entroping run with --report html to create this artifact.",
        ),
        _check_report_artifact(
            root=root,
            key="run-junit",
            label="JUnit XML",
            path=_DEFAULT_REPORT_DIR / "junit.xml",
            missing_hint="Run entroping run with --report junit to create this artifact.",
        ),
        _check_report_artifact(
            root=root,
            key="drift-baseline-candidate",
            label="Drift baseline candidate",
            path=_DEFAULT_REPORT_DIR / "drift-baseline.candidate.json",
            missing_hint="Run entroping run --drift-check to create a drift-baseline candidate.",
        ),
        _check_delta_output(root=root),
    )
    return FirstRunChecklist(items=checks)


def _check_hurl_tests(root: Path) -> FirstRunChecklistItem:
    tests_dir = (root / _DEFAULT_TEST_DIR).resolve()
    try:
        tests = discover_hurl_tests((tests_dir,), tag_filters=())
    except FileNotFoundError:
        return FirstRunChecklistItem(
            key="hurl-tests",
            label="Hurl tests",
            state="missing",
            paths=(tests_dir,),
            hints=("Create local .hurl files under tests/ before first run.",),
        )
    except (HurlMetadataSyntaxError, OSError) as exc:
        return FirstRunChecklistItem(
            key="hurl-tests",
            label="Hurl tests",
            state="error",
            paths=(tests_dir,),
            hints=(f"Could not discover Hurl tests: {exc}",),
        )

    return FirstRunChecklistItem(
        key="hurl-tests",
        label="Hurl tests",
        state="present" if tests else "missing",
        paths=(tests_dir,),
        hints=() if tests else ("No discoverable .hurl files are available under tests/.",),
    )


def _check_report_artifact(
    *,
    root: Path,
    key: str,
    label: str,
    path: Path,
    missing_hint: str,
) -> FirstRunChecklistItem:
    expected_path = (root / path).resolve()
    if expected_path.exists() and expected_path.is_file():
        return FirstRunChecklistItem(
            key=key,
            label=label,
            state="present",
            paths=(expected_path,),
        )
    return FirstRunChecklistItem(
        key=key,
        label=label,
        state="missing",
        paths=(expected_path,),
        hints=(missing_hint,),
    )


def _check_delta_output(root: Path) -> FirstRunChecklistItem:
    reports_dir = (root / _DEFAULT_REPORT_DIR).resolve()
    delta_candidates = _delta_candidates(reports_dir)
    if delta_candidates:
        return FirstRunChecklistItem(
            key="delta-output",
            label="Delta output",
            state="present",
            paths=delta_candidates,
        )

    return FirstRunChecklistItem(
        key="delta-output",
        label="Delta output",
        state="optional-missing",
        paths=tuple((root / path).resolve() for path in _DEFAULT_DELTA_PATHS),
        hints=(
            "No delta output artifact is present.",
            (
                "Optionally persist delta artifacts (for example report delta --"
                "output json > reports/delta.json)."
            ),
        ),
    )


def _delta_candidates(reports_dir: Path) -> tuple[Path, ...]:
    if not reports_dir.is_dir():
        return ()

    fallback_checks = tuple(reports_dir / path.name for path in _DEFAULT_DELTA_PATHS)
    found = [path for path in fallback_checks if path.is_file()]
    if found:
        return tuple(sorted(found))

    fallback = [
        path
        for path in sorted(reports_dir.iterdir())
        if path.is_file() and "delta" in path.name.lower()
    ]
    return tuple(fallback)
