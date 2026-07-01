"""Regression tests for the Python runtime compatibility promise."""

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SETUP_PYTHON_PIN = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
_SUPPORTED_PYTHONS = ["3.12", "3.13"]


def test_package_metadata_declares_only_ci_proven_python_versions() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    classifiers = set(project["classifiers"])

    assert project["requires-python"] == ">=3.12,<3.14"
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert "Programming Language :: Python :: 3.14" not in classifiers
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.12"


def test_ci_proves_supported_python_versions() -> None:
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )

    jobs = _mapping(workflow["jobs"])
    checks = _mapping(jobs["checks"])
    optional_extras = _mapping(jobs["optional-extras-smoke"])
    checks_setup = _setup_python_step(checks)
    optional_setup = _setup_python_step(optional_extras)

    checks_matrix = _mapping(_mapping(checks["strategy"])["matrix"])
    optional_matrix = _mapping(_mapping(optional_extras["strategy"])["matrix"])

    assert checks_matrix["python-version"] == _SUPPORTED_PYTHONS
    assert _mapping(checks_setup["with"])["python-version"] == "${{ matrix.python-version }}"
    assert optional_matrix["python-version"] == _SUPPORTED_PYTHONS
    assert _mapping(optional_setup["with"])["python-version"] == "${{ matrix.python-version }}"
    assert optional_extras["needs"] == "checks"


def test_docs_and_release_checklist_explain_python_compatibility_evidence() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = (_REPO_ROOT / "docs" / "user" / "USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
    tds = (_REPO_ROOT / "docs" / "technical" / "TDS.md").read_text(encoding="utf-8")
    development = (_REPO_ROOT / "docs" / "architecture" / "DEVELOPMENT.md").read_text(
        encoding="utf-8"
    )
    test_strategy = (_REPO_ROOT / "docs" / "meta" / "TEST_STRATEGY.md").read_text(
        encoding="utf-8"
    )
    release_checklist = (
        _REPO_ROOT / "docs" / "meta" / "RELEASE_CHECKLIST.md"
    ).read_text(encoding="utf-8")
    compatibility = (
        _REPO_ROOT / "docs" / "technical" / "PYTHON_COMPATIBILITY.md"
    ).read_text(encoding="utf-8")

    combined = "\n".join(
        [readme, user_guide, tds, development, test_strategy, release_checklist, compatibility]
    )
    assert "Python 3.12 or 3.13" in combined
    assert "CI proves Python 3.12 and 3.13" in combined
    assert "not claimed for Python 3.14" in combined
    assert "3.12 remains the syntax and mypy floor" in combined
    assert "Python 3.12+" not in readme
    assert "Python 3.12+" not in user_guide
    assert "Python 3.12+" not in tds


def _setup_python_step(job: dict[str, object]) -> dict[str, object]:
    for step in _sequence(job["steps"]):
        if isinstance(step, dict) and step.get("uses") == _SETUP_PYTHON_PIN:
            return cast(dict[str, object], step)
    raise AssertionError("job must use pinned actions/setup-python")


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    assert isinstance(value, Sequence)
    return value
