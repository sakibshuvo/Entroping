"""Run suite manifest loading tests."""

from pathlib import Path

import pytest

from entroping.core import run_suite_manifest as suite_manifest_module
from entroping.core.run_suite_manifest import RunSuiteManifestError, load_run_suite_manifest


def test_load_run_suite_manifest_resolves_reviewable_suite(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    suites_dir = tmp_path / "suites"
    tests_dir.mkdir()
    suites_dir.mkdir()
    (tests_dir / "health.hurl").write_text("# entroping: tags=smoke\n", encoding="utf-8")
    (tests_dir / "security.hurl").write_text("# entroping: tags=security\n", encoding="utf-8")
    (suites_dir / "smoke.yaml").write_text(
        """
version: entroping.suite.v1
name: smoke
env: local
tags:
  - smoke
  - security
paths:
  - tests/*.hurl
reports:
  - json
  - junit
parallel: true
fail_fast: true
drift_check: true
""".lstrip(),
        encoding="utf-8",
    )

    suite = load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")

    assert suite.name == "smoke"
    assert suite.environment == "local"
    assert suite.tag_filters == ("security", "smoke")
    assert suite.report_formats == ("json", "junit")
    assert suite.parallel is True
    assert suite.fail_fast is True
    assert suite.drift_check is True
    assert suite.discovery_roots == (
        (tests_dir / "health.hurl").resolve(),
        (tests_dir / "security.hurl").resolve(),
    )


def test_load_run_suite_manifest_defaults_to_tests_root(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "regression.yaml").write_text(
        "version: entroping.suite.v1\nname: regression\n",
        encoding="utf-8",
    )

    suite = load_run_suite_manifest(project_root=tmp_path, suite_name="regression")

    assert suite.discovery_roots == ((tmp_path / "tests").resolve(),)
    assert suite.tag_filters == ()
    assert suite.report_formats == ()


def test_load_run_suite_manifest_accepts_null_optional_fields(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "minimal.yaml").write_text(
        "version: entroping.suite.v1\nname: null\nenv: null\n",
        encoding="utf-8",
    )

    suite = load_run_suite_manifest(project_root=tmp_path, suite_name="minimal")

    assert suite.name == "minimal"
    assert suite.environment is None


def test_load_run_suite_manifest_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(RunSuiteManifestError, match="not found"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text("[", encoding="utf-8")

    with pytest.raises(RunSuiteManifestError, match="Invalid YAML"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text("- item\n", encoding="utf-8")

    with pytest.raises(RunSuiteManifestError, match="YAML mapping"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_non_string_yaml_keys(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text("1: value\n", encoding="utf-8")

    with pytest.raises(RunSuiteManifestError, match="keys must be strings"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("version: entroping.suite.v1\nenv: ''\n", "must not be empty"),
        ('version: entroping.suite.v1\nenv: "ci\\nprod"\n', "control characters"),
        ("version: entroping.suite.v1\ntags:\n  - ''\n", "items must not be empty"),
        ('version: entroping.suite.v1\ntags:\n  - "smoke\\nprod"\n', "control characters"),
    ],
)
def test_load_run_suite_manifest_rejects_invalid_schema_fields(
    tmp_path: Path,
    body: str,
    expected: str,
) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text(body, encoding="utf-8")

    with pytest.raises(RunSuiteManifestError, match=expected):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


@pytest.mark.parametrize("suite_name", ["../smoke", "", ".", "bad/name", "bad\u007fname"])
def test_load_run_suite_manifest_rejects_unsafe_suite_names(
    tmp_path: Path,
    suite_name: str,
) -> None:
    with pytest.raises(RunSuiteManifestError, match="suite name"):
        load_run_suite_manifest(project_root=tmp_path, suite_name=suite_name)


@pytest.mark.parametrize(
    ("path_glob", "expected"),
    [
        ("../outside/*.hurl", "stay inside"),
        ("https://example.com/tests/*.hurl", "local relative"),
        ("tests/\n*.hurl", "control characters"),
    ],
)
def test_load_run_suite_manifest_rejects_unsafe_suite_paths(
    tmp_path: Path,
    path_glob: str,
    expected: str,
) -> None:
    (tmp_path / "suites").mkdir()
    path_literal = '"tests/\\n*.hurl"' if "\n" in path_glob else repr(path_glob)
    (tmp_path / "suites" / "smoke.yaml").write_text(
        f"""
version: entroping.suite.v1
name: smoke
paths:
  - {path_literal}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match=expected):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_symlinked_suite_file(tmp_path: Path) -> None:
    suites_dir = tmp_path / "suites"
    suites_dir.mkdir()
    (tmp_path / "outside.yaml").write_text("version: entroping.suite.v1\n", encoding="utf-8")
    (suites_dir / "smoke.yaml").symlink_to(tmp_path / "outside.yaml")

    with pytest.raises(RunSuiteManifestError, match="must not use symlinks"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_path_symlink_to_outside_root(tmp_path: Path) -> None:
    suites_dir = tmp_path / "suites"
    tests_dir = tmp_path / "tests"
    outside = tmp_path.parent / f"{tmp_path.name}-outside.hurl"
    suites_dir.mkdir()
    tests_dir.mkdir()
    outside.write_text("GET http://localhost:18080\n", encoding="utf-8")
    (tests_dir / "outside.hurl").symlink_to(outside)
    (suites_dir / "smoke.yaml").write_text(
        "version: entroping.suite.v1\npaths:\n  - tests/*.hurl\n",
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match="stay inside project root"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_path_symlink_inside_root(tmp_path: Path) -> None:
    suites_dir = tmp_path / "suites"
    tests_dir = tmp_path / "tests"
    suites_dir.mkdir()
    tests_dir.mkdir()
    (tests_dir / "real.hurl").write_text("GET http://localhost:18080\n", encoding="utf-8")
    (tests_dir / "linked.hurl").symlink_to(tests_dir / "real.hurl")
    (suites_dir / "smoke.yaml").write_text(
        "version: entroping.suite.v1\npaths:\n  - tests/linked.hurl\n",
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match="must not use symlinks"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_rejects_non_hurl_file_match(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "notes.txt").write_text("not hurl\n", encoding="utf-8")
    (tmp_path / "suites" / "smoke.yaml").write_text(
        "version: entroping.suite.v1\npaths:\n  - tests/*.txt\n",
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match=".hurl files or directories"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_wraps_invalid_glob_patterns(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text(
        "version: entroping.suite.v1\npaths:\n  - tests/**.hurl\n",
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match="Invalid run suite path glob"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_load_run_suite_manifest_normalizes_dot_slash_paths(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "tests").mkdir()
    hurl_path = tmp_path / "tests" / "health.hurl"
    hurl_path.write_text("GET http://localhost:18080\n", encoding="utf-8")
    (tmp_path / "suites" / "smoke.yaml").write_text(
        "version: entroping.suite.v1\npaths:\n  - ./tests/*.hurl\n",
        encoding="utf-8",
    )

    suite = load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")

    assert suite.discovery_roots == (hurl_path.resolve(),)


def test_load_run_suite_manifest_rejects_name_mismatch(tmp_path: Path) -> None:
    (tmp_path / "suites").mkdir()
    (tmp_path / "suites" / "smoke.yaml").write_text(
        "version: entroping.suite.v1\nname: regression\n",
        encoding="utf-8",
    )

    with pytest.raises(RunSuiteManifestError, match="must match"):
        load_run_suite_manifest(project_root=tmp_path, suite_name="smoke")


def test_run_suite_manifest_direct_path_guards_cover_low_level_errors(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(RunSuiteManifestError, match="manifest must stay under project root"):
        suite_manifest_module._validate_manifest_path(tmp_path / "outside.yaml", root=root)
    with pytest.raises(RunSuiteManifestError, match="Could not read run suite manifest"):
        suite_manifest_module._read_yaml_mapping(tmp_path)
    with pytest.raises(RunSuiteManifestError, match="control characters"):
        suite_manifest_module._safe_suite_path("tests/\n*.hurl")
